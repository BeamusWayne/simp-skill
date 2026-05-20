#!/usr/bin/env python3
"""
simp-skill · Time Tracker
互动时间记录与分析 — 数据录入、查询、分析

用法：
  python3 tools/time_tracker.py record <slug> <type> [options]
  python3 tools/time_tracker.py analyze <slug> [--frequency|--milestones|--reply|--golden] [--output file]
"""

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path("crushes")

VALID_INTERACTION_TYPES = frozenset({
    "chat_sent",
    "chat_received",
    "meeting",
    "call",
    "online_interaction",
})

_DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def record_interaction(
    slug: str,
    interaction_type: str,
    data: dict[str, Any],
    ts: datetime | None = None,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> None:
    if interaction_type not in VALID_INTERACTION_TYPES:
        raise ValueError(f"未知互动类型: {interaction_type}")

    crush_dir = base_dir / slug
    if not crush_dir.exists():
        raise FileNotFoundError(f"档案不存在: {slug}")

    if ts is None:
        ts = datetime.now()

    interactions_path = crush_dir / "interactions.jsonl"

    # Dedup: same ts + same type → skip
    if interactions_path.exists():
        last_line = ""
        with interactions_path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
            if last_line:
                try:
                    last_record = json.loads(last_line)
                    if last_record.get("ts") == ts.isoformat() and last_record.get("type") == interaction_type:
                        logger.info("⏭️  重复记录已跳过")
                        return
                except json.JSONDecodeError:
                    pass

    computed = {
        **data,
        "hour": ts.hour,
        "day_of_week": _DAY_NAMES[ts.weekday()],
    }

    if interaction_type == "chat_sent":
        computed["is_initiator"] = True
    elif interaction_type == "chat_received":
        computed["is_initiator"] = False

    record = {
        "ts": ts.isoformat(),
        "v": 1,
        "type": interaction_type,
        "slug": slug,
        "data": computed,
    }

    with interactions_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    meta_path = crush_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        updated_meta = {
            **meta,
            "interaction_count": meta.get("interaction_count", 0) + 1,
            "last_interaction": ts.isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        meta_path.write_text(json.dumps(updated_meta, ensure_ascii=False, indent=2), encoding="utf-8")


def get_interactions(
    slug: str,
    days: int | None = None,
    types: list[str] | None = None,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> list[dict[str, Any]]:
    interactions_path = base_dir / slug / "interactions.jsonl"
    if not interactions_path.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days) if days else None
    results: list[dict[str, Any]] = []

    for line in interactions_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue

        if types and record.get("type") not in types:
            continue

        if cutoff:
            try:
                record_ts = datetime.fromisoformat(record["ts"])
                if record_ts < cutoff:
                    continue
            except (ValueError, KeyError):
                continue

        results.append(record)

    return results


def get_reply_times(
    slug: str,
    days: int = 30,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> list[dict[str, Any]]:
    interactions = get_interactions(slug, days=days, types=["chat_received"], base_dir=base_dir)
    return [i for i in interactions if "reply_delay_min" in i.get("data", {})]


def get_interaction_frequency(
    slug: str,
    days: int = 30,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> dict[str, Any]:
    interactions = get_interactions(slug, days=days, base_dir=base_dir)

    hour_counts: dict[int, int] = {}
    dow_counts: dict[str, int] = {}

    for interaction in interactions:
        data = interaction.get("data", {})
        hour = data.get("hour")
        dow = data.get("day_of_week")
        if hour is not None:
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        if dow:
            dow_counts[dow] = dow_counts.get(dow, 0) + 1

    return {
        "total": len(interactions),
        "by_hour": dict(sorted(hour_counts.items())),
        "by_day_of_week": {d: dow_counts.get(d, 0) for d in _DAY_NAMES},
    }


def analyze_timeline(
    slug: str,
    days: int = 30,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> dict[str, Any]:
    interactions = get_interactions(slug, days=days, base_dir=base_dir)

    if not interactions:
        return {
            "total": 0,
            "active_days": 0,
            "total_days": days,
            "current_streak": 0,
            "max_streak": 0,
            "user_ratio": 0.0,
        }

    active_dates: set[str] = set()
    user_count = 0
    them_count = 0

    for interaction in interactions:
        ts_str = interaction.get("ts", "")[:10]
        if ts_str:
            active_dates.add(ts_str)
        data = interaction.get("data", {})
        if data.get("is_initiator") is True:
            user_count += 1
        elif data.get("is_initiator") is False:
            them_count += 1

    sorted_dates = sorted(active_dates)
    max_streak = 1
    current_streak = 1

    for i in range(1, len(sorted_dates)):
        prev = datetime.strptime(sorted_dates[i - 1], "%Y-%m-%d").date()
        curr = datetime.strptime(sorted_dates[i], "%Y-%m-%d").date()
        if (curr - prev).days == 1:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 1

    today = datetime.now().strftime("%Y-%m-%d")
    if sorted_dates and sorted_dates[-1] == today:
        display_streak = current_streak
    elif sorted_dates:
        last_date = datetime.strptime(sorted_dates[-1], "%Y-%m-%d").date()
        if (datetime.now().date() - last_date).days == 1:
            display_streak = current_streak
        else:
            display_streak = 0
    else:
        display_streak = 0

    total = len(interactions)
    user_ratio = round(user_count / total * 100, 1) if total else 0.0

    return {
        "total": total,
        "active_days": len(active_dates),
        "total_days": days,
        "current_streak": display_streak,
        "max_streak": max(max_streak, 1) if sorted_dates else 0,
        "user_count": user_count,
        "them_count": them_count,
        "user_ratio": user_ratio,
    }


_REPLY_BUCKETS = [
    ("lte_5min", 0, 5),
    ("min_5_to_15", 5, 15),
    ("min_15_to_60", 15, 60),
    ("hr_1_to_4", 60, 240),
    ("gt_4h", 240, float("inf")),
]


def analyze_reply_times(
    slug: str,
    days: int = 30,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> dict[str, Any]:
    replies = get_reply_times(slug, days=days, base_dir=base_dir)

    if not replies:
        return {
            "total_replies": 0,
            "average_min": None,
            "median_min": None,
            "distribution": {},
            "weekly_trend": [],
        }

    delays = [r["data"]["reply_delay_min"] for r in replies if "reply_delay_min" in r.get("data", {})]
    if not delays:
        return {
            "total_replies": 0,
            "average_min": None,
            "median_min": None,
            "distribution": {},
            "weekly_trend": [],
        }

    average_min = round(sum(delays) / len(delays), 1)
    sorted_delays = sorted(delays)
    median_min = sorted_delays[len(sorted_delays) // 2]

    bucket_counts: dict[str, int] = {label: 0 for label, _, _ in _REPLY_BUCKETS}
    for d in delays:
        for label, lo, hi in _REPLY_BUCKETS:
            if lo <= d < hi:
                bucket_counts[label] += 1
                break

    total = len(delays)
    distribution = {label: round(count / total * 100, 1) for label, count in bucket_counts.items()}

    return {
        "total_replies": total,
        "average_min": average_min,
        "median_min": median_min,
        "distribution": distribution,
        "weekly_trend": [],
    }


def analyze_golden_hours(
    slug: str,
    days: int = 30,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> dict[str, Any]:
    received = get_interactions(slug, days=days, types=["chat_received"], base_dir=base_dir)

    if not received:
        return {"peak_hour": None, "top_windows": [], "weekday_peak": None, "weekend_peak": None}

    hour_counts: dict[int, int] = {}
    weekday_hours: dict[int, int] = {}
    weekend_hours: dict[int, int] = {}

    for r in received:
        data = r.get("data", {})
        hour = data.get("hour")
        dow = data.get("day_of_week", "")
        if hour is None:
            continue
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
        if dow in ("sat", "sun"):
            weekend_hours[hour] = weekend_hours.get(hour, 0) + 1
        else:
            weekday_hours[hour] = weekday_hours.get(hour, 0) + 1

    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None

    sorted_hours = sorted(hour_counts.items(), key=lambda x: -x[1])
    top_windows = [{"hour": h, "count": c, "pct": round(c / len(received) * 100, 1)} for h, c in sorted_hours[:3]]

    weekday_peak = max(weekday_hours, key=weekday_hours.get) if weekday_hours else None
    weekend_peak = max(weekend_hours, key=weekend_hours.get) if weekend_hours else None

    return {
        "peak_hour": peak_hour,
        "top_windows": top_windows,
        "weekday_peak": weekday_peak,
        "weekend_peak": weekend_peak,
    }


_STAGE_BASELINES: dict[str, tuple[int, int]] = {
    "破冰期": (7, 14),
    "升温期": (10, 21),
    "暧昧期": (14, 35),
    "表白前": (7, 21),
    "表白后-成功": (0, 0),
}


def analyze_milestones(
    slug: str,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> dict[str, Any]:
    crush_dir = base_dir / slug

    profile_path = crush_dir / "profile.md"
    if not profile_path.exists():
        return {"stages": [], "total_days": 0}

    profile_text = profile_path.read_text(encoding="utf-8")
    created_at_str: str | None = None
    if profile_text.startswith("---"):
        parts = profile_text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if line.strip().startswith("created_at:"):
                    created_at_str = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break

    if not created_at_str:
        return {"stages": [], "total_days": 0}

    try:
        created_at = datetime.strptime(created_at_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return {"stages": [], "total_days": 0}

    events_path = crush_dir / "events.jsonl"
    stage_transitions: list[dict[str, Any]] = []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "stage_changed":
                ts_str = event.get("ts", "")[:10]
                try:
                    ts_date = datetime.strptime(ts_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                stage_transitions.append({
                    "date": ts_date,
                    "from": event.get("data", {}).get("from", ""),
                    "to": event.get("data", {}).get("to", ""),
                })

    today = datetime.now().date()
    total_days = (today - created_at).days

    stages: list[dict[str, Any]] = []
    prev_date = created_at

    for i, transition in enumerate(stage_transitions):
        days_in_stage = (transition["date"] - prev_date).days
        stage_name = transition["from"]
        baseline_lo, baseline_hi = _STAGE_BASELINES.get(stage_name, (0, 0))

        status = "normal"
        if baseline_lo > 0 and days_in_stage > baseline_hi:
            status = "slow"
        elif baseline_lo > 0 and days_in_stage < baseline_lo:
            status = "fast"

        stages.append({
            "name": stage_name,
            "start": prev_date.isoformat(),
            "end": transition["date"].isoformat(),
            "days": days_in_stage,
            "baseline_lo": baseline_lo,
            "baseline_hi": baseline_hi,
            "status": status,
        })
        prev_date = transition["date"]

    if stage_transitions:
        current_stage_name = stage_transitions[-1]["to"]
    else:
        current_stage_name = "破冰期"

    current_days = (today - prev_date).days
    baseline_lo, baseline_hi = _STAGE_BASELINES.get(current_stage_name, (0, 0))

    current_status = "normal"
    if baseline_lo > 0 and current_days > baseline_hi:
        current_status = "slow"
    elif baseline_lo > 0 and current_days < baseline_lo:
        current_status = "fast"

    stages.append({
        "name": current_stage_name,
        "start": prev_date.isoformat(),
        "end": None,
        "days": current_days,
        "baseline_lo": baseline_lo,
        "baseline_hi": baseline_hi,
        "status": current_status,
    })

    return {
        "stages": stages,
        "total_days": total_days,
        "created_at": created_at.isoformat(),
    }


def _bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _format_frequency(tl: dict, freq: dict) -> str:
    lines = [
        "📊 互动频率分析",
        f"  总互动次数: {tl['total']}",
        f"  活跃天数: {tl['active_days']}/{tl['total_days']}",
        f"  连续互动: 当前 {tl['current_streak']} 天 | 最长 {tl['max_streak']} 天",
        f"  主动比例: {tl['user_ratio']}%",
        "",
        "  时段分布:",
    ]
    by_hour = freq.get("by_hour", {})
    max_count = max(by_hour.values()) if by_hour else 1
    for hour in range(24):
        count = by_hour.get(hour, 0)
        if count > 0:
            bar_width = int(count / max_count * 15)
            lines.append(f"    {hour:02d}:00  {'█' * bar_width} ({count})")
    return "\n".join(lines)


def _format_milestones(ms: dict) -> str:
    if not ms["stages"]:
        return "🎯 追求进度追踪\n  暂无阶段数据"
    lines = [
        "🎯 追求进度追踪",
        f"  总天数: {ms['total_days']} 天",
        "",
    ]
    for stage in ms["stages"]:
        status_icon = {"fast": "⚡", "normal": "✅", "slow": "🐌"}.get(stage["status"], "❓")
        end_str = stage["end"] or "进行中"
        baseline_str = f"(基线 {stage['baseline_lo']}-{stage['baseline_hi']} 天)" if stage["baseline_lo"] > 0 else ""
        lines.append(f"  {status_icon} {stage['name']}: {stage['days']} 天 {baseline_str}")
        lines.append(f"     {stage['start']} → {end_str}")
    return "\n".join(lines)


def _format_reply(rt: dict) -> str:
    if rt["total_replies"] == 0:
        return "⏱️  回复时间分析\n  暂无回复数据"
    lines = [
        "⏱️  回复时间分析",
        f"  平均回复: {rt['average_min']:.0f} 分钟",
        f"  中位回复: {rt['median_min']:.0f} 分钟",
        "",
        "  分布:",
    ]
    labels = {
        "lte_5min": "≤5分钟",
        "min_5_to_15": "5-15分钟",
        "min_15_to_60": "15-60分钟",
        "hr_1_to_4": "1-4小时",
        "gt_4h": ">4小时",
    }
    for key, label in labels.items():
        pct = rt["distribution"].get(key, 0)
        lines.append(f"    {label:>8s}  {_bar(pct)} {pct:.0f}%")
    return "\n".join(lines)


def _format_golden(gh: dict) -> str:
    if gh["peak_hour"] is None:
        return "🌟 黄金时段建议\n  暂无数据"
    lines = [
        "🌟 黄金时段建议",
        f"  最活跃时段: {gh['peak_hour']}:00",
        "",
        "  最佳发送窗口:",
    ]
    for w in gh["top_windows"]:
        lines.append(f"    {w['hour']:02d}:00  ({w['count']} 次, {w['pct']:.0f}%)")
    if gh["weekday_peak"] is not None:
        lines.append(f"  工作日高峰: {gh['weekday_peak']}:00")
    if gh["weekend_peak"] is not None:
        lines.append(f"  周末高峰: {gh['weekend_peak']}:00")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="simp-skill · 互动时间追踪")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record", help="记录互动")
    p.add_argument("slug")
    p.add_argument("type", choices=sorted(VALID_INTERACTION_TYPES))
    p.add_argument("--summary", help="内容摘要")
    p.add_argument("--duration", type=int, help="时长（分钟）")
    p.add_argument("--activity", help="活动描述")
    p.add_argument("--location", help="地点")
    p.add_argument("--initiator", choices=["me", "them", "mutual"], help="发起方")
    p.add_argument("--time", help="时间（ISO 格式，如 2026-05-15T22:30）")
    p.add_argument("--base-dir", default="crushes")

    p = sub.add_parser("analyze", help="分析互动数据")
    p.add_argument("slug")
    p.add_argument("--frequency", action="store_true")
    p.add_argument("--milestones", action="store_true")
    p.add_argument("--reply", action="store_true")
    p.add_argument("--golden", action="store_true")
    p.add_argument("--output", help="导出 Markdown 报告")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--base-dir", default="crushes")

    args = parser.parse_args()
    base_dir = Path(args.base_dir)

    if args.cmd == "record":
        ts = datetime.fromisoformat(args.time) if args.time else None
        data: dict[str, Any] = {}
        if args.summary:
            data["content_summary"] = args.summary
        if args.duration:
            data["duration_min"] = args.duration
        if args.activity:
            data["activity"] = args.activity
        if args.location:
            data["location"] = args.location
        if args.initiator:
            data["initiator"] = args.initiator

        record_interaction(args.slug, args.type, data, ts=ts, base_dir=base_dir)
        logger.info("✅ 互动已记录：%s", args.type)

    elif args.cmd == "analyze":
        slug = args.slug
        base = Path(args.base_dir)
        days = args.days

        sections: list[str] = []

        if args.frequency or not (args.frequency or args.milestones or args.reply or args.golden):
            tl = analyze_timeline(slug, days=days, base_dir=base)
            freq = get_interaction_frequency(slug, days=days, base_dir=base)
            section = _format_frequency(tl, freq)
            sections.append(section)

        if args.milestones or not (args.frequency or args.milestones or args.reply or args.golden):
            ms = analyze_milestones(slug, base_dir=base)
            section = _format_milestones(ms)
            sections.append(section)

        if args.reply or not (args.frequency or args.milestones or args.reply or args.golden):
            rt = analyze_reply_times(slug, days=days, base_dir=base)
            section = _format_reply(rt)
            sections.append(section)

        if args.golden or not (args.frequency or args.milestones or args.reply or args.golden):
            gh = analyze_golden_hours(slug, days=days, base_dir=base)
            section = _format_golden(gh)
            sections.append(section)

        report = "\n\n".join(sections)

        if args.output:
            Path(args.output).write_text(report, encoding="utf-8")
            logger.info("📊 报告已导出到 %s", args.output)
        else:
            print(report)


if __name__ == "__main__":
    main()
