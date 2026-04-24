#!/usr/bin/env python3
"""
simp-skill · Memory System
心上人档案记忆系统 — 事件追加、状态读写、快照管理

用法：
  python3 tools/memory.py append <slug> <event_type> '<json_data>'
  python3 tools/memory.py events <slug> [--last 5] [--type signal_recorded]
  python3 tools/memory.py context <slug> [--with-strategy]
  python3 tools/memory.py snapshot <slug>
  python3 tools/memory.py timeline <slug>
  python3 tools/memory.py rebuild <slug>
"""

import argparse
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path("crushes")

VALID_EVENT_TYPES = frozenset({
    "profile_created",
    "profile_updated",
    "stage_changed",
    "signal_recorded",
    "analysis_done",
    "progress_evaluated",
    "strategy_updated",
    "crisis_handled",
    "quit_evaluated",
    "confess_prepared",
})

_SECTION_ORDER = [
    "## 当前状态（一句话）",
    "## 最近信号（最新3条）",
    "## 当前策略方向",
    "## 下一步建议",
]

_TIMELINE_LABELS: dict[str, str] = {
    "profile_created": "🌱 档案创建",
    "profile_updated": "✏️  档案更新",
    "stage_changed": "📍 阶段变化",
    "signal_recorded": "📡 信号记录",
    "analysis_done": "🔍 完成分析",
    "progress_evaluated": "📊 进度评估",
    "strategy_updated": "🗺️  策略更新",
    "crisis_handled": "🆘 危机处理",
    "quit_evaluated": "🍃 放弃判断",
    "confess_prepared": "💌 表白准备",
}


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """解析 Markdown YAML frontmatter，返回 (字段dict, 正文)"""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    fields: dict[str, Any] = {}
    for line in parts[1].strip().splitlines():
        if ": " not in line:
            continue
        key, _, raw = line.partition(": ")
        value: Any = raw.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        elif value == "null":
            value = None
        elif value.lstrip("-").isdigit():
            value = int(value)
        else:
            try:
                value = float(value)
            except ValueError:
                pass
        fields[key.strip()] = value

    return fields, parts[2]


def _render_frontmatter(fields: dict[str, Any], body: str) -> str:
    """将字段dict和正文渲染回 frontmatter 格式"""
    _NEEDS_QUOTE = set(':#{[}],&*?|<>=!%@`')
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        else:
            s = str(value)
            if any(c in s for c in _NEEDS_QUOTE) or not s:
                lines.append(f'{key}: "{s}"')
            else:
                lines.append(f"{key}: {s}")
    lines.append("---")
    return "\n".join(lines) + body


def _parse_body_sections(body: str) -> dict[str, str]:
    """将 Markdown 正文按 ## 标题拆分为 {标题: 内容} 字典"""
    sections: dict[str, str] = {}
    current_header: str | None = None
    current_lines: list[str] = []

    for line in body.splitlines():
        if line.startswith("## "):
            if current_header is not None:
                sections[current_header] = "\n".join(current_lines).strip()
            current_header = line
            current_lines = []
        elif current_header is not None:
            current_lines.append(line)

    if current_header is not None:
        sections[current_header] = "\n".join(current_lines).strip()

    return sections


def append_event(
    slug: str,
    event_type: str,
    data: dict[str, Any],
    base_dir: Path = DEFAULT_BASE_DIR,
) -> None:
    """追加一条事件到 events.jsonl，同时更新 meta.json 的 event_count"""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"未知事件类型: {event_type}")

    crush_dir = base_dir / slug
    if not crush_dir.exists():
        raise FileNotFoundError(f"档案不存在: {slug}")

    event = {
        "ts": datetime.now().isoformat(),
        "v": 1,
        "type": event_type,
        "slug": slug,
        "data": data,
    }

    events_path = crush_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    meta_path = crush_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        updated_meta = {
            **meta,
            "event_count": meta.get("event_count", 0) + 1,
            "updated_at": datetime.now().isoformat(),
        }
        meta_path.write_text(json.dumps(updated_meta, ensure_ascii=False, indent=2), encoding="utf-8")


def get_recent_events(
    slug: str,
    n: int = 5,
    event_types: list[str] | None = None,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> list[dict[str, Any]]:
    """返回最近 N 条事件，可按 type 列表过滤"""
    events_path = base_dir / slug / "events.jsonl"
    if not events_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if event_types is None or event.get("type") in event_types:
            events.append(event)

    return events[-n:]


def load_context(
    slug: str,
    include_strategy: bool = False,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> str:
    """拼装 profile.md + state.md，供 Claude 注入 context"""
    crush_dir = base_dir / slug
    parts: list[str] = []

    for filename, label in [("profile.md", "[档案]"), ("state.md", "[状态]")]:
        path = crush_dir / filename
        if path.exists():
            parts.append(f"# {label} {filename}\n\n")
            parts.append(path.read_text(encoding="utf-8"))
            parts.append("\n\n")

    if include_strategy:
        strategy_path = crush_dir / "strategy.md"
        if strategy_path.exists():
            parts.append("# [策略] strategy.md\n\n")
            parts.append(strategy_path.read_text(encoding="utf-8"))

    return "".join(parts)


def update_state(
    slug: str,
    frontmatter_updates: dict[str, Any],
    sections: dict[str, str],
    base_dir: Path = DEFAULT_BASE_DIR,
) -> None:
    """全量覆盖 state.md；frontmatter_updates 合并 YAML 字段，sections 合并正文章节"""
    crush_dir = base_dir / slug
    if not crush_dir.exists():
        raise FileNotFoundError(f"档案不存在: {slug}")

    state_path = crush_dir / "state.md"
    existing_fm: dict[str, Any] = {}
    existing_sections: dict[str, str] = {}

    if state_path.exists():
        existing_fm, body = _parse_frontmatter(state_path.read_text(encoding="utf-8"))
        existing_sections = _parse_body_sections(body)

    new_fm = {**existing_fm, **frontmatter_updates, "last_updated": datetime.now().isoformat()}
    merged_sections = {**existing_sections, **sections}

    body_parts: list[str] = ["\n"]
    for header in _SECTION_ORDER:
        content = merged_sections.get(header, "[待生成]")
        body_parts.append(f"\n{header}\n\n{content}\n")

    state_path.write_text(_render_frontmatter(new_fm, "".join(body_parts)), encoding="utf-8")

    meta_path = crush_dir / "meta.json"
    if meta_path.exists():
        sync_keys = {"current_stage", "signal_score"}
        sync_updates = {k: v for k, v in frontmatter_updates.items() if k in sync_keys}
        if sync_updates:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            updated_meta = {**meta, **sync_updates, "updated_at": datetime.now().isoformat()}
            meta_path.write_text(json.dumps(updated_meta, ensure_ascii=False, indent=2), encoding="utf-8")


def take_snapshot(
    slug: str,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> Path:
    """将 meta.json + state.md frontmatter 合并写入 snapshots/YYYY-MM-DD.json"""
    crush_dir = base_dir / slug
    snapshots_dir = crush_dir / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)

    snapshot: dict[str, Any] = {
        "slug": slug,
        "snapshot_date": date.today().isoformat(),
    }

    meta_path = crush_dir / "meta.json"
    if meta_path.exists():
        snapshot["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))

    state_path = crush_dir / "state.md"
    if state_path.exists():
        state_fm, _ = _parse_frontmatter(state_path.read_text(encoding="utf-8"))
        snapshot["state"] = state_fm

    snapshot_path = snapshots_dir / f"{date.today().isoformat()}.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        updated_meta = {**meta, "last_snapshot": date.today().isoformat()}
        meta_path.write_text(json.dumps(updated_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("✅ 快照已保存：%s", snapshot_path)
    return snapshot_path


def rebuild_state_from_events(
    slug: str,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> dict[str, Any]:
    """从 events.jsonl 重放所有事件，返回推断的当前状态"""
    events = get_recent_events(slug, n=100_000, base_dir=base_dir)

    state: dict[str, Any] = {
        "current_stage": "未知",
        "signal_score": None,
        "last_signal_score": None,
        "score_trend": "stable",
        "recommended_mode": "hybrid",
        "milestones_done": 0,
    }

    for event in events:
        etype = event.get("type")
        data = event.get("data", {})

        if etype == "stage_changed":
            state = {**state, "current_stage": data.get("to", state["current_stage"])}
        elif etype in ("analysis_done", "progress_evaluated"):
            new_score = data.get("score")
            prev_score = state.get("signal_score")
            trend = "stable"
            if new_score is not None and prev_score is not None:
                diff = new_score - prev_score
                trend = "up" if diff >= 2 else ("down" if diff <= -2 else "stable")
            state = {
                **state,
                "last_signal_score": prev_score,
                "signal_score": new_score if new_score is not None else state["signal_score"],
                "score_trend": trend,
                "current_stage": data.get("stage", state["current_stage"]),
            }
            if etype == "progress_evaluated" and "milestones_done" in data:
                state = {**state, "milestones_done": data["milestones_done"]}

    return state


def _format_timeline(events: list[dict[str, Any]]) -> str:
    """格式化事件时间线为可读字符串"""
    if not events:
        return "暂无事件记录"

    _DIRECTION_ICON = {"green": "🟢", "red": "🔴", "neutral": "🟡"}

    lines = [f"📅 事件时间线（共 {len(events)} 条）", ""]
    for event in events:
        ts = event.get("ts", "")[:16].replace("T", " ")
        label = _TIMELINE_LABELS.get(event.get("type", ""), event.get("type", ""))
        data = event.get("data", {})
        etype = event.get("type")

        if etype == "stage_changed":
            desc = f"{data.get('from', '?')} → {data.get('to', '?')}"
        elif etype in ("analysis_done", "progress_evaluated"):
            desc = f"评分 {data.get('score', '?')}/25  阶段：{data.get('stage', '?')}"
        elif etype == "signal_recorded":
            icon = _DIRECTION_ICON.get(data.get("direction", ""), "")
            desc = f"{icon} {data.get('content', '')}"
        elif etype == "crisis_handled":
            desc = data.get("crisis_type", "")
        else:
            desc = ""

        lines.append(f"  {ts}  {label}  {desc}".rstrip())

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="simp-skill · 记忆系统")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("append", help="追加事件")
    p.add_argument("slug")
    p.add_argument("event_type")
    p.add_argument("data", help="JSON 字符串")
    p.add_argument("--base-dir", default="crushes")

    p = sub.add_parser("events", help="查看最近事件")
    p.add_argument("slug")
    p.add_argument("--last", type=int, default=5)
    p.add_argument("--type", dest="event_type", help="按事件类型过滤")
    p.add_argument("--base-dir", default="crushes")

    p = sub.add_parser("context", help="读取档案上下文")
    p.add_argument("slug")
    p.add_argument("--with-strategy", action="store_true")
    p.add_argument("--base-dir", default="crushes")

    p = sub.add_parser("snapshot", help="生成日快照")
    p.add_argument("slug")
    p.add_argument("--base-dir", default="crushes")

    p = sub.add_parser("timeline", help="查看事件时间线")
    p.add_argument("slug")
    p.add_argument("--base-dir", default="crushes")

    p = sub.add_parser("rebuild", help="从事件流重建状态")
    p.add_argument("slug")
    p.add_argument("--base-dir", default="crushes")

    args = parser.parse_args()
    base_dir = Path(args.base_dir)

    if args.cmd == "append":
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            logger.error("❌ data 必须是合法 JSON：%s", e)
            return
        append_event(args.slug, args.event_type, data, base_dir)
        logger.info("✅ 事件已记录：%s", args.event_type)

    elif args.cmd == "events":
        types = [args.event_type] if args.event_type else None
        events = get_recent_events(args.slug, args.last, types, base_dir)
        for event in events:
            print(json.dumps(event, ensure_ascii=False))
        if not events:
            logger.info("暂无事件记录")

    elif args.cmd == "context":
        print(load_context(args.slug, args.with_strategy, base_dir))

    elif args.cmd == "snapshot":
        take_snapshot(args.slug, base_dir)

    elif args.cmd == "timeline":
        all_events = get_recent_events(args.slug, n=100_000, base_dir=base_dir)
        print(_format_timeline(all_events))

    elif args.cmd == "rebuild":
        state = rebuild_state_from_events(args.slug, base_dir)
        print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
