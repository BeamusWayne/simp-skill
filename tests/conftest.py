import json
from pathlib import Path
import pytest
from tools.chat_parser import parse_export
from tools.skill_writer import init_crush


@pytest.fixture
def base(tmp_path):
    base = tmp_path / 'profiles'
    init_crush('alice', base)
    return base


@pytest.fixture
def source():
    return [{'kind': 'user', 'locator': 'session:1', 'excerpt': '用户确认的实际内容'}]


@pytest.fixture
def exported(tmp_path):
    def make(rows=None, **meta):
        path = tmp_path / 'export.json'
        default = {'accountId': 'u', 'peerId': 't', 'conversationId': 'chat', 'conversationType': 'direct'}
        default.update(meta)
        default['messages'] = rows if rows is not None else [
            {'localId': '1', 'isSend': 1, 'time': '2026-05-10T10:00:00+08:00', 'content': '周末想一起吃饭吗？'},
            {'localId': '2', 'isSend': 0, 'time': '2026-05-10T10:01:00+08:00', 'content': '我不想约会，只当朋友。'}]
        path.write_text(json.dumps(default, ensure_ascii=False), encoding='utf-8')
        return parse_export(path, '小美')
    return make
