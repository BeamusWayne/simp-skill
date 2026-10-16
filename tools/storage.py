"""Local profile I/O, OS-released locks and checksum-verified restore points."""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from uuid import uuid4
from tools.contracts import file_digest, utc_now

DEFAULT_BASE_DIR = Path("crushes")
EXCLUDED = {"versions", ".lock", ".migration.json", ".pending.json", ".restore.json"}


def profile_path(slug: str, base_dir: Path = DEFAULT_BASE_DIR) -> Path:
    if not isinstance(slug, str) or not re.fullmatch(r"[\w-]+", slug, flags=re.UNICODE) or slug in {".", ".."}:
        raise ValueError("slug must contain only letters, numbers, underscores or hyphens")
    base = Path(base_dir).resolve()
    path = base / slug
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()) or path.resolve().parent != base:
        raise ValueError("profile path must stay directly inside base directory")
    return path


def member(root: Path, name: str) -> Path:
    path = root / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escapes profile or backup")
    for ancestor in (path, *path.parents):
        if ancestor == root.parent:
            break
        if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
            raise ValueError("symlinks/junctions are not supported in profile data")
    return path


def atomic_write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def profile_lock(root: Path):
    """The OS releases this advisory lock even when the process crashes."""
    if not root.is_dir():
        raise FileNotFoundError(f"Profile does not exist: {root}")
    path = member(root, ".lock")
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Profile is busy; retry when the other operation finishes") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def ensure_ready(root: Path, *, allow_pending=False):
    for name in (".migration.json", ".restore.json"):
        if member(root, name).exists():
            raise RuntimeError(f"Incomplete maintenance ({name}); run the documented recovery command")
    if not allow_pending and member(root, ".pending.json").exists():
        raise RuntimeError("Incomplete projection update; run memory.py rebuild")
    meta = json.loads(member(root, "meta.json").read_text(encoding="utf-8"))
    if meta.get("schema_version") != 2:
        raise ValueError("Legacy profile; preview tools/migrate_v2.py before writing")
    return meta


def data_files(root: Path):
    result = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        current = Path(directory)
        dirs[:] = [d for d in dirs if not d.startswith(".write-") and not (current == root and d in EXCLUDED)]
        for name in dirs + files:
            if name.startswith(".write-") or (current == root and name in EXCLUDED):
                continue
            rel = (current / name).relative_to(root)
            path = member(root, rel.as_posix())
            if path.is_file():
                result.append(rel.as_posix())
    return sorted(result)


def backup_state(root: Path, purpose="backup") -> str:
    identifier = utc_now().replace(":", "").replace("+", "_") + "-" + uuid4().hex[:8]
    destination = member(root, "versions/" + identifier)
    destination.mkdir(parents=True)
    files = {}
    for rel in data_files(root):
        source = member(root, rel)
        target = member(destination / "files", rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files[rel] = file_digest(target)
    write_json(destination / "manifest.json", {"snapshot_format": 1, "id": identifier,
               "purpose": purpose, "created_at": utc_now(), "files": files})
    return identifier


def verify_backup(root: Path, identifier: str) -> dict:
    if not identifier or identifier in {".", ".."} or Path(identifier).name != identifier or "/" in identifier or "\\" in identifier:
        raise ValueError("an exact backup ID is required")
    directory = member(root, "versions/" + identifier)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("snapshot_format") != 1 or manifest.get("id") != identifier:
        raise ValueError("unsupported or mismatched backup manifest")
    for rel, digest in manifest["files"].items():
        if Path(rel).parts[0] in EXCLUDED or file_digest(member(directory / "files", rel)) != digest:
            raise ValueError(f"backup checksum/path invalid: {rel}")
    return manifest


def restore_state(root: Path, identifier: str, *, checkpoint=None):
    """Caller holds the lock and a maintenance marker; deletions stay within root."""
    manifest = verify_backup(root, identifier)
    checkpoint = checkpoint or (lambda step: None)
    for rel in data_files(root):
        if rel not in manifest["files"]:
            member(root, rel).unlink()
            checkpoint("delete:" + rel)
    for rel in manifest["files"]:
        atomic_write(member(root, rel), member(root, "versions/" + identifier + "/files/" + rel).read_bytes())
        checkpoint("restore:" + rel)
    for rel, digest in manifest["files"].items():
        if file_digest(member(root, rel)) != digest:
            raise ValueError("restore verification failed: " + rel)
