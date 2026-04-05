#!/usr/bin/env python3
"""
simp-skill · Social Media Parser
扫描社交媒体内容目录（朋友圈截图、微博、小红书等），
提取文字内容，生成心上人社交画像报告。

支持内容：
- 图片：jpg / jpeg / png / gif / webp / bmp / heic
- 文字导出：txt / md / json / csv

用法：
  python3 social_parser.py --dir crushes/xiaomei/memories/social --output crushes/xiaomei/memories/social/report.md
  python3 social_parser.py --dir ./social_screenshots --target 小美
"""

import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter


# ─────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}
TEXT_EXTS  = {".txt", ".md", ".json", ".csv"}

# 平台关键词（用于从文件名推测来源平台）
PLATFORM_HINTS = {
    "weibo":        ["微博", "weibo", "wb_"],
    "xiaohongshu":  ["小红书", "红书", "xhs", "xiaohongshu", "rednote"],
    "moments":      ["朋友圈", "moments", "wechat"],
    "douyin":       ["抖音", "douyin", "dy_"],
    "instagram":    ["instagram", "ig_"],
    "twitter":      ["twitter", "tweet"],
    "bilibili":     ["bilibili", "bili", "b站"],
}

# 情感信号关键词（用于文字内容的信号扫描）
SIGNAL_KEYWORDS = {
    "积极信号": [
        "喜欢", "开心", "快乐", "幸福", "期待", "想你", "念你", "陪伴",
        "一起", "约", "见面", "等你", "好想", "最近怎么样", "你在吗",
        "miss", "happy", "love", "together", "date",
    ],
    "情绪低落": [
        "难过", "伤心", "哭", "失眠", "想太多", "孤独", "一个人",
        "失落", "心情不好", "烦", "累", "sad", "lonely", "cry",
    ],
    "感情相关": [
        "喜欢一个人", "暗恋", "表白", "心动", "心跳", "脸红",
        "好看", "好温柔", "好厉害", "崇拜",
        "crush", "like someone", "confession",
    ],
}


# ─────────────────────────────────────────────
# 扫描目录
# ─────────────────────────────────────────────

def scan_directory(directory: str) -> dict:
    """递归扫描目录，按类型分类文件"""
    result = {"images": [], "texts": [], "others": []}
    base = Path(directory)

    if not base.exists():
        print(f"⚠️  目录不存在：{directory}")
        return result

    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        rel = str(path.relative_to(base))

        if ext in IMAGE_EXTS:
            result["images"].append({"path": str(path), "rel": rel, "name": path.name, "size": path.stat().st_size})
        elif ext in TEXT_EXTS:
            result["texts"].append({"path": str(path), "rel": rel, "name": path.name, "size": path.stat().st_size})
        elif path.name.startswith(".") or path.name == "report.md":
            continue  # 跳过隐藏文件和已生成的报告
        else:
            result["others"].append({"path": str(path), "rel": rel, "name": path.name})

    return result


# ─────────────────────────────────────────────
# 平台识别
# ─────────────────────────────────────────────

def detect_platform(filename: str) -> str:
    """从文件名推测社交平台来源"""
    name_lower = filename.lower()
    for platform, hints in PLATFORM_HINTS.items():
        for hint in hints:
            if hint.lower() in name_lower:
                return platform
    return "未知平台"


def platform_display(platform: str) -> str:
    display = {
        "weibo": "微博",
        "xiaohongshu": "小红书",
        "moments": "微信朋友圈",
        "douyin": "抖音",
        "instagram": "Instagram",
        "twitter": "Twitter / X",
        "bilibili": "哔哩哔哩",
        "未知平台": "未知来源",
    }
    return display.get(platform, platform)


# ─────────────────────────────────────────────
# 文字内容提取与分析
# ─────────────────────────────────────────────

def read_text_file(filepath: str, max_chars: int = 5000) -> str:
    """读取文本文件，限制长度"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(max_chars)
        if len(content) == max_chars:
            content += "\n\n[... 内容过长，已截断 ...]"
        return content.strip()
    except Exception as e:
        return f"[读取失败：{e}]"


def parse_json_export(filepath: str) -> list:
    """尝试解析 JSON 导出（微博/小红书等平台的数据导出）"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        posts = []
        # 尝试常见的 JSON 结构
        items = (
            data if isinstance(data, list)
            else data.get("data", data.get("posts", data.get("items", [])))
        )

        for item in items[:50]:  # 最多取50条
            text = (
                item.get("text") or item.get("content") or
                item.get("description") or item.get("body") or ""
            )
            created = (
                item.get("created_at") or item.get("time") or
                item.get("timestamp") or item.get("date") or ""
            )
            posts.append({"text": str(text).strip(), "time": str(created)})

        return [p for p in posts if p["text"]]
    except Exception:
        return []


def scan_signals(text: str) -> dict:
    """扫描文字内容中的情感信号关键词"""
    found = {}
    text_lower = text.lower()
    for category, keywords in SIGNAL_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text_lower]
        if hits:
            found[category] = hits
    return found


# ─────────────────────────────────────────────
# 报告生成
# ─────────────────────────────────────────────

def generate_report(directory: str, target_name: str, output_path: str = None) -> str:
    """生成社交媒体内容分析报告"""
    files = scan_directory(directory)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    images  = files["images"]
    texts   = files["texts"]

    lines = [
        f"# 📱 社交媒体内容报告",
        f"",
        f"> 心上人：**{target_name}**  |  分析时间：{now}",
        f"> 来源目录：`{directory}`",
        f"",
        f"---",
        f"",
        f"## 📊 内容概览",
        f"",
        f"| 类型 | 数量 |",
        f"|------|------|",
        f"| 图片 | {len(images)} 张 |",
        f"| 文字文件 | {len(texts)} 个 |",
        f"| 合计 | {len(images) + len(texts)} 个文件 |",
        f"",
    ]

    # ── 图片清单 ──────────────────────────────
    if images:
        # 按平台分组
        platform_groups: dict = {}
        for img in images:
            plat = detect_platform(img["name"])
            platform_groups.setdefault(plat, []).append(img)

        lines += [
            f"---",
            f"",
            f"## 🖼️ 图片清单（{len(images)} 张）",
            f"",
            f"> 图片需要通过 Claude 的视觉能力分析，",
            f"> 可将图片路径告诉 Claude，让其直接读取图片内容。",
            f"",
        ]

        for plat, imgs in sorted(platform_groups.items()):
            lines.append(f"### {platform_display(plat)}（{len(imgs)} 张）")
            lines.append(f"")
            for img in imgs:
                size_kb = round(img["size"] / 1024, 1)
                lines.append(f"- `{img['rel']}`（{size_kb} KB）")
            lines.append(f"")

        lines += [
            f"**使用建议**：",
            f"将以上图片路径逐一告诉 Claude，配合以下提示词分析：",
            f"",
            f"```",
            f"请分析这张图片，告诉我：",
            f"1. 图片内容是什么？（文字/场景/情绪）",
            f"2. 有没有关于 {target_name} 性格或生活状态的信息？",
            f"3. 有没有可以用于定制情话的细节？",
            f"```",
            f"",
        ]

    # ── 文字内容 ──────────────────────────────
    if texts:
        lines += [
            f"---",
            f"",
            f"## 📝 文字内容（{len(texts)} 个文件）",
            f"",
        ]

        all_signals: dict = {}

        for tf in texts:
            filepath = tf["path"]
            filename = tf["name"]
            ext = Path(filename).suffix.lower()
            plat = detect_platform(filename)

            lines += [
                f"### 📄 {tf['rel']}",
                f"",
                f"**来源平台**：{platform_display(plat)}",
                f"",
            ]

            # JSON 导出特殊处理
            if ext == ".json":
                posts = parse_json_export(filepath)
                if posts:
                    lines.append(f"**解析到 {len(posts)} 条内容**：")
                    lines.append(f"")
                    for i, post in enumerate(posts[:10], 1):
                        time_str = f"（{post['time']}）" if post["time"] else ""
                        lines.append(f"{i}. {time_str}{post['text'][:200]}")
                    if len(posts) > 10:
                        lines.append(f"... 共 {len(posts)} 条，仅展示前10条")
                    lines.append(f"")
                    # 合并所有文字做信号扫描
                    combined = " ".join(p["text"] for p in posts)
                    signals = scan_signals(combined)
                else:
                    content = read_text_file(filepath)
                    lines.append(f"```")
                    lines.append(content)
                    lines.append(f"```")
                    lines.append(f"")
                    signals = scan_signals(content)
            else:
                content = read_text_file(filepath)
                lines.append(f"```")
                lines.append(content)
                lines.append(f"```")
                lines.append(f"")
                signals = scan_signals(content)

            # 信号标注
            if signals:
                lines.append(f"**🔍 检测到的情感关键词**：")
                for cat, kws in signals.items():
                    lines.append(f"- {cat}：{', '.join(f'`{k}`' for k in kws)}")
                lines.append(f"")
                # 累计
                for cat, kws in signals.items():
                    all_signals.setdefault(cat, []).extend(kws)

        # 全局信号汇总
        if all_signals:
            lines += [
                f"---",
                f"",
                f"## 🎯 社交内容信号汇总",
                f"",
                f"从所有文字内容中检测到以下情感关键词：",
                f"",
            ]
            for cat, kws in all_signals.items():
                freq = Counter(kws).most_common(5)
                lines.append(f"**{cat}**：{', '.join(f'{k}×{c}' if c > 1 else k for k, c in freq)}")
            lines += [
                f"",
                f"> 💡 这些关键词可以帮助你了解 {target_name} 近期的情绪状态和关注点，",
                f"> 用于定制更贴近ta当下心情的情话。",
                f"",
            ]

    # ── 空目录提示 ────────────────────────────
    if not images and not texts:
        lines += [
            f"",
            f"⚠️  目录中没有找到可分析的文件。",
            f"",
            f"**如何获取社交媒体内容**：",
            f"",
            f"| 平台 | 方法 |",
            f"|------|------|",
            f"| 微信朋友圈 | 截图保存为图片 |",
            f"| 微博 | 截图 或 使用数据导出工具 |",
            f"| 小红书 | 截图 或 复制文字粘贴为 .txt |",
            f"| 抖音 | 截图视频封面 |",
            f"",
            f"将文件放入 `{directory}/` 后重新运行本工具。",
        ]

    lines += [
        f"---",
        f"",
        f"## 📌 后续建议",
        f"",
        f"1. 将图片路径告诉 Claude 进行视觉分析，补充 `profile.md` 中的画像细节",
        f"2. 运行 `/simp analyze` 结合聊天记录与社交内容进行综合信号评估",
        f"3. 社交内容揭示的情绪关键词可以作为情话的切入点",
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
        description="simp-skill · 社交媒体内容解析器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 social_parser.py --dir crushes/xiaomei/memories/social
  python3 social_parser.py --dir ./screenshots --target 小美 --output report.md
        """,
    )
    parser.add_argument("--dir", required=True, help="社交媒体内容目录路径")
    parser.add_argument("--target", default="心上人", help="心上人的名字（默认：心上人）")
    parser.add_argument("--output", "-o", help="输出报告路径（默认：打印到控制台）")

    args = parser.parse_args()

    print(f"💝 simp-skill · 社交内容解析器")
    print(f"📂 扫描目录：{args.dir}")
    print(f"🎯 心上人：{args.target}")
    print()

    report = generate_report(args.dir, args.target, args.output)

    if not args.output:
        print(report)


if __name__ == "__main__":
    main()
