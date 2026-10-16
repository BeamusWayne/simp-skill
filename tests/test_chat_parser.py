import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from tools.chat_parser import parse_export, detect_format, deduplicate_messages, generate_report
from tools.chat_stats import reply_samples, summarize_delays, describe_messages
from tools.contracts import Message, parse_time


@pytest.mark.parametrize('value,status', [(None,'missing'),('', 'missing'),('bad','invalid'),(True,'invalid'),
    ('2026-05-10','date_only'),('2026/05/10 10:00:00','timezone_unknown'),
    ('2026-05-10T10:00:00Z','known'),(0,'known'),(1700000000000,'known'),(float('inf'),'invalid')])
def test_clock_status(value, status):
    assert parse_time(value)[1] == status


def test_epoch_is_utc():
    assert parse_time(0)[0] == datetime(1970,1,1,tzinfo=timezone.utc)


def test_is_send_and_quotes_are_separate(exported):
    result = exported([
        {'localId':1,'isSend':1,'content':'喜欢你','time':'2026-01-01T12:00:00+08:00'},
        {'localId':2,'isSend':0,'content':'这是你说的，我没答应','quote':{'id':1,'content':'喜欢你'}}])
    assert [m.role for m in result.messages] == ['user','target']
    assert result.messages[1].quoted_message_id == result.messages[0].message_id
    assert result.messages[1].sender_id == 't'
    assert result.messages[1].source_refs[0]['locator'] == 'record:2'
    assert 'quoted_message_id' in result.messages[1].to_dict()


def test_same_display_names_use_ids(exported):
    result = exported([{'senderId':'u','sender':'小美','content':'one'},
                       {'senderId':'x','sender':'小美','content':'two'},
                       {'senderId':'t','sender':'小美','content':'three'}],conversationType='group')
    assert [m.role for m in result.messages] == ['user','unknown','target']
    assert [m.content for m in result.messages] == ['one','two','three']
    assert reply_samples(result.messages)['samples'] == []


def test_explicit_mapping_and_conflict(tmp_path):
    path = tmp_path/'group.json'
    path.write_text(json.dumps({'accountId':'u','messages':[{'senderId':'x','isSend':1,'content':'x'}]}))
    msg = parse_export(path,'小美',participants={'x':'third_party'}).messages[0]
    assert msg.role == 'unknown'
    assert 'sender_id_conflicts_with_isSend' in msg.issues


def test_is_send_false_in_group_not_target(exported):
    msg = exported([{'isSend':False,'content':'hi'}],conversationType='group').messages[0]
    assert msg.role == 'unknown' and msg.sender_id is None


def test_source_fallback_and_scoped_original_ids(tmp_path):
    a=tmp_path/'a.json'; b=tmp_path/'b.json'
    a.write_text('[{"content":"hi","localId":1}]'); b.write_text('[{"content":"hi","localId":1}, {"content":"bye"}]')
    am=parse_export(a,'t').messages[0]; bm=parse_export(b,'t').messages[0]
    assert am.message_id != bm.message_id
    aa=parse_export(a,'t',user_id='u',conversation_id='chat').messages[0]
    bb=parse_export(b,'t',user_id='u',conversation_id='chat').messages[0]
    assert aa.message_id == bb.message_id
    merged,n=deduplicate_messages([aa,bb])
    assert n == 1 and len(merged[0].source_refs)==2
    cc=parse_export(b,'t',user_id='other-account',conversation_id='chat').messages[0]
    assert cc.message_id != aa.message_id


def test_duplicate_conflicts_fail(exported):
    with pytest.raises(ValueError,match='Conflicting'):
        exported([{'localId':1,'content':'a'}, {'localId':1,'content':'b'}])


def test_repeated_identical_text_different_ids_is_not_duplicate(exported):
    result=exported([{'localId':1,'isSend':1,'content':'哈'}, {'localId':2,'isSend':1,'content':'哈'}])
    assert len(result.messages)==2


def test_malformed_jsonl_is_visible(tmp_path):
    p=tmp_path/'a.jsonl';p.write_text('{"content":"a"}\nBAD\n42\n{}',encoding='utf-8')
    result=parse_export(p,'t')
    assert result.input_records==4 and len(result.messages)==1
    assert {d['problem'] for d in result.diagnostics} == {'invalid_json','record_is_not_an_object','empty_record'}


@pytest.mark.parametrize('filename,text,expected',[
    ('wx.txt','2026-05-10 12:00:00\n我\n你好\n继续\n2026-05-10 12:01:00\n小美\n你好',['你好\n继续','你好']),
    ('qq.txt','2026-05-10 12:00:00 我(123)\n你好\n2026-05-10 12:01:00 小美(456)\n收到',['你好','收到']),
    ('qq.mht','<html>2026-05-10 12:00:00 我(123)<br>你好 2026-05-10 12:01:00 小美(456)<br>收到</html>',['你好','收到']),
    ('wx.html','<div class="message"><span class="time">2026-05-10 12:00:00</span><span class="sender">我</span><div class="content">你&amp;我<br>再见</div></div>',['你&我\n再见']),
    ('wx.csv','time,sender,content\n2026-05-10 12:00:00,我,"你好\n下一行"',['你好\n下一行']),
])
def test_supported_layouts(tmp_path,filename,text,expected):
    p=tmp_path/filename;p.write_text(text,encoding='utf-8',newline='')
    result=parse_export(p,'小美')
    assert [m.content for m in result.messages]==expected
    assert all(m.source_refs[0]['sha256'] for m in result.messages)
    assert [m.source_order for m in result.messages]==list(range(len(expected)))


def test_partial_layout_and_unknown_format(tmp_path):
    p=tmp_path/'partial.txt';p.write_text('truncated text\n2026-05-10 12:00:00\n我\n你好',encoding='utf-8')
    assert parse_export(p,'小美').diagnostics[0]['problem']=='unparsed_material'
    p.write_text('not an export')
    with pytest.raises(ValueError,match='Unsupported'):parse_export(p,'小美')


def test_normalized_roundtrip(exported,tmp_path):
    result=exported()
    p=tmp_path/'normal.json';p.write_text(json.dumps(result.to_dict()),encoding='utf-8')
    again=parse_export(p,'t')
    assert [m.to_dict() for m in again.messages]==[m.to_dict() for m in result.messages]


def test_quote_outside_excerpt_is_explicit(exported):
    msg=exported([{'content':'no','quoteId':100}]).messages[0]
    assert 'unresolved_reference' in msg.issues


def test_no_score_and_original_refusal_preserved(exported):
    report=generate_report(exported().messages,'小美','我')
    assert '我不想约会，只当朋友' in report
    assert '恋爱意愿' in report
    for removed in ['signal_score','green_light','强烈绿灯','准备表白']:assert removed not in report


def test_reply_turns_use_last_message_no_gap_cutoff(exported):
    rows=[{'localId':i,'isSend':direction,'content':'x','time':time} for i,(direction,time) in enumerate([
        (1,'2026-01-01T10:00:00Z'),(1,'2026-01-01T10:05:00Z'),(0,'2026-01-01T16:05:00Z')])]
    result=reply_samples(exported(rows).messages)
    assert result['samples'][0]['seconds']==21600
    assert result['candidate_pairs']==1
    assert summarize_delays([10,30])['median_seconds']==20


@pytest.mark.parametrize('times,reason',[
    (['bad','2026-01-01T10:00:00Z'],'missing_or_imprecise_time'),
    (['2026-01-01','2026-01-01T10:00:00Z'],'missing_or_imprecise_time'),
    (['2026-01-01T10:00:00','2026-01-01T10:01:00Z'],'incomparable_timezones'),
    (['2026-01-01T10:01:00Z','2026-01-01T10:00:00Z'],'backward_source_time'),
])
def test_excluded_pairs_have_reasons(exported,times,reason):
    msgs=exported([{'isSend':1-i,'content':'x','time':t} for i,t in enumerate(times)]).messages
    stats=reply_samples(msgs)
    assert not stats['samples'] and stats['excluded'][reason]==1


def test_third_party_breaks_reply_pair(exported):
    msgs=exported([{'senderId':s,'content':'x','time':f'2026-01-01T10:0{i}:00Z'} for i,s in enumerate(['u','x','t'])]).messages
    assert reply_samples(msgs)['samples']==[]


def test_unknown_conversation_excludes_reply_inference(exported):
    stats=reply_samples(exported(conversationType='unknown').messages)
    assert stats['samples']==[]


def test_renaming_same_id_and_cross_account_scope(exported,tmp_path):
    rows=[{'localId':1,'senderId':'t','sender':'旧名','content':'one'},
          {'localId':2,'senderId':'t','sender':'新名','content':'two'}]
    a=exported(rows).messages
    assert [m.role for m in a]==['target','target']
    assert a[0].sender_id==a[1].sender_id
    b=exported(rows,accountId='other-user').messages
    assert a[0].conversation_id!=b[0].conversation_id


def test_mime_mht_decodes_html_part(tmp_path):
    from email.message import EmailMessage
    email=EmailMessage();email.set_content('MHT export')
    email.add_alternative('<html>2026-05-10 10:00:00 我(123)<br>中文内容</html>',subtype='html')
    path=tmp_path/'chat.mht';path.write_bytes(email.as_bytes())
    assert parse_export(path,'小美').messages[0].content=='中文内容'


def test_different_timezone_same_absolute_time(exported):
    msgs=exported([{'isSend':1,'content':'x','time':'2026-01-01T10:00:00+08:00'},
                   {'isSend':0,'content':'y','time':'2026-01-01T02:01:00Z'}]).messages
    assert reply_samples(msgs)['samples'][0]['seconds']==60
