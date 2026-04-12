"""
tests/test_skill_writer.py
pytest 测试套件 · skill_writer.py
"""

import json
import logging
import pytest
from pathlib import Path

from tools.skill_writer import (
    backup_crush,
    init_crush,
    list_crushes,
    list_versions,
    rollback_crush,
    update_meta,
    SIGNAL_SCORE_MIN,
    SIGNAL_SCORE_MAX,
)


@pytest.fixture
def tmp_base(tmp_path: Path) -> Path:
    return tmp_path / "crushes"


# ---------------------------------------------------------------------------
# init_crush
# ---------------------------------------------------------------------------


class TestInitCrush:
    def test_creates_directory_structure(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        crush_dir = tmp_base / "xiaomei"
        assert crush_dir.is_dir()
        assert (crush_dir / "profile.md").exists()
        assert (crush_dir / "state.md").exists()
        assert (crush_dir / "events.jsonl").exists()
        assert (crush_dir / "strategy.md").exists()
        assert (crush_dir / "meta.json").exists()
        assert (crush_dir / "memories" / "chats").is_dir()
        assert (crush_dir / "memories" / "social").is_dir()
        assert (crush_dir / "memories" / "photos").is_dir()
        assert (crush_dir / "versions").is_dir()
        assert (crush_dir / "snapshots").is_dir()

    def test_meta_json_defaults(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["slug"] == "xiaomei"
        assert meta["version"] == "v1"
        assert meta["mode"] == "hybrid"
        assert meta["signal_score"] is None
        assert meta["current_stage"] == "未知"
        assert meta["nickname"] == "[待填写]"
        assert meta["event_count"] == 0
        assert meta["last_snapshot"] is None

    def test_profile_md_has_yaml_frontmatter(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        content = (tmp_base / "xiaomei" / "profile.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "slug: xiaomei" in content
        assert "personality_type:" in content
        assert "created_at:" in content

    def test_state_md_has_yaml_frontmatter(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        content = (tmp_base / "xiaomei" / "state.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "current_stage:" in content
        assert "signal_score:" in content
        assert "milestones_done:" in content

    def test_events_jsonl_is_empty_on_init(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        content = (tmp_base / "xiaomei" / "events.jsonl").read_text(encoding="utf-8")
        assert content == ""

    def test_does_not_overwrite_existing_profile(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        profile_path = tmp_base / "xiaomei" / "profile.md"
        profile_path.write_text("custom content", encoding="utf-8")
        init_crush("xiaomei", tmp_base)
        assert profile_path.read_text(encoding="utf-8") == "custom content"

    def test_does_not_overwrite_existing_state(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        state_path = tmp_base / "xiaomei" / "state.md"
        state_path.write_text("custom state", encoding="utf-8")
        init_crush("xiaomei", tmp_base)
        assert state_path.read_text(encoding="utf-8") == "custom state"

    def test_does_not_overwrite_existing_events(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        events_path = tmp_base / "xiaomei" / "events.jsonl"
        events_path.write_text('{"type":"test"}\n', encoding="utf-8")
        init_crush("xiaomei", tmp_base)
        assert events_path.read_text(encoding="utf-8") == '{"type":"test"}\n'

    def test_idempotent_on_repeated_calls(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        init_crush("xiaomei", tmp_base)
        assert (tmp_base / "xiaomei" / "meta.json").exists()


# ---------------------------------------------------------------------------
# list_crushes
# ---------------------------------------------------------------------------


class TestListCrushes:
    def test_nonexistent_base_dir(self, tmp_base: Path, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            list_crushes(tmp_base / "nonexistent")
        assert "还没有任何心上人档案" in caplog.text

    def test_empty_base_dir(self, tmp_base: Path, caplog: pytest.LogCaptureFixture) -> None:
        tmp_base.mkdir()
        with caplog.at_level(logging.INFO):
            list_crushes(tmp_base)
        assert "还没有任何心上人档案" in caplog.text

    def test_lists_existing_crushes(self, tmp_base: Path, caplog: pytest.LogCaptureFixture) -> None:
        init_crush("xiaomei", tmp_base)
        with caplog.at_level(logging.INFO):
            list_crushes(tmp_base)
        assert "xiaomei" in caplog.text

    def test_shows_score_as_not_evaluated_when_none(
        self, tmp_base: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        init_crush("xiaomei", tmp_base)
        with caplog.at_level(logging.INFO):
            list_crushes(tmp_base)
        assert "未评估" in caplog.text

    def test_shows_score_when_set(self, tmp_base: Path, caplog: pytest.LogCaptureFixture) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, signal_score=18)
        with caplog.at_level(logging.INFO):
            list_crushes(tmp_base)
        assert "18/25" in caplog.text


# ---------------------------------------------------------------------------
# backup_crush
# ---------------------------------------------------------------------------


class TestBackupCrush:
    def test_backup_creates_version_directory(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        version_name = backup_crush("xiaomei", tmp_base)
        assert version_name != ""
        assert (tmp_base / "xiaomei" / "versions" / version_name).is_dir()

    def test_backup_copies_core_files(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        version_name = backup_crush("xiaomei", tmp_base)
        version_dir = tmp_base / "xiaomei" / "versions" / version_name
        assert (version_dir / "profile.md").exists()
        assert (version_dir / "state.md").exists()
        assert (version_dir / "strategy.md").exists()
        assert (version_dir / "meta.json").exists()

    def test_backup_increments_version_number(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        backup_crush("xiaomei", tmp_base)
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["version"] == "v2"

    def test_backup_nonexistent_slug_returns_empty(self, tmp_base: Path) -> None:
        result = backup_crush("nobody", tmp_base)
        assert result == ""


# ---------------------------------------------------------------------------
# rollback_crush
# ---------------------------------------------------------------------------


class TestRollbackCrush:
    def test_rollback_restores_profile(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        profile_path = tmp_base / "xiaomei" / "profile.md"
        original_content = profile_path.read_text(encoding="utf-8")

        backup_crush("xiaomei", tmp_base)
        profile_path.write_text("modified content", encoding="utf-8")

        rollback_crush("xiaomei", "v1", tmp_base)
        assert profile_path.read_text(encoding="utf-8") == original_content

    def test_rollback_creates_backup_before_restoring(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        backup_crush("xiaomei", tmp_base)
        rollback_crush("xiaomei", "v1", tmp_base)
        versions_dir = tmp_base / "xiaomei" / "versions"
        assert len(list(versions_dir.iterdir())) == 2

    def test_rollback_nonexistent_version(
        self, tmp_base: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        init_crush("xiaomei", tmp_base)
        backup_crush("xiaomei", tmp_base)
        with caplog.at_level(logging.ERROR):
            rollback_crush("xiaomei", "v99", tmp_base)
        assert "不存在" in caplog.text

    def test_rollback_no_version_history(
        self, tmp_base: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        init_crush("xiaomei", tmp_base)
        with caplog.at_level(logging.ERROR):
            rollback_crush("xiaomei", "v1", tmp_base)
        assert "没有找到版本历史" in caplog.text


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


class TestListVersions:
    def test_no_versions(self, tmp_base: Path, caplog: pytest.LogCaptureFixture) -> None:
        init_crush("xiaomei", tmp_base)
        with caplog.at_level(logging.INFO):
            list_versions("xiaomei", tmp_base)
        assert "没有版本历史" in caplog.text

    def test_lists_existing_versions(self, tmp_base: Path, caplog: pytest.LogCaptureFixture) -> None:
        init_crush("xiaomei", tmp_base)
        backup_crush("xiaomei", tmp_base)
        with caplog.at_level(logging.INFO):
            list_versions("xiaomei", tmp_base)
        assert "v1_" in caplog.text


# ---------------------------------------------------------------------------
# update_meta
# ---------------------------------------------------------------------------


class TestUpdateMeta:
    def test_updates_stage(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, current_stage="暧昧期")
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["current_stage"] == "暧昧期"

    def test_updates_mode(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, mode="sweet")
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["mode"] == "sweet"

    def test_valid_score_is_saved(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, signal_score=18)
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["signal_score"] == 18

    def test_zero_score_is_saved(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, signal_score=0)
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["signal_score"] == 0

    def test_negative_score_within_range_is_saved(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, signal_score=-5)
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["signal_score"] == -5

    def test_score_above_max_is_rejected(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, signal_score=SIGNAL_SCORE_MAX + 1)
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["signal_score"] is None

    def test_score_below_min_is_rejected(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, signal_score=SIGNAL_SCORE_MIN - 1)
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["signal_score"] is None

    def test_nonexistent_slug_is_noop(
        self, tmp_base: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.ERROR):
            update_meta("nobody", tmp_base, current_stage="暧昧期")
        assert "不存在" in caplog.text

    def test_does_not_lose_existing_fields(self, tmp_base: Path) -> None:
        init_crush("xiaomei", tmp_base)
        update_meta("xiaomei", tmp_base, current_stage="升温期")
        update_meta("xiaomei", tmp_base, signal_score=12)
        meta = json.loads((tmp_base / "xiaomei" / "meta.json").read_text(encoding="utf-8"))
        assert meta["current_stage"] == "升温期"
        assert meta["signal_score"] == 12
        assert meta["slug"] == "xiaomei"
