"""Run deterministic v1/v2 probes on identical synthetic material; no model calls.

Requires the trusted baseline commit in this checkout's Git object database.
"""
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = '71f64215f50aeb5b619fb34fa44adb9247c85770'


def run():
    old_source = subprocess.check_output(['git','show',BASE+':tools/chat_parser.py'],cwd=ROOT).decode('utf-8')
    old = {'__name__':'baseline_chat_parser','__file__':'baseline/tools/chat_parser.py'}
    exec(compile(old_source,'baseline/tools/chat_parser.py','exec'),old)
    source=ROOT/'tests/fixtures/v2/rejection-fast-reply.json'
    raw=json.loads(source.read_text(encoding='utf-8'))['messages']
    messages=[old['Message'](datetime.fromisoformat(r['time']),r['sender'],r['content']) for r in raw]
    old_score=old['SignalAnalyzer'](messages,'小美','我').signal_score()
    direct=ROOT/'tests/fixtures/v2/direct.json'
    old_count=len(old['parse_json'](str(direct),'小美','我'))
    from tools.chat_parser import parse_export, generate_report
    result=parse_export(source,'小美')
    new_report=generate_report(result.messages,'小美','我')
    return {'base_commit':BASE,'v1':{'isSend_only_import_count':old_count,'explicit_rejection_fast_reply':old_score},
            'v2':{'isSend_only_import_count':len(parse_export(direct,'小美').messages),
                  'rejection_messages':len(result.messages), 'has_score':hasattr(__import__('tools.chat_parser',fromlist=['SignalAnalyzer']),'SignalAnalyzer'),
                  'refusal_text_preserved':'明确拒绝约会' in new_report,
                  'tool_recommends_confession':'准备表白' in new_report},
            'scope':'Deterministic tools only. Not a model behavior evaluation.'}


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
