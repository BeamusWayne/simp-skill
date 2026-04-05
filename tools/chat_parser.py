#!/usr/bin/env python3
"""
simp-skill · Chat Parser
解析微信/QQ聊天记录，提取信号分析报告

支持格式：
- 微信导出 TXT（WeChatMsg/留痕等工具）
- 微信导出 HTML（WeChatMsg）
- 微信导出 CSV（PyWxDump）
- QQ 导出 TXT（QQ消息管理器）
- QQ 导出 MHT/MHTML（QQ消息管理器）
- 通用 JSON 格式

用法：
  python3 chat_parser.py <input_file> <target_name> [--user <your_name>] [--output <output_file>]

示例：
  python3 chat_parser.py wechat_export.txt 小美 --output output/xiaomei_analysis.md
  python3 chat_parser.py qq_log.txt 小美 --user 我 --output output/xiaomei_analysis.md
"""

import re
import sys
import json
import html
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict
from typing import Optional


# ─────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────

class Message:
    """单条消息"""
    def __init__(self, timestamp: datetime, sender: str, content: str, msg_type: str = "text"):
        self.timestamp = timestamp
        self.sender = sender
        self.content = content
        self.msg_type = msg_type  # text / image / sticker / voice / system

    def __repr__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.sender}: {self.content[:30]}"


# ─────────────────────────────────────────────
# 格式探测与解析
# ─────────────────────────────────────────────

def detect_format(filepath: str) -> str:
    """自动探测聊天记录格式"""
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext == ".json":
        return "json"
    if ext in (".mht", ".mhtml"):
        return "qq_mht"
    if ext == ".csv":
        return "wechat_csv"
    if ext == ".html":
        return "wechat_html"

    # TXT 格式需要读取内容判断
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            sample = f.read(4096)
    except Exception:
        return "unknown"

    # QQ TXT: "2024-01-01 12:00:00 用户名(12345678)"
    if re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} .+\(\d+\)', sample):
        return "qq_txt"

    # 微信 WeChatMsg TXT: "2024-01-01 12:00:00\n用户名\n消息内容"
    if re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', sample):
        return "wechat_txt"

    return "plaintext"


def parse_wechat_txt(filepath: str, target_name: str, user_name: str) -> list:
    """解析微信导出 TXT（WeChatMsg格式）"""
    messages = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 匹配时间戳行
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\n(.+?)\n(.*?)(?=\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)

    for ts_str, sender, msg_content in matches:
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        sender = sender.strip()
        msg_content = msg_content.strip()

        if not msg_content or msg_content in ("[图片]", "[语音]", "[视频]", "[文件]"):
            msg_type = "image" if "[图片]" in msg_content else (
                "voice" if "[语音]" in msg_content else "media"
            )
            if not msg_content:
                continue
            messages.append(Message(ts, sender, msg_content, msg_type))
        else:
            messages.append(Message(ts, sender, msg_content))

    return messages


def parse_qq_txt(filepath: str, target_name: str, user_name: str) -> list:
    """解析QQ导出 TXT"""
    messages = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    current_ts = None
    current_sender = None
    current_content = []

    header_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (.+?)(?:\(\d+\))?$')

    def flush():
        if current_ts and current_sender and current_content:
            content = "\n".join(current_content).strip()
            if content:
                messages.append(Message(current_ts, current_sender, content))

    for line in lines:
        line = line.rstrip()
        m = header_pattern.match(line)
        if m:
            flush()
            try:
                current_ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                current_ts = None
            current_sender = m.group(2).strip()
            current_content = []
        elif current_ts is not None:
            current_content.append(line)

    flush()
    return messages


def parse_qq_mht(filepath: str, target_name: str, user_name: str) -> list:
    """解析QQ导出 MHT/MHTML"""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    # 去除HTML标签
    clean = re.sub(r'<[^>]+>', ' ', raw)
    clean = html.unescape(clean)
    clean = re.sub(r'\s+', ' ', clean)

    # 同QQ TXT 解析
    messages = []
    pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (.+?)(?:\(\d+\))? (.+?)(?=\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}|\Z)')
    for m in pattern.finditer(clean):
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            sender = m.group(2).strip()
            content = m.group(3).strip()
            if content:
                messages.append(Message(ts, sender, content))
        except ValueError:
            continue

    return messages


def parse_wechat_html(filepath: str, target_name: str, user_name: str) -> list:
    """解析微信导出 HTML（WeChatMsg）"""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    messages = []
    # 匹配消息块
    msg_pattern = re.compile(
        r'<div class="message[^"]*"[^>]*>.*?'
        r'<span class="time"[^>]*>([^<]+)</span>.*?'
        r'<span class="sender"[^>]*>([^<]+)</span>.*?'
        r'<div class="content"[^>]*>(.*?)</div>',
        re.DOTALL
    )
    for m in msg_pattern.finditer(raw):
        ts_str = m.group(1).strip()
        sender = html.unescape(m.group(2).strip())
        content = html.unescape(re.sub(r'<[^>]+>', '', m.group(3))).strip()

        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                ts = datetime.strptime(ts_str, "%Y/%m/%d %H:%M:%S")
            except ValueError:
                continue

        if content:
            messages.append(Message(ts, sender, content))

    return messages


def parse_wechat_csv(filepath: str, target_name: str, user_name: str) -> list:
    """解析 PyWxDump CSV 导出"""
    import csv
    messages = []
    with open(filepath, "r", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_field = row.get("CreateTime") or row.get("timestamp") or row.get("time", "")
            sender_field = row.get("NickName") or row.get("sender") or row.get("from", "")
            content_field = row.get("StrContent") or row.get("content") or row.get("msg", "")

            try:
                if ts_field.isdigit():
                    ts = datetime.fromtimestamp(int(ts_field))
                else:
                    ts = datetime.strptime(ts_field[:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, AttributeError):
                continue

            sender = sender_field.strip()
            content = content_field.strip()
            if content:
                messages.append(Message(ts, sender, content))

    return messages


def parse_json(filepath: str, target_name: str, user_name: str) -> list:
    """解析通用 JSON 格式"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = []
    items = data if isinstance(data, list) else data.get("messages", [])

    for item in items:
        ts_raw = item.get("timestamp") or item.get("time") or item.get("createTime", "")
        sender = item.get("sender") or item.get("from") or item.get("nickName", "")
        content = item.get("content") or item.get("text") or item.get("msg", "")

        try:
            if isinstance(ts_raw, (int, float)):
                ts = datetime.fromtimestamp(ts_raw)
            else:
                ts = datetime.strptime(str(ts_raw)[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue

        if content:
            messages.append(Message(ts, str(sender).strip(), str(content).strip()))

    return messages


def parse_chat(filepath: str, target_name: str, user_name: str = "我") -> list:
    """主解析入口：自动选择格式"""
    fmt = detect_format(filepath)
    parsers = {
        "wechat_txt": parse_wechat_txt,
        "wechat_html": parse_wechat_html,
        "wechat_csv": parse_wechat_csv,
        "qq_txt": parse_qq_txt,
        "qq_mht": parse_qq_mht,
        "json": parse_json,
        "plaintext": parse_wechat_txt,  # fallback
    }
    parser = parsers.get(fmt, parse_wechat_txt)
    messages = parser(filepath, target_name, user_name)

    # 过滤：只保留目标和用户的消息
    relevant = [m for m in messages if target_name in m.sender or user_name in m.sender]

    # 按时间排序
    relevant.sort(key=lambda m: m.timestamp)
    return relevant


# ─────────────────────────────────────────────
# 信号分析引擎
# ─────────────────────────────────────────────

class SignalAnalyzer:
    """信号分析引擎：从聊天记录中提取追求策略相关信号"""

    def __init__(self, messages: list, target_name: str, user_name: str):
        self.messages = messages
        self.target = target_name
        self.user = user_name
        self.target_msgs = [m for m in messages if target_name in m.sender]
        self.user_msgs = [m for m in messages if user_name in m.sender]

    # ── 基础统计 ──────────────────────────────────

    def message_counts(self) -> dict:
        return {
            "total": len(self.messages),
            "from_target": len(self.target_msgs),
            "from_user": len(self.user_msgs),
            "target_ratio": round(len(self.target_msgs) / max(len(self.messages), 1) * 100, 1),
        }

    def date_range(self) -> dict:
        if not self.messages:
            return {}
        first = self.messages[0].timestamp
        last = self.messages[-1].timestamp
        days = (last - first).days + 1
        return {
            "first_date": first.strftime("%Y-%m-%d"),
            "last_date": last.strftime("%Y-%m-%d"),
            "total_days": days,
            "avg_msgs_per_day": round(len(self.messages) / max(days, 1), 1),
        }

    # ── 主动性分析 ─────────────────────────────────

    def initiative_analysis(self) -> dict:
        """分析谁更主动开启对话"""
        sessions = self._split_sessions()
        target_starts = 0
        user_starts = 0

        for session in sessions:
            if not session:
                continue
            first = session[0]
            if self.target in first.sender:
                target_starts += 1
            elif self.user in first.sender:
                user_starts += 1

        total = target_starts + user_starts or 1
        return {
            "target_initiates": target_starts,
            "user_initiates": user_starts,
            "target_initiative_ratio": round(target_starts / total * 100, 1),
            "user_initiative_ratio": round(user_starts / total * 100, 1),
            "verdict": self._initiative_verdict(target_starts, user_starts),
        }

    def _initiative_verdict(self, target: int, user: int) -> str:
        if user == 0 and target == 0:
            return "数据不足"
        ratio = target / (target + user)
        if ratio >= 0.6:
            return "🟢 ta 经常主动找你（强绿灯）"
        elif ratio >= 0.4:
            return "🟡 双方主动程度差不多"
        elif ratio >= 0.2:
            return "🟡 你更主动，ta 偶尔主动"
        else:
            return "🔴 几乎都是你在主动，ta 很少主动"

    # ── 回复速度分析 ───────────────────────────────

    def reply_speed_analysis(self) -> dict:
        """分析回复速度和趋势"""
        target_delays = []
        user_delays = []

        for i in range(1, len(self.messages)):
            prev = self.messages[i - 1]
            curr = self.messages[i]
            delay = (curr.timestamp - prev.timestamp).total_seconds()

            # 超过4小时视为新会话，不计算
            if delay > 14400:
                continue

            if self.target in curr.sender and self.user in prev.sender:
                target_delays.append(delay)
            elif self.user in curr.sender and self.target in prev.sender:
                user_delays.append(delay)

        def stats(delays):
            if not delays:
                return {"avg_seconds": None, "median_seconds": None, "fast_ratio": None}
            avg = sum(delays) / len(delays)
            sorted_d = sorted(delays)
            median = sorted_d[len(sorted_d) // 2]
            fast = sum(1 for d in delays if d < 300) / len(delays)  # 5分钟内回复
            return {
                "avg_seconds": round(avg),
                "avg_display": _format_seconds(avg),
                "median_display": _format_seconds(median),
                "fast_ratio": round(fast * 100, 1),
            }

        target_stats = stats(target_delays)
        user_stats = stats(user_delays)

        # 速度趋势：比较前半段和后半段
        trend = "数据不足"
        if len(target_delays) >= 10:
            first_half = sum(target_delays[:len(target_delays)//2]) / (len(target_delays)//2)
            second_half = sum(target_delays[len(target_delays)//2:]) / (len(target_delays) - len(target_delays)//2)
            if second_half < first_half * 0.7:
                trend = "🟢 ta 回复越来越快（温度在升）"
            elif second_half > first_half * 1.5:
                trend = "🔴 ta 回复越来越慢（需要注意）"
            else:
                trend = "🟡 回复速度变化不大"

        return {
            "target_reply": target_stats,
            "user_reply": user_stats,
            "speed_comparison": self._speed_verdict(target_stats, user_stats),
            "trend": trend,
        }

    def _speed_verdict(self, target: dict, user: dict) -> str:
        ta = target.get("avg_seconds")
        me = user.get("avg_seconds")
        if ta is None or me is None:
            return "数据不足"
        if ta < 120:
            return "🟢 ta 回复你很快（秒回/分钟级）"
        elif ta < 600:
            return "🟢 ta 回复较及时（10分钟内）"
        elif ta < me * 0.5:
            return "🟡 ta 比你回复略慢，但尚可"
        elif ta > me * 2:
            return "🔴 ta 回复你明显比你回复ta慢"
        else:
            return "🟡 双方回复速度差不多"

    # ── 消息长度分析 ───────────────────────────────

    def message_length_analysis(self) -> dict:
        """分析消息长度（情感投入指标）"""
        target_lens = [len(m.content) for m in self.target_msgs if m.msg_type == "text"]
        user_lens = [len(m.content) for m in self.user_msgs if m.msg_type == "text"]

        def avg(lst):
            return round(sum(lst) / len(lst), 1) if lst else 0

        target_avg = avg(target_lens)
        user_avg = avg(user_lens)

        verdict = ""
        if target_avg > user_avg * 1.3:
            verdict = "🟢 ta 发给你的消息比你的更长（投入度高）"
        elif target_avg < user_avg * 0.5:
            verdict = "🔴 ta 的消息明显比你短（可能不够投入）"
        elif target_avg > 50:
            verdict = "🟢 ta 愿意给你发长消息（有话说）"
        else:
            verdict = "🟡 双方消息长度差不多"

        return {
            "target_avg_len": target_avg,
            "user_avg_len": user_avg,
            "target_long_msgs": sum(1 for l in target_lens if l > 100),
            "verdict": verdict,
        }

    # ── 深夜信号分析 ───────────────────────────────

    def late_night_analysis(self) -> dict:
        """深夜消息（22:00-02:00）是重要亲密度信号"""
        late_night_range = set(range(22, 24)) | set(range(0, 3))

        target_late = [m for m in self.target_msgs if m.timestamp.hour in late_night_range]
        user_late = [m for m in self.user_msgs if m.timestamp.hour in late_night_range]

        target_initiates_late = 0
        for session in self._split_sessions():
            if not session:
                continue
            first = session[0]
            if first.timestamp.hour in late_night_range and self.target in first.sender:
                target_initiates_late += 1

        verdict = ""
        if target_initiates_late >= 5:
            verdict = "🟢🟢 ta 多次在深夜主动找你（强亲密信号）"
        elif target_initiates_late >= 2:
            verdict = "🟢 ta 有过深夜主动联系你"
        elif len(target_late) > 0:
            verdict = "🟡 ta 有在深夜回复你，但不常主动"
        else:
            verdict = "⚪ 没有明显的深夜互动记录"

        return {
            "target_late_msgs": len(target_late),
            "target_initiates_late_night": target_initiates_late,
            "verdict": verdict,
        }

    # ── 话题分析 ───────────────────────────────────

    def topic_analysis(self) -> dict:
        """分析高频话题和ta主动延伸的话题"""
        all_words = []
        for m in self.target_msgs:
            # 简单分词：按标点和空格切分
            words = re.findall(r'[\u4e00-\u9fff]{2,6}', m.content)
            all_words.extend(words)

        # 过滤停用词
        stopwords = {
            '什么', '这个', '那个', '一个', '可以', '没有', '知道', '觉得', '感觉',
            '就是', '但是', '因为', '所以', '如果', '现在', '时候', '已经', '还是',
            '好像', '应该', '可能', '不是', '一样', '这样', '那样', '一下',
        }
        filtered = [w for w in all_words if w not in stopwords]
        top_topics = Counter(filtered).most_common(15)

        # 话题延伸：ta在我发消息后是否追问
        follow_up_count = 0
        for i in range(1, len(self.messages)):
            prev = self.messages[i - 1]
            curr = self.messages[i]
            delay = (curr.timestamp - prev.timestamp).total_seconds()
            if (self.user in prev.sender and self.target in curr.sender
                    and delay < 3600 and '？' in curr.content or '?' in curr.content):
                follow_up_count += 1

        return {
            "top_topics": top_topics,
            "target_follow_up_questions": follow_up_count,
            "follow_up_verdict": (
                "🟢 ta 经常追问你的话（在乎你说的）" if follow_up_count >= 10
                else "🟡 ta 有时会追问" if follow_up_count >= 3
                else "⚪ ta 很少追问"
            ),
        }

    # ── 语言特征提取 ───────────────────────────────

    def language_features(self) -> dict:
        """提取ta的语言习惯，用于画像构建"""
        all_target_text = " ".join(m.content for m in self.target_msgs)

        # 语气词/口头禅检测
        particles = ['哈哈', '哈', '嗯', '啊', '呢', '吧', '哦', '噢', '嘿', '诶',
                     '好的', '好啊', '好哦', '嗯嗯', '哎', '哎呀', '唉', '哇', '哇哦',
                     '嗯哦', '好嘞', '行', '行吧', '确实', '对哦', '对的', '对对', '真的',
                     '真的吗', '没有', '有吗', '是吗', '是哦', '可以', '好可以', '6', '666']

        particle_counts = {p: all_target_text.count(p) for p in particles if all_target_text.count(p) > 0}
        top_particles = sorted(particle_counts.items(), key=lambda x: -x[1])[:8]

        # emoji统计
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0\U000024C2-\U0001F251]+",
            flags=re.UNICODE
        )
        all_emojis = emoji_pattern.findall(all_target_text)
        emoji_freq = Counter(all_emojis).most_common(5)

        # 标点习惯
        has_ellipsis = all_target_text.count("...") + all_target_text.count("……")
        has_exclaim = all_target_text.count("！") + all_target_text.count("!")
        has_question = all_target_text.count("？") + all_target_text.count("?")
        total_msgs = max(len(self.target_msgs), 1)

        # 消息风格
        short_msgs = sum(1 for m in self.target_msgs if len(m.content) < 20)
        long_msgs = sum(1 for m in self.target_msgs if len(m.content) > 100)
        style = (
            "短句连发型" if short_msgs > total_msgs * 0.7
            else "长篇输出型" if long_msgs > total_msgs * 0.2
            else "混合型"
        )

        return {
            "top_particles": top_particles,
            "top_emojis": emoji_freq,
            "exclamation_per_msg": round(has_exclaim / total_msgs, 2),
            "question_per_msg": round(has_question / total_msgs, 2),
            "ellipsis_count": has_ellipsis,
            "message_style": style,
        }

    # ── 综合信号评分 ───────────────────────────────

    def signal_score(self) -> dict:
        """计算综合信号评分（满分25）"""
        score = 0
        signals = []

        counts = self.message_counts()
        initiative = self.initiative_analysis()
        speed = self.reply_speed_analysis()
        length = self.message_length_analysis()
        late_night = self.late_night_analysis()
        topic = self.topic_analysis()

        # 主动性评分（0-6）
        ratio = initiative["target_initiative_ratio"]
        if ratio >= 50:
            score += 6
            signals.append(f"🟢 ta主动开启 {ratio}% 的对话（强绿灯）")
        elif ratio >= 35:
            score += 3
            signals.append(f"🟡 ta主动开启 {ratio}% 的对话")
        elif ratio >= 20:
            score += 1
        else:
            score -= 2
            signals.append("🔴 ta几乎不主动联系你")

        # 回复速度评分（0-5）
        target_avg = speed["target_reply"].get("avg_seconds")
        if target_avg is not None:
            if target_avg < 120:
                score += 5
                signals.append(f"🟢 ta平均 {_format_seconds(target_avg)} 回复你（很快）")
            elif target_avg < 600:
                score += 3
                signals.append(f"🟢 ta平均 {_format_seconds(target_avg)} 回复你")
            elif target_avg > 3600:
                score -= 1
                signals.append(f"🔴 ta平均 {_format_seconds(target_avg)} 才回复你（较慢）")

        # 回复速度趋势评分（0-3）
        trend = speed.get("trend", "")
        if "越来越快" in trend:
            score += 3
            signals.append("🟢 ta最近回复你越来越快（温度在升）")
        elif "越来越慢" in trend:
            score -= 2
            signals.append("🔴 ta最近回复你越来越慢（需注意）")

        # 消息长度评分（0-3）
        if "投入度高" in length["verdict"]:
            score += 3
            signals.append("🟢 ta发给你的消息比你的长（更用心）")
        elif "明显比你短" in length["verdict"]:
            score -= 1

        # 深夜信号评分（0-5）
        late_initiates = late_night["target_initiates_late_night"]
        if late_initiates >= 5:
            score += 5
            signals.append(f"🟢🟢 ta {late_initiates} 次在深夜主动找你")
        elif late_initiates >= 2:
            score += 2
            signals.append(f"🟢 ta有过深夜主动联系你 ({late_initiates}次)")
        elif late_night["target_late_msgs"] > 0:
            score += 1

        # 追问行为评分（0-3）
        follow_up = topic["target_follow_up_questions"]
        if follow_up >= 10:
            score += 3
            signals.append(f"🟢 ta经常追问你 ({follow_up}次)，说明ta在意你说的话")
        elif follow_up >= 3:
            score += 1

        # 确定等级
        if score >= 18:
            level = "🟢🟢🟢 强烈绿灯"
            advice = "信号非常明显！是时候认真准备表白了。"
        elif score >= 12:
            level = "🟢🟡 中度绿灯"
            advice = "有明显好感，继续深化情感连接，创造更多1v1机会。"
        elif score >= 6:
            level = "🟡 模糊信号"
            advice = "信号不够明确，可以适当试探，不要急着表白。"
        elif score >= 0:
            level = "🟡🔴 弱信号"
            advice = "目前还没明显兴趣迹象，先建立更稳固的关系基础。"
        else:
            level = "🔴 警示信号"
            advice = "有一些不积极的信号，建议重新评估追求策略。"

        return {
            "score": score,
            "max_score": 25,
            "level": level,
            "key_signals": signals,
            "advice": advice,
        }

    # ── 辅助方法 ───────────────────────────────────

    def _split_sessions(self, gap_minutes: int = 60) -> list:
        """将消息按时间间隔分割成会话"""
        if not self.messages:
            return []
        sessions = []
        current = [self.messages[0]]
        for m in self.messages[1:]:
            gap = (m.timestamp - current[-1].timestamp).total_seconds() / 60
            if gap > gap_minutes:
                sessions.append(current)
                current = [m]
            else:
                current.append(m)
        sessions.append(current)
        return sessions


# ─────────────────────────────────────────────
# 报告生成
# ─────────────────────────────────────────────

def _format_seconds(seconds: float) -> str:
    """将秒数格式化为可读字符串"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds/60)}分钟"
    else:
        return f"{seconds/3600:.1f}小时"


def generate_report(messages: list, target_name: str, user_name: str, output_path: Optional[str] = None) -> str:
    """生成完整的信号分析报告"""
    if not messages:
        return "❌ 未找到有效消息，请检查文件格式和姓名设置。"

    analyzer = SignalAnalyzer(messages, target_name, user_name)

    counts = analyzer.message_counts()
    date_range = analyzer.date_range()
    initiative = analyzer.initiative_analysis()
    speed = analyzer.reply_speed_analysis()
    length = analyzer.message_length_analysis()
    late_night = analyzer.late_night_analysis()
    topic = analyzer.topic_analysis()
    features = analyzer.language_features()
    score = analyzer.signal_score()

    lines = [
        f"# 💝 聊天记录信号分析报告",
        f"",
        f"> 心上人：**{target_name}**  |  分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 记录时间：{date_range.get('first_date', '?')} ～ {date_range.get('last_date', '?')}（{date_range.get('total_days', '?')}天）",
        f"",
        f"---",
        f"",
        f"## 📊 综合信号评分",
        f"",
        f"**{score['score']} / {score['max_score']} 分**  —  {score['level']}",
        f"",
        f"**关键信号**：",
    ]

    for sig in score["key_signals"]:
        lines.append(f"- {sig}")

    lines += [
        f"",
        f"> 💡 **建议**：{score['advice']}",
        f"",
        f"---",
        f"",
        f"## 📱 基础统计",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 总消息数 | {counts['total']} 条 |",
        f"| ta 发的消息 | {counts['from_target']} 条（{counts['target_ratio']}%） |",
        f"| 你发的消息 | {counts['from_user']} 条 |",
        f"| 日均消息数 | {date_range.get('avg_msgs_per_day', '?')} 条 |",
        f"",
        f"---",
        f"",
        f"## 🎯 主动性分析",
        f"",
        f"- ta 主动开启对话：**{initiative['target_initiates']} 次**（{initiative['target_initiative_ratio']}%）",
        f"- 你主动开启对话：**{initiative['user_initiates']} 次**（{initiative['user_initiative_ratio']}%）",
        f"- 判断：{initiative['verdict']}",
        f"",
        f"---",
        f"",
        f"## ⚡ 回复速度",
        f"",
        f"- ta 平均回复速度：**{speed['target_reply'].get('avg_display', '数据不足')}**",
        f"- 你的平均回复速度：**{speed['user_reply'].get('avg_display', '数据不足')}**",
        f"- ta 5分钟内快速回复比例：{speed['target_reply'].get('fast_ratio', '?')}%",
        f"- 速度对比：{speed['speed_comparison']}",
        f"- 趋势：{speed['trend']}",
        f"",
        f"---",
        f"",
        f"## 📏 消息长度（情感投入度）",
        f"",
        f"- ta 平均消息长度：**{length['target_avg_len']} 字**",
        f"- 你的平均消息长度：**{length['user_avg_len']} 字**",
        f"- ta 发给你的长消息（>100字）：{length['target_long_msgs']} 条",
        f"- 判断：{length['verdict']}",
        f"",
        f"---",
        f"",
        f"## 🌙 深夜信号（22:00-02:00）",
        f"",
        f"- ta 在深夜发的消息：{late_night['target_late_msgs']} 条",
        f"- ta 主动在深夜开启对话：{late_night['target_initiates_late_night']} 次",
        f"- 判断：{late_night['verdict']}",
        f"",
        f"---",
        f"",
        f"## 💬 话题分析",
        f"",
        f"**ta 的高频词汇 Top 10**：",
    ]

    for word, count in topic["top_topics"][:10]:
        lines.append(f"- 「{word}」× {count}")

    lines += [
        f"",
        f"- ta 追问你的次数：{topic['target_follow_up_questions']} 次",
        f"- 判断：{topic['follow_up_verdict']}",
        f"",
        f"---",
        f"",
        f"## 🗣️ ta 的语言特征（用于定制情话）",
        f"",
        f"- 消息风格：**{features['message_style']}**",
        f"- 每条消息平均感叹号：{features['exclamation_per_msg']} 个",
        f"- 每条消息平均问号：{features['question_per_msg']} 个",
        f"",
        f"**常用语气词/口头禅**：",
    ]

    for particle, count in features["top_particles"]:
        lines.append(f"- 「{particle}」× {count}")

    if features["top_emojis"]:
        lines.append(f"")
        lines.append(f"**常用 Emoji**：")
        for emoji, count in features["top_emojis"]:
            lines.append(f"- {emoji} × {count}")

    lines += [
        f"",
        f"---",
        f"",
        f"## 🎯 给你的追求建议",
        f"",
        f"基于以上分析，当前阶段的建议：",
        f"",
        f"1. **根据信号等级**：{score['advice']}",
        f"",
        f"2. **基于ta的语言习惯**，你的消息风格建议：",
        f"   - ta 是「{features['message_style']}」，所以你的消息也不要太长/太短，跟ta的节奏走",
        f"   - 适当用ta熟悉的语气词，会让ta觉得亲切",
        f"",
        f"3. **最优互动时间**：",
    ]

    if late_night["target_initiates_late_night"] >= 2:
        lines.append(f"   - ta 有深夜主动联系你的习惯，这是最亲密的互动时段")
    lines += [
        f"   - 根据回复速度，ta 在快速回复时更活跃，选择那个时间段互动效果更好",
        f"",
        f"4. **下一步行动**：运行 `/simp analyze` 获取更详细的策略建议",
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
        description="simp-skill · 聊天记录信号分析器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 chat_parser.py wechat.txt 小美
  python3 chat_parser.py qq_log.txt 小美 --user 我的QQ昵称
  python3 chat_parser.py wechat.html 小美 --output crushes/xiaomei/memories/chats/analysis.md
        """
    )
    parser.add_argument("input", help="聊天记录文件路径")
    parser.add_argument("target", help="心上人的名字（需与聊天记录中的显示名一致）")
    parser.add_argument("--user", default="我", help="你自己的名字（默认：我）")
    parser.add_argument("--output", "-o", help="输出文件路径（默认：打印到控制台）")
    parser.add_argument("--format", "-f", choices=["wechat_txt", "qq_txt", "qq_mht", "wechat_html", "wechat_csv", "json"],
                        help="强制指定格式（默认：自动检测）")

    args = parser.parse_args()

    print(f"💝 simp-skill · 聊天记录分析器")
    print(f"📂 读取文件：{args.input}")
    print(f"🎯 心上人：{args.target}")
    print(f"👤 你的名字：{args.user}")
    print()

    try:
        messages = parse_chat(args.input, args.target, args.user)
    except FileNotFoundError:
        print(f"❌ 文件不存在：{args.input}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 解析失败：{e}")
        sys.exit(1)

    if not messages:
        print(f"⚠️  未找到有效消息。请确认：")
        print(f"   1. 文件格式是否正确")
        print(f"   2. 名字「{args.target}」是否与聊天记录中一致（区分大小写）")
        print(f"   3. 如果名字包含空格，请用引号括起来")
        sys.exit(1)

    print(f"✅ 成功读取 {len(messages)} 条消息")
    print(f"🔍 正在分析信号...")
    print()

    report = generate_report(messages, args.target, args.user, args.output)

    if not args.output:
        print(report)


if __name__ == "__main__":
    main()
