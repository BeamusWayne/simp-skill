#!/usr/bin/env python3
"""Confirmed interactions and descriptive statistics. Never derives relationship stages."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.contracts import Message, parse_time
from tools.chat_parser import deduplicate_messages
from tools.chat_stats import describe_messages, reply_samples
from tools.storage import DEFAULT_BASE_DIR, ensure_ready, member, profile_lock, profile_path
from tools.memory import (_commit, _prepare, _read_records, append_event, record_statuses,
                          get_recent_events, verify_projections)

VALID_INTERACTION_TYPES = frozenset({"chat_sent", "chat_received", "meeting", "call", "online_interaction"})


def import_messages(slug, messages, base_dir=DEFAULT_BASE_DIR):
    """Import into an explicitly initialized profile; all validation precedes writing.

    Stable original IDs deduplicate overlapping exports. Conflicting content under
    the same ID is rejected. Existing user-corrected identity mappings take priority.
    """
    root = profile_path(slug, base_dir)
    messages, _ = deduplicate_messages(messages)
    with profile_lock(root):
        ensure_ready(root)
        verify_projections(root)
        records = _read_records(root)
        states = record_statuses(records)
        active = [r for r in records if states[r["record_id"]] == "active"]
        identities = {(r["data"]["conversation_id"], r["data"]["sender_id"]): r
                      for r in active if r["kind"] == "identity_mapping"}
        prior_messages = {}
        for record in records:
            if record["kind"] == "observation" and "message" in record["data"]:
                m = record["data"]["message"]
                prior_messages[(m["conversation_id"], m["message_id"])] = record
        before = len(records)
        imported = skipped = 0
        for original in messages:
            msg = Message.from_dict(original.to_dict())
            key = (msg.conversation_id, msg.message_id)
            prior = prior_messages.get(key)
            if prior:
                pm = Message.from_dict(prior["data"]["message"])
                # Validate content/clock identity even if a different export was supplied.
                deduplicate_messages([pm, msg])
                if states.get(prior["record_id"]) in {"invalidated", "superseded"}:
                    raise ValueError("Corrected message requires explicit re-verification; reimport cannot revive it")
                if states.get(prior["record_id"], "active") == "active":
                    skipped += 1
                    continue
            identity = identities.get((msg.conversation_id, msg.sender_id))
            if identity is None and msg.sender_id:
                identity = _prepare("identity_mapping", {"summary": f"{msg.sender}: {msg.role}",
                    "conversation_id": msg.conversation_id, "sender_id": msg.sender_id,
                    "role": msg.role, "basis": "export adapter / explicit import mapping"}, records,
                    source_refs=msg.source_refs)
                records.append(identity)
                identities[(msg.conversation_id, msg.sender_id)] = identity
            if identity:
                msg.role = identity["data"]["role"]
            data = {"summary": msg.content or f"[{msg.msg_type}]", "message": msg.to_dict(),
                    "identity_ids": [identity["record_id"]] if identity else []}
            record = _prepare("observation", data, records, source_refs=msg.source_refs,
                              occurred_at=msg.timestamp.isoformat() if msg.timestamp else None,
                              supersedes=[prior["record_id"]] if prior else [])
            records.append(record)
            prior_messages[key] = record
            imported += 1
        if len(records) > before:
            _commit(root, records)
        return {"imported": imported, "duplicates": skipped, "new_records": len(records) - before}


def record_interaction(slug, interaction_type, data, ts=None, base_dir=DEFAULT_BASE_DIR):
    if interaction_type not in VALID_INTERACTION_TYPES:
        raise ValueError("Unknown interaction type: " + interaction_type)
    if data.get("confirmed") is not True:
        raise ValueError("Only user-confirmed actions can be recorded; drafts belong in advice")
    stamp = ts.isoformat() if isinstance(ts, datetime) else ts
    return append_event(slug, "action_report", {**deepcopy(data), "interaction_type": interaction_type},
                        base_dir, occurred_at=stamp,
                        source_refs=[{"kind": "user", "locator": "cli:record", "excerpt": data.get("summary", "")}])


def get_interactions(slug, days=None, base_dir=DEFAULT_BASE_DIR, *, now=None):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root)
        verify_projections(root)
        rows = [json.loads(line) for line in member(root, "interactions.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if days is None:
        return rows
    if days <= 0:
        raise ValueError("days must be positive")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    cutoff = now - timedelta(days=days)
    return [r for r in rows if parse_time(r["occurred_at"])[1] == "known"
            and cutoff <= parse_time(r["occurred_at"])[0] <= now]


def analyze_timeline(slug, days=None, base_dir=DEFAULT_BASE_DIR, *, now=None):
    all_rows = get_interactions(slug, base_dir=base_dir)
    rows = get_interactions(slug, days, base_dir, now=now) if days is not None else all_rows
    messages = [Message.from_dict(r["message"]) for r in rows if r["kind"] == "message"]
    hours = Counter(str(m.timestamp.hour) for m in messages if m.timestamp and m.time_status not in {"date_only", "invalid", "missing"})
    return {"interactions": len(rows), "messages": describe_messages(messages),
            "reported_actions": sum(r["kind"] == "reported_action" for r in rows),
            "active_hours": dict(hours), "active_hours_note": "Hours as recorded; mixed/unknown timezones are not harmonized. Not an ideal messaging schedule.",
            "days": days, "excluded_by_window": len(all_rows) - len(rows),
            "window_note": "Date-only/unknown timezone records are excluded only when --days is used."}


def analyze_reply_times(slug, days=None, base_dir=DEFAULT_BASE_DIR, *, now=None):
    return reply_samples([Message.from_dict(r["message"]) for r in get_interactions(slug, days, base_dir, now=now) if r["kind"] == "message"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["record", "analyze"])
    parser.add_argument("slug")
    parser.add_argument("interaction_type", nargs="?", choices=sorted(VALID_INTERACTION_TYPES))
    parser.add_argument("--summary")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--time", help="Actual event time; omitted means unknown, not now")
    parser.add_argument("--days", type=int)
    parser.add_argument("--now", help="Timezone-aware anchor for reproducible windows")
    parser.add_argument("--base-dir", default="crushes")
    parser.add_argument("--output")
    flags = parser.add_mutually_exclusive_group()
    for name in ("frequency", "milestones", "reply", "golden"):
        flags.add_argument("--" + name, action="store_true")
    args = parser.parse_args()
    base = Path(args.base_dir)
    try:
        now = parse_time(args.now)[0] if args.now else None
        if args.now and (now is None or now.tzinfo is None):
            raise ValueError("--now requires a valid timezone-aware timestamp")
        if args.command == "record":
            result = record_interaction(args.slug, args.interaction_type, {"summary": args.summary,
                                        "confirmed": args.confirmed}, args.time, base)
        elif args.reply:
            result = analyze_reply_times(args.slug, args.days, base, now=now)
        elif args.milestones:
            result = get_recent_events(args.slug, 100, ["action_report", "outcome"], base)
        else:
            result = analyze_timeline(args.slug, args.days, base, now=now)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            # Reports must not overwrite authoritative profile files.
            out = Path(args.output).resolve()
            if out.is_relative_to(profile_path(args.slug, base)):
                raise ValueError("Write reports outside the profile directory")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        else:
            print(text)
    except (ValueError, RuntimeError, OSError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
