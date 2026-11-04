"""Paper-linked event-level preparation; original files are never edited."""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd


import os
BASE_CONTROLS = ['post_len_log','post_emoji_count','log_account_age','log_since_first','mention_order',
                 'lag_reply','cum_reply_count_before_n','reply_streak_before_n',
                 'roll_neg_post_rate','roll_pos_post_rate',
                 'post_year_month_cat','post_region_cat','topic_cat']


def horizon_label(event: pd.Series, duration: pd.Series, seconds: int) -> pd.Series:
    """Observed event by horizon -> 1; known event-free through horizon -> 0; otherwise unknown."""
    if seconds <= 0: raise ValueError('观察窗口必须为正。')
    result=pd.Series(float('nan'),index=event.index)
    valid=event.isin([0,1]) & duration.notna() & (duration>0)
    result.loc[valid & (duration>=seconds)]=0.
    result.loc[valid & (event==1) & (duration<=seconds)]=1.
    return result


def load_registered_catalog(path: Path) -> list[dict]:
    if not path.is_file(): return []
    payload=json.loads(path.read_text(encoding='utf-8'))
    configured=os.environ.get('CAUSALOPS_PRIVATE_DATA_ROOT')
    if not configured: raise ValueError('请先显式设置本地私有数据根目录。')
    root=Path(configured).resolve()
    records=[]
    for item in payload.get('datasets',[]):
        source=Path(item['path']).resolve()
        if not source.is_relative_to(root) or source.suffix.lower()!='.parquet':
            raise ValueError('已登记数据必须位于显式配置的私有数据目录内，且使用 Parquet。')
        if not source.is_file(): raise ValueError('已登记数据文件不存在。')
        records.append(item)
    return records


def real_external_model_authorized(project_root: Path, source_sha256: str | None = None) -> bool:
    path=project_root/'artifacts/real-model-authorization.json'
    if not path.is_file(): return False
    try:
        payload=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return False
    if not isinstance(payload,dict):
        return False
    return (payload.get('authorized_by')=='user' and payload.get('provider_url')=='https://api.deepseek.com'
            and payload.get('scope')=='questions_schema_and_aggregate_evidence_only'
            and bool(payload.get('source_sha256'))
            and (source_sha256 is None or source_sha256==payload.get('source_sha256')))
