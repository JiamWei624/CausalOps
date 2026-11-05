
"""Stage-two deterministic fault injection; only public-data fixtures."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_automation_v2 import archive, system, approved, through_s02, ab_runs
from causalops.general.service import DesignError
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace

def reopen(co):
    return ResearchService(AssistantWorkspace(GeneralWorkspace(co.ws.root))).automation_v2()

def test_budget_persistent_physical_limit(system):
    from causalops.application.automation_budget import BudgetLedger, BudgetExceeded
    co,t=system;b=BudgetLedger(co.ws,t["id"])
    for i in range(12): b.reserve_model("test",{"model":"test"},100)
    with pytest.raises(BudgetExceeded): BudgetLedger(co.ws,t["id"]).reserve_model("test",{},100)
    assert b.snapshot()["physical_requests"]==12

def test_pause_during_tool(system,monkeypatch):
    co,t=approved(system);co.advance(t["id"])
    real=co.a.tools.execute;entered=threading.Event();release=threading.Event()
    def wait(*args):
        entered.set();assert release.wait(10);return real(*args)
    monkeypatch.setattr(co.a.tools,"execute",wait)
    with ThreadPoolExecutor(1) as pool:
        f=pool.submit(co.run,t["id"]);assert entered.wait(10)
        state=reopen(co).pause(t["id"],human_confirmed=True)
        assert state["status"]=="pause_requested"
        release.set();assert f.result()["status"]=="paused"
    assert co.steps(t["id"])[1]["status"]=="succeeded"
    assert ab_runs(co)==0

def test_reconcile_lost_tool_reply_without_recompute(system,monkeypatch):
    co,t=approved(system);co.advance(t["id"])
    real=co.a.tools.execute;calls=[]
    def lost(*args):
        env=real(*args);calls.append(env.run_id);raise OSError("lost return")
    monkeypatch.setattr(co.a.tools,"execute",lost)
    assert co.run(t["id"])["status"]=="interrupted"
    other=reopen(co)
    assert other.resume(t["id"],human_confirmed=True)["status"]=="approved"
    assert other.evidence(t["id"],"S02")["body"]["run_id"]==calls[0]
    assert other.run(t["id"])["status"]=="completed"
    assert len(calls)==1 and ab_runs(other)==1



@pytest.mark.parametrize("step_id",["S02","S04"])
def test_process_restart_after_committed_run(system,step_id,tmp_path):
    """Actual child exit after real registered statistics, before logical publication."""
    import os,subprocess,sys
    co,t=approved(system)
    script="""
import os,sys
from pathlib import Path
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace
c=ResearchService(AssistantWorkspace(GeneralWorkspace(Path(sys.argv[1])))).automation_v2()
def crash(point,tid,step):
    if point=='stat_committed' and step==sys.argv[3]:os._exit(71)
c._fault=crash
c.run(sys.argv[2])
"""
    r=subprocess.run([sys.executable,"-c",script,str(co.ws.root),t["id"],step_id],timeout=60)
    assert r.returncode==71
    other=reopen(co)
    assert other.resume(t["id"],human_confirmed=True)["status"]=="approved"
    assert other.run(t["id"])["status"]=="completed"
    runs=other.report(t["id"])["source_runs"]
    other.resume if False else None
    assert len(set(runs))==2 and ab_runs(other)==1
    assert any(e["event"]=="run_reconciled" for e in other.events(t["id"]))

def test_process_restart_before_step(system):
    import os,subprocess,sys
    co,t=approved(system)
    code="""
import os,sys
from pathlib import Path
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace
c=ResearchService(AssistantWorkspace(GeneralWorkspace(Path(sys.argv[1])))).automation_v2()
c._fault=lambda *a:os._exit(72)
c.advance(sys.argv[2])
"""
    p=subprocess.run([sys.executable,"-c",code,str(co.ws.root),t["id"]],timeout=30)
    assert p.returncode==72
    co=reopen(co);co.resume(t["id"],human_confirmed=True)
    assert co.run(t["id"])["status"]=="completed"

@pytest.mark.parametrize("damage",["file","orphan","multiple","checkpoint"])
def test_uncertain_reconciliation_stops(system,monkeypatch,damage):
    co,t=approved(system);co.advance(t["id"])
    real=co.a.tools.execute
    def lost(*args):
        result=real(*args)
        if damage=="file":
            with co.ws.connection() as c:path=c.execute("SELECT path FROM exploration_runs WHERE run_id=?",(result.run_id,)).fetchone()[0]
            (co.ws.root/path).write_text("broken",encoding="utf8")
        elif damage=="orphan":
            with co.ws.connection() as c:c.execute("DELETE FROM exploration_runs WHERE run_id=?",(result.run_id,))
        elif damage=="multiple":
            cp=args[2];co.a.ex.run(cp["study_id"],cp["version"])
        raise OSError("lost")
    monkeypatch.setattr(co.a.tools,"execute",lost)
    assert co.run(t["id"])["status"]=="interrupted"
    if damage=="checkpoint":
        aid=co.steps(t["id"])[1]["assistant_task_id"];row=co.a.runtime.row(aid);cp=json.loads(row["checkpoint"]);cp["automation_task_id"]="wrong"
        with co.ws.connection() as c:c.execute("UPDATE assistant_checkpoints SET checkpoint=? WHERE task_id=?",(json.dumps(cp),aid))
    other=reopen(co)
    with pytest.raises(DesignError):other.resume(t["id"],human_confirmed=True)
    assert other.task(t["id"])["status"]=="paused" and ab_runs(other)==0
    assert "恢复核查" in other.task(t["id"])["reason"]

def test_live_owner_refuses_takeover(system):
    import os
    from causalops.assistant.runtime import process_birth
    co,t=approved(system);co._init_control(t["id"])
    with co.ws.connection() as c:
        c.execute("INSERT OR REPLACE INTO automation_v2_owners VALUES(?,?,?,?)",(t["id"],"live",os.getpid(),process_birth(os.getpid())))
        c.execute("UPDATE automation_v2_tasks SET status='interrupted' WHERE id=?",(t["id"],))
    with pytest.raises(DesignError):co.resume(t["id"],human_confirmed=True)
    assert all(s["status"]=="pending" for s in co.steps(t["id"]))

@pytest.mark.parametrize("change",["data","approval","plan"])
def test_resume_rechecks_binding(system,change):
    co,t=through_s02(system);co.pause(t["id"],human_confirmed=True)
    with co.ws.connection() as c:
        if change=="data":c.execute("UPDATE general_uploads SET frame_sha='changed' WHERE upload_id=?",(t["plan"]["data"]["upload_id"],))
        elif change=="approval":c.execute("UPDATE automation_v2_approvals SET revoked=1 WHERE task_id=?",(t["id"],))
        else:c.execute("UPDATE automation_v2_tasks SET plan_sha='changed' WHERE id=?",(t["id"],))
    with pytest.raises(DesignError):reopen(co).resume(t["id"],human_confirmed=True)
    assert ab_runs(co)==0

def test_cancel_during_stat_keeps_result(system,monkeypatch):
    co,t=approved(system);co.advance(t["id"])
    real=co.a.tools.execute
    def cancel(*a):
        assert reopen(co).cancel(t["id"],human_confirmed=True)["status"]=="cancel_requested"
        return real(*a)
    monkeypatch.setattr(co.a.tools,"execute",cancel)
    assert co.run(t["id"])["status"]=="cancelled"
    assert co.evidence(t["id"],"S02")["body"]["run_id"]
    assert ab_runs(co)==0
    assert co.cancel(t["id"],human_confirmed=True)["status"]=="cancelled"
    with pytest.raises(DesignError):co.resume(t["id"],human_confirmed=True)

@pytest.mark.parametrize("failures,kind,complete",[(1,TimeoutError,True),(2,TimeoutError,False),(1,ValueError,False)])
def test_single_retry_budget(system,monkeypatch,failures,kind,complete):
    co,t=approved(system);real=co.a.tools.execute;calls=[]
    def transient(*args):
        if args[2]["kind"]=="exploration":
            calls.append(1)
            if len(calls)<=failures:raise kind("controlled")
        return real(*args)
    monkeypatch.setattr(co.a.tools,"execute",transient)
    result=co.run(t["id"])
    assert (result["status"]=="completed")==complete
    assert len(calls)==(2 if kind is TimeoutError else 1)
    if not complete:assert ab_runs(co)==0

def test_repeat_resume_and_history(system):
    co,t=through_s02(system);saved=co.evidence(t["id"],"S02")
    co.pause(t["id"],human_confirmed=True);co.pause(t["id"],human_confirmed=True)
    co.resume(t["id"],human_confirmed=True);co.resume(t["id"],human_confirmed=True)
    assert co.run(t["id"])["status"]=="completed"
    assert co.evidence(t["id"],"S02")==saved and ab_runs(co)==1

def test_semantic_revision_budget_durable(system):
    from causalops.application.automation_budget import BudgetLedger,BudgetExceeded
    co,t=system;b=BudgetLedger(co.ws,t["id"]);b.revision("version-b");b.revision("version-b");b.revision("version-c")
    with pytest.raises(BudgetExceeded):BudgetLedger(co.ws,t["id"]).revision("version-d")
    assert b.snapshot()["semantic_revisions"]==2

def test_budget_reservation_atomic_and_bytes(system):
    from causalops.application.automation_budget import BudgetLedger,BudgetExceeded
    co,t=system;b=BudgetLedger(co.ws,t["id"])
    def reserve(_):
        try:b.reserve_model("parallel",{},100);return True
        except BudgetExceeded:return False
    with ThreadPoolExecutor(6) as p:assert sum(p.map(reserve,range(18)))==12
    assert b.snapshot()["usage_unknown"]==12
    with pytest.raises(BudgetExceeded):b.reserve_model("oversize",{},131073)



def test_http_retry_json_repair_share_ledger(system):
    import secrets,httpx
    from causalops.llm.providers import ProviderConfig,StructuredModelClient,OutputContractError
    from causalops.application.automation_budget import BudgetLedger,BudgetExceeded
    co,t=system;b=BudgetLedger(co.ws,t["id"]);seen=[]
    def handler(req):
        seen.append(req)
        if len(seen)==1:return httpx.Response(503)
        return httpx.Response(200,json={"status":"completed","model":"deepseek-flash","output_text":"broken" if len(seen)==2 else '{"ok":true}',"usage":{"input_tokens":3,"output_tokens":2}})
    schema={"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model=StructuredModelClient(ProviderConfig(max_retries=1),secrets.token_hex(16),client=client,sleep=lambda _:None)
        with b.model_scope("JSON_repair_test"):
            with pytest.raises(OutputContractError):model.complete_json(system_instruction="test",user_payload={},output_schema=schema)
            assert model.complete_json(system_instruction="repair",user_payload={},output_schema=schema)=={"ok":True}
            for _ in range(9):model.complete_json(system_instruction="test",user_payload={},output_schema=schema)
            with pytest.raises(BudgetExceeded):model.complete_json(system_instruction="test",user_payload={},output_schema=schema)
    assert len(seen)==12
    snap=b.snapshot()
    assert snap["physical_requests"]==12 and snap["usage_unknown"]==1
    assert snap["input_tokens"]==33
    assert len(snap["events"])==12

def test_cost_warning_and_unknown_usage(system):
    from causalops.application.automation_budget import BudgetLedger,BudgetExceeded
    co,t=system;b=BudgetLedger(co.ws,t["id"])
    b.configure_price(model="synthetic-price-model",input_cny_per_million=2,output_cny_per_million=8,source="https://example.org/test-tariff",version="test-only-1")
    rid=b.reserve_model("test",{"model":"synthetic-price-model"},20)
    b.receipt(rid,{"model":"synthetic-price-model","status":"completed","input_tokens":500000,"output_tokens":1})
    assert b.snapshot()["estimated_cost_cny"]>1
    with pytest.raises(BudgetExceeded):b.reserve_model("test",{},20)
    assert b.snapshot()["price_version"]["version"]=="test-only-1"

def test_stop_refuses_budget_and_model_binding(system):
    from causalops.application.automation_budget import BudgetLedger,BudgetExceeded
    co,t=approved(system);b=BudgetLedger(co.ws,t["id"])
    co.pause(t["id"],human_confirmed=True)
    with pytest.raises(BudgetExceeded):b.reserve_model("test",{},20)
    assert b.snapshot()["physical_requests"]==0

def test_live_stat_owner_refuses_recovery(system):
    import os
    from causalops.assistant.runtime import process_birth
    co,t=approved(system);co.advance(t["id"])
    step=co.steps(t["id"])[1];token,cp=co.a.runtime.claim(step["assistant_task_id"],"test",max_attempts=2)
    with co.ws.connection() as c:
        c.execute("UPDATE automation_v2_tasks SET status='interrupted' WHERE id=?",(t["id"],))
        c.execute("UPDATE automation_v2_steps SET status='running' WHERE task_id=? AND step_id='S02'",(t["id"],))
    with pytest.raises(DesignError):co.resume(t["id"],human_confirmed=True)
    assert ab_runs(co)==0

def test_resource_policy_tamper_invalidates_execution(system):
    co,t=approved(system)
    with co.ws.connection() as c:c.execute("UPDATE automation_v2_budget SET policy='{}' WHERE task_id=?",(t["id"],))
    assert co.run(t["id"])["status"]=="blocked"
    assert ab_runs(co)==0



def test_v2_fixed_plan_rejects_nested_model_before_http(system,monkeypatch):
    import httpx,secrets
    from causalops.llm.providers import StructuredModelClient,ProviderConfig
    co,t=approved(system);requests=[]
    def handler(req):requests.append(req);raise AssertionError("must not send")
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        model=StructuredModelClient(ProviderConfig(),secrets.token_hex(16),client=c)
        def injected(_):
            return model.complete_json(system_instruction="test",user_payload={},output_schema={"type":"object"})
        monkeypatch.setattr(co,"_audit",injected)
        assert co.run(t["id"])["status"]=="blocked"
    assert requests==[] and co.budget(t["id"])["physical_requests"]==0

def test_legacy_sdk_rejected_under_v2_scope(system):
    from causalops.application.automation_budget import BudgetLedger
    from causalops.llm.deepseek import DeepSeekStructuredModelClient,DeepSeekConfigurationError
    co,t=system
    client=DeepSeekStructuredModelClient(client=object())
    with BudgetLedger(co.ws,t["id"]).model_scope("test"):
        with pytest.raises(DeepSeekConfigurationError):
            client.complete_json(system_instruction="test",user_payload={},output_schema={})

def test_model_scope_rejects_provider_change(system):
    import httpx,secrets
    from causalops.application.automation_budget import BudgetLedger
    from causalops.llm.providers import StructuredModelClient,ProviderConfig,ProviderError
    co,t=system;cfg=ProviderConfig();different={**cfg.binding(),"model":"another-model"}
    with httpx.Client(transport=httpx.MockTransport(lambda _:pytest.fail("must not send"))) as client:
        model=StructuredModelClient(cfg,secrets.token_hex(16),client=client)
        with BudgetLedger(co.ws,t["id"]).model_scope("test",binding=different):
            with pytest.raises(ProviderError):model.complete_json(system_instruction="test",user_payload={},output_schema={})

def test_finished_task_repeat_resume_is_read_only(system):
    co,t=approved(system);assert co.run(t["id"])["status"]=="completed"
    original=co.report(t["id"]);assert co.resume(t["id"],human_confirmed=True)["status"]=="completed"
    assert co.report(t["id"])==original and ab_runs(co)==1



def test_exhausted_budget_keeps_previous_statistical_evidence(system):
    from causalops.application.automation_budget import BudgetLedger,BudgetExceeded
    co,t=through_s02(system);original=co.evidence(t["id"],"S02");b=BudgetLedger(co.ws,t["id"])
    for _ in range(12):b.reserve_model("injected-budget-test",{},10)
    with pytest.raises(BudgetExceeded):b.reserve_model("injected-budget-test",{},10)
    assert co.task(t["id"])["status"]=="paused"
    assert co.evidence(t["id"],"S02")==original and ab_runs(co)==0
    assert b.snapshot()["stops"]
    # Recovery cannot grant a 13th request; pure deterministic work has no model cost.
    co.resume(t["id"],human_confirmed=True)
    with pytest.raises(BudgetExceeded):b.reserve_model("test",{},10)
    assert b.snapshot()["physical_requests"]==12

def test_result_units_and_historical_hashes_survive_restart(system):
    import hashlib
    co,t=approved(system);co.run(t["id"]);before=co.report(t["id"])
    hashes={str(p.relative_to(co.ws.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (co.ws.root/"runs").rglob("*") if p.is_file()}
    other=reopen(co);assert other.run(t["id"])["status"]=="completed"
    assert other.report(t["id"])==before
    assert hashes=={str(p.relative_to(co.ws.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (co.ws.root/"runs").rglob("*") if p.is_file()}

