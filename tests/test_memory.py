import json
import pytest
from tools import memory
from tools.memory import append_event, append_records, get_recent_events, load_context, rebuild_state_from_events, take_snapshot
from tools.time_tracker import import_messages


def report(base,source,summary='她拒绝约会'):
    return append_event('alice','user_report',{'summary':summary},base,source_refs=source)


def test_no_implicit_profile(tmp_path,source):
    base=tmp_path/'none'
    with pytest.raises(FileNotFoundError):report(base,source)
    assert not base.exists()


def test_repeat_is_idempotent_and_drafts_not_interactions(base,source):
    r=report(base,source)
    assert report(base,source)==r
    append_event('alice','advice',{'summary':'邀请喝咖啡','draft':'周末喝杯咖啡？'},base,related_record_ids=[r['record_id']])
    append_event('alice','assessment',{'summary':'信息不足'},base,related_record_ids=[r['record_id']])
    meta=json.loads((base/'alice/meta.json').read_text())
    assert meta['record_count']==3 and meta['interaction_count']==0 and meta['last_interaction'] is None


def test_correction_invalidates_transitive_judgments(base,source):
    r=report(base,source)
    a=append_event('alice','assessment',{'summary':'旧判断','supporting_ids':[r['record_id']]},base)
    b=append_event('alice','advice',{'summary':'旧建议'},base,related_record_ids=[a['record_id']])
    append_event('alice','correction',{'summary':'那句话是第三方说的'},base,source_refs=source,supersedes=[r['record_id']])
    records=get_recent_events('alice',base_dir=base,include_history=True)
    statuses={x['record_id']:x['status'] for x in records}
    assert statuses[r['record_id']]=='invalidated'
    assert statuses[a['record_id']]==statuses[b['record_id']]=='needs_review'
    assert '旧判断' not in (base/'alice/state.md').read_text(encoding='utf-8')
    with pytest.raises(ValueError,match='invalidated'):append_event('alice','assessment',{'summary':'again'},base,related_record_ids=[a['record_id']])


def test_identity_correction_and_reimport(base,exported,source):
    msgs=exported().messages
    import_messages('alice',msgs,base)
    identity=next(r for r in get_recent_events('alice',base_dir=base) if r['kind']=='identity_mapping' and r['data']['role']=='target')
    append_event('alice','identity_mapping',{**identity['data'],'role':'third_party','summary':'实际是朋友'},base,
                 source_refs=source,supersedes=[identity['record_id']])
    assert json.loads((base/'alice/meta.json').read_text())['needs_review_count']==1
    import_messages('alice',msgs,base)
    interactions=[json.loads(x) for x in (base/'alice/interactions.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(interactions)==2
    assert interactions[-1]['message']['role']=='third_party'


def test_actions_require_confirmation_and_outcomes_reference_actions(base,source):
    advice=append_event('alice','advice',{'summary':'还没发的草稿'},base)
    with pytest.raises(ValueError,match='confirmation'):
        append_event('alice','action_report',{'summary':'发消息'},base,source_refs=source)
    with pytest.raises(ValueError,match='action_report'):
        append_event('alice','outcome',{'summary':'回复了','action_id':advice['record_id']},base,source_refs=source)
    action=append_event('alice','action_report',{'summary':'我实际发了不同的内容','confirmed':True},base,source_refs=source)
    outcome=append_event('alice','outcome',{'summary':'她拒绝','action_id':action['record_id']},base,source_refs=source)
    assert outcome['related_record_ids']==[action['record_id']]


@pytest.mark.parametrize('kind',['user_report','observation','preference','identity_mapping','action_report','outcome','correction'])
def test_factual_record_requires_source(base,kind):
    with pytest.raises(ValueError):append_event('alice',kind,{'summary':'x'},base)


def test_batch_validation_writes_nothing(base,source):
    before=(base/'alice/events.jsonl').read_bytes()
    with pytest.raises(ValueError):append_records('alice',[{'kind':'user_report','data':{'summary':'valid'},'source_refs':source},
                                                         {'kind':'unknown','data':{'summary':'invalid'}}],base)
    assert (base/'alice/events.jsonl').read_bytes()==before


def test_manual_edits_detected_preserved_and_rebuilt(base,source):
    report(base,source)
    p=base/'alice/state.md';p.write_text('手工笔记',encoding='utf-8')
    with pytest.raises(RuntimeError,match='Edited'):load_context('alice',base_dir=base)
    rebuild_state_from_events('alice',base)
    assert any(p.read_text(encoding='utf-8')=='手工笔记' for p in (base/'alice/versions').glob('*/files/state.md'))
    assert '手工笔记' not in load_context('alice',base_dir=base)


def test_interrupted_commit_recovers_without_losing_event(base,source,monkeypatch):
    original=memory._project
    def fail(*args):raise OSError('injected failure')
    monkeypatch.setattr(memory,'_project',fail)
    with pytest.raises(OSError):report(base,source)
    with pytest.raises(RuntimeError,match='Incomplete'):load_context('alice',base_dir=base)
    monkeypatch.setattr(memory,'_project',original)
    rebuild_state_from_events('alice',base)
    assert get_recent_events('alice',base_dir=base)[0]['data']['summary']=='她拒绝约会'


def test_invalid_ledger_never_silently_drops_line(base,source):
    report(base,source)
    p=base/'alice/events.jsonl';p.write_text(p.read_text(encoding='utf-8')+'BROKEN\n',encoding='utf-8')
    with pytest.raises(ValueError,match='line 2'):rebuild_state_from_events('alice',base)
    assert p.read_text(encoding='utf-8').endswith('BROKEN\n')


def test_context_includes_dependencies_and_discloses_scope(base,source):
    r=report(base,source,'早期明确拒绝')
    for i in range(6):report(base,source,f'无关记录 {i}')
    a=append_event('alice','assessment',{'summary':'当前仍不能推断好感','opposing_ids':[r['record_id']]},base)
    result=json.loads(load_context('alice',base_dir=base,query='当前',limit=1))
    assert [x['record_id'] for x in result['records']]==[r['record_id'],a['record_id']]
    assert result['selected_records']==2 and result['total_records']==8
    assert 'not the complete history' in result['scope']


def test_snapshot_is_valid_json_and_rebuild_is_stable(base,source):
    report(base,source)
    before={name:(base/'alice'/name).read_bytes() for name in memory.PROJECTIONS}
    path=take_snapshot('alice',base)
    assert json.loads(path.read_text())['schema_version']==2
    rebuild_state_from_events('alice',base)
    assert before=={name:(base/'alice'/name).read_bytes() for name in memory.PROJECTIONS}


def test_unknown_identity_is_revisionable(base,source,exported):
    msgs=exported([{'senderId':'x','localId':1,'content':'你好'}],conversationType='group').messages
    import_messages('alice',msgs,base)
    identity=next(r for r in get_recent_events('alice',base_dir=base) if r['kind']=='identity_mapping')
    assert identity['data']['role']=='unknown'
    append_event('alice','identity_mapping',{**identity['data'],'role':'third_party','summary':'确认是朋友'},base,
                 source_refs=source,supersedes=[identity['record_id']])
    import_messages('alice',msgs,base)
    observation=next(r for r in get_recent_events('alice',base_dir=base) if r['kind']=='observation')
    assert observation['data']['message']['role']=='third_party'


def test_reimport_cannot_revive_a_corrected_fact(base,source,exported):
    msgs=exported().messages;import_messages('alice',msgs,base)
    observation=next(r for r in get_recent_events('alice',base_dir=base) if r['kind']=='observation')
    append_event('alice','correction',{'summary':'这条内容来自错误导出，撤回'},base,source_refs=source,supersedes=[observation['record_id']])
    before=(base/'alice/events.jsonl').read_bytes()
    with pytest.raises(ValueError,match='re-verification'):import_messages('alice',msgs,base)
    assert (base/'alice/events.jsonl').read_bytes()==before
