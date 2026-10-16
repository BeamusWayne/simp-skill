#!/usr/bin/env python3
"""Preview by default. Legacy judgments remain unverified records. Recovery restores checksummed files."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.contracts import file_digest, stable_id, utc_now, validate_record
from tools.storage import (DEFAULT_BASE_DIR, atomic_write, backup_state, data_files, member, profile_lock,
                           profile_path, restore_state, verify_backup, write_json)
from tools.memory import _project, _read_records, verify_projections
from tools.storage import ensure_ready


def preview(slug, base_dir=DEFAULT_BASE_DIR):
    root = profile_path(slug, base_dir)
    if not root.is_dir():
        raise FileNotFoundError(root)
    # Deliberately no lock-file creation: a dry run has no filesystem mutation.
    for marker in (".migration.json", ".restore.json", ".pending.json"):
        if member(root, marker).exists():
            raise RuntimeError("Incomplete maintenance; recover before another migration")
    meta_path = member(root, "meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    version = meta.get("schema_version", 1)
    if version not in {1, 2}:
        raise ValueError("Unsupported future profile schema")
    files = {rel: file_digest(member(root, rel)) for rel in data_files(root)}
    issues = []
    for name in ("events.jsonl", "interactions.jsonl"):
        path = member(root, name)
        if path.exists():
            for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not text.strip():
                    continue
                try:
                    json.loads(text)
                except json.JSONDecodeError:
                    issues.append({"file": name, "line": line, "problem": "malformed_line_preserved_as_legacy"})
    return {"slug": slug, "source_schema": version, "already_v2": version == 2,
            "files": files, "fingerprint": stable_id(files, "migration:"), "issues": issues,
            "policy": "All legacy content is preserved; no old score, stage or personality is promoted to fact"}


def migrate(slug, base_dir=DEFAULT_BASE_DIR, *, checkpoint=None, expected_fingerprint=None):
    root = profile_path(slug, base_dir)
    checkpoint = checkpoint or (lambda step: None)
    with profile_lock(root):
        plan = preview(slug, base_dir)
        if expected_fingerprint and plan["fingerprint"] != expected_fingerprint:
            raise ValueError("Source changed since preview; generate a new preview")
        if plan["already_v2"]:
            return {"status": "already_v2", "slug": slug}
        backup = backup_state(root, "before-v2-migration")
        manifest = verify_backup(root, backup)
        marker = member(root, ".migration.json")
        write_json(marker, {"backup": backup, "fingerprint": plan["fingerprint"], "status": "in_progress"})
        checkpoint("marker")
        records = []
        stamp = utc_now()
        for rel in manifest["files"]:
            source = member(root, "versions/" + backup + "/files/" + rel)
            # Keep source material at its original path; archive all old logical state.
            if rel.startswith("memories/"):
                continue
            target = member(root, "legacy/v1/" + rel)
            if target.exists():
                raise ValueError("legacy/v1 already contains data; inspect before migrating")
            atomic_write(target, source.read_bytes())
            checkpoint("archive:" + rel)
            if source.suffix in {".md", ".json", ".jsonl"}:
                content = source.read_text(encoding="utf-8")
                chunks = list(enumerate(content.splitlines(), 1)) if source.suffix == ".jsonl" else [(1, content)]
                for line, text in chunks:
                    if not text.strip():
                        continue
                    record = {"schema_version": 2, "record_id": stable_id([rel, line, text], "legacy:"),
                              "kind": "legacy_record", "recorded_at": stamp, "occurred_at": None,
                              "source_refs": [{"kind": "file", "path": str(target), "sha256": file_digest(target), "locator": f"line:{line}"}],
                              "related_record_ids": [], "supersedes": [],
                              "data": {"summary": f"待核实的旧版内容 {rel}:{line}", "raw": text, "origin_schema": 1}}
                    validate_record(record)
                    records.append(record)
        atomic_write(member(root, "events.jsonl"), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
        checkpoint("events")
        write_json(member(root, "meta.json"), {"schema_version": 2, "slug": slug, "created_at": stamp, "nickname": slug})
        checkpoint("meta")
        _read_records(root)
        _project(root, records)
        checkpoint("projections")
        write_json(member(root, "legacy/v1/migration-report.json"), {"backup": backup, "issues": plan["issues"], "legacy_records": len(records)})
        checkpoint("report")
        marker.unlink()
        return {"status": "migrated", "slug": slug, "backup": backup, "legacy_records": len(records), "issues": plan["issues"]}


def recover(slug, base_dir=DEFAULT_BASE_DIR, *, checkpoint=None):
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        marker = member(root, ".migration.json")
        operation = json.loads(marker.read_text(encoding="utf-8"))
        # Save partially applied state too; never erase potential later content silently.
        saved = backup_state(root, "before-migration-recovery")
        restore_state(root, operation["backup"], checkpoint=checkpoint)
        marker.unlink()
        return {"status": "restored_v1", "backup": operation["backup"], "saved_partial_as": saved}


def check(slug, base_dir=DEFAULT_BASE_DIR):
    """Validate current ledger, projections and all file references; never repair implicitly."""
    root = profile_path(slug, base_dir)
    with profile_lock(root):
        ensure_ready(root)
        records = _read_records(root)
        verify_projections(root)
        files = set()
        for record in records:
            for ref in record["source_refs"]:
                if ref["kind"] == "file":
                    pair = (ref["path"], ref["sha256"])
                    if pair not in files and file_digest(Path(ref["path"])) != ref["sha256"]:
                        raise ValueError("Referenced source has changed: " + ref["path"])
                    files.add(pair)
        return {"status": "valid", "records": len(records), "verified_sources": len(files)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("slug")
    p.add_argument("--base-dir", default="crushes")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--recover", action="store_true")
    mode.add_argument("--check", action="store_true")
    p.add_argument("--expected-fingerprint")
    args = p.parse_args()
    try:
        if args.check:
            result = check(args.slug, Path(args.base_dir))
        elif args.recover:
            result = recover(args.slug, Path(args.base_dir))
        elif args.apply:
            result = migrate(args.slug, Path(args.base_dir), expected_fingerprint=args.expected_fingerprint)
        else:
            result = preview(args.slug, Path(args.base_dir))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
