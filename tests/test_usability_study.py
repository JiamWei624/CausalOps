"""Study infrastructure privacy and classification tests; no product behavior changes."""
import importlib.util,json,sqlite3,hashlib,csv,io
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('usability_study',Path(__file__).resolve().parents[1]/'scripts/usability_study.py')
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)

def test_synthetic_materials_have_distinct_valid_binary_outcomes():
    rows=list(csv.DictReader(io.StringIO(study.synthetic_csv().decode())))
    assert len(rows)==24 and len({r['subject'] for r in rows})==24
    assert {r['arm'] for r in rows}=={'standard','variant'}
    assert any(r['completed']!=r['retained'] for r in rows)
    for field in ['completed','retained']:assert {r[field] for r in rows}=={'yes','no'}

def test_bad_source_fails_before_creating_trial_records(tmp_path):
    source=tmp_path/'bad.csv';source.write_text('not the verified public table')
    with pytest.raises(ValueError):study.prepare(tmp_path/'study',source)
    assert not (tmp_path/'study').exists()

def test_existing_records_are_never_silently_overwritten(tmp_path):
    p=tmp_path/'records.json';study.stable_write(p,'original');study.stable_write(p,'original')
    with pytest.raises(ValueError):study.stable_write(p,'changed')
    assert p.read_text()=='original'

def test_missing_database_not_created_by_metadata_export(tmp_path):
    with pytest.raises(ValueError):study.export_events(tmp_path)
    assert not (tmp_path/'research.sqlite3').exists()

def test_metadata_export_is_readonly_and_does_not_infer_human_or_clicks(tmp_path):
    p=tmp_path/'research.sqlite3'
    with sqlite3.connect(p) as db:
        db.executescript('CREATE TABLE configurable_user_events(id,task_id,upload_id,action,origin,error_class,created);CREATE TABLE private_notes(content);')
        db.execute('INSERT INTO configurable_user_events VALUES(?,?,?,?,?,?,?)',('event','task','private-upload','plan_created','local_user',None,'2026-11-08T08:00:00Z'))
        db.execute('INSERT INTO private_notes VALUES(?)',('sensitive observation content',))
    before=hashlib.sha256(p.read_bytes()).hexdigest();r=study.export_events(tmp_path)
    assert r['effective_click_count'] is None and r['full_user_time'] is None
    assert r['milestones'][0]['origin']=='local_user'
    assert 'private-upload' not in json.dumps(r) and 'sensitive observation' not in json.dumps(r)
    assert hashlib.sha256(p.read_bytes()).hexdigest()==before

def test_model_receipts_export_only_allowlisted_usage(tmp_path):
    with sqlite3.connect(tmp_path/'research.sqlite3') as db:
        db.execute('CREATE TABLE automation_v2_model_requests(id,task_id,purpose,status,receipt,created)')
        db.execute('INSERT INTO automation_v2_model_requests VALUES(?,?,?,?,?,?)',('r','t','planning','failed',json.dumps({'status':'failed','input_tokens':12,'raw_response':'private raw content','authorization':'private header'}),1))
    r=study.export_events(tmp_path);assert r['model_requests'][0]['receipt']=={'status':'failed','input_tokens':12}
    assert 'private' not in json.dumps(r)
