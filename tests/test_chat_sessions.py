"""Real persisted chat references; no model or estimator fixture answers."""
import copy
import json
import pytest
from test_configurable_research import co, create, approve
from causalops.assistant.service import digest
from causalops.application.chat_sessions import ChatService, ChatSession, MessageReference


def finished(co, **changes):
    task=create(co, **changes);approve(co,task);co.run(task["id"]);return task


def counts(co):
    with co.ws.connection() as db:
        return {t:db.execute("SELECT count(*) FROM "+t).fetchone()[0] for t in ("assistant_sessions","assistant_plans","analysis_runs","exploration_runs","automation_v2_approvals")}


def test_empty_chat_is_persistent_separate_identity_and_no_domain_actions(co):
    s=ChatService(co.s);before=counts(co)
    c=s.create(request_key="empty-first")
    assert isinstance(c,ChatSession) and not c.active_binding_id
    assert s.create(request_key="empty-first").id==c.id
    assert ChatService(co.s).session(c.id)==c
    turn=s.submit(c.id,"我想研究两个方案的效果",request_key="first")
    assert isinstance(turn,MessageReference) and turn.status=="completed"
    assert s.messages(c.id)[0]["answer"]["source"]=="本地工作台能力说明"
    assert counts(co)==before


def test_actual_qa_references_saved_answer_and_real_runs_without_copying_statistics(co):
    t=finished(co);s=ChatService(co.s);c=s.create()
    b=s.bind(c.id,"automation_v2",t["id"])
    assert c.id!=t["id"] and b.subject_id==t["id"]
    before=counts(co)
    a=s.submit(c.id,"两组完成比例的差异是多少，区间说明什么？",request_key="qa")
    assert a.status=="completed"
    m=s.messages(c.id)[0]
    assert m["available"] and m["answer"]["run_ids"]
    assert set(m["answer"]["run_ids"])<=set(s.view(c.id)["metadata"]["run_ids"])
    assert s.submit(c.id,"两组完成比例的差异是多少，区间说明什么？",request_key="qa").id==a.id
    assert len(s.messages(c.id))==1 and counts(co)==before
    with co.ws.connection() as db:
        raw=json.loads(db.execute("SELECT reply FROM chat_turns WHERE id=?",(a.id,)).fetchone()[0])
    assert raw["kind"]=="assistant_event" and "event_id" in raw
    assert "facts" not in raw and "text" not in raw and "effect" not in raw


def test_two_chats_task_binding_refresh_and_frozen_history(co):
    t=finished(co);s=ChatService(co.s);a=s.create();b=s.create()
    ba=s.bind(a.id,"automation_v2",t["id"])
    s.submit(a.id,"请解释当前结果和限制",request_key="a")
    # A second independent data session has no statistical run.
    uid=co.ws.ingest(b"x,y\n1,0\n2,1\n","second.csv")
    sid=co.a.create(uid,"另一份研究")
    s.bind(b.id,"assistant",sid)
    s.submit(b.id,"这个研究已经有统计结果吗？",request_key="b")
    restored=ChatService(co.s)
    assert restored.session(a.id).active_binding_id==ba.id
    assert restored.view(b.id)["metadata"]["run_ids"]==[]
    assert restored.messages(a.id)[0]["answer"]["run_ids"]
    assert not restored.messages(b.id)[0]["answer"].get("run_ids")
    prior=restored.messages(a.id)[0]["reference"]
    restored.bind(a.id,"assistant",sid)
    assert restored.messages(a.id)[0]["reference"]==prior
    assert restored.messages(a.id)[0]["binding"].subject_id==t["id"]


def test_same_request_key_different_input_rejected(co):
    s=ChatService(co.s);c=s.create();s.submit(c.id,"请说明支持哪些范围",request_key="one")
    with pytest.raises(ValueError):s.submit(c.id,"请直接执行所有统计",request_key="one")


def test_invalid_chat_or_cross_chat_binding_cannot_fallback(co):
    s=ChatService(co.s);a=s.create();b=s.create();t=create(co)
    ref=s.bind(a.id,"automation_v2",t["id"])
    with pytest.raises(ValueError):s.session(t["id"])
    with pytest.raises(ValueError):s.view(b.id,binding_id=ref.id)
    with pytest.raises(ValueError):s.bind(b.id,"automation_v2","missing")
    assert s.session(b.id).active_binding_id is None


def test_chat_assent_and_execution_request_do_not_grant_permission(co):
    t=create(co);s=ChatService(co.s);c=s.create();s.bind(c.id,"automation_v2",t["id"]);before=counts(co)
    s.submit(c.id,"同意",request_key="yes")
    s.submit(c.id,"请批准并执行这个研究",request_key="execute")
    assert counts(co)==before and co.task(t["id"])["status"]=="candidate"
    assert not s.view(c.id)["metadata"]["run_ids"]


def test_data_contract_change_blocks_new_answer_without_rewriting_history(co):
    t=finished(co);s=ChatService(co.s);c=s.create();s.bind(c.id,"automation_v2",t["id"])
    turn=s.submit(c.id,"解释当前完成比例",request_key="old");before=s.messages(c.id)[0]["reference"]
    row=co.s.contracts.latest(t["session_id"]);body=copy.deepcopy(row["body"]);body["metric_label"]="新的结果指标名称"
    co.s.contracts.save(t["session_id"],body,expected_sha=row["sha"],human_confirmed=True)
    with pytest.raises(ValueError):s.view(c.id)
    assert not s.messages(c.id)[0]["available"]
    assert s.messages(c.id)[0]["reference"]==before
    new=s.submit(c.id,"继续说明结果",request_key="new")
    assert new.status=="blocked"


def test_damaged_report_source_is_rejected_without_alternate_success(co):
    t=finished(co);s=ChatService(co.s);c=s.create();s.bind(c.id,"automation_v2",t["id"])
    with co.ws.connection() as db:
        db.execute("UPDATE automation_v2_steps SET output_sha='damaged' WHERE task_id=? AND step_id='S05'",(t["id"],))
    with pytest.raises(ValueError):s.view(c.id)
    assert s.submit(c.id,"解释研究结果",request_key="broken").status=="blocked"
    assert not s.messages(c.id)[0]["answer"].get("facts")


def test_model_unavailable_is_explicit_not_silent_local_response(co):
    t=finished(co);s=ChatService(co.s);c=s.create();s.bind(c.id,"automation_v2",t["id"])
    before=counts(co)
    result=s.submit(c.id,"请解释当前统计结果",request_key="model",mode="model")
    assert result.status=="failed"
    m=s.messages(c.id)[0];assert "模型" in m["answer"]["text"] and "本地" in m["answer"]["text"]
    assert counts(co)==before


def test_original_answer_event_cannot_be_rewritten_as_chat_fact(co):
    t=finished(co);s=ChatService(co.s);c=s.create();s.bind(c.id,"automation_v2",t["id"])
    tr=s.submit(c.id,"请解释当前访问结果",request_key="a")
    with co.ws.connection() as db:
        ref=json.loads(db.execute("SELECT reply FROM chat_turns WHERE id=?",(tr.id,)).fetchone()[0])
        db.execute("UPDATE assistant_events SET body=? WHERE id=?",(json.dumps({"text":"虚构统计结果","run_ids":[]}),ref["event_id"]))
    assert not s.messages(c.id)[0]["available"] and s.messages(c.id)[0]["answer"] is None


def test_import_uses_real_reader_and_dedup_not_file_selection(co):
    s=ChatService(co.s);c=s.create();before=counts(co)
    turn=s.import_data(c.id,b"score,arm\n1,a\n0,b\n",name="sample.csv",request_key="upload")
    assert turn.status=="completed"
    sid=s.view(c.id)["metadata"]["assistant_session_id"]
    assert co.a.session(sid) and not co.s.contracts.latest(sid)
    assert s.import_data(c.id,b"score,arm\n1,a\n0,b\n",name="sample.csv",request_key="upload").id==turn.id
    after=counts(co);assert after["assistant_sessions"]==before["assistant_sessions"]+1
    assert after["analysis_runs"]==before["analysis_runs"] and after["assistant_plans"]==before["assistant_plans"]


def test_unfinished_request_is_not_blindly_replayed(co):
    s=ChatService(co.s);c=s.create();tr=s.submit(c.id,"说明当前支持范围",request_key="one")
    with co.ws.connection() as db:db.execute("UPDATE chat_turns SET status='running' WHERE id=?",(tr.id,))
    assert s.submit(c.id,"说明当前支持范围",request_key="one").status=="running"

def test_readonly_chat_label_uses_first_question_not_task_identity(co):
    s=ChatService(co.s);c=s.create()
    s.submit(c.id,'请解释当前研究的访问比例',request_key='label')
    assert s.label(c.id)=='请解释当前研究的访问比例'
    other=s.create('由用户命名的会话')
    assert s.label(other.id)=='由用户命名的会话'
