import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests/fixtures/v2'


def invoke(monkeypatch,capsys,name,*args):
    monkeypatch.setattr(sys,'argv',[name,*map(str,args)])
    importlib.import_module('tools.'+name).main()
    return capsys.readouterr().out


def test_actual_script_end_to_end_with_unicode_path(tmp_path):
    base=tmp_path/'中文 档案'
    env={**os.environ,'PYTHONIOENCODING':'utf-8'}
    commands=[['skill_writer.py','--action','init','--slug','小美','--base-dir',str(base)],
              ['chat_parser.py',str(FIXTURES/'direct.json'),'小美','--json','--track-time','--slug','小美','--base-dir',str(base)],
              ['time_tracker.py','analyze','小美','--reply','--base-dir',str(base)],
              ['memory.py','context','小美','--base-dir',str(base)],
              ['migrate_v2.py','小美','--check','--base-dir',str(base)]]
    results=[]
    for name,*args in commands:
        result=subprocess.run([sys.executable,str(ROOT/'tools'/name),*args],capture_output=True,encoding='utf-8',env=env)
        assert result.returncode==0,result.stderr
        results.append(json.loads(result.stdout))
    assert len(results[1]['messages'])==2 and results[2]['valid_pairs']==1
    assert results[-1]['status']=='valid'


def test_memory_cli_all_operations(base,source,tmp_path,monkeypatch,capsys):
    payload=tmp_path/'record.json';payload.write_text(json.dumps({'kind':'user_report','data':{'summary':'真实转述'},'source_refs':source}),encoding='utf-8')
    result=invoke(monkeypatch,capsys,'memory','append','alice','--input',payload,'--base-dir',base)
    assert json.loads(result)['kind']=='user_report'
    for command in ['events','timeline','context','snapshot','rebuild']:
        assert invoke(monkeypatch,capsys,'memory',command,'alice','--base-dir',base)


def test_writer_cli_lifecycle(base,monkeypatch,capsys):
    assert invoke(monkeypatch,capsys,'skill_writer','--action','list','--base-dir',base)
    invoke(monkeypatch,capsys,'skill_writer','--action','update-meta','--slug','alice','--nickname','新昵称','--base-dir',base)
    backup=json.loads(invoke(monkeypatch,capsys,'skill_writer','--action','backup','--slug','alice','--base-dir',base))
    assert invoke(monkeypatch,capsys,'skill_writer','--action','versions','--slug','alice','--base-dir',base)
    assert invoke(monkeypatch,capsys,'skill_writer','--action','rollback','--slug','alice','--version',backup,'--base-dir',base)


@pytest.mark.parametrize('args',[['--action','list','--score','20'],['--action','init'],['--action','rollback','--slug','alice']])
def test_writer_cli_rejects_removed_or_missing_args(base,monkeypatch,capsys,args):
    before=(base/'alice/events.jsonl').read_bytes()
    with pytest.raises(SystemExit) as error:invoke(monkeypatch,capsys,'skill_writer',*args,'--base-dir',base)
    assert error.value.code==2 and (base/'alice/events.jsonl').read_bytes()==before


def test_chat_cli_readonly_and_output_guard(tmp_path,base,monkeypatch,capsys):
    result=invoke(monkeypatch,capsys,'chat_parser',FIXTURES/'direct.json','小美','--json')
    assert len(json.loads(result)['messages'])==2
    output=tmp_path/'report.md'
    monkeypatch.setattr(sys,'argv',['chat_parser',str(FIXTURES/'partial.jsonl'),'小美','--output',str(output)])
    importlib.import_module('tools.chat_parser').main()
    assert output.exists() and 'invalid_json' in capsys.readouterr().err
    with pytest.raises(SystemExit):invoke(monkeypatch,capsys,'chat_parser',FIXTURES/'direct.json','小美','--output',FIXTURES/'direct.json')
    with pytest.raises(SystemExit):invoke(monkeypatch,capsys,'chat_parser',FIXTURES/'direct.json','小美','--track-time')
    with pytest.raises(SystemExit):invoke(monkeypatch,capsys,'chat_parser',FIXTURES/'direct.json','小美','--track-time','--slug','alice','--base-dir',base,'--output',base/'alice/events.jsonl')


def test_time_cli_record_and_analysis(base,tmp_path,monkeypatch,capsys):
    invoke(monkeypatch,capsys,'time_tracker','record','alice','meeting','--summary','已经见面','--confirmed','--time','2026-05-10T10:00:00+08:00','--base-dir',base)
    for option in ['--frequency','--milestones','--golden','--reply']:
        assert invoke(monkeypatch,capsys,'time_tracker','analyze','alice',option,'--base-dir',base)
    out=tmp_path/'timeline.json'
    invoke(monkeypatch,capsys,'time_tracker','analyze','alice','--days','5','--now','2026-05-11T10:00:00+08:00','--output',out,'--base-dir',base)
    assert json.loads(out.read_text(encoding='utf-8'))['interactions']==1
    with pytest.raises(SystemExit):invoke(monkeypatch,capsys,'time_tracker','analyze','alice','--now','bad','--base-dir',base)
    with pytest.raises(SystemExit):invoke(monkeypatch,capsys,'time_tracker','analyze','alice','--output',base/'alice/events.jsonl','--base-dir',base)


def test_migration_cli_preview_apply_check(tmp_path,monkeypatch,capsys):
    base=tmp_path/'profiles';shutil.copytree(FIXTURES/'legacy',base/'alice')
    preview=json.loads(invoke(monkeypatch,capsys,'migrate_v2','alice','--base-dir',base))
    assert preview['source_schema']==1
    invoke(monkeypatch,capsys,'migrate_v2','alice','--apply','--expected-fingerprint',preview['fingerprint'],'--base-dir',base)
    assert json.loads(invoke(monkeypatch,capsys,'migrate_v2','alice','--check','--base-dir',base))['status']=='valid'


def test_social_photo_cli(tmp_path,monkeypatch,capsys):
    from PIL import Image
    source=tmp_path/'photos';source.mkdir()
    Image.new('RGB',(8,8),(0,100,200)).save(source/'synthetic.jpg')
    (source/'note.txt').write_text('不是恋爱意愿',encoding='utf-8')
    out=tmp_path/'social.md'
    invoke(monkeypatch,capsys,'social_parser','--dir',source,'--output',out)
    assert '图片仅列出' in out.read_text(encoding='utf-8')
    report=invoke(monkeypatch,capsys,'photo_analyzer','--dir',source,'--gap','5','--radius','3')
    assert 'synthetic.jpg' in report and '不证明双方见面' in report
