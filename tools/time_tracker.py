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


# Analysis functions added in Tasks 2-4


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
