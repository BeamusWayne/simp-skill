import json
from pathlib import Path
import subprocess
import sys
import pytest
from tools.skill_writer import init_crush, backup_crush, rollback_crush, recover_restore, update_meta, list_versions, list_crushes
from tools.storage import data_files, member, profile_lock, verify_backup
from tools.memory import append_event, load_context


def state(root):return {rel:(root/rel).read_bytes() for rel in data_files(root)}


@pytest.mark.parametrize('slug',['../outside','a/b','a\\b','','..','.','C:\\outside'])
def test_slug_rejects_escape(tmp_path,slug):
    with pytest.raises(ValueError):init_crush(slug,tmp_path)


def test_unicode_initialization_is_idempotent(tmp_path):
    root=init_crush('小美',tmp_path)
    before=state(root)
    assert init_crush('小美',tmp_path)==root
    assert state(root)==before
    assert json.loads((root/'meta.json').read_text(encoding='utf-8'))['schema_version']==2


def test_profile_backup_and_full_rollback(base,source):
    root=base/'alice'
    (root/'memories/chats/raw.txt').write_text('original')
    before=state(root);backup=backup_crush('alice',base)
    append_event('alice','user_report',{'summary':'new'},base,source_refs=source)
    (root/'memories/chats/raw.txt').write_text('changed')
    (root/'memories/photos/new.jpg').write_bytes(b'new')
    result=rollback_crush('alice',backup,base)
    assert state(root)==before
    saved=verify_backup(root,result['saved_current_as'])
    assert 'memories/photos/new.jpg' in saved['files']
    assert len(list_versions('alice',base))==2


def test_restore_interruption_blocks_reads_and_resumes(base,source):
    root=base/'alice';before=state(root);backup=backup_crush('alice',base)
    append_event('alice','user_report',{'summary':'new'},base,source_refs=source)
    def fail(step):raise OSError(step)
    with pytest.raises(OSError):rollback_crush('alice',backup,base,checkpoint=fail)
    with pytest.raises(RuntimeError,match='maintenance'):load_context('alice',base_dir=base)
    recover_restore('alice',base)
    assert state(root)==before


def test_tampered_backup_and_prefix_refused_before_restore(base):
    root=base/'alice';backup=backup_crush('alice',base);before=state(root)
    with pytest.raises((ValueError,FileNotFoundError)):rollback_crush('alice',backup[:10],base)
    (root/'versions'/backup/'files/meta.json').write_text('{}')
    with pytest.raises(ValueError,match='checksum'):rollback_crush('alice',backup,base)
    assert state(root)==before


def test_path_members_stay_inside(base):
    with pytest.raises(ValueError):member(base/'alice','../outside')
    with pytest.raises(ValueError):member(base/'alice',str(base/'outside'))


def test_metadata_updates_are_typed_no_scores(base):
    update_meta('alice',base,nickname='小美',mode='sweet')
    update_meta('alice',base,nickname='小美',mode='strategic')
    meta=json.loads((base/'alice/meta.json').read_text(encoding='utf-8'))
    assert meta['nickname']=='小美' and meta['mode']=='strategic'
    before=state(base/'alice')
    with pytest.raises(ValueError,match='score'):update_meta('alice',base,score=20)
    assert before==state(base/'alice')
    assert list_crushes(base)[0]['nickname']=='小美'


def test_process_lock_prevents_second_writer_and_releases(base):
    code="from tools.skill_writer import backup_crush; from pathlib import Path; import sys; backup_crush('alice', Path(sys.argv[1]))"
    with profile_lock(base/'alice'):
        result=subprocess.run([sys.executable,'-c',code,str(base)],capture_output=True,text=True)
        assert result.returncode != 0 and 'busy' in result.stderr
    result=subprocess.run([sys.executable,'-c',code,str(base)],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
