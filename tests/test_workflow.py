"""One real local workflow; signed synthetic inputs, actual files and rollback."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest
from safe_merge_gate import GatePolicy
from shipcheck import workflow as wf
from shipcheck.cli import main
from shipcheck.release_gate.canonical import object_digest
from shipcheck.release_gate.errors import ValidationError
from shipcheck.release_gate.demo import build_demo
from shipcheck.release_gate.models import Observation, ReleaseEvidence
from shipcheck.release_gate.trust import sign_observation


def fixture(tmp_path):
    root=tmp_path/"inputs";root.mkdir()
    now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    old,policy,trust,_=build_demo(now=now)
    replacements={}
    bindings=[]
    for observation in old.observations:
        if observation.kind=="artifact":
            payload=observation.payload
            raw=payload["name"].encode()[:1]*payload["size_bytes"]
            (root/payload["name"]).write_bytes(raw)
            replacements[payload["digest"]]=hashlib.sha256(raw).hexdigest()
            bindings.append({"name":payload["name"],"path":payload["name"]})
    def replace(value):
        if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
        if isinstance(value,list):return [replace(v) for v in value]
        return replacements.get(value,value) if isinstance(value,str) else value
    observations=[]
    artifact_set=object_digest(sorted([{"name":x["name"],"digest":hashlib.sha256((root/x["path"]).read_bytes()).hexdigest()} for x in bindings],key=lambda x:x["name"]))
    for old_observation in old.observations:
        payload=replace(dict(old_observation.payload))
        if old_observation.kind=="changelog":payload["artifact_set_digest"]=artifact_set
        new=Observation(old_observation.observation_id,old_observation.kind,old_observation.source_kind,
            old_observation.subject_candidate_digest,old_observation.subject_commit,
            old_observation.collected_at,old_observation.trust,payload)
        observations.append(sign_observation(new,trust._keys[old_observation.trust.key_id]))
    evidence=ReleaseEvidence(old.release_id,old.created_at,old.candidate,tuple(observations))
    diff=next(o.payload for o in evidence.observations if o.kind=="diff")
    snapshot={"schema_version":"1.0","repository":old.candidate.repository,
        "expected_sha":old.candidate.base_commit,"observed_sha":old.candidate.base_commit,
        "merge_sha":old.candidate.head_commit,"captured_at":now.isoformat(),
        "ci":{"tests":"success","package":"success"},"required_ci":["tests","package"],
        "optional_ci":[],"tests_complete":True,"tests_passed":True,"secret_scan_complete":True,
        "secret_findings":[],"clean_tree":True,"inventory":{"changes":[{k:v for k,v in item.items()
        if k in {"path","additions","deletions","binary"}} for item in diff["files"]]}}
    state={"repository":old.candidate.repository,"current_sha":old.candidate.base_commit,"preserve":"spacing"}
    (root/"state.json").write_text(json.dumps(state,indent=4)+"\n",encoding="utf-8")
    (root/"junit.xml").write_text('<testsuite name="unit" tests="88">'+''.join(
        f'<testcase name="synthetic-{i}"/>' for i in range(88))+'</testsuite>',encoding="utf-8")
    request={"schema_version":"shipcheck/workflow-v1","release_evidence":evidence.to_dict(),
        "release_policy":policy.to_dict(),"merge_snapshot":snapshot,"merge_policy":GatePolicy().to_dict(),
        "artifacts":bindings,"junit":["junit.xml"],"state_path":"state.json","allow_lab":True}
    return root,request,trust


def exercise(tmp_path, mutate=None):
    root,request,trust=fixture(tmp_path)
    before=(root/"state.json").read_bytes()
    if mutate:mutate(root,request)
    result=wf.run_workflow(request,root=root,output=tmp_path/"run",trust_store=trust)
    assert (root/"state.json").read_bytes()==before
    return result,root,request


def test_workflow_chains_real_engines_and_restores_exact_bytes(tmp_path):
    result,root,request=exercise(tmp_path)
    assert result["status"]=="ready_lab",result
    assert result["production_ready"] is False and result["publication"] is False
    assert result["tests_executed_here"] is False
    assert [s["stage"] for s in result["stages"]]==["evidence","risk","tests","release_gate","rollback"]
    rollback=result["stages"][-1]
    assert rollback["before_sha256"]==rollback["restored_sha256"]
    assert rollback["applied_sha256"]!=rollback["before_sha256"]
    assert (tmp_path/"run/drill-state.json").read_bytes()==(root/"state.json").read_bytes()
    assert json.loads((tmp_path/"run/workflow-receipt.json").read_text())==result


def test_changed_artifact_never_reaches_tests_or_drill(tmp_path):
    result,_,_=exercise(tmp_path,lambda root,request:(root/request["artifacts"][0]["path"]).write_bytes(b"tampered"))
    assert result["status"]=="blocked"
    assert not (tmp_path/"run/drill-state.json").exists()


def test_real_failed_junit_blocks_even_when_summary_claims_green(tmp_path):
    def mutate(root,request):
        p=root/"junit.xml";p.write_text(p.read_text().replace('<testcase name="synthetic-0"/>','<testcase name="synthetic-0"><failure/></testcase>'))
    result,_,_=exercise(tmp_path,mutate)
    assert result["status"]=="blocked"
    assert [s["stage"] for s in result["stages"]]==["evidence","risk","stop"]
    assert not (tmp_path/"run/rollback-receipt.json").exists()


def test_risk_is_consumed_by_release_gate(tmp_path):
    result,_,_=exercise(tmp_path,lambda root,request:request["release_policy"].update(max_diff_risk=0))
    assert result["status"]=="blocked",result
    decision=json.loads((tmp_path/"run/release-decision.json").read_text())
    assert decision["outcome"]=="BLOCKED"
    assert not (tmp_path/"run/drill-state.json").exists()


def test_lab_ready_is_not_production_authority(tmp_path):
    result,_,_=exercise(tmp_path,lambda root,request:request.update(allow_lab=False))
    assert result["status"]=="blocked" and result["production_ready"] is False
    assert not (tmp_path/"run/drill-state.json").exists()


def test_merge_failure_cannot_hide_behind_release_ready(tmp_path):
    result,_,_=exercise(tmp_path,lambda root,request:request["merge_snapshot"].update(tests_passed=False))
    assert result["status"]=="blocked"
    stage=next(s for s in result["stages"] if s["stage"]=="release_gate")
    assert stage["status"]=="READY" and stage["merge_decision"]=="blocked"


def test_identity_mismatch_rejected_before_any_output(tmp_path):
    root,request,trust=fixture(tmp_path)
    request["merge_snapshot"]["merge_sha"]="f"*40
    with pytest.raises(ValidationError):wf.run_workflow(request,root=root,output=tmp_path/"run",trust_store=trust)
    assert not (tmp_path/"run").exists()


def test_duplicate_bindings_and_traversal_rejected(tmp_path):
    root,request,trust=fixture(tmp_path)
    request["artifacts"].append(dict(request["artifacts"][0]))
    with pytest.raises(ValidationError):wf.run_workflow(request,root=root,output=tmp_path/"run",trust_store=trust)
    request["artifacts"].pop()
    request["state_path"]="../elsewhere.json"
    with pytest.raises(ValidationError):wf.run_workflow(request,root=root,output=tmp_path/"run",trust_store=trust)
    assert not (tmp_path/"run").exists()


def test_rollback_conflict_remains_blocked_and_preserves_changed_copy(monkeypatch,tmp_path):
    original=wf.LocalMergeTransaction.verify
    def concurrent_write(self,receipt,state):
        result=original(self,receipt,state)
        Path(state).write_bytes(b'{"changed_by":"another_actor"}')
        return result
    monkeypatch.setattr(wf.LocalMergeTransaction,"verify",concurrent_write)
    result,_,_=exercise(tmp_path)
    assert result["status"]=="blocked"
    assert (tmp_path/"run/drill-state.json").read_bytes()==b'{"changed_by":"another_actor"}'


def test_existing_output_is_never_reused(tmp_path):
    root,request,trust=fixture(tmp_path)
    output=tmp_path/"run";output.mkdir();(output/"preserve").write_bytes(b"kept")
    with pytest.raises(FileExistsError):wf.run_workflow(request,root=root,output=output,trust_store=trust)
    assert (output/"preserve").read_bytes()==b"kept"


def test_public_cli_runs_workflow_not_only_a_dispatcher(monkeypatch,tmp_path,capsys):
    root,request,trust=fixture(tmp_path)
    path=tmp_path/"request.json";path.write_text(json.dumps(request))
    actual=wf.run_workflow
    def configured(request,**kwargs):
        kwargs["trust_store"]=trust
        return actual(request,**kwargs)
    monkeypatch.setattr(wf,"run_workflow",configured)
    assert main(["workflow",str(path),"--root",str(root),"--output",str(tmp_path/"run")])==0
    result=json.loads(capsys.readouterr().out)
    assert result["status"]=="ready_lab" and result["stages"][-1]["stage"]=="rollback"
