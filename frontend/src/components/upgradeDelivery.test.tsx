import {it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {StudyContextPanel} from './StudyContextPanel';
import type {Study,Artifacts} from '../api';
const noop=()=>{};
const study={title:'合法历史研究',scope:{metric:'response',window:'两周'},run_ids:['saved-run'],status:'completed',domain:'automation_v2',report_available:true,links:{}} as unknown as Study;
it('offers recheck while retaining the native report entry for a verified stale diagnostic',()=>{
 const artifacts={diagnostic:null,decisions:[],diagnostic_status:'recheck_required',diagnostic_message:'研究诊断需要重新核验，原有报告和历史记录已保留。'} as unknown as Artifacts;
 const html=renderToStaticMarkup(<StudyContextPanel study={study} setup={null} artifacts={artifacts} loading={false} error='' onClose={noop} onReport={noop} onConfigure={noop} onCandidate={noop} onInsights={noop}/>);
 expect(html).toContain('研究诊断需要重新核验，原有报告和历史记录已保留。');
 expect(html).toContain('重新检查研究证据');expect(html).toContain('阅读研究报告');
});
