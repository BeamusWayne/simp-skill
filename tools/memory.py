#!/usr/bin/env python3
"""Typed, attributable memory. events.jsonl is authoritative; projections are disposable."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.contracts import KINDS, file_digest, parse_time, stable_id, utc_now, validate_record
from tools.storage import (DEFAULT_BASE_DIR, atomic_write, backup_state, ensure_ready, member,
                           profile_lock, profile_path, write_json)

PROJECTIONS = ("profile.md", "state.md", "strategy.md", "participants.json", "interactions.jsonl", "meta.json")


def _read_records(root: Path) -> list[dict]:
    path = member(root, "events.jsonl")
    records = []
    seen = set()
    for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not text.strip():
            continue
        try:
            record = json.loads(text)
            validate_record(record)
            if record["record_id"] in seen:
                raise ValueError("duplicate record ID")
            refs = record["related_record_ids"] + record["supersedes"]
            if any(ref not in seen for ref in refs):
                raise ValueError("dangling or forward record reference")
            seen.add(record["record_id"])
            records.append(record)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"events.jsonl line {line} is invalid; restore or repair without dropping data: {exc}") from exc
    return records


def record_statuses(records):
    states = {r["record_id"]: "active" for r in records}
    for record in records:
        for ref in record["supersedes"]:
            states[ref] = "invalidated" if record["kind"] == "correction" else "superseded"
    # References only point backward, so this single pass propagates invalidity.
    for record in records:
        rid = record["record_id"]
        if states[rid] == "active" and any(states.get(ref) != "active" for ref in record["related_record_ids"]):
            states[rid] = "needs_review"
    return states


def verify_projections(root):
    manifest_path = member(root, ".projections.json")
    if not manifest_path.exists():
        raise RuntimeError("Missing projection manifest; run memory.py rebuild")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["ledger_sha256"] != file_digest(member(root, "events.jsonl")):
        raise RuntimeError("Stale projections; run memory.py rebuild")
    changed = [name for name, digest in manifest["files"].items()
               if not member(root, name).exists() or file_digest(member(root, name)) != digest]
    if changed:
        raise RuntimeError("Edited/missing projections: " + ", ".join(changed) + "; rebuild preserves a backup of edits")


def _frontmatter(fields, body):
    return "---\n" + "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items()) + "\n---\n\n" + body + "\n"


def _project(root, records):
    statuses = record_statuses(records)
    active = [r for r in records if statuses[r["record_id"]] == "active" and r["kind"] != "legacy_record"]
    preferences = {}
    identities = {}
    for record in active:
        data = record["data"]
        if record["kind"] == "preference":
            preferences[data["key"]] = {"value": data["value"], "record_id": record["record_id"],
                                        "confirmed": data.get("confirmed", False)}
        if record["kind"] == "identity_mapping":
            identities[data["conversation_id"] + "|" + data["sender_id"]] = {**data, "record_id": record["record_id"]}
    assessments = [r for r in active if r["kind"] == "assessment"]
    advice = [r for r in active if r["kind"] == "advice"]
    interactions = []
    seen_interactions = set()
    for record in active:
        data = record["data"]
        message = data.get("message") if record["kind"] == "observation" else None
        if message:
            key = message["conversation_id"] + "|" + message["message_id"]
            if key in seen_interactions:
                continue
            seen_interactions.add(key)
            interactions.append({"record_id": record["record_id"], "kind": "message", "occurred_at": record["occurred_at"],
                                 "source_refs": record["source_refs"], "message": message})
        elif record["kind"] == "action_report":
            interactions.append({"record_id": record["record_id"], "kind": "reported_action", "occurred_at": record["occurred_at"],
                                 "source_refs": record["source_refs"], "data": data})
    dated = [(parse_time(i["occurred_at"])[0], i["occurred_at"]) for i in interactions
             if parse_time(i["occurred_at"])[1] == "known"]
    last_interaction = max(dated, key=lambda pair: pair[0])[1] if dated else None
    old_meta = json.loads(member(root, "meta.json").read_text(encoding="utf-8"))
    stamp = records[-1]["recorded_at"] if records else old_meta.get("created_at", utc_now())
    meta = {"schema_version": 2, "slug": root.name, "created_at": old_meta.get("created_at", stamp),
            "memory_enabled": True, "nickname": preferences.get("nickname", {}).get("value", root.name),
            "mode": preferences.get("mode", {}).get("value", "hybrid"), "record_count": len(records),
            "updated_at": stamp, "last_record_id": records[-1]["record_id"] if records else None,
            "interaction_count": len(interactions), "last_interaction": last_interaction,
            "undated_or_local_interactions": sum(parse_time(i["occurred_at"])[1] != "known" for i in interactions),
            "needs_review_count": sum(s == "needs_review" for s in statuses.values())}
    fields = {"schema_version": 2, "slug": root.name, "last_record_id": meta["last_record_id"]}
    profile_body = "# 已记录偏好\n\n" + ("\n".join(f"- {key}: {json.dumps(value, ensure_ascii=False)}" for key, value in preferences.items()) or "尚无已记录偏好。")
    state_body = "# 当前判断\n\n" + (assessments[-1]["data"]["summary"] if assessments else "尚无当前有效判断。")
    if assessments:
        state_body += "\n\n依据记录：" + json.dumps(assessments[-1]["related_record_ids"], ensure_ascii=False)
    state_body += f"\n\n待重新评估记录：{meta['needs_review_count']}。建议不代表已执行。"
    strategy_body = "# 当前建议\n\n" + (advice[-1]["data"]["summary"] if advice else "尚无当前有效建议。")
    for name, body in (("profile.md", profile_body), ("state.md", state_body), ("strategy.md", strategy_body)):
        atomic_write(member(root, name), _frontmatter(fields, body))
    write_json(member(root, "participants.json"), {"schema_version": 2, "identities": identities})
    atomic_write(member(root, "interactions.jsonl"), "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in interactions))
    write_json(member(root, "meta.json"), meta)
    write_json(member(root, ".projections.json"), {"ledger_sha256": file_digest(member(root, "events.jsonl")),
               "files": {name: file_digest(member(root, name)) for name in PROJECTIONS}})


def _prepare(kind, data, records, *, source_refs=None, related_record_ids=None, supersedes=None, occurred_at=None):
    data = deepcopy(data)
    related = list(related_record_ids or [])
    for key in ("supporting_ids", "opposing_ids", "identity_ids"):
        values = data.get(key, [])
        if not isinstance(values, list):
            raise ValueError(key + " must be a list")
        related.extend(values)
    if kind == "outcome" and data.get("action_id"):
        related.append(data["action_id"])
    payload = {"schema_version": 2, "kind": kind, "data": data, "source_refs": deepcopy(source_refs or []),
               "related_record_ids": sorted(set(related)), "supersedes": sorted(set(supersedes or [])), "occurred_at": occurred_at}
    record = {**payload, "record_id": stable_id(payload, "r:"), "recorded_at": utc_now()}
    validate_record(record)
    by_id = {r["record_id"]: r for r in records}
    if record["record_id"] in by_id:
        return by_id[record["record_id"]]
    statuses = record_statuses(records)
    for ref in record["related_record_ids"] + record["supersedes"]:
        if ref not in by_id:
            raise ValueError("Unknown record reference: " + ref)
    if any(statuses[ref] != "active" for ref in record["related_record_ids"]):
        raise ValueError("Cannot use an invalidated/superseded dependency as current evidence")
    if kind != "legacy_record" and any(by_id[ref]["kind"] == "legacy_record" for ref in related):
        raise ValueError("Legacy judgments require re-verification before use as evidence")
    if kind == "outcome" and by_id[data["action_id"]]["kind"] != "action_report":
        raise ValueError("outcome must reference an action_report, not a draft")
    if kind in {"identity_mapping", "preference"}:
        for prior in records:
            if prior["kind"] != kind or statuses[prior["record_id"]] != "active":
                continue
            pd = prior["data"]
            same = pd.get("key") == data.get("key") if kind == "preference" else (pd.get("conversation_id"), pd.get("sender_id")) == (data.get("conversation_id"), data.get("sender_id"))
            if same and prior["record_id"] not in record["supersedes"]:
                raise ValueError("Replacing an active preference/identity requires explicit supersedes")
    return record


def _commit(root, records):
    write_json(member(root, ".pending.json"), {"operation": "project", "at": utc_now()})
    atomic_write(member(root, "events.jsonl"), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    _project(root, records)
    member(root, ".pending.json").unlink()


def append_records(slug, payloads, base_dir=DEFAULT_BASE_DIR):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root)
        verify_projections(root)
        records = _read_records(root)
        existing = {r["record_id"] for r in records}
        added, output = False, []
        for payload in payloads:
            record = _prepare(records=records, **payload)
            output.append(record)
            if record["record_id"] not in existing:
                records.append(record)
                existing.add(record["record_id"])
                added = True
        if added:
            _commit(root, records)
        return output


def append_event(slug, event_type, data, base_dir=DEFAULT_BASE_DIR, **kwargs):
    return append_records(slug, [{"kind": event_type, "data": data, **kwargs}], base_dir)[0]


def get_recent_events(slug, n=20, event_types=None, base_dir=DEFAULT_BASE_DIR, *, include_history=False):
    if n < 0:
        raise ValueError("n must be nonnegative")
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root)
        verify_projections(root)
        records = _read_records(root)
    statuses = record_statuses(records)
    visible = [{**r, "status": statuses[r["record_id"]]} for r in records
               if (include_history or (statuses[r["record_id"]] == "active" and r["kind"] != "legacy_record"))
               and (event_types is None or r["kind"] in event_types)]
    return visible[-n:] if n else []


def load_context(slug, include_strategy=False, base_dir=DEFAULT_BASE_DIR, *, query=None, kinds=None, limit=20):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root)
        verify_projections(root)
        records = _read_records(root)
    statuses = record_statuses(records)
    active = {r["record_id"]: r for r in records if statuses[r["record_id"]] == "active" and r["kind"] != "legacy_record"}
    if limit < 1:
        raise ValueError("limit must be positive")
    selected = [r for r in active.values() if (kinds is None or r["kind"] in kinds)
                and (not query or query.casefold() in json.dumps(r, ensure_ascii=False).casefold())][-limit:]
    ids = {r["record_id"] for r in selected}
    todo = list(ids)
    while todo:
        rid = todo.pop()
        for dependency in active[rid]["related_record_ids"]:
            if dependency not in ids:
                ids.add(dependency)
                todo.append(dependency)
    context = [r for r in records if r["record_id"] in ids]
    return json.dumps({"schema_version": 2, "slug": slug, "query": query, "total_records": len(records),
                       "active_records": len(active), "selected_records": len(context),
                       "scope": "Selected records plus dependencies; not the complete history. Search contrary evidence separately.",
                       "records": context}, ensure_ascii=False, indent=2)


def rebuild_state_from_events(slug, base_dir=DEFAULT_BASE_DIR):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root, allow_pending=True)
        records = _read_records(root)
        backup_state(root, "before-rebuild-preserve-edits")
        write_json(member(root, ".pending.json"), {"operation": "rebuild", "at": utc_now()})
        _project(root, records)
        pending = member(root, ".pending.json")
        if pending.exists():
            pending.unlink()
        return json.loads(member(root, "meta.json").read_text(encoding="utf-8"))


def take_snapshot(slug, base_dir=DEFAULT_BASE_DIR):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root)
        verify_projections(root)
        path = member(root, "snapshots/" + utc_now().replace(":", "").replace("+", "_") + ".json")
        write_json(path, {"schema_version": 2, "ledger_sha256": file_digest(member(root, "events.jsonl")),
                         "meta": json.loads(member(root, "meta.json").read_text(encoding="utf-8"))})
        return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["append", "events", "context", "snapshot", "rebuild", "timeline"])
    parser.add_argument("slug")
    parser.add_argument("kind", nargs="?")
    parser.add_argument("data", nargs="?")
    parser.add_argument("--input", help="JSON payload: kind, data, source_refs, related_record_ids, supersedes, occurred_at")
    parser.add_argument("--base-dir", default="crushes")
    parser.add_argument("--last", type=int, default=20)
    parser.add_argument("--type", dest="kind_filter", choices=sorted(KINDS))
    parser.add_argument("--query")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    base = Path(args.base_dir)
    try:
        if args.command == "append":
            payload = json.loads(Path(args.input).read_text(encoding="utf-8")) if args.input else {"kind": args.kind, "data": json.loads(args.data or "{}")}
            output = append_records(args.slug, [payload], base)[0]
        elif args.command in {"events", "timeline"}:
            output = get_recent_events(args.slug, args.last, [args.kind_filter] if args.kind_filter else None, base, include_history=args.history)
        elif args.command == "context":
            print(load_context(args.slug, base_dir=base, query=args.query, kinds=[args.kind_filter] if args.kind_filter else None, limit=args.last))
            return
        elif args.command == "snapshot":
            output = str(take_snapshot(args.slug, base))
        else:
            output = rebuild_state_from_events(args.slug, base)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
