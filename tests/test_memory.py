"""tests/test_memory.py — memory.py 的 pytest 测试套件"""
import json
import pytest
from datetime import date
from pathlib import Path

from tools.memory import (
    _parse_frontmatter,
    _parse_body_sections,
    _render_frontmatter,
    append_event,
    get_recent_events,
    load_context,
    rebuild_state_from_events,
    take_snapshot,
    update_state,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    return tmp_path / "crushes"


@pytest.fixture
def slug() -> str:
    return "testcrush"


@pytest.fixture
def crush_dir(base_dir: Path, slug: str) -> Path:
    d = base_dir / slug
    d.mkdir(parents=True)
    (d / "events.jsonl").touch()
    (d / "meta.json").write_text(
        json.dumps({"slug": slug, "event_count": 0, "updated_at": "2026-01-01T00:00:00"}),
        encoding="utf-8",
    )
    (d / "profile.md").write_text(
        "---\nnickname: 测试\nslug: testcrush\n---\n\n## 性格画像\n\n测试画像\n",
        encoding="utf-8",
    )
    (d / "state.md").write_text(
        "---\ncurrent_stage: 破冰期\nsignal_score: null\nscore_trend: stable\n---\n\n"
        "## 当前状态（一句话）\n\n初始状态\n",
        encoding="utf-8",
    )
    (d / "strategy.md").write_text("# 策略\n\n测试策略\n", encoding="utf-8")
    (d / "snapshots").mkdir()
    return d


# ─── _parse_frontmatter ────────────────────────────────────────────────────────


def test_parse_frontmatter_basic() -> None:
    content = '---\nname: 小美\nage: 22\nscore: null\n---\n\n正文'
    fm, body = _parse_frontmatter(content)
    assert fm["name"] == "小美"
    assert fm["age"] == 22
    assert fm["score"] is None
    assert "正文" in body


def test_parse_frontmatter_quoted_strings() -> None:
    content = '---\nnickname: "测试用户"\n---\n\n正文'
    fm, _ = _parse_frontmatter(content)
    assert fm["nickname"] == "测试用户"


def test_parse_frontmatter_no_frontmatter() -> None:
    content = "只是正文，没有 frontmatter"
    fm, body = _parse_frontmatter(content)
    assert fm == {}
    assert body == content


# ─── _render_frontmatter ──────────────────────────────────────────────────────


def test_render_frontmatter_roundtrip() -> None:
    original = '---\nname: 小美\nage: 22\nscore: null\n---\n\n正文'
    fm, body = _parse_frontmatter(original)
    rendered = _render_frontmatter(fm, body)
    fm2, body2 = _parse_frontmatter(rendered)
    assert fm2["name"] == "小美"
    assert fm2["age"] == 22
    assert fm2["score"] is None
    assert "正文" in body2


def test_render_frontmatter_none_value() -> None:
    result = _render_frontmatter({"key": None}, "\n正文")
    assert "key: null" in result


# ─── _parse_body_sections ─────────────────────────────────────────────────────


def test_parse_body_sections_basic() -> None:
    body = "\n## 第一节\n\n内容一\n\n## 第二节\n\n内容二\n"
    sections = _parse_body_sections(body)
    assert sections["## 第一节"] == "内容一"
    assert sections["## 第二节"] == "内容二"


# ─── append_event ─────────────────────────────────────────────────────────────


def test_append_event_writes_jsonl(crush_dir: Path, base_dir: Path, slug: str) -> None:
    append_event(slug, "profile_created", {"nickname": "小美"}, base_dir)
    lines = (crush_dir / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["type"] == "profile_created"
    assert event["data"]["nickname"] == "小美"
    assert event["slug"] == slug
    assert event["v"] == 1


def test_append_event_increments_event_count(crush_dir: Path, base_dir: Path, slug: str) -> None:
    append_event(slug, "signal_recorded", {"direction": "green", "content": "秒回"}, base_dir)
    meta = json.loads((crush_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["event_count"] == 1


def test_append_event_multiple_increments(crush_dir: Path, base_dir: Path, slug: str) -> None:
    for _ in range(3):
        append_event(slug, "signal_recorded", {"direction": "green", "content": "x"}, base_dir)
    meta = json.loads((crush_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["event_count"] == 3


def test_append_event_invalid_type(crush_dir: Path, base_dir: Path, slug: str) -> None:
    with pytest.raises(ValueError, match="未知事件类型"):
        append_event(slug, "invalid_type", {}, base_dir)


def test_append_event_missing_slug(base_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        append_event("nonexistent", "profile_created", {}, base_dir)


# ─── get_recent_events ────────────────────────────────────────────────────────


def test_get_recent_events_returns_n(crush_dir: Path, base_dir: Path, slug: str) -> None:
    for i in range(7):
        append_event(slug, "signal_recorded", {"content": f"信号{i}", "direction": "green"}, base_dir)
    events = get_recent_events(slug, n=5, base_dir=base_dir)
    assert len(events) == 5
    assert events[-1]["data"]["content"] == "信号6"


def test_get_recent_events_filters_by_type(crush_dir: Path, base_dir: Path, slug: str) -> None:
    append_event(slug, "signal_recorded", {"direction": "green", "content": "好"}, base_dir)
    append_event(slug, "analysis_done", {"score": 15, "stage": "升温期", "summary": "ok"}, base_dir)
    events = get_recent_events(slug, n=10, event_types=["analysis_done"], base_dir=base_dir)
    assert len(events) == 1
    assert events[0]["type"] == "analysis_done"


def test_get_recent_events_empty_file(crush_dir: Path, base_dir: Path, slug: str) -> None:
    events = get_recent_events(slug, base_dir=base_dir)
    assert events == []


def test_get_recent_events_no_file(base_dir: Path) -> None:
    (base_dir / "ghost").mkdir(parents=True)
    events = get_recent_events("ghost", base_dir=base_dir)
    assert events == []


# ─── load_context ─────────────────────────────────────────────────────────────


def test_load_context_includes_profile_and_state(crush_dir: Path, base_dir: Path, slug: str) -> None:
    ctx = load_context(slug, base_dir=base_dir)
    assert "[档案]" in ctx
    assert "[状态]" in ctx
    assert "测试画像" in ctx
    assert "初始状态" in ctx


def test_load_context_with_strategy(crush_dir: Path, base_dir: Path, slug: str) -> None:
    ctx = load_context(slug, include_strategy=True, base_dir=base_dir)
    assert "[策略]" in ctx
    assert "测试策略" in ctx


def test_load_context_without_strategy(crush_dir: Path, base_dir: Path, slug: str) -> None:
    ctx = load_context(slug, include_strategy=False, base_dir=base_dir)
    assert "[策略]" not in ctx


# ─── update_state ─────────────────────────────────────────────────────────────


def test_update_state_merges_frontmatter(crush_dir: Path, base_dir: Path, slug: str) -> None:
    update_state(slug, {"signal_score": 17, "current_stage": "暧昧期"}, {}, base_dir)
    fm, _ = _parse_frontmatter((crush_dir / "state.md").read_text(encoding="utf-8"))
    assert fm["signal_score"] == 17
    assert fm["current_stage"] == "暧昧期"


def test_update_state_preserves_existing_fields(crush_dir: Path, base_dir: Path, slug: str) -> None:
    update_state(slug, {"signal_score": 10}, {}, base_dir)
    update_state(slug, {"current_stage": "升温期"}, {}, base_dir)
    fm, _ = _parse_frontmatter((crush_dir / "state.md").read_text(encoding="utf-8"))
    assert fm["signal_score"] == 10
    assert fm["current_stage"] == "升温期"


def test_update_state_merges_sections(crush_dir: Path, base_dir: Path, slug: str) -> None:
    update_state(slug, {}, {"## 当前状态（一句话）": "ta开始主动找我了"}, base_dir)
    content = (crush_dir / "state.md").read_text(encoding="utf-8")
    assert "ta开始主动找我了" in content


def test_update_state_syncs_meta_stage(crush_dir: Path, base_dir: Path, slug: str) -> None:
    update_state(slug, {"current_stage": "暧昧期"}, {}, base_dir)
    meta = json.loads((crush_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["current_stage"] == "暧昧期"


def test_update_state_syncs_meta_score(crush_dir: Path, base_dir: Path, slug: str) -> None:
    update_state(slug, {"signal_score": 18}, {}, base_dir)
    meta = json.loads((crush_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["signal_score"] == 18


def test_update_state_missing_slug(base_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        update_state("nonexistent", {}, {}, base_dir)


# ─── take_snapshot ────────────────────────────────────────────────────────────


def test_take_snapshot_creates_file(crush_dir: Path, base_dir: Path, slug: str) -> None:
    snap_path = take_snapshot(slug, base_dir)
    assert snap_path.exists()
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    assert snap["slug"] == slug
    assert snap["snapshot_date"] == date.today().isoformat()


def test_take_snapshot_includes_meta(crush_dir: Path, base_dir: Path, slug: str) -> None:
    snap_path = take_snapshot(slug, base_dir)
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    assert "meta" in snap
    assert snap["meta"]["slug"] == slug


def test_take_snapshot_updates_last_snapshot(crush_dir: Path, base_dir: Path, slug: str) -> None:
    take_snapshot(slug, base_dir)
    meta = json.loads((crush_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["last_snapshot"] == date.today().isoformat()


# ─── rebuild_state_from_events ────────────────────────────────────────────────


def test_rebuild_state_tracks_stage_changes(crush_dir: Path, base_dir: Path, slug: str) -> None:
    append_event(slug, "stage_changed", {"from": "破冰期", "to": "升温期"}, base_dir)
    append_event(slug, "stage_changed", {"from": "升温期", "to": "暧昧期"}, base_dir)
    state = rebuild_state_from_events(slug, base_dir)
    assert state["current_stage"] == "暧昧期"


def test_rebuild_state_tracks_scores_and_trend(crush_dir: Path, base_dir: Path, slug: str) -> None:
    append_event(slug, "analysis_done", {"score": 10, "stage": "升温期", "summary": "ok"}, base_dir)
    append_event(slug, "analysis_done", {"score": 15, "stage": "暧昧期", "summary": "好"}, base_dir)
    state = rebuild_state_from_events(slug, base_dir)
    assert state["signal_score"] == 15
    assert state["last_signal_score"] == 10
    assert state["score_trend"] == "up"


def test_rebuild_state_score_trend_down(crush_dir: Path, base_dir: Path, slug: str) -> None:
    append_event(slug, "analysis_done", {"score": 18, "stage": "暧昧期", "summary": "好"}, base_dir)
    append_event(slug, "analysis_done", {"score": 12, "stage": "升温期", "summary": "变冷"}, base_dir)
    state = rebuild_state_from_events(slug, base_dir)
    assert state["score_trend"] == "down"


def test_rebuild_state_empty_events(crush_dir: Path, base_dir: Path, slug: str) -> None:
    state = rebuild_state_from_events(slug, base_dir)
    assert state["current_stage"] == "未知"
    assert state["signal_score"] is None
