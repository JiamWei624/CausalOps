import pandas as pd
import pytest

from causalops.application.research_quality import audit_research
from causalops.application.research_service import ResearchService
from causalops.application.variable_timing import require_eligible
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import DesignError, GeneralWorkspace


@pytest.mark.parametrize("name", ["engagement_7d", "loyalty"])
@pytest.mark.parametrize("timing,allowed", [("pre_treatment",True),("post_treatment",False),("unknown",False)])
def test_total_effect_inputs(name,timing,allowed):
    config=dict(method="ols",predictors=["arm",name])
    contract=dict(purpose="causal",treatment="arm",fields=[dict(field=name,timing=timing)])
    if allowed:
        require_eligible(config,contract)
    else:
        with pytest.raises(DesignError,match=name):
            require_eligible(config,contract)


def test_post_exposure_association_remains_available(tmp_path):
    service, sid, body, f=study(tmp_path,"exploratory","post_treatment")
    receipt=review(service,f)
    assert receipt["status"]=="completed"
    ref=service.a.completed_runs(sid)[0]
    assert service.a.ex.load(ref["run_id"])["claim_level"]=="associational"


def study(path,purpose,timing):
    from causalops.evaluation.v1.cases import prepare
    data,sep,_=prepare("T08",None)
    service=ResearchService(AssistantWorkspace(GeneralWorkspace(path)))
    sid=service.create_task(payload=data,name="synthetic.csv",separator=sep)
    body=dict(analysis_unit="用户",purpose=purpose,structure="cross_section",treatment="group",
              outcome="y",predictors=["group","x"],fields=[dict(field="x",timing=timing)],
              method_facts={"ols":{"independent_rows_reviewed":True}})
    service.contracts.save(sid,body,expected_sha=None,human_confirmed=True)
    f=service.start(sid,"使用 OLS 分析 group 和 x 与结果 y 的关系",mode="plan")
    return service,sid,body,f


def review(service,f,dispatch=True,**kwargs):
    p=service.a.get_plan(f["plan_id"])
    return service.review(f["id"],accept=True,expected_plan_id=p["id"],expected_plan_sha=p["sha"],
                          expected_data_sha=f["request"]["data"]["frame_sha"],dispatch=dispatch,
                          human_confirmed=True,use_contract_facts=True,**kwargs)


@pytest.mark.parametrize("timing",["post_treatment","unknown"])
def test_blocked_review_and_direct_execution(tmp_path,timing):
    service,sid,_,f=study(tmp_path,"causal",timing)
    assert not service.output(f["id"],"readiness")["configuration_ready"]
    with pytest.raises(DesignError,match="x"):
        review(service,f,confirmations={"0":{"covariates_reviewed":True}})
    with pytest.raises(DesignError):
        service.gateway.execute(f["id"])
    # Even a locally accepted candidate cannot substitute for the workflow receipt.
    p=service.a.get_plan(f["plan_id"])
    service.a.accept(p["id"],p["sha"])
    with pytest.raises(DesignError,match="批准"):
        service.a.execute(p["id"],permit=True)
    assert not service.a.completed_runs(sid)


def test_changed_role_invalidates_receipt_at_both_entry_points(tmp_path):
    service,sid,body,f=study(tmp_path,"causal","pre_treatment")
    review(service,f,dispatch=False)
    body["fields"][0]["role"]="outcome"
    service.contracts.save(sid,body,expected_sha=service.contracts.latest(sid)["sha"],human_confirmed=True)
    for execute in (lambda:service.gateway.execute(f["id"]),lambda:service.a.execute(f["plan_id"],permit=True)):
        with pytest.raises(DesignError,match="字典"):
            execute()
    assert not service.a.completed_runs(sid)


def test_panel_repetition_vs_duplicate_post(tmp_path):
    frame=pd.DataFrame({"user":[1,1,2,2,None],"post":[10,11,12,13,14],"day":[1,2,1,2,3]})
    def checks(entity,unit):
        return {c["code"]:c for c in audit_research(frame,dict(entity=entity,time="day",analysis_unit=unit))["checks"]}
    users=checks("user","用户日")
    posts=checks("post","帖子")
    assert users["entity_time"]["status"]=="pass" and users["repeated_entity"]["count"]==2
    assert "2 个不同实体" in users["repeated_entity"]["detail"] and "缺失标识 1 条" in users["repeated_entity"]["detail"]
    assert posts["repeated_entity"]["count"]==0 and "5 个不同实体" in posts["repeated_entity"]["detail"]
    assert len(frame)==5


def test_inference_without_confirmed_measurement_cannot_be_enabled_by_checkbox():
    with pytest.raises(DesignError,match="未知"):
        require_eligible(dict(method="ipw",covariates=["engagement"],covariates_reviewed=True),
                         dict(fields=[],purpose="causal"))
