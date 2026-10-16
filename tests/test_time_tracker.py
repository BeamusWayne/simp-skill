from datetime import datetime, timezone
import json
import pytest
from tools.time_tracker import import_messages, get_interactions, record_interaction, analyze_timeline, analyze_reply_times


def test_idempotent_import_and_no_last_interaction_inflation(base,exported):
    msgs=exported().messages
    assert import_messages('alice',msgs,base)['imported']==2
    before=(base/'alice/meta.json').read_bytes()
    assert import_messages('alice',msgs,base)['duplicates']==2
    assert (base/'alice/meta.json').read_bytes()==before
    assert len(get_interactions('alice',base_dir=base))==2
    assert analyze_reply_times('alice',base_dir=base)['samples'][0]['seconds']==60


def test_time_window_has_explicit_anchor(base,exported):
    import_messages('alice',exported().messages,base)
    now=datetime(2026,5,11,tzinfo=timezone.utc)
    assert len(get_interactions('alice',2,base,now=now))==2
    assert len(get_interactions('alice',2,base,now=datetime(2027,1,1,tzinfo=timezone.utc)))==0
    assert len(get_interactions('alice',base_dir=base))==2
    with pytest.raises(ValueError):get_interactions('alice',2,base,now=datetime(2026,5,11))


def test_unknown_event_time_never_defaults_to_now(base):
    record_interaction('alice','meeting',{'summary':'上次确实见过面，忘了日期','confirmed':True},base_dir=base)
    meta=json.loads((base/'alice/meta.json').read_text())
    assert meta['last_interaction'] is None and meta['interaction_count']==1
    assert len(get_interactions('alice',base_dir=base))==1
    assert get_interactions('alice',30,base)==[]


def test_unconfirmed_event_rejected(base):
    with pytest.raises(ValueError,match='confirmed'):
        record_interaction('alice','chat_sent',{'summary':'准备发送'},base_dir=base)


def test_statistics_do_not_recommend_messaging_hours(base,exported):
    import_messages('alice',exported().messages,base)
    report=analyze_timeline('alice',base_dir=base)
    assert report['active_hours']=={'10':2}
    assert 'Not an ideal' in report['active_hours_note']
    assert 'score' not in json.dumps(report)


def test_failed_import_is_atomic(base,exported):
    msgs=exported().messages;import_messages('alice',msgs,base)
    before=(base/'alice/events.jsonl').read_bytes()
    msgs[-1].content='changed'
    with pytest.raises(ValueError,match='Conflicting'):import_messages('alice',msgs,base)
    assert (base/'alice/events.jsonl').read_bytes()==before


def test_media_only_message_is_importable(base,exported):
    result=exported([{'localId':1,'isSend':1,'type':'image','content':''}])
    assert import_messages('alice',result.messages,base)['imported']==1
    assert len(get_interactions('alice',base_dir=base))==1


@pytest.mark.parametrize('days',[0,-1])
def test_invalid_window_rejected(base,days):
    with pytest.raises(ValueError):analyze_timeline('alice',days,base)
