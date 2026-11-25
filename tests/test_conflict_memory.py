import json
import subprocess
import sys

import pytest

from tools.memory import append_event, append_records, get_recent_events, load_context, rebuild_state_from_events


def report(base, source, summary, **fields):
    return append_event("alice", "user_report", {"summary": summary, **fields}, base, source_refs=source)


def conflict_payload(opening, *, status="open", evidence=(), previous=None, summary="这件事还需要处理"):
    opening_id = opening["record_id"]
    evidence_ids = [record["record_id"] for record in evidence]
    return {
        "kind": "assessment",
        "data": {
            "repair_schema": 1,
            "summary": summary,
            "supporting_ids": list(dict.fromkeys([opening_id, *evidence_ids])),
            "conflict": {"opening_record_id": opening_id, "status": status, "status_evidence_ids": evidence_ids},
        },
        "supersedes": [previous["record_id"]] if previous else [],
    }


def issue_id(record):
    return record["data"]["conflict"]["issue_id"]


def context(base, **selectors):
    return json.loads(load_context("alice", base_dir=base, **selectors))


def test_conflict_lookup_is_independent_of_recency_and_general_state(base, source):
    opening = report(base, source, "对方当众拿我的工作开玩笑")
    conflict = append_records("alice", [conflict_payload(opening)], base)[0]
    for i in range(25):
        append_event("alice", "assessment", {"summary": f"无关判断 {i}"}, base)
    result = context(base, open_issues=True, limit=1)
    assert result["issues"] == [
        {"head_record_id": conflict["record_id"], "issue_id": issue_id(conflict),
         "status": "open", "summary": "这件事还需要处理"}
    ]
    assert list(result["records"]) == [opening, conflict]
    assert "无关判断 24" in (base / "alice/state.md").read_text(encoding="utf-8")
    rebuild_state_from_events("alice", base)
    assert context(base, open_issues=True, limit=1) == result


def test_conflict_revisions_use_same_issue_cas_and_allow_identical_replay(base, source):
    opening = report(base, source, "约好见面却被放鸽子")
    initial = conflict_payload(opening)
    first = append_records("alice", [initial], base)[0]
    discussion = report(base, source, "我们确实谈过，但还没有说开")
    revised = conflict_payload(opening, status="discussed", evidence=[discussion], previous=first)
    second = append_records("alice", [revised], base)[0]

    stale = conflict_payload(opening, status="discussed", evidence=[discussion], previous=first, summary="另一条旧版本写入")
    with pytest.raises(ValueError, match="Stale scoped revision"):
        append_records("alice", [stale], base)
    with pytest.raises(ValueError, match="same scope"):
        append_event("alice", "assessment", {"summary": "非法替代"}, base, supersedes=[second["record_id"]])

    before = (base / "alice/events.jsonl").read_bytes()
    retry = append_records("alice", [initial], base, include_scope_state=True)[0]
    assert retry["record_id"] == first["record_id"]
    assert retry["scope_state"] == {"head_record_id": second["record_id"], "head_status": "active", "replay": True}
    assert (base / "alice/events.jsonl").read_bytes() == before
    assert issue_id(first) == issue_id(second)
    assert context(base, issue=issue_id(first))["issues"][0]["status"] == "discussed"


def test_issue_links_only_confirmed_actions_and_needs_real_closing_evidence(base, source):
    opening = report(base, source, "我拿她的工作开玩笑，她说不舒服")
    with pytest.raises(ValueError, match="initial conflict assessment must be open"):
        append_records("alice", [conflict_payload(opening, status="resolved", evidence=[opening])], base)
    first = append_records("alice", [conflict_payload(opening)], base)[0]
    issue = issue_id(first)
    with pytest.raises(ValueError, match="fresh status evidence"):
        append_records("alice", [conflict_payload(opening, status="resolved", evidence=[opening], previous=first)], base)
    draft = append_event("alice", "advice", {"summary": "建议发一个道歉草稿"}, base, related_record_ids=[first["record_id"]])
    action_data = {"summary": "我实际发了一条道歉消息", "confirmed": True, "repair_schema": 1, "issue_id": issue}
    with pytest.raises(ValueError, match="draft"):
        append_event("alice", "action_report", action_data, base, source_refs=source, related_record_ids=[draft["record_id"]])
    action = append_event("alice", "action_report", action_data, base, source_refs=source)
    with pytest.raises(ValueError, match="status evidence"):
        append_records("alice", [conflict_payload(opening, status="resolved", evidence=[action], previous=first)], base)
    assert context(base, issue=issue)["issues"][0]["status"] == "open"

    outcome = append_event("alice", "outcome", {
        "summary": "对方回应说我们已经谈开，并同意以后别拿这件事开玩笑",
        "action_id": action["record_id"],
    }, base, source_refs=source)
    assert outcome["data"]["issue_id"] == issue
    assert context(base, issue=issue)["issues"][0]["status"] == "open"
    closed = append_records("alice", [conflict_payload(opening, status="resolved", evidence=[outcome], previous=first)], base)[0]
    result = context(base, issue=issue, limit=1)
    assert result["issues"][0]["status"] == "resolved"
    assert result["matching_linked_records"] == 2
    assert result["records"] == [opening, action, outcome, closed]
    assert context(base, open_issues=True)["issues"] == []


def test_correction_hides_obsolete_issue_claim_and_reassessment_reuses_issue(base, source):
    opening = report(base, source, "过时的归属：对方公开开了我的玩笑")
    first = append_records("alice", [conflict_payload(opening)], base)[0]
    append_event("alice", "correction", {"summary": "重新核对归属"}, base, source_refs=source,
                 supersedes=[opening["record_id"]])
    result = context(base, open_issues=True)
    assert result["issues"] == [{"head_record_id": first["record_id"], "issue_id": issue_id(first), "status": "needs_review"}]
    assert result["records"] == []
    corrected = report(base, source, "原说法来自第三方；真正的争议是约会迟到")
    payload = conflict_payload(opening, previous=first)
    payload["data"]["supporting_ids"] = [corrected["record_id"]]
    second = append_records("alice", [payload], base)[0]
    assert issue_id(first) == issue_id(second)
    append_event("alice", "correction", {"summary": "这条议题判断已撤回"}, base, source_refs=source,
                 supersedes=[second["record_id"]])
    assert context(base, open_issues=True)["issues"] == []
    assert context(base, issue=issue_id(first))["issues"][0]["status"] == "withdrawn"


def test_corrected_issue_keeps_independently_confirmed_action_visible(base, source):
    opening = report(base, source, "待更正的事件归属")
    first = append_records("alice", [conflict_payload(opening)], base)[0]
    issue = issue_id(first)
    action = append_event("alice", "action_report", {
        "summary": "用户实际发过一条消息", "confirmed": True, "repair_schema": 1, "issue_id": issue,
    }, base, source_refs=source)
    append_event("alice", "correction", {"summary": "事件归属不正确"}, base,
                 source_refs=source, supersedes=[opening["record_id"]])
    result = context(base, issue=issue)
    assert result["issues"] == [{"head_record_id": first["record_id"], "issue_id": issue, "status": "needs_review"}]
    assert result["records"] == [action]


def boundary_payload(source, statement, key="contact:all", value="no_contact", previous=None):
    return {
        "kind": "preference", "source_refs": source,
        "data": {"repair_schema": 1, "key": key, "value": value, "summary": "对方明确的联系边界", "confirmed": True,
                 "supporting_ids": [statement["record_id"]]},
        "supersedes": [previous["record_id"]] if previous else [],
    }


def test_contact_scope_is_available_without_issue_and_replaced_by_explicit_target_statement(base, source):
    vague = report(base, source, "对方可能不想被联系")
    with pytest.raises(ValueError, match="explicit statement"):
        append_records("alice", [boundary_payload(source, vague)], base)
    old = report(base, source, "原话：请别再联系我", reported_role="target")
    first = append_records("alice", [boundary_payload(source, old)], base)[0]
    romance = report(base, source, "她明确说只接受朋友来往", reported_role="target")
    append_records("alice", [boundary_payload(source, romance, "contact:romance", "no_romance")], base)
    for i in range(25):
        report(base, source, f"无关材料 {i}")
    result = context(base, open_issues=True, limit=1)
    assert result["issues"] == []
    assert {item["value"] for item in result["contact_boundaries"]} == {"no_contact", "no_romance"}

    new = report(base, source, "她明确告诉我可以正常联系", reported_role="target")
    with pytest.raises(ValueError, match="Stale scoped revision"):
        append_records("alice", [boundary_payload(source, new, value="lifted")], base)
    with pytest.raises(ValueError, match="fresh statement"):
        append_records("alice", [boundary_payload(source, old, value="lifted", previous=first)], base)
    append_records("alice", [boundary_payload(source, new, value="lifted", previous=first)], base)
    active = {item["key"]: item["value"] for item in context(base, contact_boundaries=True)["contact_boundaries"]}
    assert active == {"contact:all": "lifted", "contact:romance": "no_romance"}


def test_contact_correction_hides_stale_boundary_value_and_quote(base, source):
    old = report(base, source, "过时引用：别联系我", reported_role="target")
    boundary = append_records("alice", [boundary_payload(source, old)], base)[0]
    append_event("alice", "correction", {"summary": "实际是群里别人说的话"}, base, source_refs=source,
                 supersedes=[old["record_id"]])
    result = context(base, issue="issue:missing")
    assert result["issues"] == []
    assert result["contact_boundaries"] == [
        {"key": "contact:all", "head_record_id": boundary["record_id"], "status": "needs_review"}
    ]
    assert result["records"] == []
    assert any(r["status"] == "invalidated" for r in get_recent_events("alice", base_dir=base, include_history=True))


def test_older_contact_permission_cannot_override_a_newer_refusal(base, source):
    def dated_statement(summary, day):
        return append_event("alice", "user_report", {"summary": summary, "reported_role": "target"}, base,
                            source_refs=source, occurred_at=f"2026-11-{day}T20:00:00+08:00")

    permission = dated_statement("当时她说可以联系", 20)
    old_head = append_records("alice", [boundary_payload(source, permission, value="lifted")], base)[0]
    refusal = dated_statement("她后来要求不要联系", 25)
    head = append_records("alice", [boundary_payload(source, refusal, previous=old_head)], base)[0]
    late_import = dated_statement("补录以前她说可以联系", 21)
    for old in (permission, late_import):
        with pytest.raises(ValueError, match="fresh statement"):
            append_records("alice", [boundary_payload(source, old, value="lifted", previous=head)], base)
    assert context(base, contact_boundaries=True)["contact_boundaries"][0]["value"] == "no_contact"


def test_preexisting_custom_fields_keep_their_old_meaning(base, source):
    for key in ("contact:frequency", "contact:all"):
        append_event("alice", "preference", {"summary": "个人联系偏好", "key": key, "value": "weekends"},
                     base, source_refs=source)
    append_event("alice", "assessment", {"summary": "旧自定义字段", "conflict": "模糊"}, base)
    assert context(base, open_issues=True)["issues"] == []
    assert context(base, contact_boundaries=True)["contact_boundaries"] == []
    statement = report(base, source, "她说别联系", reported_role="target")
    append_records("alice", [boundary_payload(source, statement)], base)
    assert context(base, contact_boundaries=True)["contact_boundaries"][0]["value"] == "no_contact"


def test_scoped_context_cli_returns_issue_and_contact_evidence(base, source):
    old = report(base, source, "她说先别联系", reported_role="target")
    append_records("alice", [boundary_payload(source, old, value="pause")], base)
    opening = report(base, source, "我们有一个具体误会")
    first = append_records("alice", [conflict_payload(opening)], base)[0]
    output = subprocess.run([sys.executable, "tools/memory.py", "context", "alice", "--issue", issue_id(first),
                             "--last", "1", "--base-dir", str(base)], capture_output=True, check=True, encoding="utf-8")
    data = json.loads(output.stdout)
    assert data["issues"][0]["status"] == "open"
    assert data["contact_boundaries"][0]["value"] == "pause"
