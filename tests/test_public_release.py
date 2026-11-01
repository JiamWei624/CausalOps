import hashlib,json,sqlite3
from pathlib import Path
import pandas as pd
import pytest
from causalops.sample_data import wine_example,create_wine_task
from causalops.launch import launch_url,active_jobs
from causalops.assistant.service import AssistantWorkspace

def test_public_example_provenance_and_raw_shape():
    import io
    raw,m=wine_example();df=pd.read_csv(io.BytesIO(raw),sep=m['separator'])
    assert df.shape==(1599,12)
    assert hashlib.sha256(raw).hexdigest()==m['sha256']
    assert m['license']=='CC BY 4.0' and m['doi'].startswith('https://doi.org/')
    assert df.duplicated().sum()==240 and df.isna().sum().sum()==0

def test_example_creates_unapproved_local_task(tmp_path):
    from causalops.general.service import GeneralWorkspace
    a=AssistantWorkspace(GeneralWorkspace(tmp_path))
    sid=create_wine_task(a)
    assert a.ws.load_upload(a.session(sid)['upload_id']).shape==(1599,12)
    assert not a.plans(sid) and not a.completed_runs(sid)
    assert not a.session(sid).get('external_consent')

def test_launch_url_is_release_scoped():
    assert launch_url(8513,'0.13.0','f'*64)=='http://127.0.0.1:8513/?route=home&release=0.13.0&build=ffffffffffff'

def test_restart_checks_actual_background_jobs(tmp_path):
    assert active_jobs(tmp_path)==0
    db=tmp_path/'research.sqlite3'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE workflow_jobs(status TEXT)')
        c.executemany('INSERT INTO workflow_jobs VALUES (?)',[(x,) for x in ['completed','running','queued','cancel_requested']])
    assert active_jobs(tmp_path)==3
