"""Display projections preserve actual stored evidence and reject raw HTML."""
import copy,re
from test_chat_answer_delivery import studies
from causalops.application.automation_results import snapshot
from causalops.application.automation_answer import answer

def test_result_projection_preserves_real_values_and_source(studies):
    from causalops.ui.chat_typography import display_parts
    co,t,_=studies;view=snapshot(co,t['id']);r=answer(co.a,t['session_id'],view,'两组比例、样本量、差异、置信区间和研究限制');original=copy.deepcopy(r)
    parts=display_parts(r)
    assert parts[0][0]=='lead' and any(k=='markdown' and text.startswith('|') for k,text in parts)
    normalize=lambda text:sorted(x.strip().replace('**','') for x in text.split('\n\n'))
    assert normalize('\n\n'.join(text for _,text in parts))==normalize(r['text'])
    assert r==original and r['run_ids']==view['report']['source_runs']

def test_description_does_not_acquire_inferential_claim(studies):
    from causalops.ui.chat_typography import display_parts
    co,_,t=studies;r=answer(co.a,t['session_id'],snapshot(co,t['id']),'比例、样本量、差异、置信区间和研究限制')
    shown='\n'.join(text for _,text in display_parts(r))
    assert '描述性差异' in shown and '区间未执行' in shown and '随机分配依据未知' in shown
    assert '原工具95%区间' not in shown and len(r['run_ids'])==1

def test_natural_reply_text_is_not_rewritten():
    from causalops.ui.chat_typography import display_parts
    text='## 方法说明\n\n这是一段**有限强调**。\n\n- 条件一\n- 条件二\n\n`run_ref`'
    assert display_parts({'text':text,'scope':'result_qa'})==[('markdown',text)]

def test_lead_markup_escapes_original_labels():
    from causalops.ui.chat_typography import lead_html
    html=lead_html('绝对差（<script>bad()</script> − 对照）：16.6667 个百分点，不是相对增长率。')
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '16.6667 个百分点' in html and 'co-result-value' in html
