#!/usr/bin/env python3
"""Normalize chat exports with identity, original order and provenance. No scoring."""
from __future__ import annotations
import argparse
import csv
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
import html
import json
from pathlib import Path
import re
import sys
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.contracts import Message, file_digest, parse_time, stable_id, validate_message
from tools.chat_stats import describe_messages

PARSER_VERSION = "2.0.0-p3"
TIME = r"\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}"


@dataclass
class ImportResult:
    messages: list[Message]
    source: dict
    diagnostics: list[dict] = field(default_factory=list)
    input_records: int = 0
    duplicates: int = 0

    def to_dict(self):
        return {"schema_version": 2, "parser_version": PARSER_VERSION, "source": self.source,
                "input_records": self.input_records, "duplicates": self.duplicates,
                "diagnostics": self.diagnostics, "messages": [m.to_dict() for m in self.messages],
                "statistics": describe_messages(self.messages)}


def detect_format(filepath):
    path = Path(filepath)
    formats = {".json": "json", ".jsonl": "jsonl", ".csv": "wechat_csv", ".html": "wechat_html",
               ".htm": "wechat_html", ".mht": "qq_mht", ".mhtml": "qq_mht"}
    if path.suffix.lower() in formats:
        return formats[path.suffix.lower()]
    sample = path.read_text(encoding="utf-8-sig")[:4096]
    if re.search(TIME + r" .+\(\d+\)", sample):
        return "qq_txt"
    return "wechat_txt" if re.search(TIME, sample) else "unknown"


def _first(item, *keys, default=None):
    return next((item[k] for k in keys if k in item and item[k] is not None and item[k] != ""), default)


def _strip_html(value):
    return html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", value, flags=re.I))).strip()


def _read_rows(path, fmt):
    diagnostics, metadata = [], {}
    if fmt in {"json", "jsonl"}:
        raw = path.read_text(encoding="utf-8-sig")
        if fmt == "jsonl":
            rows = []
            for line, text in enumerate(raw.splitlines(), 1):
                if not text.strip():
                    continue
                try:
                    rows.append((json.loads(text), f"line:{line}"))
                except json.JSONDecodeError as exc:
                    diagnostics.append({"locator": f"line:{line}", "problem": "invalid_json", "detail": str(exc)})
            return rows, metadata, diagnostics
        data = json.loads(raw)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and isinstance(data.get("messages"), list):
            metadata = {k: v for k, v in data.items() if k != "messages"}
            items = data["messages"]
        else:
            raise ValueError("JSON must be an array or an object with a messages array")
        return [(item, f"record:{i}") for i, item in enumerate(items, 1)], metadata, diagnostics
    if fmt == "wechat_csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = [(row, f"csv-row-ending-line:{reader.line_num}") for row in reader]
        return rows, metadata, diagnostics
    if fmt == "qq_mht":
        raw_bytes = path.read_bytes()
        envelope = BytesParser(policy=policy.default).parsebytes(raw_bytes)
        if envelope.is_multipart():
            parts = [p.get_content() for p in envelope.walk() if p.get_content_type() == "text/html"]
            if not parts:
                raise ValueError("MHT contains no supported HTML part")
            raw = "\n".join(parts)
        else:
            raw = raw_bytes.decode("utf-8-sig")
        raw = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))
        matches = list(re.finditer(rf"({TIME})\s+(.+?)\((\d+)\)\s*(.*?)(?={TIME}|\Z)", raw, re.S))
        rows = [({"time": m[1], "sender": m[2].strip(), "senderId": m[3], "content": m[4].strip()}, f"mht-record:{i}")
                for i, m in enumerate(matches, 1)]
    elif fmt == "wechat_html":
        raw = path.read_text(encoding="utf-8-sig")
        pattern = (r'<div\s+class="message[^"]*"[^>]*>.*?<span\s+class="time"[^>]*>(.*?)</span>.*?'
                   r'<span\s+class="sender"[^>]*>(.*?)</span>.*?<div\s+class="content"[^>]*>(.*?)</div>')
        matches = list(re.finditer(pattern, raw, re.S))
        rows = [({"time": _strip_html(m[1]), "sender": _strip_html(m[2]), "content": _strip_html(m[3])},
                 f"html-offset:{m.start()}") for m in matches]
    else:
        raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        if fmt == "qq_txt":
            matches = list(re.finditer(rf"^({TIME})[ \t]+(.+?)(?:\((\d+)\))?[ \t]*\n(.*?)(?=^{TIME}[ \t]+|\Z)", raw, re.M | re.S))
            rows = [({"time": m[1], "sender": m[2], "senderId": m[3], "content": m[4].strip()},
                     f"line:{raw.count(chr(10), 0, m.start()) + 1}") for m in matches]
        elif fmt == "wechat_txt":
            matches = list(re.finditer(rf"^({TIME})[ \t]*\n([^\n]+)\n(.*?)(?=^{TIME}[ \t]*\n|\Z)", raw, re.M | re.S))
            rows = [({"time": m[1], "sender": m[2], "content": m[3].strip()},
                     f"line:{raw.count(chr(10), 0, m.start()) + 1}") for m in matches]
        else:
            raise ValueError("Unsupported layout; use a documented export or analyze the text directly")
    if not rows or sum(m.end() - m.start() for m in matches) < len(raw.strip()):
        diagnostics.append({"locator": "file", "problem": "unparsed_material",
                            "detail": "Partial layout match; inspect original before claiming complete coverage"})
    return rows, metadata, diagnostics


def parse_export(filepath, target_name, user_name="我", *, user_id=None, target_id=None,
                 conversation_id=None, conversation_type=None, participants=None, format_hint=None):
    path = Path(filepath).resolve()
    digest = file_digest(path)
    fmt = format_hint or detect_format(str(path))
    rows, meta, diagnostics = _read_rows(path, fmt)
    user_id = user_id or _first(meta, "accountId", "user_id")
    target_id = target_id or _first(meta, "peerId", "target_id")
    conv = conversation_id or _first(meta, "conversation_id", "conversationId")
    account_scope = str(user_id or _first(meta, "accountId", default="source:" + digest))
    default_conv = stable_id([account_scope, str(conv)], "c:") if conv else "source:" + digest
    kind = conversation_type or _first(meta, "conversation_type", "conversationType", default="unknown")
    if kind not in {"direct", "group", "unknown"}:
        raise ValueError("conversation_type must be direct, group or unknown")
    participants = participants or {}
    if not isinstance(participants, dict) or any(r not in {"user", "target", "third_party", "system", "unknown"} for r in participants.values()):
        raise ValueError("participants must map exact sender IDs to roles")
    result = ImportResult([], {"path": str(path), "sha256": digest, "format": fmt}, diagnostics,
                          len(rows) + sum(d["problem"] == "invalid_json" for d in diagnostics))
    for order, (row, locator) in enumerate(rows):
        if not isinstance(row, dict):
            result.diagnostics.append({"locator": locator, "problem": "record_is_not_an_object"})
            continue
        if row.get("schema_version") == 2:
            result.messages.append(Message.from_dict(row))
            continue
        content = _first(row, "content", "text", "msg", "StrContent", default="")
        msg_type = str(_first(row, "message_type", "msg_type", "type", default="text"))
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        if not content and msg_type == "text":
            result.diagnostics.append({"locator": locator, "problem": "empty_record"})
            continue
        ts, time_status = parse_time(_first(row, "sent_at", "timestamp", "time", "createTime", "CreateTime"))
        row_conv = _first(row, "conversation_id", "conversationId")
        cid = stable_id([account_scope, str(row_conv)], "c:") if row_conv else default_conv
        row_kind = _first(row, "conversation_type", "conversationType", default=kind)
        if row_kind not in {"direct", "group", "unknown"}:
            row_kind = "unknown"
        sender = str(_first(row, "sender", "from", "nickName", "NickName", "displayName", default="")).strip()
        sid = _first(row, "sender_id", "senderId", "fromId", "SenderId")
        sid = str(sid) if sid is not None else None
        role, issues = "unknown", []
        direction = _first(row, "isSend", "IsSender")
        if direction not in (None, 0, 1, "0", "1", False, True):
            issues.append("invalid_isSend")
            direction = None
        if sid:
            role = participants.get(sid, "user" if sid == str(user_id) else "target" if sid == str(target_id) else "unknown")
        elif direction is not None and user_id:
            if str(direction).lower() in {"1", "true"}:
                sid, role = str(user_id), "user"
            elif row_kind == "direct" and target_id:
                sid, role = str(target_id), "target"
        elif sender:
            sid = stable_id([cid, sender], "label:")
            role = "unknown" if sender == user_name == target_name else "user" if sender == user_name else "target" if sender == target_name else "third_party"
            issues.append("display_name_only_identity")
        if direction is not None and sid and user_id:
            if (str(direction).lower() in {"1", "true"}) != (sid == str(user_id)):
                role = "unknown"
                issues.append("sender_id_conflicts_with_isSend")
        if role == "unknown":
            issues.append("unresolved_sender")
        sender = sender or str(sid or "未知发送者")
        raw_id = _first(row, "message_id", "localId", "msgId", "id")
        mid = stable_id([cid, str(raw_id)], "m:") if raw_id is not None else stable_id([digest, locator], "m:")
        quote = _first(row, "quoted_message_id", "quotedMessageId", "quoteId")
        reply = _first(row, "reply_to_id", "replyToId")
        quote_text = _first(row, "quoted_text", "quotedText")
        if isinstance(row.get("quote"), dict):
            quote = _first(row["quote"], "localId", "id", default=quote)
            quote_text = _first(row["quote"], "content", "text", default=quote_text)
        if time_status in {"invalid", "missing", "date_only"}:
            issues.append("imprecise_time:" + time_status)
        msg = Message(ts, sender, content, msg_type, mid, cid, sid, role, order, time_status,
                      [{"kind": "file", "path": str(path), "sha256": digest, "locator": locator}],
                      stable_id([cid, str(reply)], "m:") if reply is not None else None,
                      stable_id([cid, str(quote)], "m:") if quote is not None else None,
                      str(quote_text) if quote_text is not None else None,
                      "ambiguous" if role == "unknown" else "partial" if issues else "complete",
                      issues, row_kind, "original_id" if raw_id is not None else "source_location")
        validate_message(msg)
        result.messages.append(msg)
    result.messages, result.duplicates = deduplicate_messages(result.messages)
    ids = {m.message_id for m in result.messages}
    for msg in result.messages:
        if any(ref and ref not in ids for ref in (msg.reply_to_id, msg.quoted_message_id)):
            msg.issues.append("unresolved_reference")
            if msg.parse_status == "complete":
                msg.parse_status = "partial"
    return result


def deduplicate_messages(messages):
    output, seen, duplicates = [], {}, 0
    for msg in messages:
        key = (msg.conversation_id, msg.message_id)
        if key in seen:
            prior = seen[key]
            fields = ("sender_id", "content", "timestamp", "msg_type", "reply_to_id", "quoted_message_id", "quoted_text")
            if any(getattr(prior, field) != getattr(msg, field) for field in fields):
                raise ValueError(f"Conflicting messages share ID {msg.message_id}; review source IDs")
            for ref in msg.source_refs:
                if ref not in prior.source_refs:
                    prior.source_refs.append(ref)
            duplicates += 1
        else:
            seen[key] = msg
            output.append(msg)
    return output, duplicates


def parse_chat(filepath, target_name, user_name="我", **kwargs):
    return parse_export(filepath, target_name, user_name, **kwargs).messages


def parse_wechat_txt(filepath, target_name, user_name):
    return parse_chat(filepath, target_name, user_name, format_hint="wechat_txt")


def parse_qq_txt(filepath, target_name, user_name):
    return parse_chat(filepath, target_name, user_name, format_hint="qq_txt")


def parse_qq_mht(filepath, target_name, user_name):
    return parse_chat(filepath, target_name, user_name, format_hint="qq_mht")


def parse_wechat_html(filepath, target_name, user_name):
    return parse_chat(filepath, target_name, user_name, format_hint="wechat_html")


def parse_wechat_csv(filepath, target_name, user_name):
    return parse_chat(filepath, target_name, user_name, format_hint="wechat_csv")


def parse_json(filepath, target_name, user_name):
    return parse_chat(filepath, target_name, user_name, format_hint="json")


def generate_report(messages, target_name, user_name, output_path=None):
    lines = ["# 聊天记录整理", f"分析对象显示名：{target_name}；用户显示名：{user_name}",
             "统计描述导出片段，不代表恋爱意愿。原始顺序保留。", "", "## 客观统计", "```json",
             json.dumps(describe_messages(messages), ensure_ascii=False, indent=2), "```", "", "## 来源与消息"]
    for msg in messages:
        lines.extend([f"- [{msg.message_id}] [{msg.role}] {msg.sender} | {msg.timestamp or '时间未知'}",
                      "  " + msg.content.replace("\n", "\n  "), "  来源：" + json.dumps(msg.source_refs, ensure_ascii=False)])
        if msg.quoted_message_id or msg.reply_to_id or msg.quoted_text:
            lines.append(f"  引用：{msg.quoted_message_id}; 回复：{msg.reply_to_id}; 引用原文：{msg.quoted_text}")
        if msg.issues:
            lines.append("  待核对：" + ", ".join(msg.issues))
    text = "\n".join(lines) + "\n"
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(text, encoding="utf-8")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file")
    parser.add_argument("target")
    parser.add_argument("--user", default="我")
    for name in ("user-id", "target-id", "conversation-id", "participants", "slug"):
        parser.add_argument("--" + name)
    parser.add_argument("--conversation-type", choices=["direct", "group", "unknown"])
    parser.add_argument("--output", "-o")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--track-time", action="store_true", help="Import into an existing v2 profile")
    parser.add_argument("--base-dir", default="crushes")
    args = parser.parse_args()
    try:
        roles = json.loads(Path(args.participants).read_text(encoding="utf-8")) if args.participants else None
        result = parse_export(args.input_file, args.target, args.user, user_id=args.user_id, target_id=args.target_id,
                              conversation_id=args.conversation_id, conversation_type=args.conversation_type, participants=roles)
        if args.output and Path(args.output).resolve() == Path(args.input_file).resolve():
            raise ValueError("output must not overwrite the source")
        if args.output and args.slug:
            from tools.storage import profile_path
            if Path(args.output).resolve().is_relative_to(profile_path(args.slug, Path(args.base_dir))):
                raise ValueError("Write reports outside the profile directory")
        if args.track_time:
            if not args.slug:
                parser.error("--track-time requires --slug")
            from tools.time_tracker import import_messages
            import_messages(args.slug, result.messages, Path(args.base_dir))
        output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.json else generate_report(result.messages, args.target, args.user)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
        if result.diagnostics:
            print(json.dumps({"diagnostics": result.diagnostics}, ensure_ascii=False), file=sys.stderr)
    except (ValueError, OSError, RuntimeError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
