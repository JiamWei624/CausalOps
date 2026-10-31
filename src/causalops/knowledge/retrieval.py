"""Section retrieval with exact local-note spans and source provenance; no invented citations."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
CATALOG=Path(__file__).with_name('catalog.json')
ALIASES={
 'ab_test':r'welch|两独立样本|a/b',
 'descriptive':r'描述|缺失|分布|describe|descriptive', 'correlation':r'相关|correlat|pearson|spearman',
 'cuped':r'cuped|实验前.*降.*方差', 'logit':r'logit|二元.*转化|二项', 'poisson':r'poisson|泊松|计数.*暴露',
 'iv_2sls':r'工具变量|2sls|弱工具|排除限制|anderson.rubin',
 'rd_fuzzy':r'fuzzy|模糊断点|不完全遵从.*阈值', 'rd_sharp':r'sharp|清晰断点',
 'staggered_did':r'交错|staggered|att\(g,t\)|分期实施',
 'did':r'平行趋势|双重差分|\bdid\b', 'aipw':r'aipw|\birm\b', 'double_ml':r'doubleml|dml|双重机器学习|\bplr\b',
 'psm':r'psm|倾向.*匹配', 'ipw':r'ipw|逆概率', 'ols':r'\bols\b|最小二乘|线性回归'}

class MethodLibrary:
    def __init__(self,path=None):
        raw=Path(path or CATALOG).read_bytes();self.digest=hashlib.sha256(raw).hexdigest();self.catalog=json.loads(raw);self.cards=self.catalog['cards']
        ids=[c['card_id'] for c in self.cards]
        if len(set(ids))!=len(ids):raise ValueError('方法卡标识重复。')
        for c in self.cards:
            if set(c['source_ids'])-set(self.catalog['sources']):raise ValueError('知识卡存在未登记来源。')
        self.texts=[c['title']+' '+' '.join(c['methods']+c['tags'])+' '+' '.join(c['sections'].values()) for c in self.cards]
        self.vectorizer=TfidfVectorizer(analyzer='char',ngram_range=(2,4),sublinear_tf=True);self.matrix=self.vectorizer.fit_transform(self.texts)
        self.sections=[{'card_id':c['card_id'],'section':name,'text':text,'note_sha256':hashlib.sha256(text.encode()).hexdigest()} for c in self.cards for name,text in c['sections'].items()]
        self.section_vectorizer=TfidfVectorizer(analyzer='char',ngram_range=(2,4),sublinear_tf=True)
        self.section_matrix=self.section_vectorizer.fit_transform([r['section']+' '+r['text'] for r in self.sections])
    def _empty(self,note):return {'status':'insufficient_evidence','hits':[],'knowledge_version':self.catalog['version'],'knowledge_sha256':self.digest,'note':note,'retrieval_version':'sectional-v1'}
    def search(self,question,*,method=None,k=4,strategy='sectional'):
        if not isinstance(question,str) or not question.strip() or len(question)>3000:raise ValueError('检索问题须为1至3000字。')
        if not 1<=k<=8:raise ValueError('最多检索8条方法卡。')
        if strategy not in ('baseline','sectional'):raise ValueError('未知检索策略。')
        if re.search(r'因果森林|合成控制',question,re.I):return self._empty('当前知识库尚无该方法的已核实专门条目；不以相近关键词替代。')
        if method and not any(method in c['methods'] for c in self.cards):return self._empty('方法不在已核实知识库中，不生成相近方法的替代引用。')
        scores=cosine_similarity(self.vectorizer.transform([question.lower()]),self.matrix)[0]
        section_scores=cosine_similarity(self.section_vectorizer.transform([question.lower()]),self.section_matrix)[0]
        requested={m for m,pattern in ALIASES.items() if re.search(pattern,question,re.I)} if strategy=='sectional' else set()
        hits=[]
        for i,c in enumerate(self.cards):
            if method and method not in c['methods']:continue
            anchors=[t.lower() for t in c['tags'] if len(t)>=2 and t.lower() not in ('ai','ab','human','count')]
            score=float(scores[i])+(.10 if any(t in question.lower() for t in anchors) else 0)
            sections=[(float(section_scores[j]),r) for j,r in enumerate(self.sections) if r['card_id']==c['card_id']]
            sections.sort(key=lambda x:(-x[0],x[1]['section']))
            if strategy=='sectional':score=.75*score+.25*sections[0][0]+(.20 if requested.intersection(c['methods']) else 0)
            if score<.07:continue
            sources=[self.catalog['sources'][x] for x in c['source_ids']]
            spans=[]
            for value,row in sections[:3]:
                spans.append({**row,'score':round(value,6),'span_type':'original_local_method_summary_not_source_quote','locator':'sections.'+row['section'],'source_ids':c['source_ids']})
            provenance=[{'source_id':v['source_id'],'url':v['url'],'locator':v['locator'],'checked_on':v['checked_on'],'access_scope':v['access_scope'],'scope':'selected_pages_only' if c.get('full_text_reviewed') else v['access_scope'],'source_record_sha256':hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True).encode()).hexdigest()} for v in sources]
            hits.append(dict(**c,score=round(score,5),sources=sources,matched_sections=spans,provenance=provenance,knowledge_sha256=self.digest))
        hits.sort(key=lambda h:(-h['score'],h['card_id']))
        if hits:hits=[h for h in hits if h['score']>=max(.07,hits[0]['score']*.4)]
        return {'status':'found' if hits else 'insufficient_evidence','hits':hits[:k],'knowledge_version':self.catalog['version'],'knowledge_sha256':self.digest,'retrieval_version':strategy+'-v1','note':'方法卡为原创提炼；命中段落保留位置与摘要指纹。来源页码和核对范围按登记记录展示，全文页核对不代表全文穷尽审阅。' if hits else '没有足够相关的已核实依据，不生成论文或引用。'}
    def validate_citations(self,ids,hits):
        allowed={h['card_id']:h for h in hits}
        if not ids or set(ids)-set(allowed):raise ValueError('引用必须来自本轮实际检索的知识卡。')
        for key in ids:
            hit=allowed[key]
            if hit.get('knowledge_sha256',self.digest)!=self.digest:raise ValueError('引用知识库版本已改变，请重新检索。')
            card=next((c for c in self.cards if c['card_id']==key),None)
            if not card or card['source_ids']!=hit['source_ids']:raise ValueError('引用来源与已登记知识卡不一致。')
            expected_sources=[self.catalog['sources'][sid] for sid in card['source_ids']]
            if hit.get('sources',expected_sources)!=expected_sources:raise ValueError('引用的来源地址或核对范围与登记记录不一致。')
            for row in hit.get('matched_sections',[]):
                if row['text']!=card['sections'].get(row['section']) or hashlib.sha256(row['text'].encode()).hexdigest()!=row['note_sha256']:raise ValueError('引用段落与本地知识卡不一致。')
        return [allowed[key] for key in ids]
