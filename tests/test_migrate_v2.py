import json
import pytest
from tools.migrate_v2 import preview, migrate, recover, check
from tools.skill_writer import rollback_crush
from tools.storage import data_files
from tools.memory import get_recent_events, append_event, load_context


@pytest.fixture
def legacy(tmp_path):
    base=tmp_path/'profiles';root=base/'alice';root.mkdir(parents=True)
    files={'meta.json':'{"signal_score":20,"stage":"confess","mbti":"INFP"}',
           'events.jsonl':'{"type":"analysis","score":20}\nMALFORMED\n',
           'interactions.jsonl':'{"type":"chat_sent"}\n', 'state.md':'旧版强烈绿灯',
           'memories/chats/raw.txt':'原始聊天', 'snapshots/old.json':'{"score":20}'}
    for name,text in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    return base


def state(root):return {rel:(root/rel).read_bytes() for rel in data_files(root)}


def test_preview_is_readonly_and_reports_damage(legacy):
    root=legacy/'alice';before=state(root);all_before=set(root.rglob('*'))
    result=preview('alice',legacy)
    assert result['issues'][0]['line']==2
    assert state(root)==before and set(root.rglob('*'))==all_before


def test_migrate_preserves_legacy_no_promotion_and_is_repeatable(legacy):
    root=legacy/'alice';before=state(root)
    result=migrate('alice',legacy,expected_fingerprint=preview('alice',legacy)['fingerprint'])
    assert result['status']=='migrated'
    assert all(r['kind']=='legacy_record' for r in get_recent_events('alice',100,base_dir=legacy,include_history=True))
    assert get_recent_events('alice',base_dir=legacy)==[]
    for name,data in before.items():
        assert (root/name if name.startswith('memories/') else root/'legacy/v1'/name).read_bytes()==data
    meta=json.loads((root/'meta.json').read_text(encoding='utf-8'))
    assert 'signal_score' not in meta and meta['interaction_count']==0
    after=state(root);assert migrate('alice',legacy)['status']=='already_v2';assert state(root)==after
    rollback_crush('alice',result['backup'],legacy)
    assert state(root)==before


def test_changed_source_rejects_stale_preview(legacy):
    fingerprint=preview('alice',legacy)['fingerprint']
    (legacy/'alice/state.md').write_text('changed')
    before=state(legacy/'alice')
    with pytest.raises(ValueError,match='changed'):migrate('alice',legacy,expected_fingerprint=fingerprint)
    assert before==state(legacy/'alice')


@pytest.mark.parametrize('step',['marker','archive:events.jsonl','archive:meta.json','archive:state.md','events','meta','projections','report'])
def test_recovery_at_each_write_boundary(legacy,step):
    root=legacy/'alice';before=state(root)
    def fail(current):
        if current==step:raise OSError('injected: '+step)
    with pytest.raises(OSError):migrate('alice',legacy,checkpoint=fail)
    with pytest.raises(RuntimeError,match='maintenance'):load_context('alice',base_dir=legacy)
    with pytest.raises(RuntimeError):migrate('alice',legacy)
    recover('alice',legacy)
    assert state(root)==before
    assert migrate('alice',legacy)['status']=='migrated'


def test_legacy_cannot_be_used_as_current_evidence(legacy):
    migrate('alice',legacy)
    record=get_recent_events('alice',100,base_dir=legacy,include_history=True)[0]
    with pytest.raises(ValueError,match='re-verification'):
        append_event('alice','assessment',{'summary':'旧分数支持表白'},legacy,related_record_ids=[record['record_id']])


def test_missing_meta_supported_but_malformed_meta_fails_readonly(legacy):
    root=legacy/'alice';(root/'meta.json').unlink()
    assert preview('alice',legacy)['source_schema']==1
    (root/'meta.json').write_text('{BROKEN')
    before=state(root)
    with pytest.raises(ValueError):preview('alice',legacy)
    assert state(root)==before


def test_check_detects_changed_archive(legacy):
    migrate('alice',legacy)
    assert check('alice',legacy)['status']=='valid'
    (legacy/'alice/legacy/v1/state.md').write_text('changed')
    with pytest.raises(ValueError,match='source has changed'):check('alice',legacy)


def test_failure_inside_projection_writes_is_blocked_and_recoverable(legacy,monkeypatch):
    import tools.memory as memory
    root=legacy/'alice';before=state(root);original=memory.atomic_write
    def fail(path,content):
        if path.name=='strategy.md':raise OSError('mid-projection')
        return original(path,content)
    monkeypatch.setattr(memory,'atomic_write',fail)
    with pytest.raises(OSError):migrate('alice',legacy)
    with pytest.raises(RuntimeError):load_context('alice',base_dir=legacy)
    recover('alice',legacy)
    assert state(root)==before


def test_recovery_itself_can_be_retried(legacy):
    root=legacy/'alice';before=state(root)
    def fail(step):raise OSError('injected')
    with pytest.raises(OSError):migrate('alice',legacy,checkpoint=fail)
    with pytest.raises(OSError):recover('alice',legacy,checkpoint=fail)
    recover('alice',legacy)
    assert state(root)==before
