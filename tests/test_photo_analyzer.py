"""
tests/test_photo_analyzer.py
pytest 测试套件 · photo_analyzer.py
"""

import math
import pytest
from datetime import datetime
from pathlib import Path

from tools.photo_analyzer import (
    get_datetime,
    _dms_to_decimal,
    get_gps,
    get_make_model,
    detect_meetups,
    _gps_distance_km,
)

# PIL may not be installed in test env; skip GPS tests that need GPSTAGS
try:
    from PIL.ExifTags import GPSTAGS
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


# ─────────────────────────────────────────────
# 纯函数
# ─────────────────────────────────────────────

class TestDmsToDecimal:
    def test_positive_north_east(self) -> None:
        result = _dms_to_decimal((40, 30, 15), "N")
        assert 40.5 < result < 41

    def test_positive_south_west(self) -> None:
        result = _dms_to_decimal((40, 30, 15), "S")
        assert result < 0

    def test_west_negative(self) -> None:
        result = _dms_to_decimal((10, 0, 0), "W")
        assert result < 0

    def test_invalid_input_returns_zero(self) -> None:
        result = _dms_to_decimal(("bad", None, 0), "N")
        assert result == 0.0

    def test_rounds_to_6_decimals(self) -> None:
        result = _dms_to_decimal((40, 30, 15.123456), "N")
        decimal_part = str(result).split(".")[-1]
        assert len(decimal_part) <= 6


class TestGpsDistanceKm:
    def test_same_point_zero(self) -> None:
        a = {"lat": 31.23, "lon": 121.47}
        assert _gps_distance_km(a, a) == 0.0

    def test_known_distance(self) -> None:
        # Shanghai to Hangzhou ~160km
        sh = {"lat": 31.2304, "lon": 121.4737}
        hz = {"lat": 30.2741, "lon": 120.1551}
        dist = _gps_distance_km(sh, hz)
        assert 150 < dist < 170

    def test_symmetric(self) -> None:
        a = {"lat": 31.0, "lon": 121.0}
        b = {"lat": 32.0, "lon": 122.0}
        assert abs(_gps_distance_km(a, b) - _gps_distance_km(b, a)) < 0.001


class TestGetDatetime:
    def test_date_time_original(self) -> None:
        # 注意：EXIF 日期格式是 YYYY:MM:DD HH:MM:SS（用冒号分隔）
        exif = {"DateTimeOriginal": "2024:03:15 14:30:00"}
        result = get_datetime(exif)
        assert result == datetime(2024, 3, 15, 14, 30, 0)

    def test_date_time_fallback(self) -> None:
        # DateTime 格式不同，strptime 会失败，函数应该 fallback
        exif = {"DateTime": "2024-05-01 08:00:00"}
        result = get_datetime(exif)
        assert result is None  # wrong format, falls through

    def test_no_time_in_exif(self) -> None:
        assert get_datetime({}) is None
        assert get_datetime({"Make": "Canon"}) is None

    def test_invalid_format_falls_through(self) -> None:
        exif = {"DateTimeOriginal": "not a date"}
        assert get_datetime(exif) is None


class TestGetGps:
    @pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not installed")
    def test_full_gps_data(self) -> None:
        gps_raw = {
            1: "N",
            2: (31, 12, 36),
            3: "E",
            4: (121, 30, 0),
        }
        exif = {"GPSInfo": gps_raw}
        result = get_gps(exif)
        assert result is not None
        assert 30 < result["lat"] < 32
        assert 121 < result["lon"] < 122

    @pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not installed")
    def test_no_gps_info(self) -> None:
        assert get_gps({}) is None

    @pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not installed")
    def test_only_latitude(self) -> None:
        exif = {"GPSInfo": {1: "N", 2: (31, 12, 36)}}
        assert get_gps(exif) is None  # needs both lat and lon


class TestGetMakeModel:
    def test_both_present(self) -> None:
        exif = {"Make": "Apple", "Model": "iPhone 15"}
        assert get_make_model(exif) == "Apple iPhone 15"

    def test_model_only(self) -> None:
        exif = {"Model": "Canon EOS R5"}
        assert get_make_model(exif) == "Canon EOS R5"

    def test_make_only(self) -> None:
        exif = {"Make": "Samsung"}
        assert get_make_model(exif) == "Samsung"

    def test_empty_exif(self) -> None:
        assert get_make_model({}) == ""

    def test_whitespace_stripped(self) -> None:
        exif = {"Make": "  Sony  ", "Model": "  α7  "}
        assert "  " not in get_make_model(exif)


# ─────────────────────────────────────────────
# detect_meetups · 核心逻辑
# ─────────────────────────────────────────────

def photo(datetime_str: str, lat: float = None, lon: float = None) -> dict:
    dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
    p = {"datetime": dt, "gps": None}
    if lat is not None and lon is not None:
        p["gps"] = {"lat": lat, "lon": lon}
    return p


class TestDetectMeetups:
    def test_empty_list(self) -> None:
        assert detect_meetups([]) == []

    def test_single_photo(self) -> None:
        assert detect_meetups([photo("2024-01-01 10:00")]) == []

    def test_two_photos_same_time_and_place(self) -> None:
        photos = [
            photo("2024-01-01 10:00", 31.23, 121.47),
            photo("2024-01-01 10:30", 31.23, 121.47),
        ]
        meetups = detect_meetups(photos)
        assert len(meetups) == 1
        assert meetups[0]["photo_count"] == 2

    def test_different_times_no_meetup(self) -> None:
        photos = [
            photo("2024-01-01 10:00", 31.23, 121.47),
            photo("2024-01-01 16:00", 31.23, 121.47),
        ]
        meetups = detect_meetups(photos, time_gap_hours=4.0)
        assert meetups == []

    def test_far_apart_location_no_meetup(self) -> None:
        photos = [
            photo("2024-01-01 10:00", 31.23, 121.47),
            photo("2024-01-01 10:30", 29.55, 121.72),  # ~190km away
        ]
        meetups = detect_meetups(photos, location_radius_km=2.0)
        assert meetups == []

    def test_no_gps_uses_time_only(self) -> None:
        photos = [
            photo("2024-01-01 10:00"),
            photo("2024-01-01 10:30"),
        ]
        meetups = detect_meetups(photos, time_gap_hours=4.0)
        assert len(meetups) == 1

    def test_custom_time_gap(self) -> None:
        photos = [
            photo("2024-01-01 10:00"),
            photo("2024-01-01 14:00"),
        ]
        assert len(detect_meetups(photos, time_gap_hours=4.0)) == 1
        assert len(detect_meetups(photos, time_gap_hours=2.0)) == 0

    def test_multiple_meetups(self) -> None:
        photos = [
            photo("2024-01-01 10:00"),
            photo("2024-01-01 10:30"),
            photo("2024-01-03 14:00"),
            photo("2024-01-03 15:00"),
        ]
        meetups = detect_meetups(photos)
        assert len(meetups) == 2

    def test_photos_without_datetime_ignored(self) -> None:
        photos = [
            photo("2024-01-01 10:00"),
            {"datetime": None},
            photo("2024-01-01 10:30"),
        ]
        meetups = detect_meetups(photos)
        assert len(meetups) == 1

    def test_meetup_has_required_fields(self) -> None:
        photos = [
            photo("2024-01-01 10:00", 31.23, 121.47),
            photo("2024-01-01 11:00", 31.23, 121.47),
        ]
        m = detect_meetups(photos)[0]
        assert "date" in m
        assert "start" in m
        assert "end" in m
        assert "duration_min" in m
        assert "photo_count" in m
        assert m["photo_count"] == 2

    def test_meetup_sorted_by_date(self) -> None:
        photos = [
            photo("2024-02-01 10:00"),
            photo("2024-02-01 11:00"),
            photo("2024-01-01 10:00"),
            photo("2024-01-01 11:00"),
        ]
        meetups = detect_meetups(photos)
        assert meetups[0]["date"].startswith("2024-01-01")


# ─────────────────────────────────────────────
# scan_photos · 目录扫描
# ─────────────────────────────────────────────

class TestScanPhotos:
    def test_nonexistent_dir(self) -> None:
        from tools.photo_analyzer import scan_photos
        result = scan_photos("/no/such/dir")
        assert result == []


# ─────────────────────────────────────────────
# generate_report · 报告生成
# ─────────────────────────────────────────────

class TestGenerateReport:
    def test_no_pillow_returns_warning(self) -> None:
        from unittest.mock import patch
        from tools.photo_analyzer import generate_report, PIL_AVAILABLE
        with patch("tools.photo_analyzer.PIL_AVAILABLE", False):
            result = generate_report("/any/path", "小美")
            assert "Pillow" in result or "⚠️" in result

    def test_empty_directory_returns_no_photos_message(self, tmp_path: Path) -> None:
        from unittest.mock import patch
        from tools.photo_analyzer import generate_report
        with patch("tools.photo_analyzer.PIL_AVAILABLE", True):
            with patch("tools.photo_analyzer.scan_photos", return_value=[]):
                result = generate_report(str(tmp_path), "小美")
                assert "照片元数据分析报告" in result
                assert "未找到任何照片" in result

    def test_output_path_writes_file(self, tmp_path: Path) -> None:
        from unittest.mock import patch
        from tools.photo_analyzer import generate_report
        out = tmp_path / "report.md"
        with patch("tools.photo_analyzer.PIL_AVAILABLE", True):
            with patch("tools.photo_analyzer.scan_photos", return_value=[]):
                generate_report(str(tmp_path), "小美", str(out))
                assert out.exists()


def test_cluster_duration_does_not_wrap_after_one_day():
    from tools.photo_analyzer import cluster_photo_sessions
    photos=[photo('2024-01-01 10:00'),photo('2024-01-02 12:00')]
    assert cluster_photo_sessions(photos,time_gap_hours=30)[0]['duration_min']==1560
