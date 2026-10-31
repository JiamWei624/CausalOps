"""LangChain retriever over the existing, provenance-checked lexical index."""
from typing import Any
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import Field

class MethodRetriever(BaseRetriever):
    library: Any=Field(exclude=True)
    k: int=Field(default=4,ge=1,le=8)

    def _get_relevant_documents(self,query: str,*,run_manager: CallbackManagerForRetrieverRun):
        hits=self.library.search(query,k=self.k)
        return [Document(page_content='\n'.join(name+'：'+text for name,text in hit['sections'].items()),metadata={
            'card_id':hit['card_id'],'title':hit['title'],'knowledge_sha256':self.library.digest,
            'version':hit['version'],'source_ids':hit['source_ids'],'sources':hit['sources'],
            'matched_sections':hit.get('matched_sections',[]),'score':hit['score'],
            'content_scope':'original_local_summary_not_full_text'}) for hit in hits['hits']]

    def search_bundle(self,query: str):
        # invoke exercises the real LangChain Retriever interface; exact cards remain authoritative.
        docs=self.invoke(query,config={'callbacks':[],'tags':['local-methods']})
        hits=self.library.search(query,k=self.k)
        if [d.metadata['card_id'] for d in docs]!=[h['card_id'] for h in hits['hits']]:
            raise ValueError('检索接口与来源目录不一致。')
        if hits['hits']:self.library.validate_citations([h['card_id'] for h in hits['hits']],hits['hits'])
        return hits
