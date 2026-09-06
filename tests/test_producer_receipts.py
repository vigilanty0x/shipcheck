"""Synthetic serialized CC receipts; not evidence that a real producer ran."""
import copy
import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
import sys

import pytest

from shipcheck import workflow
from shipcheck import producer_receipts as receipts
from shipcheck.release_gate.models import Candidate
from shipcheck.release_gate.errors import ValidationError
from test_workflow import fixture as release_fixture

NOW = dt.datetime.now(dt.timezone.utc)
CANDIDATE = Candidate('example/project', 'a'*40, 'b'*40, 'c'*64, 'refs/heads/release')


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n').encode()


def make_bundle(root, *, producer='promptops', quality=True, candidate=CANDIDATE, index=0):
    """Public CC v1 wire schema; bytes and provenance remain supplied fixtures."""
    directory=root/f'producer-{index}';directory.mkdir()
    inputs=encode({'scenario':'fixture-replay'});report=encode({'passed':quality,'fixture':True})
    (directory/'request.json').write_bytes(inputs);(directory/'report.json').write_bytes(report)
    artifacts=[{'id':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
               for name,raw in [('input',inputs),('report',report)]]
    value={'schema':'skyom.business.run.v1','product_id':producer,'run_id':'run-'+f'{index:032x}',
        'source_selection':{'kind':'distribution_snapshot','fallback_reason':None,'distribution_version':'fixture'},
        'started_at':NOW.timestamp()-10,'finished_at':NOW.timestamp()-5,
        'request_sha256':hashlib.sha256(inputs).hexdigest(),'replay_of':None,'pins_sha256':'1'*64,
        'worker_sha256':'2'*64,'recipe_sha256':'3'*64,'durable':True,'reserved_bytes':67108864,
        'input_origin':'user_supplied','provider_called':False,'target_code_executed':False,
        'state':'quality_failed' if quality is False else 'completed','execution_ok':True,'gate_quality':quality,
        'quality_state':'not_measured' if quality is None else 'passed' if quality else 'failed',
        'reason_code':None,'exit_code':0,'timed_out':False,'artifacts':artifacts,
        'engine':{'mode':'fixture_serialized_not_executed'},'scope':'provided_records_only',
        'source_manifest_sha256':'4'*64,'source_snapshot_created':True,
        'storage':{'automatic_purge':False,'reserved_bytes':67108864,'budget_bytes':4294967296}}
    raw=encode(value);(directory/'receipt.json').write_bytes(raw)
    entry={'producer_id':producer,'candidate':candidate.to_dict(),
           'receipt_path':f'producer-{index}/receipt.json','receipt_sha256':hashlib.sha256(raw).hexdigest(),
           'artifacts':[{'id':'input','path':f'producer-{index}/request.json'},
                        {'id':'report','path':f'producer-{index}/report.json'}]}
    bundle={'schema_version':receipts.SCHEMA,'candidate':candidate.to_dict(),'max_age_seconds':60,
            'require_quality':True,'receipts':[entry]}
    return bundle,value


def rewrite(root,bundle,value):
    raw=encode(value);entry=bundle['receipts'][0]
    (root/entry['receipt_path']).write_bytes(raw)
    entry['receipt_sha256']=hashlib.sha256(raw).hexdigest()


def verify(root,bundle):
    return receipts.verify_producer_bundle(bundle,root=root,candidate=CANDIDATE,clock=lambda:NOW)


@pytest.mark.parametrize('producer',sorted(receipts.PRODUCERS))
def test_five_cc_wire_schemas_bind_all_bytes_without_claiming_authenticity(tmp_path,producer):
    bundle,value=make_bundle(tmp_path,producer=producer)
    result=verify(tmp_path,bundle)
    assert result['passed'],result
    assert result['subject_binding']=='declared_only'
    assert result['authenticity_established'] is False and result['publication_authorized'] is False
    assert result['native_engine_receipts_replayed'] is False
    assert result['producer_executed_here'] is False
    assert result['receipts'][0]['artifact_count']==2 and len(result['files'])==3
    assert result['receipts'][0]['age_seconds']==5
    assert result['receipts'][0]['input_sha256']==value['request_sha256']
    receipts.recheck_producer_files(result,root=tmp_path,clock=lambda:NOW)


@pytest.mark.parametrize('shift,reason', [(61,'producer_receipt_stale'),(-6,'producer_time_future')])
def test_final_recheck_does_not_freeze_receipt_freshness(tmp_path,shift,reason):
    bundle,_=make_bundle(tmp_path)
    result=verify(tmp_path,bundle)
    with pytest.raises(ValidationError,match=reason):
        receipts.recheck_producer_files(result,root=tmp_path,clock=lambda:NOW+dt.timedelta(seconds=shift))


@pytest.mark.parametrize('field,value,reason',[
    ('started_at',NOW.timestamp()+2,'producer_time_reversed'),
    ('finished_at',NOW.timestamp()+2,'producer_time_future'),
    ('started_at',True,'producer_timestamp_invalid'),
    ('execution_ok',1,'producer_boolean_invalid'),
    ('gate_quality',1,'producer_nullable_boolean_invalid'),
    ('schema','unsupported.business.run.v1','producer_schema_or_identity_mismatch'),
    ('product_id','rag-lab','producer_schema_or_identity_mismatch'),
    ('state','running','producer_state_inconsistent'),
    ('timed_out',True,'producer_execution_inconsistent'),
    ('request_sha256','0'*64,'producer_input_binding_mismatch')])
def test_typed_receipt_contradictions_are_explicit_veto(tmp_path,field,value,reason):
    bundle,record=make_bundle(tmp_path);record[field]=value;rewrite(tmp_path,bundle,record)
    result=verify(tmp_path,bundle)
    assert result['passed'] is False and result['reason_code']==reason,result


def test_old_receipt_not_rejuvenated_by_rewriting_file_mtime(tmp_path):
    bundle,record=make_bundle(tmp_path)
    record['started_at']=NOW.timestamp()-1000;record['finished_at']=NOW.timestamp()-500
    rewrite(tmp_path,bundle,record)
    result=verify(tmp_path,bundle)
    assert not result['passed'] and result['reason_code']=='producer_receipt_stale'


@pytest.mark.parametrize('raw', [b'{"schema":1,"schema":2}', b'{"extra":1e309}', b'{"extra":NaN}', b'{', b'[]'])
def test_duplicate_keys_nonfinite_and_malformed_receipt_are_refused(tmp_path, raw):
    bundle,_=make_bundle(tmp_path);entry=bundle['receipts'][0]
    (tmp_path/entry['receipt_path']).write_bytes(raw)
    entry['receipt_sha256']=hashlib.sha256(raw).hexdigest()
    assert verify(tmp_path,bundle)['passed'] is False


@pytest.mark.parametrize('mutation', ['duplicate_receipt','duplicate_run','duplicate_declared_id','size','unknown_field','partial_run'])
def test_receipt_inventory_and_contract_remain_strict(tmp_path,mutation):
    bundle,record=make_bundle(tmp_path)
    if mutation=='duplicate_receipt':
        bundle['receipts'].append(copy.deepcopy(bundle['receipts'][0]))
    elif mutation=='duplicate_run':
        second,value=make_bundle(tmp_path,index=1)
        value['run_id']=record['run_id'];rewrite(tmp_path,second,value)
        bundle['receipts'].append(second['receipts'][0])
    else:
        if mutation=='duplicate_declared_id':record['artifacts'][1]['id']='input'
        elif mutation=='size':record['artifacts'][1]['bytes']+=1
        elif mutation=='unknown_field':record['trusted']=True
        elif mutation=='partial_run':record['execution_ok']=False
        rewrite(tmp_path,bundle,record)
    assert verify(tmp_path,bundle)['passed'] is False


def test_multiple_runs_retain_separate_subjects_and_complete_inventories(tmp_path):
    bundle,_=make_bundle(tmp_path)
    second,_=make_bundle(tmp_path,producer='rag-lab',index=1)
    bundle['receipts'].append(second['receipts'][0])
    result=verify(tmp_path,bundle)
    assert result['passed'] and len(result['receipts'])==2 and len(result['files'])==6


@pytest.mark.parametrize('quality',[None,False])
def test_quality_policy_explicitly_distinguishes_unmeasured_and_failed(tmp_path,quality):
    bundle,_=make_bundle(tmp_path,quality=quality)
    result=verify(tmp_path,bundle)
    assert not result['passed']
    assert result['reason_code']==('producer_quality_not_measured' if quality is None else 'producer_quality_failed')
    bundle['require_quality']=False
    allowed=verify(tmp_path,bundle)
    assert allowed['passed'] and allowed['publication_authorized'] is False
    assert allowed['receipts'][0]['gate_quality'] is quality


@pytest.mark.parametrize('kind',['other_repository','other_commit','missing','extra','duplicate','unknown_id','duplicate_path','receipt_tamper','artifact_tamper','missing_file','empty'])
def test_binding_inventory_and_bytes_fail_closed(tmp_path,kind):
    bundle,record=make_bundle(tmp_path);entry=bundle['receipts'][0]
    if kind=='other_repository':entry['candidate']['repository']='other/project'
    elif kind=='other_commit':entry['candidate']['head_commit']='d'*40
    elif kind=='missing':entry['artifacts'].pop()
    elif kind=='extra':entry['artifacts'].append({'id':'other','path':'producer-0/report.json'})
    elif kind=='duplicate':entry['artifacts'][1]['id']='input'
    elif kind=='unknown_id':entry['artifacts'][1]['id']='not-declared'
    elif kind=='duplicate_path':entry['artifacts'][1]['path']=entry['artifacts'][0]['path']
    elif kind=='receipt_tamper':(tmp_path/entry['receipt_path']).write_bytes(b'{}')
    elif kind=='artifact_tamper':(tmp_path/'producer-0/report.json').write_bytes(b'changed')
    elif kind=='missing_file':entry['artifacts'][1]['path']='missing.json'
    elif kind=='empty':bundle['receipts']=[]
    result=verify(tmp_path,bundle)
    assert result['passed'] is False,result
    assert result['publication_authorized'] is False


@pytest.mark.parametrize('path',['../outside','/etc/passwd','a//b','C:/outside'])
def test_unsafe_paths_never_escape_supplied_root(tmp_path,path):
    bundle,_=make_bundle(tmp_path);bundle['receipts'][0]['receipt_path']=path
    assert verify(tmp_path,bundle)['passed'] is False


@pytest.mark.parametrize('kind',['symlink','directory_symlink','hardlink'])
def test_links_are_refused_even_if_bytes_match(tmp_path,kind):
    bundle,_=make_bundle(tmp_path)
    directory=tmp_path/'producer-0'
    if kind=='symlink':
        (directory/'linked.json').symlink_to(directory/'report.json')
        bundle['receipts'][0]['artifacts'][1]['path']='producer-0/linked.json'
    elif kind=='directory_symlink':
        (tmp_path/'alias').symlink_to(directory,target_is_directory=True)
        bundle['receipts'][0]['receipt_path']='alias/receipt.json'
    else:
        os.link(directory/'report.json',directory/'hard.json')
    result=verify(tmp_path,bundle)
    assert result['passed'] is False,result


def test_budgets_apply_to_actual_cumulative_bytes_and_file_count(tmp_path,monkeypatch):
    bundle,_=make_bundle(tmp_path)
    monkeypatch.setattr(receipts,'MAX_TOTAL_BYTES',8)
    assert verify(tmp_path,bundle)['reason_code']=='producer_byte_limit'
    monkeypatch.setattr(receipts,'MAX_TOTAL_BYTES',1024*1024)
    monkeypatch.setattr(receipts,'MAX_FILES',2)
    assert verify(tmp_path,bundle)['reason_code']=='producer_file_limit'


def test_identity_and_bytes_changed_during_read_are_refused(tmp_path,monkeypatch):
    bundle,_=make_bundle(tmp_path)
    original=receipts.os.read
    changed=False
    def altered(fd,size):
        nonlocal changed
        value=original(fd,size)
        if not changed:
            changed=True
            (tmp_path/'producer-0/receipt.json').write_bytes(b'changed')
        return value
    monkeypatch.setattr(receipts.os,'read',altered)
    assert verify(tmp_path,bundle)['passed'] is False


def test_root_link_is_refused(tmp_path):
    physical=tmp_path/'physical';physical.mkdir()
    bundle,_=make_bundle(physical)
    alias=tmp_path/'alias';alias.symlink_to(physical,target_is_directory=True)
    assert verify(alias,bundle)['passed'] is False


def test_checker_never_executes_imports_or_calls_producer(tmp_path,monkeypatch):
    bundle,_=make_bundle(tmp_path)
    def refused(*args,**kwargs):raise AssertionError('producer/network execution attempted')
    monkeypatch.setattr(subprocess,'Popen',refused);monkeypatch.setattr(socket,'socket',refused)
    before=set(sys.modules)
    assert verify(tmp_path,bundle)['passed']
    assert not any(n.startswith(('promptbench','rag_quality_bench','local_ai_stack','ai_software_factory','repo_doctor_ai')) for n in set(sys.modules)-before)


def test_real_native_workflow_consumes_bundle_then_preserves_release_authority(tmp_path):
    root,request,trust=release_fixture(tmp_path)
    candidate=Candidate.from_dict(request['release_evidence']['candidate'])
    bundle,_=make_bundle(root,candidate=candidate)
    request['producer_bundle']=bundle
    result=workflow.run_workflow(request,root=root,output=tmp_path/'out',trust_store=trust)
    assert result['status']=='ready_lab',result
    assert result['production_ready'] is False and result['publication'] is False
    assert result['tests_executed_here'] is False
    assert result['stages'][0]['stage']=='producer_receipts' and result['stages'][0]['status']=='passed'
    proof=json.loads((tmp_path/'out/producer-receipts.json').read_text())
    assert proof['passed'] is True and proof['authenticity_established'] is False


def test_optional_veto_blocks_before_release_and_rollback(tmp_path):
    root,request,trust=release_fixture(tmp_path)
    candidate=Candidate.from_dict(request['release_evidence']['candidate'])
    bundle,_=make_bundle(root,candidate=candidate,quality=None)
    request['producer_bundle']=bundle
    result=workflow.run_workflow(request,root=root,output=tmp_path/'out',trust_store=trust)
    assert result['status']=='blocked' and result['stages'][0]['reason_code']=='producer_quality_not_measured'
    assert not (tmp_path/'out/release-decision.json').exists()
    assert not (tmp_path/'out/drill-state.json').exists()
    assert json.loads((tmp_path/'out/producer-receipts.json').read_text())['passed'] is False


def test_coherent_bundle_cannot_turn_failed_release_into_ready(tmp_path):
    root,request,trust=release_fixture(tmp_path)
    candidate=Candidate.from_dict(request['release_evidence']['candidate'])
    bundle,_=make_bundle(root,candidate=candidate,quality=None)
    bundle['require_quality']=False;request['producer_bundle']=bundle
    request['release_policy']['max_diff_risk']=0
    result=workflow.run_workflow(request,root=root,output=tmp_path/'out',trust_store=trust)
    assert result['status']=='blocked' and result['production_ready'] is False
    assert result['stages'][0]['status']=='passed'
    assert not (tmp_path/'out/drill-state.json').exists()


def test_producer_artifact_rechecked_before_workflow_reports_completion(tmp_path,monkeypatch):
    root,request,trust=release_fixture(tmp_path)
    candidate=Candidate.from_dict(request['release_evidence']['candidate'])
    request['producer_bundle'],_=make_bundle(root,candidate=candidate)
    old=workflow.LocalMergeTransaction.verify
    def changed(self,*args,**kwargs):
        result=old(self,*args,**kwargs)
        (root/'producer-0/report.json').write_bytes(b'changed during drill')
        return result
    monkeypatch.setattr(workflow.LocalMergeTransaction,'verify',changed)
    result=workflow.run_workflow(request,root=root,output=tmp_path/'out',trust_store=trust)
    assert result['status']=='blocked' and result['production_ready'] is False


def test_absent_bundle_keeps_original_result_contract(tmp_path):
    root,request,trust=release_fixture(tmp_path)
    result=workflow.run_workflow(request,root=root,output=tmp_path/'out',trust_store=trust)
    assert result['status']=='ready_lab'
    assert [s['stage'] for s in result['stages']]==['evidence','risk','tests','release_gate','rollback']
    assert not (tmp_path/'out/producer-receipts.json').exists()
