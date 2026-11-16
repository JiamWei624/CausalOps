"""Shared read-only report identity checks; no execution authorization."""
def identity_error(view):
    """Fail closed for display conflicts; never fetch a replacement successful run."""
    if view.get('errors'):
        return '运行引用、内容哈希或步骤证据未通过读取核验。'
    t = view['task']; p = t['plan']; r = view.get('report'); ev = view['evidence']
    if not r:
        return None
    if r['scope'] != p['scope'] or r['plan_version'] != p['version']:
        return '报告指标、比较组、窗口或计划版本与所选研究不一致。'
    effect = r.get('effect')
    required = ['S02','S04'] if effect else ['S02']
    expected = [ev.get(k, {}).get('body', {}).get('run_id') for k in required]
    if None in expected or expected != r['source_runs'] or len(set(expected)) != len(expected):
        return '报告引用的统计 Run 与本任务已核验步骤不一致。'
    if r['sample_size'] != ev.get('S01', {}).get('body', {}).get('rows'):
        return '报告样本与数据审计样本不一致。'
    gate = ev.get('S03', {}).get('body', {})
    if gate and gate.get('descriptive_run_id') != expected[0]:
        return '上游门禁未引用当前描述统计 Run。'
    if effect and (p['scope'].get('assignment') == 'unknown' or effect['outcome'] != p['scope']['outcome']):
        return '效应结果不符合当前研究的指标或设计范围。'
    return None

