"""Capture only responses and provider usage; authorization and request bodies are never logged."""
import json
from datetime import datetime,timezone
from time import perf_counter
from pydantic import BaseModel,ConfigDict
from causalops.llm.providers import StructuredModelClient,ProviderConfig


def append(path,value):
    with path.open('a',encoding='utf8') as f:f.write(json.dumps(value,ensure_ascii=False,default=str)+'\n')


class Advice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:str
    methods:list[str]
    fields:list[str]
    requirements:list[str]
    reasoning:str


class Metered(StructuredModelClient):
    def __init__(self,key,folder):
        super().__init__(ProviderConfig(max_output_tokens=3000,timeout_seconds=45,max_retries=0),key)
        self.folder=folder
        self.index=0

    def _content(self,response):
        text,usage=super()._content(response)
        self.raw=text.replace(self._api_key,'[已移除]')
        self.usage=usage
        return text,usage

    def complete_json(self,**kw):
        schema=kw['output_schema'].get('title','结构化输出')
        self.index+=1
        record=dict(number=self.index,schema=schema,at=datetime.now(timezone.utc).isoformat(),config=self.provider_config.model_dump())
        append(self.folder/'requests.jsonl',record)
        t=perf_counter();self.raw=None;self.usage={};self.last_telemetry={}
        try:
            value=super().complete_json(**kw)
            record.update(valid=True,output=value)
            return value
        except Exception as err:
            record.update(valid=False,error=type(err).__name__)
            raise
        finally:
            record.update(seconds=perf_counter()-t,raw=self.raw,usage=self.usage,telemetry=self.last_telemetry)
            append(self.folder/'responses.jsonl',record)
