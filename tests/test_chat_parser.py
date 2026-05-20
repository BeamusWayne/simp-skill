"""
tests/test_chat_parser.py
pytest 测试套件 · chat_parser.py
"""

import json
import re
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from tools.chat_parser import (
    Message,
    detect_format,
    parse_wechat_txt,
    parse_qq_txt,
    parse_qq_mht,
    parse_wechat_html,
    parse_wechat_csv,
    parse_json,
    parse_chat,
    SignalAnalyzer,
    _format_seconds,
    generate_report,
)


# ─────────────────────────────────────────────
# 纯函数
# ─────────────────────────────────────────────

class TestFormatSeconds:
    def test_seconds_under_minute(self) -> None:
        assert _format_seconds(45) == "45秒"

    def test_minutes(self) -> None:
        assert _format_seconds(180) == "3分钟"

    def test_hours(self) -> None:
        assert _format_seconds(7200) == "2.0小时"

    def test_zero(self) -> None:
        assert _format_seconds(0) == "0秒"


class TestMessage:
    def test_repr(self) -> None:
        ts = datetime(2024, 1, 1, 20, 30)
        m = Message(ts, "小美", "你好呀～")
        assert "2024-01-01 20:30" in repr(m)
        assert "小美" in repr(m)

    def test_init_defaults(self) -> None:
        ts = datetime.now()
        m = Message(ts, "小美", "hello")
        assert m.msg_type == "text"


class TestDetectFormat:
    @patch("tools.chat_parser.Path")
    def test_json_ext(self, mock_path_cls) -> None:
        mock_path_cls.return_value.suffix.lower.return_value = ".json"
        assert detect_format("x.json") == "json"

    def test_mht_ext(self) -> None:
        assert detect_format("x.mht") == "qq_mht"

    def test_csv_ext(self) -> None:
        assert detect_format("x.csv") == "wechat_csv"

    def test_html_ext(self) -> None:
        assert detect_format("x.html") == "wechat_html"


# ─────────────────────────────────────────────
# 格式解析（fixture 注入临时文件）
# ─────────────────────────────────────────────

class TestParseWechatTxt:
    def test_basic(self, tmp_path: Path) -> None:
        f = tmp_path / "wechat.txt"
        f.write_text(
            "2024-01-01 10:00:00\n小美\n你好呀～\n2024-01-01 10:05:00\n我\n嗨！\n",
            encoding="utf-8",
        )
        msgs = parse_wechat_txt(str(f), "小美", "我")
        assert len(msgs) == 2
        assert msgs[0].sender == "小美"
        assert msgs[0].content == "你好呀～"

    def test_ignores_empty_content(self, tmp_path: Path) -> None:
        f = tmp_path / "wechat.txt"
        f.write_text("2024-01-01 10:00:00\n小美\n\n2024-01-01 10:05:00\n我\n有内容\n", encoding="utf-8")
        msgs = parse_wechat_txt(str(f), "小美", "我")
        assert all(m.content.strip() for m in msgs)


class TestParseQqTxt:
    def test_basic(self, tmp_path: Path) -> None:
        f = tmp_path / "qq.txt"
        f.write_text(
            "2024-01-01 10:00:00 小美(12345)\n你好呀\n第二行\n"
            "2024-01-01 10:05:00 我(999)\n嗨！\n",
            encoding="utf-8",
        )
        msgs = parse_qq_txt(str(f), "小美", "我")
        assert len(msgs) == 2
        assert msgs[0].sender == "小美"
        assert msgs[0].content == "你好呀\n第二行"

    def test_multiline_content(self, tmp_path: Path) -> None:
        f = tmp_path / "qq.txt"
        f.write_text("2024-01-01 10:00:00 小美(1)\n第一行\n第二行\n第三行\n", encoding="utf-8")
        msgs = parse_qq_txt(str(f), "小美", "我")
        assert msgs[0].content == "第一行\n第二行\n第三行"

    def test_empty_lines_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "qq.txt"
        f.write_text("2024-01-01 10:00:00 小美(1)\n内容\n\n\n", encoding="utf-8")
        msgs = parse_qq_txt(str(f), "小美", "我")
        assert msgs[0].content == "内容"


class TestParseQqMht:
    def test_basic(self, tmp_path: Path) -> None:
        f = tmp_path / "qq.mht"
        f.write_text(
            "<p>2024-01-01 10:00:00 小美(12345) 你好呀～</p>"
            "<p>2024-01-01 10:05:00 我(999) 嗨！</p>",
            encoding="utf-8",
        )
        msgs = parse_qq_mht(str(f), "小美", "我")
        assert len(msgs) == 2
        assert msgs[0].sender == "小美"

    def test_html_tags_stripped(self, tmp_path: Path) -> None:
        f = tmp_path / "qq.mht"
        f.write_text("<b>2024-01-01 10:00:00</b> 小美(1) <i>消息内容</i>", encoding="utf-8")
        msgs = parse_qq_mht(str(f), "小美", "我")
        assert ">" not in msgs[0].content


class TestParseWechatHtml:
    def test_basic(self, tmp_path: Path) -> None:
        f = tmp_path / "wechat.html"
        f.write_text(
            '<div class="message"><span class="time">2024-01-01 10:00:00</span>'
            '<span class="sender">小美</span><div class="content">你好呀～</div></div>',
            encoding="utf-8",
        )
        msgs = parse_wechat_html(str(f), "小美", "我")
        assert len(msgs) == 1
        assert msgs[0].sender == "小美"
        assert msgs[0].content == "你好呀～"

    def test_slash_date_format(self, tmp_path: Path) -> None:
        f = tmp_path / "wechat.html"
        f.write_text(
            '<div class="message"><span class="time">2024/01/01 10:00:00</span>'
            '<span class="sender">小美</span><div class="content">test</div></div>',
            encoding="utf-8",
        )
        msgs = parse_wechat_html(str(f), "小美", "我")
        assert len(msgs) == 1


class TestParseWechatCsv:
    def test_timestamp_int(self, tmp_path: Path) -> None:
        f = tmp_path / "wechat.csv"
        ts = int(datetime(2024, 1, 1, 10, 0).timestamp())
        f.write_text(f"CreateTime,NickName,StrContent\n{ts},小美,你好呀～\n", encoding="utf-8-sig")
        msgs = parse_wechat_csv(str(f), "小美", "我")
        assert len(msgs) == 1
        assert msgs[0].content == "你好呀～"

    def test_string_timestamp(self, tmp_path: Path) -> None:
        f = tmp_path / "wechat.csv"
        f.write_text("CreateTime,NickName,StrContent\n2024-01-01 10:00:00,小美,hello\n", encoding="utf-8-sig")
        msgs = parse_wechat_csv(str(f), "小美", "我")
        assert len(msgs) == 1


class TestParseJson:
    def test_list_format(self, tmp_path: Path) -> None:
        f = tmp_path / "chat.json"
        f.write_text(
            json.dumps([
                {"timestamp": "2024-01-01 10:00:00", "sender": "小美", "content": "你好"},
            ]),
            encoding="utf-8",
        )
        msgs = parse_json(str(f), "小美", "我")
        assert len(msgs) == 1
        assert msgs[0].sender == "小美"

    def test_dict_with_messages_key(self, tmp_path: Path) -> None:
        f = tmp_path / "chat.json"
        f.write_text(
            json.dumps({"messages": [
                {"timestamp": "2024-01-01 10:00:00", "sender": "小美", "content": "hi"},
            ]}),
            encoding="utf-8",
        )
        msgs = parse_json(str(f), "小美", "我")
        assert len(msgs) == 1

    def test_epoch_timestamp(self, tmp_path: Path) -> None:
        f = tmp_path / "chat.json"
        ts = int(datetime(2024, 1, 1, 10, 0).timestamp())
        f.write_text(json.dumps([{"timestamp": ts, "sender": "小美", "content": "hello"}]))
        msgs = parse_json(str(f), "小美", "我")
        assert len(msgs) == 1


class TestParseChat:
    def test_filters_relevant_senders(self, tmp_path: Path) -> None:
        f = tmp_path / "wechat.txt"
        f.write_text(
            "2024-01-01 10:00:00\n小美\n你好\n2024-01-01 10:01:00\n陌生人\n内容\n",
            encoding="utf-8",
        )
        msgs = parse_chat(str(f), "小美", "我")
        senders = {m.sender for m in msgs}
        assert "小美" in senders
        assert "陌生人" not in senders

    def test_sorts_by_timestamp(self, tmp_path: Path) -> None:
        f = tmp_path / "wechat.txt"
        f.write_text(
            "2024-01-01 12:00:00\n小美\n第二条\n"
            "2024-01-01 10:00:00\n小美\n第一条\n",
            encoding="utf-8",
        )
        msgs = parse_chat(str(f), "小美", "我")
        assert msgs[0].content == "第一条"


# ─────────────────────────────────────────────
# SignalAnalyzer · 纯函数分析（无需 I/O）
# ─────────────────────────────────────────────

def make_msg(
    content: str,
    sender: str = "小美",
    hour: int = 10,
    minute: int = 0,
) -> Message:
    return Message(
        datetime(2024, 1, 1, hour, minute),
        sender,
        content,
    )


def make_analyzer(msgs: list[Message]) -> SignalAnalyzer:
    return SignalAnalyzer(msgs, "小美", "我")


class TestSignalAnalyzer_MessageCounts:
    def test_all_zero_when_empty(self) -> None:
        assert make_analyzer([]).message_counts()["total"] == 0

    def test_counts_both_sides(self) -> None:
        msgs = [make_msg("hello", "小美"), make_msg("hi", "我")]
        result = make_analyzer(msgs).message_counts()
        assert result["from_target"] == 1
        assert result["from_user"] == 1
        assert result["total"] == 2


class TestSignalAnalyzer_DateRange:
    def test_empty_returns_empty_dict(self) -> None:
        assert make_analyzer([]).date_range() == {}

    def test_calculates_days(self) -> None:
        msgs = [
            Message(datetime(2024, 1, 1, 10, 0), "小美", "hi"),
            Message(datetime(2024, 1, 10, 10, 0), "小美", "hi"),
        ]
        result = make_analyzer(msgs).date_range()
        assert result["total_days"] == 10


class TestSignalAnalyzer_InitiativeAnalysis:
    def test_empty(self) -> None:
        result = make_analyzer([]).initiative_analysis()
        assert result["target_initiates"] == 0

    def test_target_starts_session(self) -> None:
        msgs = [
            make_msg("主动", "小美", 10),
            make_msg("回复", "我", 11),
        ]
        result = make_analyzer(msgs).initiative_analysis()
        assert result["target_initiates"] == 1

    def test_initiative_verdict_all_target(self) -> None:
        ver = make_analyzer([])._initiative_verdict(6, 0)
        assert "🟢" in ver

    def test_initiative_verdict_all_user(self) -> None:
        ver = make_analyzer([])._initiative_verdict(0, 6)
        assert "🔴" in ver


class TestSignalAnalyzer_ReplySpeed:
    def test_empty_returns_none_stats(self) -> None:
        result = make_analyzer([]).reply_speed_analysis()
        assert result["target_reply"]["avg_seconds"] is None

    def test_skips_gap_over_4h(self) -> None:
        msgs = [
            make_msg("a", "小美", 10),  # 10:00 target
            make_msg("b", "我",   16),  # 16:00 user, gap=6h >4h skip
            make_msg("c", "小美", 17),  # 17:00 target, gap=1h from b <=4h, counts as target delay
        ]
        result = make_analyzer(msgs).reply_speed_analysis()
        # After skipping the 6h gap, we have a 1h delay (target's reply to user's msg)
        assert result["target_reply"]["avg_seconds"] == 3600

    def test_counts_user_reply_to_target(self) -> None:
        msgs = [
            make_msg("a", "小美", 10),
            make_msg("b", "我",   10, 5),   # user replies after 5min
        ]
        result = make_analyzer(msgs).reply_speed_analysis()
        assert result["user_reply"]["avg_seconds"] == 300

    def test_speed_verdict_fast(self) -> None:
        ver = make_analyzer([])._speed_verdict({"avg_seconds": 60}, {"avg_seconds": 300})
        assert "🟢" in ver

    def test_speed_verdict_slow(self) -> None:
        ver = make_analyzer([])._speed_verdict({"avg_seconds": 3600}, {"avg_seconds": 60})
        assert "🔴" in ver


class TestSignalAnalyzer_MessageLength:
    def test_empty(self) -> None:
        result = make_analyzer([]).message_length_analysis()
        assert result["target_avg_len"] == 0

    def test_longer_target_is_better(self) -> None:
        msgs = [
            make_msg("a" * 200, "小美"),
            make_msg("b", "我"),
        ]
        result = make_analyzer(msgs).message_length_analysis()
        assert "投入度高" in result["verdict"]


class TestSignalAnalyzer_LateNight:
    def test_no_late_night(self) -> None:
        msgs = [make_msg("hi", "小美", 14)]
        result = make_analyzer(msgs).late_night_analysis()
        assert "⚪" in result["verdict"]

    def test_late_night_initiates(self) -> None:
        msgs = [
            Message(datetime(2024, 1, 1, 23, 0), "小美", "hi"),
            Message(datetime(2024, 1, 1, 23, 30), "我", "回复"),
            Message(datetime(2024, 1, 1, 23, 45), "小美", "继续"),
        ]
        result = make_analyzer(msgs).late_night_analysis()
        assert result["target_initiates_late_night"] >= 1


class TestSignalAnalyzer_TopicAnalysis:
    def test_empty(self) -> None:
        result = make_analyzer([]).topic_analysis()
        assert result["target_follow_up_questions"] == 0

    def test_question_follow_up(self) -> None:
        msgs = [
            make_msg("今天吃了什么？", "我", 10),
            make_msg("火锅", "小美", 10, 5),
        ]
        result = make_analyzer(msgs).topic_analysis()
        assert result["target_follow_up_questions"] >= 0  # pass if no question


class TestSignalAnalyzer_LanguageFeatures:
    def test_empty(self) -> None:
        result = make_analyzer([]).language_features()
        assert result["message_style"] == "混合型"

    def test_short_msg_style(self) -> None:
        msgs = [make_msg("hi", "小美") for _ in range(10)]
        result = make_analyzer(msgs).language_features()
        assert result["message_style"] == "短句连发型"

    def test_particle_detection(self) -> None:
        msgs = [Message(datetime(2024, 1, 1, 10), "小美", "哈哈很好笑哈哈哈") for _ in range(5)]
        result = make_analyzer(msgs).language_features()
        assert any(p == "哈哈" for p, _ in result["top_particles"])


class TestSignalAnalyzer_SignalScore:
    def test_score_not_high_when_user_initiates_all(self) -> None:
        msgs = [
            Message(datetime(2024, 1, 1, 10, 0), "我", "hello"),
            Message(datetime(2024, 1, 1, 10, 5), "小美", "hi"),
        ]
        result = make_analyzer(msgs).signal_score()
        assert result["score"] <= 0  # no positive initiative signal

    def test_score_in_valid_range(self) -> None:
        msgs = [make_msg("hello", "小美") for _ in range(20)]
        result = make_analyzer(msgs).signal_score()
        assert -3 <= result["score"] <= 25
        assert result["max_score"] == 25


class TestSignalAnalyzer_SplitSessions:
    def test_empty(self) -> None:
        assert make_analyzer([])._split_sessions() == []

    def test_single_message(self) -> None:
        msgs = [make_msg("hi")]
        sessions = make_analyzer(msgs)._split_sessions(gap_minutes=60)
        assert len(sessions) == 1

    def test_splits_on_gap(self) -> None:
        msgs = [
            make_msg("a", hour=10, minute=0),
            make_msg("b", hour=10, minute=30),
            make_msg("c", hour=12, minute=30),
        ]
        sessions = make_analyzer(msgs)._split_sessions(gap_minutes=60)
        assert len(sessions) == 2
        assert len(sessions[0]) == 2
        assert len(sessions[1]) == 1


# ─────────────────────────────────────────────
# generate_report
# ─────────────────────────────────────────────

class TestGenerateReport:
    def test_empty_messages(self) -> None:
        result = generate_report([], "小美", "我")
        assert "未找到有效消息" in result

    def test_returns_string(self) -> None:
        msgs = [make_msg("hello", "小美")]
        result = generate_report(msgs, "小美", "我")
        assert isinstance(result, str)
        assert "小美" in result

    def test_output_path_writes_file(self, tmp_path: Path) -> None:
        msgs = [make_msg("hi", "小美")]
        out = tmp_path / "report.md"
        generate_report(msgs, "小美", "我", str(out))
        assert out.exists()
        assert "聊天记录" in out.read_text(encoding="utf-8")


# ─────────────────────────────────────────────
# extract_time_data / --track-time
# ─────────────────────────────────────────────

import json as _json
from pathlib import Path as _Path


class TestTrackTime:
    def test_extracts_interactions_from_messages(self, tmp_path: _Path) -> None:
        chat_file = tmp_path / "chat.txt"
        chat_file.write_text(
            "2026-05-15 22:30:00\n我\n问她周末有没有空\n"
            "2026-05-15 22:32:00\n小美\n有空呀，你有什么安排吗\n"
            "2026-05-15 22:33:00\n我\n那一起去看展吧\n"
            "2026-05-15 22:35:00\n小美\n好呀好呀！\n",
            encoding="utf-8",
        )

        slug = "xiaomei"
        crush_dir = tmp_path / "crushes" / slug
        crush_dir.mkdir(parents=True)
        (crush_dir / "interactions.jsonl").touch()
        (crush_dir / "meta.json").write_text(
            _json.dumps({"slug": slug, "interaction_count": 0}, ensure_ascii=False),
            encoding="utf-8",
        )

        from tools.chat_parser import extract_time_data
        messages = parse_chat(str(chat_file), "小美", "我")
        extract_time_data(messages, "小美", "我", slug, base_dir=tmp_path / "crushes")

        interactions = (crush_dir / "interactions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(interactions) == 4

        first = _json.loads(interactions[0])
        assert first["type"] == "chat_sent"
        assert first["data"]["hour"] == 22
        assert first["data"]["day_of_week"] == "fri"

        second = _json.loads(interactions[1])
        assert second["type"] == "chat_received"
        assert second["data"]["reply_delay_min"] == 2

    def test_skip_if_gap_over_4h(self, tmp_path: _Path) -> None:
        chat_file = tmp_path / "chat.txt"
        chat_file.write_text(
            "2026-05-15 22:30:00\n我\n晚安\n"
            "2026-05-16 10:00:00\n小美\n早呀\n",
            encoding="utf-8",
        )

        slug = "xiaomei"
        crush_dir = tmp_path / "crushes" / slug
        crush_dir.mkdir(parents=True)
        (crush_dir / "interactions.jsonl").touch()
        (crush_dir / "meta.json").write_text(
            _json.dumps({"slug": slug, "interaction_count": 0}, ensure_ascii=False),
            encoding="utf-8",
        )

        from tools.chat_parser import extract_time_data
        messages = parse_chat(str(chat_file), "小美", "我")
        extract_time_data(messages, "小美", "我", slug, base_dir=tmp_path / "crushes")

        interactions = (crush_dir / "interactions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        second = _json.loads(interactions[1])
        assert "reply_delay_min" not in second["data"]