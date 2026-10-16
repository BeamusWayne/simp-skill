#!/usr/bin/env python3
"""Create explicit local profiles and restore complete, exact checkpoints."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.contracts import utc_now
from tools.storage import (DEFAULT_BASE_DIR, atomic_write, backup_state, ensure_ready, member, profile_lock,
                           profile_path, restore_state, verify_backup, write_json)
from tools.memory import _project, append_event, get_recent_events, verify_projections


def init_crush(slug, base_dir=DEFAULT_BASE_DIR):
    root = profile_path(slug, base_dir)
    root.mkdir(parents=True, exist_ok=True)
    with profile_lock(root):
        if member(root, "meta.json").exists():
            ensure_ready(root)
            return root
        if any(p.name != ".lock" for p in root.iterdir()):
            raise ValueError("Existing profile without metadata; inspect/migrate it instead of overwriting")
        for directory in ("memories/chats", "memories/social", "memories/photos", "versions", "snapshots"):
            member(root, directory).mkdir(parents=True, exist_ok=True)
        write_json(member(root, ".pending.json"), {"operation": "initialize"})
        write_json(member(root, "meta.json"), {"schema_version": 2, "slug": slug, "created_at": utc_now(), "nickname": slug})
        atomic_write(member(root, "events.jsonl"), "")
        _project(root, [])
        member(root, ".pending.json").unlink()
    return root


def list_crushes(base_dir=DEFAULT_BASE_DIR):
    base = Path(base_dir)
    if not base.exists():
        return []
    result = []
    for path in sorted(base.iterdir()):
        if path.is_dir() and not path.name.startswith("."):
            root = profile_path(path.name, base)
            try:
                with profile_lock(root):
                    meta = ensure_ready(root)
                    verify_projections(root)
                    result.append({k: meta.get(k) for k in ("slug", "nickname", "updated_at", "last_interaction", "needs_review_count")})
            except (OSError, ValueError, RuntimeError) as exc:
                result.append({"slug": path.name, "status": str(exc)})
    return result


def backup_crush(slug, base_dir=DEFAULT_BASE_DIR):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root)
        return backup_state(root)


def rollback_crush(slug, version, base_dir=DEFAULT_BASE_DIR, *, checkpoint=None):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root, allow_pending=True)
        verify_backup(root, version)
        before = backup_state(root, "before-restore")
        write_json(member(root, ".restore.json"), {"target": version, "before": before})
        restore_state(root, version, checkpoint=checkpoint)
        pending = member(root, ".pending.json")
        if pending.exists():
            pending.unlink()
        member(root, ".restore.json").unlink()
        return {"restored": version, "saved_current_as": before}


def recover_restore(slug, base_dir=DEFAULT_BASE_DIR):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        marker = member(root, ".restore.json")
        operation = json.loads(marker.read_text(encoding="utf-8"))
        restore_state(root, operation["target"])
        pending = member(root, ".pending.json")
        if pending.exists():
            pending.unlink()
        marker.unlink()
        return operation


def list_versions(slug, base_dir=DEFAULT_BASE_DIR):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root)
        versions = member(root, "versions")
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(versions.glob("*/manifest.json"))]


def update_meta(slug, base_dir=DEFAULT_BASE_DIR, **kwargs):
    if set(kwargs) - {"nickname", "mode", "goal"}:
        raise ValueError("Only nickname, mode and goal may be updated; score/stage writes were removed in v2")
    if "mode" in kwargs and kwargs["mode"] not in {"sweet", "strategic", "hybrid"}:
        raise ValueError("invalid expression mode")
    for key, value in kwargs.items():
        old = [r for r in get_recent_events(slug, n=10**9, event_types=["preference"], base_dir=base_dir) if r["data"]["key"] == key]
        if old and old[-1]["data"]["value"] == value:
            continue
        append_event(slug, "preference", {"summary": f"用户设置 {key}", "key": key, "value": value, "confirmed": True},
                     base_dir, source_refs=[{"kind": "user", "locator": "cli:update-meta", "excerpt": json.dumps({key: value}, ensure_ascii=False)}],
                     supersedes=[old[-1]["record_id"]] if old else [])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--action", required=True, choices=["init", "list", "backup", "rollback", "recover-restore", "versions", "update-meta"])
    p.add_argument("--slug")
    p.add_argument("--version", help="Exact ID from backup/versions; prefixes are not accepted")
    p.add_argument("--base-dir", default="crushes")
    for field in ("nickname", "mode", "goal", "stage", "score"):
        p.add_argument("--" + field)
    args = p.parse_args()
    if args.stage is not None or args.score is not None:
        p.error("--stage/--score are removed in v2; no data was changed")
    if args.action != "list" and not args.slug:
        p.error("--slug is required")
    base = Path(args.base_dir)
    try:
        if args.action == "init":
            result = str(init_crush(args.slug, base))
        elif args.action == "list":
            result = list_crushes(base)
        elif args.action == "backup":
            result = backup_crush(args.slug, base)
        elif args.action == "rollback":
            if not args.version:
                p.error("--version requires an exact backup ID")
            result = rollback_crush(args.slug, args.version, base)
        elif args.action == "recover-restore":
            result = recover_restore(args.slug, base)
        elif args.action == "versions":
            result = list_versions(args.slug, base)
        else:
            result = update_meta(args.slug, base, **{key: getattr(args, key) for key in ("nickname", "mode", "goal") if getattr(args, key) is not None})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
