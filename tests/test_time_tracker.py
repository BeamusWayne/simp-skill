"""tests/test_time_tracker.py — time_tracker.py 的 pytest 测试套件"""
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from tools.time_tracker import (
    VALID_INTERACTION_TYPES,
    record_interaction,
    get_interactions,
    get_reply_times,
    get_interaction_frequency,
    analyze_timeline,
    analyze_reply_times,
    analyze_golden_hours,
)


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
    (d / "interactions.jsonl").touch()
    (d / "meta.json").write_text(
        json.dumps(
            {
                "slug": slug,
                "event_count": 0,
                "updated_at": "2026-01-01T00:00:00",
                "interaction_count": 0,
                "last_interaction": None,
                "consecutive_days": 0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return d


class TestRecordInteraction:
    def test_appends_chat_sent(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        ts = datetime(2026, 5, 15, 22, 30, 0)
        record_interaction(
            slug,
            "chat_sent",
            {"content_summary": "问她周末有没有空"},
            ts=ts,
            base_dir=base_dir,
        )
        lines = (crush_dir / "interactions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["type"] == "chat_sent"
        assert record["ts"] == "2026-05-15T22:30:00"
        assert record["data"]["hour"] == 22
        assert record["data"]["day_of_week"] == "fri"
        assert record["data"]["is_initiator"] is True

    def test_appends_chat_received_with_reply_delay(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        ts = datetime(2026, 5, 15, 22, 32, 0)
        record_interaction(
            slug,
            "chat_received",
            {"content_summary": "有空呀", "reply_delay_min": 2},
            ts=ts,
            base_dir=base_dir,
        )
        lines = (crush_dir / "interactions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["data"]["reply_delay_min"] == 2
        assert record["data"]["is_initiator"] is False

    def test_appends_meeting(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        ts = datetime(2026, 5, 17, 19, 0, 0)
        record_interaction(
            slug,
            "meeting",
            {"duration_min": 180, "activity": "咖啡+散步", "location": "外滩"},
            ts=ts,
            base_dir=base_dir,
        )
        lines = (crush_dir / "interactions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["type"] == "meeting"
        assert record["data"]["duration_min"] == 180

    def test_raises_on_unknown_type(self, base_dir: Path, slug: str) -> None:
        with pytest.raises(ValueError, match="未知互动类型"):
            record_interaction(slug, "unknown_type", {}, base_dir=base_dir)

    def test_raises_on_missing_slug(self, base_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            record_interaction("nonexistent", "chat_sent", {"content_summary": "hi"}, base_dir=base_dir)

    def test_updates_meta_json(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        ts = datetime(2026, 5, 15, 22, 30, 0)
        record_interaction(slug, "chat_sent", {"content_summary": "hi"}, ts=ts, base_dir=base_dir)
        meta = json.loads((crush_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["interaction_count"] == 1
        assert meta["last_interaction"] == "2026-05-15T22:30:00"

    def test_deduplicates_same_ts_and_type(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        ts = datetime(2026, 5, 15, 22, 30, 0)
        data = {"content_summary": "hi"}
        record_interaction(slug, "chat_sent", data, ts=ts, base_dir=base_dir)
        record_interaction(slug, "chat_sent", data, ts=ts, base_dir=base_dir)
        lines = (crush_dir / "interactions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_defaults_ts_to_now(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        record_interaction(slug, "chat_sent", {"content_summary": "hi"}, base_dir=base_dir)
        lines = (crush_dir / "interactions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["ts"].startswith("202")


class TestGetInteractions:
    def test_returns_all_by_default(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        for i in range(5):
            ts = datetime(2026, 5, 10 + i, 10, 0, 0)
            record_interaction(slug, "chat_sent", {"content_summary": f"msg {i}"}, ts=ts, base_dir=base_dir)
        result = get_interactions(slug, base_dir=base_dir)
        assert len(result) == 5

    def test_filters_by_type(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        ts1 = datetime(2026, 5, 10, 10, 0, 0)
        ts2 = datetime(2026, 5, 10, 10, 5, 0)
        record_interaction(slug, "chat_sent", {"content_summary": "hi"}, ts=ts1, base_dir=base_dir)
        record_interaction(slug, "meeting", {"duration_min": 60, "activity": "coffee"}, ts=ts2, base_dir=base_dir)
        result = get_interactions(slug, types=["meeting"], base_dir=base_dir)
        assert len(result) == 1
        assert result[0]["type"] == "meeting"

    def test_filters_by_days(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        old_ts = datetime(2026, 4, 1, 10, 0, 0)
        recent_ts = datetime(2026, 5, 18, 10, 0, 0)
        record_interaction(slug, "chat_sent", {"content_summary": "old"}, ts=old_ts, base_dir=base_dir)
        record_interaction(slug, "chat_sent", {"content_summary": "new"}, ts=recent_ts, base_dir=base_dir)
        result = get_interactions(slug, days=7, base_dir=base_dir)
        assert len(result) == 1
        assert result[0]["data"]["content_summary"] == "new"

    def test_returns_empty_for_no_file(self, base_dir: Path, slug: str) -> None:
        d = base_dir / slug
        d.mkdir(parents=True)
        (d / "interactions.jsonl").touch()
        result = get_interactions(slug, base_dir=base_dir)
        assert result == []


class TestGetReplyTimes:
    def test_returns_only_received_with_delay(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        ts1 = datetime(2026, 5, 10, 10, 0, 0)
        ts2 = datetime(2026, 5, 10, 10, 5, 0)
        ts3 = datetime(2026, 5, 10, 10, 10, 0)
        record_interaction(slug, "chat_sent", {"content_summary": "hi"}, ts=ts1, base_dir=base_dir)
        record_interaction(slug, "chat_received", {"content_summary": "hey", "reply_delay_min": 5}, ts=ts2, base_dir=base_dir)
        record_interaction(slug, "chat_received", {"content_summary": "no delay"}, ts=ts3, base_dir=base_dir)
        result = get_reply_times(slug, base_dir=base_dir)
        assert len(result) == 1
        assert result[0]["data"]["reply_delay_min"] == 5


class TestAnalyzeTimeline:
    def _seed_interactions(self, base_dir: Path, slug: str) -> None:
        now = datetime.now()
        for day_offset in range(7):
            day = now - timedelta(days=day_offset)
            ts = day.replace(hour=20, minute=0, second=0, microsecond=0)
            if day_offset in (3, 5):
                continue
            record_interaction(slug, "chat_sent", {"content_summary": f"msg d-{day_offset}"}, ts=ts, base_dir=base_dir)
            recv_ts = day.replace(hour=20, minute=10, second=0, microsecond=0)
            record_interaction(
                slug, "chat_received",
                {"content_summary": f"reply d-{day_offset}", "reply_delay_min": 10},
                ts=recv_ts, base_dir=base_dir,
            )

    def test_counts_total_interactions(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_interactions(base_dir, slug)
        result = analyze_timeline(slug, days=7, base_dir=base_dir)
        assert result["total"] == 10

    def test_consecutive_days(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_interactions(base_dir, slug)
        result = analyze_timeline(slug, days=7, base_dir=base_dir)
        assert result["current_streak"] >= 2

    def test_max_consecutive(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_interactions(base_dir, slug)
        result = analyze_timeline(slug, days=7, base_dir=base_dir)
        assert result["max_streak"] >= 3

    def test_initiator_ratio(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_interactions(base_dir, slug)
        result = analyze_timeline(slug, days=7, base_dir=base_dir)
        assert result["user_ratio"] == 50.0

    def test_active_days(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_interactions(base_dir, slug)
        result = analyze_timeline(slug, days=7, base_dir=base_dir)
        assert result["active_days"] == 5
        assert result["total_days"] == 7


class TestAnalyzeReplyTimes:
    def _seed_replies(self, base_dir: Path, slug: str) -> None:
        delays = [2, 3, 5, 8, 12, 15, 25, 45, 90, 180, 300, 600, 1200]
        for i, delay in enumerate(delays):
            ts = datetime(2026, 5, 18 - i, 20, 0, 0)
            record_interaction(
                slug, "chat_received",
                {"content_summary": f"reply {i}", "reply_delay_min": delay},
                ts=ts, base_dir=base_dir,
            )

    def test_average_and_median(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_replies(base_dir, slug)
        result = analyze_reply_times(slug, days=30, base_dir=base_dir)
        assert result["average_min"] > 0
        assert result["median_min"] > 0

    def test_distribution_buckets(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_replies(base_dir, slug)
        result = analyze_reply_times(slug, days=30, base_dir=base_dir)
        dist = result["distribution"]
        assert dist["lte_5min"] > 0
        assert dist["gt_4h"] > 0
        total_pct = sum(dist.values())
        assert abs(total_pct - 100.0) < 1.0

    def test_empty_data(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        result = analyze_reply_times(slug, days=30, base_dir=base_dir)
        assert result["average_min"] is None
        assert result["median_min"] is None


class TestAnalyzeGoldenHours:
    def _seed_hourly(self, base_dir: Path, slug: str) -> None:
        for _ in range(8):
            ts = datetime(2026, 5, 15, 21, 30, 0)
            record_interaction(
                slug, "chat_received",
                {"content_summary": "night reply", "reply_delay_min": 5},
                ts=ts, base_dir=base_dir,
            )
        for _ in range(3):
            ts = datetime(2026, 5, 15, 12, 0, 0)
            record_interaction(
                slug, "chat_received",
                {"content_summary": "lunch reply", "reply_delay_min": 10},
                ts=ts, base_dir=base_dir,
            )
        ts = datetime(2026, 5, 15, 8, 0, 0)
        record_interaction(
            slug, "chat_received",
            {"content_summary": "morning reply", "reply_delay_min": 15},
            ts=ts, base_dir=base_dir,
        )

    def test_peak_hour(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_hourly(base_dir, slug)
        result = analyze_golden_hours(slug, days=30, base_dir=base_dir)
        assert result["peak_hour"] == 21

    def test_top_windows(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        self._seed_hourly(base_dir, slug)
        result = analyze_golden_hours(slug, days=30, base_dir=base_dir)
        assert len(result["top_windows"]) >= 1
        assert result["top_windows"][0]["hour"] == 21

    def test_empty_data(self, crush_dir: Path, base_dir: Path, slug: str) -> None:
        result = analyze_golden_hours(slug, days=30, base_dir=base_dir)
        assert result["peak_hour"] is None
        assert result["top_windows"] == []
