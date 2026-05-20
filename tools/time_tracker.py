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
        logger.info("⏳ 分析功能将在后续任务中实现...")


if __name__ == "__main__":
    main()
