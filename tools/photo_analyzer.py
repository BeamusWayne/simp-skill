#!/usr/bin/env python3
"""
simp-skill · Photo Analyzer
分析照片的 EXIF 元数据，提取拍摄时间线和地点信息，
并按时间与已知地点整理拍摄聚类；不推断见面或恋爱意愿。

依赖：pip install Pillow

支持格式：jpg / jpeg / png / heic / heif

用法：
  python3 photo_analyzer.py --dir crushes/xiaomei/memories/photos
  python3 photo_analyzer.py --dir ./photos --target 小美 --output report.md
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.contracts import file_digest

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}


# ─────────────────────────────────────────────
# EXIF 提取
# ─────────────────────────────────────────────

def get_exif_data(filepath: str) -> dict:
    """提取照片的 EXIF 元数据"""
    if not PIL_AVAILABLE:
        return {}
    try:
        with Image.open(filepath) as img:
            raw_exif = img._getexif()
        if not raw_exif:
            return {}

        exif = {}
        for tag_id, value in raw_exif.items():
            tag = TAGS.get(tag_id, tag_id)
            exif[tag] = value
        return exif
    except Exception:
        return {}


def get_datetime(exif: dict) -> Optional[datetime]:
    """从 EXIF 提取拍摄时间"""
    for field in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
        raw = exif.get(field)
        if raw:
            try:
                return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
            except ValueError:
                continue
    return None


def _dms_to_decimal(dms, ref: str) -> float:
    """将度分秒坐标转为十进制"""
    try:
        d = float(dms[0])
        m = float(dms[1])
        s = float(dms[2])
        decimal = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return 0.0


def get_gps(exif: dict) -> Optional[dict]:
    """从 EXIF 提取 GPS 坐标"""
    gps_raw = exif.get("GPSInfo")
    if not gps_raw:
        return None

    gps = {}
    for key, val in gps_raw.items():
        tag = GPSTAGS.get(key, key)
        gps[tag] = val

    lat_dms = gps.get("GPSLatitude")
    lat_ref = gps.get("GPSLatitudeRef", "N")
    lon_dms = gps.get("GPSLongitude")
    lon_ref = gps.get("GPSLongitudeRef", "E")

    if lat_dms and lon_dms:
        return {
            "lat": _dms_to_decimal(lat_dms, lat_ref),
            "lon": _dms_to_decimal(lon_dms, lon_ref),
        }
    return None


def get_make_model(exif: dict) -> str:
    """提取设备型号；型号不能确认拍摄者。"""
    make  = str(exif.get("Make",  "")).strip()
    model = str(exif.get("Model", "")).strip()
    if make and model:
        return f"{make} {model}"
    return model or make or ""


# ─────────────────────────────────────────────
# 扫描与分析
# ─────────────────────────────────────────────

def scan_photos(directory: str) -> list:
    """扫描目录下所有照片并提取元数据"""
    base = Path(directory)
    if not base.exists():
        print(f"⚠️  目录不存在：{directory}")
        return []

    photos = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in PHOTO_EXTS:
            continue

        exif = get_exif_data(str(path))
        dt   = get_datetime(exif)
        gps  = get_gps(exif)
        cam  = get_make_model(exif)

        photos.append({
            "path": str(path),
            "name": path.name,
            "rel":  str(path.relative_to(base)),
            "datetime": dt,
            "gps": gps,
            "camera": cam,
            "size_kb": round(path.stat().st_size / 1024, 1),
        })

    # 按时间排序（无时间的排后面）
    photos.sort(key=lambda p: (p["datetime"] is None, p["datetime"] or datetime.min))
    return photos


# ─────────────────────────────────────────────
# 约会检测（核心创新功能）
# ─────────────────────────────────────────────

def _gps_distance_km(a: dict, b: dict) -> float:
    """粗略计算两个 GPS 坐标之间的距离（km），使用等经纬度近似"""
    import math
    lat1, lon1 = math.radians(a["lat"]), math.radians(a["lon"])
    lat2, lon2 = math.radians(b["lat"]), math.radians(b["lon"])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a_ = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 6371 * 2 * math.asin(math.sqrt(a_))


def cluster_photo_sessions(photos: list, time_gap_hours: float = 4.0, location_radius_km: float = 2.0) -> list:
    """Group nearby recorded times/locations; shared presence is not established."""
    if time_gap_hours < 0 or location_radius_km < 0:
        raise ValueError("Clustering windows must be nonnegative")
    timed = [p for p in photos if p["datetime"] is not None]
    if len(timed) < 2:
        return []

    visited = set()
    meetups = []

    for i, photo in enumerate(timed):
        if i in visited:
            continue

        cluster = [photo]
        visited.add(i)

        for j, other in enumerate(timed):
            if j in visited or j == i:
                continue

            # 时间差检测
            delta = abs((other["datetime"] - photo["datetime"]).total_seconds()) / 3600
            if delta > time_gap_hours:
                continue

            # GPS 检测（如果双方都有 GPS）
            if photo["gps"] and other["gps"]:
                dist = _gps_distance_km(photo["gps"], other["gps"])
                if dist > location_radius_km:
                    continue

            cluster.append(other)
            visited.add(j)

        if len(cluster) >= 2:
            cluster.sort(key=lambda p: p["datetime"])
            start = cluster[0]["datetime"]
            end   = cluster[-1]["datetime"]
            duration = int((end - start).total_seconds() // 60)

            # 有 GPS 的取第一张的坐标
            gps_ref = next((p["gps"] for p in cluster if p["gps"]), None)

            meetups.append({
                "date": start.strftime("%Y-%m-%d"),
                "start": start.strftime("%H:%M"),
                "end":   end.strftime("%H:%M"),
                "duration_min": duration,
                "photo_count": len(cluster),
                "gps": gps_ref,
                "photos": cluster,
            })

    meetups.sort(key=lambda m: m["date"])
    return meetups


# ─────────────────────────────────────────────
# 报告生成
# ─────────────────────────────────────────────

# Backward-compatible callable name; its result is only photo clusters.
detect_meetups = cluster_photo_sessions


def generate_report(directory: str, target_name: str, output_path=None, *, time_gap_hours=4.0, location_radius_km=2.0):
    if output_path and Path(output_path).exists() and Path(output_path).suffix.lower() in PHOTO_EXTS:
        raise ValueError("output must not overwrite a photo")
    if not PIL_AVAILABLE:
        report = "未安装 Pillow，无法读取 EXIF 元数据。安装后重新运行。"
    else:
        photos = scan_photos(directory)
        lines = ["# 照片元数据分析报告", f"对象标签：{target_name}",
                 "EXIF 可能缺失或被编辑；未提供时区的时间按原样展示。设备型号不能确认拍摄者。",
                 "时间和地点相近的照片不证明双方见面，也不证明恋爱意愿。缺少 GPS 时仅按时间聚类。", ""]
        if not photos:
            lines.append("未找到任何照片。")
        for photo in photos:
            path = Path(photo["path"]).resolve()
            if output_path and Path(output_path).resolve() == path:
                raise ValueError("output must not overwrite a photo")
            record = {**photo, "datetime": photo["datetime"].isoformat() if photo["datetime"] else None,
                      "time_status": "timezone_unknown" if photo["datetime"] else "missing",
                      "source_refs": [{"kind": "file", "path": str(path), "sha256": file_digest(path), "locator": "EXIF"}]}
            lines.extend(["```json", json.dumps(record, ensure_ascii=False, indent=2), "```"])
        clusters = cluster_photo_sessions(photos, time_gap_hours, location_radius_km)
        lines.append("## 拍摄聚类")
        lines.append(f"参数：时间窗口 {time_gap_hours} 小时，已知位置半径 {location_radius_km} 公里。")
        for cluster in clusters:
            lines.append(f"- {cluster['date']} {cluster['start']}–{cluster['end']}：{cluster['photo_count']} 张照片，跨度 {cluster['duration_min']} 分钟。")
        report = "\n".join(lines)
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--target", default="心上人")
    parser.add_argument("--output", "-o")
    parser.add_argument("--gap", type=float, default=4.0, help="拍摄聚类时间窗口（小时）")
    parser.add_argument("--radius", type=float, default=2.0, help="已知位置半径（公里）")
    args = parser.parse_args()
    try:
        report = generate_report(args.dir, args.target, args.output, time_gap_hours=args.gap, location_radius_km=args.radius)
        if not args.output:
            print(report)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
