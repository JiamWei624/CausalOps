import pytest

from causalops.application.task_conclusions import source_dictionary
from causalops.general.service import DesignError
from causalops.ui.report_target import report_request, report_target
from test_v21_flow_boundaries import completed_orders, mean_for, reopen, review, study


def test_preview_does_not_change_plan_contract_or_run(study):
    service, sid, frame = study
    old, rid = completed_orders(service, sid)
    contract = service.contracts.ref(sid)
    target = report_target(service, sid, old)
    for preview in ("orders", "visitors"):
        request = report_request(service, sid, target, preview, frame)
        assert preview in request
        assert report_target(service, sid, old) == target
        assert target.version == 1 and target.outcome == "orders" and target.run_id == rid
        assert service.contracts.ref(sid) == contract
        assert len(service.a.plans(sid)) == len(service.a.completed_runs(sid)) == 1


@pytest.mark.parametrize("identical", [True, False])
def test_preview_revision_is_scoped_and_survives_reopen(tmp_path,study,identical):
    service, sid, frame = study
    if identical:
        frame["visitors"] = frame["orders"]
        sid = service.create_task(payload=frame.to_csv(index=False).encode(), name="daily.csv")
        data = service.contracts.latest(study[1])["body"]
        data["fields"] = [{"field":"visitors","meaning":"访客人数","unit":"人","role":"measure","timing":"unknown"}]
        service.contracts.save(sid,data,expected_sha=None,human_confirmed=True)
    old, rid = completed_orders(service, sid)
    contract = service.contracts.ref(sid)
    base = report_target(service, sid, old)
    q = report_request(service,sid,base,"visitors",frame)
    f = service.start(sid,q,mode="plan",parent_flow_id=base.flow_id,run_ids=[base.run_id])
    p = report_target(service,sid,f)
    assert p.pending and p.version == 2 and p.outcome == "visitors" and not p.run_id
    assert [r["run_id"] for r in service.a.completed_runs(sid)] == [rid]
    with pytest.raises(DesignError):
        service.gateway.execute(f["id"])
    with pytest.raises(DesignError):
        report_request(service,sid,p,"orders",frame)
    review(service,f)
    resumed = reopen(tmp_path)
    new = report_target(resumed,sid,resumed.flow(f["id"]))
    assert new.outcome == "visitors" and new.version == 2 and new.run_id != rid
    assert report_target(resumed,sid,resumed.flow(old["id"])) == base
    assert resumed.contracts.ref(sid) == contract
    assert mean_for(resumed,sid,rid,"orders") == pytest.approx(frame.orders.mean())
    assert mean_for(resumed,sid,new.run_id,"visitors") == pytest.approx(frame.visitors.mean())
    if identical:
        a = source_dictionary(resumed.a,sid,rid)[0]
        b = source_dictionary(resumed.a,sid,new.run_id)[0]
        assert (a["outcome"],a["metric_unit"]) == ("orders","单")
        assert (b["outcome"],b["metric_unit"]) == ("visitors","人")


def test_no_run_change_requires_confirmed_context(study):
    s,sid,frame=study
    t=report_target(s,sid,None)
    with pytest.raises(DesignError,match="首个研究指标"):
        report_request(s,sid,t,"visitors",frame)
    assert not s.a.plans(sid)
