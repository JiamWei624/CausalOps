import { it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { CandidatePlanView } from './CandidatePlanView';
import type { SetupView,Study } from '../api';
const noop=()=>{},accept=async()=>{};
const base={phase:'adopted',candidate:{id:'1'.repeat(32),source_state:'adopted',source_current:false,source_error:null,candidate:{candidate:{objective:'真实领域来源的组件投影示例',research_type:'descriptive_binary',declared_assignment:'unknown',steps:[]}}}} as unknown as SetupView;
function render(setup:SetupView){return renderToStaticMarkup(<CandidatePlanView setup={setup} study={{status:'candidate',run_ids:[],links:{}} as unknown as Study} busy={false} error='' onBack={noop} onConfigure={noop} onGenerate={noop} onAdopt={accept} onReview={noop}/>)}
it('a verified adopted projection explains completion rather than stale failure',()=>{
 const html=render(base);expect(html).toContain('已转为待审方案');expect(html).not.toContain('当前不能采纳');expect(html).toContain('进入正式人工审核');expect(html).not.toContain('>采纳为待审方案<');
});
it('an actual stale unadopted source remains an error',()=>{
 const value={...base,phase:'candidate',candidate:{...base.candidate!,source_state:'stale',source_error:'合同版本已变化'}} as unknown as SetupView;
 const html=render(value);expect(html).toContain('合同版本已变化');expect(html).toContain('当前不能采纳');expect(html).toContain('disabled');
});
