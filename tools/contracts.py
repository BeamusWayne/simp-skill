"""Versioned data contracts. No relationship inference belongs in this module."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
ROLES = {"user", "target", "third_party", "system", "unknown"}
KINDS = {"observation", "user_report", "identity_mapping", "preference", "assessment",
         "advice", "action_report", "outcome", "correction", "legacy_record"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(value: Any, prefix: str = "") -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_time(value: Any) -> tuple[datetime | None, str]:
    """Naive source times remain naive; numeric epochs are UTC, never host time."""
    if value is None or value == "":
        return None, "missing"
    try:
        if isinstance(value, bool):
            return None, "invalid"
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)) or str(value).strip().lstrip("-").isdigit():
            number = float(value)
            if not math.isfinite(number):
                return None, "invalid"
            if abs(number) >= 100_000_000_000:
                number /= 1000
            dt = datetime.fromtimestamp(number, timezone.utc)
        else:
            raw = str(value).strip().replace("/", "-")
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if len(raw) == 10:
                return dt, "date_only"
        return dt, "known" if dt.tzinfo is not None else "timezone_unknown"
    except (ValueError, TypeError, OverflowError, OSError):
        return None, "invalid"


def validate_source(ref: dict) -> None:
    if not isinstance(ref, dict):
        raise ValueError("source_refs entries must be objects")
    if ref.get("kind") == "file":
        if not all(isinstance(ref.get(k), str) and ref[k] for k in ("path", "sha256", "locator")):
            raise ValueError("file sources require path, sha256 and locator")
        digest = ref["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid source checksum")
    elif ref.get("kind") in {"user", "session"}:
        if not all(isinstance(ref.get(k), str) and ref[k] for k in ("locator", "excerpt")):
            raise ValueError("user/session sources require locator and excerpt")
    else:
        raise ValueError("unknown source kind")


@dataclass
class Message:
    timestamp: datetime | None
    sender: str
    content: str
    msg_type: str = "text"
    message_id: str = ""
    conversation_id: str = ""
    sender_id: str | None = None
    role: str = "unknown"
    source_order: int = 0
    time_status: str = "missing"
    source_refs: list[dict] = field(default_factory=list)
    reply_to_id: str | None = None
    quoted_message_id: str | None = None
    quoted_text: str | None = None
    parse_status: str = "complete"
    issues: list[str] = field(default_factory=list)
    conversation_type: str = "unknown"
    id_method: str = "source_location"

    def __repr__(self) -> str:
        return f"[{self.timestamp or 'unknown time'}] {self.sender}: {self.content[:30]}"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["sent_at"] = data.pop("timestamp").isoformat() if self.timestamp else None
        data["message_type"] = data.pop("msg_type")
        data["schema_version"] = SCHEMA_VERSION
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Message:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported message schema")
        values = dict(data)
        values.pop("schema_version")
        values["timestamp"], _ = parse_time(values.pop("sent_at", None))
        values["msg_type"] = values.pop("message_type", "text")
        msg = cls(**values)
        validate_message(msg)
        return msg


def validate_message(msg: Message) -> None:
    if not all(isinstance(v, str) and v for v in (msg.message_id, msg.conversation_id)) or not isinstance(msg.content, str):
        raise ValueError("message requires identity, conversation and text")
    if not isinstance(msg.sender, str) or any(value is not None and not isinstance(value, str)
                                              for value in (msg.sender_id, msg.reply_to_id, msg.quoted_message_id, msg.quoted_text)):
        raise ValueError("sender and reference fields must be strings or null")
    if msg.role not in ROLES or type(msg.source_order) is not int or msg.source_order < 0 or not msg.source_refs:
        raise ValueError("invalid message role, order or provenance")
    if msg.time_status not in {"known", "timezone_unknown", "date_only", "missing", "invalid"}:
        raise ValueError("invalid time status")
    if msg.parse_status not in {"complete", "partial", "ambiguous"}:
        raise ValueError("invalid parse status")
    if msg.conversation_type not in {"direct", "group", "unknown"}:
        raise ValueError("invalid conversation type")
    if msg.time_status == "known" and (msg.timestamp is None or msg.timestamp.tzinfo is None):
        raise ValueError("known time requires an offset")
    if msg.time_status in {"timezone_unknown", "date_only"} and (msg.timestamp is None or msg.timestamp.tzinfo is not None):
        raise ValueError("local/date-only time requires a naive timestamp")
    if msg.time_status in {"missing", "invalid"} and msg.timestamp is not None:
        raise ValueError("missing/invalid time cannot contain a parsed timestamp")
    for ref in msg.source_refs:
        validate_source(ref)


def validate_record(record: dict) -> None:
    if record.get("schema_version") != SCHEMA_VERSION or record.get("kind") not in KINDS:
        raise ValueError("unsupported record schema or kind")
    if not record.get("record_id") or parse_time(record.get("recorded_at"))[1] != "known":
        raise ValueError("record requires ID and timezone-aware recorded_at")
    if record.get("occurred_at") is not None and parse_time(record["occurred_at"])[1] in {"invalid", "missing"}:
        raise ValueError("invalid occurred_at")
    data = record.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("summary"), str) or not data["summary"].strip():
        raise ValueError("data.summary is required")
    for key in ("source_refs", "related_record_ids", "supersedes"):
        if not isinstance(record.get(key), list):
            raise ValueError(f"{key} must be a list")
    for key in ("related_record_ids", "supersedes"):
        if any(not isinstance(item, str) or not item for item in record[key]):
            raise ValueError(f"{key} must contain record IDs")
    for ref in record["source_refs"]:
        validate_source(ref)
    kind = record["kind"]
    if kind in {"observation", "user_report", "identity_mapping", "preference", "action_report", "outcome", "correction"} and not record["source_refs"]:
        raise ValueError(f"{kind} requires provenance")
    if kind == "observation" and not any(r["kind"] == "file" for r in record["source_refs"]):
        raise ValueError("observations require original material; use user_report for retellings")
    if kind == "action_report" and data.get("confirmed") is not True:
        raise ValueError("actions require explicit confirmation")
    if kind == "outcome" and not data.get("action_id"):
        raise ValueError("outcome requires action_id")
    if kind == "correction" and not record["supersedes"]:
        raise ValueError("correction must identify superseded records")
    if kind == "identity_mapping":
        if not all(isinstance(data.get(k), str) and data[k] for k in ("conversation_id", "sender_id")) or data.get("role") not in ROLES:
            raise ValueError("identity_mapping requires conversation_id, sender_id and role")
    if kind == "preference" and (not isinstance(data.get("key"), str) or "value" not in data):
        raise ValueError("preference requires key and value")
    for key in ("supporting_ids", "opposing_ids", "identity_ids"):
        if key in data and (not isinstance(data[key], list) or any(not isinstance(x, str) for x in data[key])):
            raise ValueError(f"data.{key} must contain record IDs")
        if any(ref not in record["related_record_ids"] for ref in data.get(key, [])):
            raise ValueError(f"data.{key} must be included in related_record_ids")
    if kind == "outcome" and data["action_id"] not in record["related_record_ids"]:
        raise ValueError("action_id must be included in related_record_ids")
    if kind == "observation" and "message" in data:
        msg = Message.from_dict(data["message"])
        if msg.source_refs != record["source_refs"]:
            raise ValueError("message provenance must match observation provenance")
