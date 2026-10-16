import json
from pathlib import Path
import re
from collections import Counter
import pytest
from tools.chat_parser import parse_export
ROOT=Path(__file__).resolve().parents[1]


def test_entry_references_exist_and_all_prompts_reachable():
    text=(ROOT/'SKILL.md').read_text(encoding='utf-8')
    refs=set(re.findall(r'`((?:prompts|docs)/[^`]+\.md)`',text))
    assert refs
    assert all((ROOT/ref).is_file() for ref in refs)
    assert {p.relative_to(ROOT).as_posix() for p in (ROOT/'prompts').glob('*.md')} <= refs
    assert text.startswith('---\nname: simp\n')


def test_eval_partition_and_observable_checks():
    cases=[json.loads(line) for line in (ROOT/'evals/cases.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(cases)==24 and len({c['id'] for c in cases})==24
    assert Counter(c['split'] for c in cases)=={'development':12,'holdout':12}
    for group in range(1,9):assert any(c['group']==group and c['split']=='holdout' for c in cases)
    for case in cases:
        assert case['must'] and case['must_not'] and case['synthetic']
        if case['fixture']:assert (ROOT/case['fixture']).exists()


@pytest.mark.parametrize('name',['wechat.txt','qq.txt','wechat.csv','wechat.html','qq.mht','direct.json'])
def test_committed_format_fixtures(name):
    result=parse_export(ROOT/'tests/fixtures/v2'/name,'小美')
    assert len(result.messages)==2
    assert all(m.source_refs for m in result.messages)


def test_tools_have_no_romantic_scoring_api():
    import tools.chat_parser as chat
    import tools.social_parser as social
    assert not hasattr(chat,'SignalAnalyzer')
    assert not hasattr(social,'SIGNAL_KEYWORDS')
