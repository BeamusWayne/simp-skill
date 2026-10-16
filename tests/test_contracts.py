from copy import deepcopy
import pytest
from tools.contracts import Message, validate_source, validate_record, stable_id, utc_now
from tools.memory import append_event, rebuild_state_from_events


@pytest.mark.parametrize('ref',[None,{}, {'kind':'file'}, {'kind':'file','path':'x','sha256':'a','locator':'line:1'},
    {'kind':'file','path':'x','sha256':'Z'*64,'locator':'line:1'}, {'kind':'user','locator':'x'},
    {'kind':'session','excerpt':'x'}, {'kind':'unknown','locator':'x','excerpt':'x'}])
def test_invalid_source_rejected(ref):
    with pytest.raises(ValueError):validate_source(ref)


@pytest.mark.parametrize('field,value',[
    ('schema_version',1),('message_id',''),('conversation_id',''),('content',4),('role','lover'),
    ('source_order',-1),('source_order',True),('time_status','estimated'),('source_refs',[]),
    ('parse_status','guess'),('conversation_type','room'),('time_status','missing'),
    ('time_status','timezone_unknown'),('sent_at',None)])
def test_bad_message_contract(exported,field,value):
    data=exported().messages[0].to_dict();data[field]=value
    with pytest.raises((ValueError,TypeError)):Message.from_dict(data)


@pytest.mark.parametrize('field,value',[
    ('schema_version',1),('kind','analysis_done'),('record_id',''),('recorded_at','2026-01-01'),
    ('occurred_at','invalid'),('data',{}),('data',{'summary':' '}),('source_refs',{}),
    ('related_record_ids',['']),('supersedes',[42])])
def test_bad_record_contract(field,value):
    record={'schema_version':2,'record_id':'r:1','kind':'assessment','recorded_at':utc_now(),
            'occurred_at':None,'source_refs':[],'related_record_ids':[],'supersedes':[],'data':{'summary':'unknown'}}
    record[field]=value
    with pytest.raises(ValueError):validate_record(record)


def test_stable_id_ignores_object_key_order():
    assert stable_id({'a':1,'b':2})==stable_id({'b':2,'a':1})


def test_cannot_reference_future_record(base):
    with pytest.raises(ValueError,match='Unknown record'):
        append_event('alice','assessment',{'summary':'x'},base,related_record_ids=['r:missing'])


def test_preference_correction_removes_stale_projection(base,source):
    old=append_event('alice','preference',{'summary':'nickname','key':'nickname','value':'错误昵称'},base,source_refs=source)
    append_event('alice','correction',{'summary':'撤回这个昵称'},base,source_refs=source,supersedes=[old['record_id']])
    meta=rebuild_state_from_events('alice',base)
    assert meta['nickname']=='alice'


def test_replacing_identity_requires_explicit_supersedes(base,source):
    data={'summary':'identity','conversation_id':'c','sender_id':'s','role':'target'}
    append_event('alice','identity_mapping',data,base,source_refs=source)
    with pytest.raises(ValueError,match='supersedes'):
        append_event('alice','identity_mapping',{**data,'role':'third_party'},base,source_refs=source)
