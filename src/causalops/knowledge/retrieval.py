"""Deterministic local sparse retrieval: original bilingual method cards, no data embedding."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
CATALOG=Path(__file__).with_name('catalog.json')
class MethodLibrary:
    def __init__(self,path=None):
        raw=Path(path or CATALOG).read_bytes();self.digest=hashlib.sha256(raw).hexdigest();self.catalog=json.loads(raw);self.cards=self.catalog['cards']
        self.texts=[c['title']+' '+ ' '.join(c['methods']+c['tags'])+' '+ ' '.join(c['sections'].values()) for c in self.cards]
        self.vectorizer=TfidfVectorizer(analyzer='char',ngram_range=(2,4),sublinear_tf=True);self.matrix=self.vectorizer.fit_transform(self.texts)
    def search(self,question,*,method=None,k=4):
        if not isinstance(question,str) or not question.strip() or len(question)>3000:raise ValueError('检索问题须为1至3000字。')
        if not 1<=k<=8:raise ValueError('最多检索8条方法卡。')
        if re.search(r'因果森林|合成控制',question,re.I):
            return {'status':'insufficient_evidence','hits':[],'knowledge_version':self.catalog['version'],'knowledge_sha256':self.digest,'note':'当前知识库尚无该方法的已核实专门条目；不以相近关键词替代。'}
        scores=cosine_similarity(self.vectorizer.transform([question.lower()]),self.matrix)[0];hits=[]
        for i,c in enumerate(self.cards):
            if method and method not in c['methods']:continue
            anchors=[t.lower() for t in c['tags'] if len(t)>=2 and t.lower() not in ('ai','ab','human','count')]
            if any(t in question.lower() for t in anchors):scores[i]+=.10
            if scores[i]<.07:continue
            sources=[self.catalog['sources'][s] for s in c['source_ids']]
            hits.append(dict(**c,score=round(float(scores[i]),5),sources=sources,knowledge_sha256=self.digest))
        hits.sort(key=lambda h:(-h['score'],h['card_id']))
        if hits:hits=[h for h in hits if h['score']>=max(.07,hits[0]['score']*.4)]
        return {'status':'found' if hits else 'insufficient_evidence','hits':hits[:k],'knowledge_version':self.catalog['version'],'knowledge_sha256':self.digest,'note':'原创方法提炼；实证例子分摘要和已核对全文页，均不是当前数据的识别证明。' if hits else '知识库中没有足够相关的已核实依据，不生成论文或引用。'}
    def validate_citations(self,ids,hits):
        allowed={h['card_id'] for h in hits}
        if not ids or set(ids)-allowed:raise ValueError('引用必须来自本轮实际检索的知识卡。')
        return [h for h in hits if h['card_id'] in ids]
