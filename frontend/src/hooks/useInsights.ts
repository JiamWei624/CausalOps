import {useEffect,useRef,useState} from 'react';
import {request,key} from '../api';
import type {InsightView,DecisionInput} from '../insights';
type Receipt={report_id:string;decision_id?:string;receipt_ref:string};
export function useInsights(cid:string|null,ready:boolean,bindingId?:string){
  const [value,setValue]=useState<InsightView|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const current=useRef(cid),sequence=useRef(0),generation=useRef(0),writing=useRef(false),pending=useRef<{signature:string;body:object;key:string}|null>(null);
  current.current=cid;
  async function load(id:string,report?:string){
    const version=generation.current,n=++sequence.current;
    const v=await request<InsightView>('/chats/'+id+'/insights'+(report?'/reports/'+report:''));
    if(current.current===id&&version===generation.current&&n===sequence.current){setValue(v);setError('');return v;}
    return null;
  }
  useEffect(()=>{
    generation.current++;setValue(null);setError('');setNotice('');pending.current=null;
    if(!cid||!ready)return;
    const id=cid,version=generation.current;
    const report=new URLSearchParams(location.search).get('diagnostic')||undefined;
    void load(id,report).catch(e=>{if(current.current===id&&version===generation.current)setError(e.message)});
  },[cid,ready,bindingId]);
  async function refresh(report?:string){
    if(!cid)return;const id=cid,version=generation.current;
    try{const v=await load(id,report);if(v){const u=new URL(location.href);if(v.report)u.searchParams.set('diagnostic',v.report.report_id);else u.searchParams.delete('diagnostic');history.replaceState({},'',u);}}
    catch(e){if(current.current===id&&version===generation.current){setValue(null);setError((e as Error).message);}}
  }
  async function operate(action:'generate'|'decisions',decision?:DecisionInput){
    if(!cid||!value||value.chat_id!==cid||writing.current)return;
    const id=cid,version=generation.current;
    const fields={expected_binding_id:value.binding_id,expected_context_sha:value.context_sha,human_confirmed:true,
      ...(decision?{...decision,report_id:value.report!.report_id,expected_report_sha:value.report_sha}:{})};
    const signature=JSON.stringify({id,action,...fields});
    if(pending.current?.signature!==signature){const k=key();pending.current={signature,key:k,body:{...fields,request_key:k}};}
    const op=pending.current;writing.current=true;setBusy(true);setError('');setNotice('正在核验当前报告与来源…');
    const apply=async(r:Receipt)=>{
      if(current.current!==id||generation.current!==version)return;
      pending.current=null;await refresh(r.report_id);
      setNotice(r.decision_id?'研究决定已保存 · 无统计执行权限':'诊断已保存 · 未执行新的统计');
    };
    try{await apply(await request<Receipt>('/chats/'+id+'/insights/'+action,{method:'POST',body:JSON.stringify(op.body)}));}
    catch(e){
      if(current.current===id&&generation.current===version){
        // A write may already have committed. Read the durable receipt; never
        // replay the POST automatically, even on timeout or network failure.
        try{const r=await request<{receipt:Receipt|null}>('/chats/'+id+'/insights/receipts/'+op.key);if(r.receipt){await apply(r.receipt);return;}}catch{/* retain original failure */}
        setNotice('操作未确认完成；已核查持久回执，未自动重发。请先刷新来源。');
        try{await load(id,value.report?.report_id)}catch{setValue(null);}
        if(current.current===id&&generation.current===version)setError((e as Error).message);
      }
    }finally{writing.current=false;setBusy(false);}
  }
  return {value:value?.chat_id===cid?value:null,error,busy,notice,refresh,generate:()=>operate('generate'),save:(d:DecisionInput)=>operate('decisions',d)};
}
