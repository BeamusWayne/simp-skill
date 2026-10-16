"""Shared, descriptive chat statistics with explicit sample accounting."""
from __future__ import annotations
from collections import Counter
from statistics import mean, median
from tools.contracts import Message


def summarize_delays(seconds: list[float]) -> dict:
    return {"count": len(seconds), "average_seconds": mean(seconds) if seconds else None,
            "median_seconds": median(seconds) if seconds else None,
            "min_seconds": min(seconds) if seconds else None, "max_seconds": max(seconds) if seconds else None}


def reply_samples(messages: list[Message]) -> dict:
    """Adjacent cross-speaker turns, from the LAST message of the previous turn.

    No long-gap cutoff. Groups, unknown actors, incomparable clocks and backward
    source times break a pair instead of inventing a reply. No implicit sorting.
    """
    samples = []
    excluded = Counter()
    candidate_pairs = 0
    previous = None
    for msg in messages:
        if previous is not None and previous.conversation_id == msg.conversation_id:
            if previous.sender_id != msg.sender_id or msg.sender_id is None:
                candidate_pairs += 1
                reason = None
                if msg.conversation_type == "group" or previous.conversation_type == "group":
                    reason = "group_conversation"
                elif msg.conversation_type != "direct" or previous.conversation_type != "direct":
                    reason = "unknown_conversation_type"
                elif {previous.role, msg.role} != {"user", "target"}:
                    reason = "not_a_resolved_user_target_pair"
                elif previous.timestamp is None or msg.timestamp is None or any(
                    x.time_status in {"date_only", "invalid", "missing"} for x in (previous, msg)
                ):
                    reason = "missing_or_imprecise_time"
                elif (previous.timestamp.tzinfo is None) != (msg.timestamp.tzinfo is None):
                    reason = "incomparable_timezones"
                if reason:
                    excluded[reason] += 1
                else:
                    delay = (msg.timestamp - previous.timestamp).total_seconds()
                    if delay < 0:
                        excluded["backward_source_time"] += 1
                    else:
                        samples.append({"message_id": msg.message_id, "previous_message_id": previous.message_id,
                                        "role": msg.role, "seconds": delay,
                                        "clock": "source_local_unknown_zone" if msg.timestamp.tzinfo is None else "absolute"})
        previous = msg
    return {"method": "adjacent_cross_speaker_turns_from_last_message_no_gap_cutoff",
            "candidate_pairs": candidate_pairs, "valid_pairs": len(samples),
            "excluded": dict(excluded), "samples": samples,
            "user": summarize_delays([s["seconds"] for s in samples if s["role"] == "user"]),
            "target": summarize_delays([s["seconds"] for s in samples if s["role"] == "target"])}


def describe_messages(messages: list[Message], session_gap_minutes: float = 60) -> dict:
    if session_gap_minutes <= 0:
        raise ValueError("session gap must be positive")
    counts = Counter(m.role for m in messages)
    initiators = Counter()
    previous = None
    for msg in messages:
        if msg.role not in {"user", "target"} or msg.conversation_type != "direct":
            previous = None
            continue
        if msg.timestamp is None or msg.time_status not in {"known", "timezone_unknown"}:
            previous = None
            continue
        new = previous is None or previous.conversation_id != msg.conversation_id
        if not new and (msg.timestamp.tzinfo is None) == (previous.timestamp.tzinfo is None):
            gap = (msg.timestamp - previous.timestamp).total_seconds()
            new = gap > session_gap_minutes * 60
        if new:
            initiators[msg.role] += 1
        previous = msg
    known_times = [m.timestamp.isoformat() for m in messages if m.timestamp is not None]
    return {"total_messages": len(messages), "counts_by_role": dict(counts),
            "time_status_counts": dict(Counter(m.time_status for m in messages)),
            "first_source_time": known_times[0] if known_times else None,
            "last_source_time": known_times[-1] if known_times else None,
            "session_initiators": dict(initiators), "session_gap_minutes": session_gap_minutes,
            "session_note": "observed excerpt/session starts; not necessarily first contact",
            "replies": reply_samples(messages)}
