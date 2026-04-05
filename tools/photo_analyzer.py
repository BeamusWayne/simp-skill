#!/usr/bin/env python3
"""
simp-skill · Photo Analyzer
分析照片的 EXIF 元数据，提取拍摄时间线和地点信息，
并检测可能的约会/见面记录（同地点+同时段的照片聚类）。

依赖：pip install Pillow

支持格式：jpg / jpeg / png / heic / heif

用法：
  python3 photo_analyzer.py --dir crushes/xiaomei/memories/photos
  python3 photo_analyzer.py --dir ./photos --target 小美 --output report.md
"""

import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

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
        img = Image.open(filepath)
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
    """提取相机型号（可判断是谁拍的）"""
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


def detect_meetups(photos: list, time_gap_hours: float = 4.0, location_radius_km: float = 2.0) -> list:
    """
    检测可能的约会/见面记录：
    - 在同一时间段（time_gap_hours 以内）
    - 在同一地点附近（location_radius_km 以内）
    的照片聚类 = 可能的一次见面

    返回聚类列表，每个聚类代表一次可能的见面。
    """
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
            duration = (end - start).seconds // 60

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

def generate_report(directory: str, target_name: str, output_path: str = None) -> str:
    """生成完整的照片分析报告"""

    if not PIL_AVAILABLE:
        warn = (
            "⚠️  未安装 Pillow，无法读取 EXIF 元数据。\n"
            "请运行：pip install Pillow\n\n"
            "安装后重新运行本工具以获取完整分析。"
        )
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(warn, encoding="utf-8")
        return warn

    photos  = scan_photos(directory)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# 📷 照片元数据分析报告",
        f"",
        f"> 心上人：**{target_name}**  |  分析时间：{now_str}",
        f"> 来源目录：`{directory}`",
        f"",
        f"---",
        f"",
    ]

    if not photos:
        lines += [
            f"⚠️  未找到任何照片文件。",
            f"",
            f"请将照片（.jpg / .jpeg / .png / .heic）放入 `{directory}/` 后重新运行。",
        ]
        report = "\n".join(lines)
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(report, encoding="utf-8")
            print(f"✅ 报告已保存到 {output_path}")
        return report

    # 统计
    with_time = [p for p in photos if p["datetime"]]
    with_gps  = [p for p in photos if p["gps"]]

    lines += [
        f"## 📊 概览",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 照片总数 | {len(photos)} 张 |",
        f"| 包含拍摄时间 | {len(with_time)} 张 |",
        f"| 包含 GPS 位置 | {len(with_gps)} 张 |",
    ]

    if with_time:
        first = with_time[0]["datetime"]
        last  = with_time[-1]["datetime"]
        lines += [
            f"| 最早照片 | {first.strftime('%Y-%m-%d')} |",
            f"| 最新照片 | {last.strftime('%Y-%m-%d')} |",
            f"| 时间跨度 | {(last - first).days} 天 |",
        ]

    lines.append(f"")

    # ── 约会检测 ──────────────────────────────
    meetups = detect_meetups(photos)

    if meetups:
        lines += [
            f"---",
            f"",
            f"## 🗓️ 可能的见面记录（{len(meetups)} 次）",
            f"",
            f"> 以下是照片聚类检测到的时间+地点相近的拍摄记录，",
            f"> 可能代表你们曾经在一起的时刻。",
            f"",
        ]

        for i, meetup in enumerate(meetups, 1):
            dur_str = f"{meetup['duration_min']}分钟内" if meetup["duration_min"] > 0 else "同一时刻"
            gps_str = ""
            if meetup["gps"]:
                g = meetup["gps"]
                gps_str = f"  📍 坐标：{g['lat']}, {g['lon']}"

            lines += [
                f"### 第 {i} 次  {meetup['date']}",
                f"",
                f"- 时间段：{meetup['start']} ～ {meetup['end']}（{dur_str}）",
                f"- 照片数：{meetup['photo_count']} 张",
            ]
            if gps_str:
                lines.append(gps_str)

            lines.append(f"- 照片列表：")
            for p in meetup["photos"][:5]:
                t = p["datetime"].strftime("%H:%M") if p["datetime"] else "?"
                lines.append(f"  - `{p['rel']}`（{t}）")
            if len(meetup["photos"]) > 5:
                lines.append(f"  - ... 共 {len(meetup['photos'])} 张")
            lines.append(f"")

        lines += [
            f"**💡 使用建议**：",
            f"将这些照片路径告诉 Claude，让它描述照片内容，",
            f"从中挖掘可以用于情话的细节（场景、表情、你们的互动）。",
            f"",
        ]
    else:
        if with_time:
            lines += [
                f"---",
                f"",
                f"## 🗓️ 见面检测",
                f"",
                f"未检测到明确的时间/地点聚类，可能原因：",
                f"- 照片缺少 EXIF 时间信息（截图、社交媒体下载的图通常无 EXIF）",
                f"- 照片拍摄时间间隔超过 4 小时",
                f"- 缺少 GPS 数据导致位置无法比对",
                f"",
            ]

    # ── 完整时间线 ────────────────────────────
    if with_time:
        lines += [
            f"---",
            f"",
            f"## 📅 照片时间线",
            f"",
        ]

        # 按月分组
        monthly: dict = defaultdict(list)
        for p in with_time:
            key = p["datetime"].strftime("%Y年%m月")
            monthly[key].append(p)

        for month, month_photos in sorted(monthly.items()):
            lines.append(f"### {month}（{len(month_photos)} 张）")
            lines.append(f"")
            for p in month_photos:
                dt_str  = p["datetime"].strftime("%m-%d %H:%M")
                cam_str = f"  📱 {p['camera']}" if p["camera"] else ""
                gps_str = f"  📍 {p['gps']['lat']:.4f}, {p['gps']['lon']:.4f}" if p["gps"] else ""
                lines.append(f"- `{p['rel']}`  🕐 {dt_str}{cam_str}{gps_str}")
            lines.append(f"")

    # ── 无时间信息的照片 ─────────────────────
    no_time = [p for p in photos if not p["datetime"]]
    if no_time:
        lines += [
            f"---",
            f"",
            f"## ❓ 无时间信息的照片（{len(no_time)} 张）",
            f"",
            f"> 这些照片缺少 EXIF 时间数据（常见于截图、从社交媒体保存的图片）。",
            f"",
        ]
        for p in no_time:
            lines.append(f"- `{p['rel']}`（{p['size_kb']} KB）")
        lines.append(f"")

    lines += [
        f"---",
        f"",
        f"## 📌 后续建议",
        f"",
        f"1. **有见面记录**：把照片路径告诉 Claude，让它描述内容，",
        f"   提取可以用于情话的具体细节",
        f"2. **无 EXIF 数据**：说明照片可能来自网络/截图，",
        f"   这类照片更适合直接给 Claude 看内容",
        f"3. **结合聊天记录**：对比见面日期和聊天记录，",
        f"   看看见面当天和之后的消息有没有温度变化",
        f"",
        f"---",
        f"",
        f"*由 simp-skill · 追爱军师 生成*",
    ]

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"✅ 报告已保存到 {output_path}")

    return report


# ─────────────────────────────────────────────
# 主程序
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="simp-skill · 照片元数据分析器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 photo_analyzer.py --dir crushes/xiaomei/memories/photos
  python3 photo_analyzer.py --dir ./photos --target 小美 --output report.md
  python3 photo_analyzer.py --dir ./photos --gap 6 --radius 5
        """,
    )
    parser.add_argument("--dir",    required=True, help="照片目录路径")
    parser.add_argument("--target", default="心上人", help="心上人的名字")
    parser.add_argument("--output", "-o", help="输出报告路径（默认：打印到控制台）")
    parser.add_argument("--gap",    type=float, default=4.0,
                        help="约会检测时间窗口（小时，默认：4）")
    parser.add_argument("--radius", type=float, default=2.0,
                        help="约会检测地点半径（公里，默认：2）")

    args = parser.parse_args()

    print(f"💝 simp-skill · 照片分析器")
    print(f"📂 扫描目录：{args.dir}")
    print(f"🎯 心上人：{args.target}")
    if not PIL_AVAILABLE:
        print(f"⚠️  Pillow 未安装，请运行：pip install Pillow")
        print()
    print()

    report = generate_report(args.dir, args.target, args.output)

    if not args.output:
        print(report)


if __name__ == "__main__":
    main()
