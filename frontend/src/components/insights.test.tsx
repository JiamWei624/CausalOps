import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,it,expect,vi} from 'vitest';
import {DecisionForm,InsightsReader} from './InsightsReader';
import type {InsightView} from '../insights';
const base={chat_id:'chat',subject_id:'task',title:'实际单元属性',mode:'post_run',history:[],source_current:true,decisions:[],reminders:[],report:null} as unknown as InsightView;
const props={error:'',notice:'',busy:false,onGenerate:vi.fn(),onSave:vi.fn(),onReport:vi.fn(),onBack:vi.fn(),onSelect:vi.fn(),onRefresh:vi.fn()};
describe('explicit diagnostic and user decision boundary',()=>{
 it('does not generate a report just to render the entry',()=>{
  const s=renderToStaticMarkup(<InsightsReader {...props} value={base}/>);
  expect(s).toContain('尚未生成研究诊断');expect(props.onGenerate).not.toHaveBeenCalled();
 });
 it('note and confirmation default to a disabled save',()=>{
  const s=renderToStaticMarkup(<DecisionForm value={base} busy={false} onSave={props.onSave}/>);
  expect(s).toContain('不批准或执行统计');expect(s).not.toContain('checked=""');expect(s).toMatch(/disabled=""[^>]*>保存研究决定/);
 });
 it('stale source cannot submit a decision',()=>{
  const s=renderToStaticMarkup(<DecisionForm value={{...base,source_current:false}} busy={false} onSave={props.onSave}/>);
  expect(s).toContain('disabled=""');expect(props.onSave).not.toHaveBeenCalled();
 });
 it('suggestion type is initially unselected, not accepted',()=>{
  const suggestion={suggestion_id:'sg',rule_id:'PD-02',action:'补充来源'} as never;
  const s=renderToStaticMarkup(<DecisionForm value={{...base,report:{report_id:'r'} as never}} suggestion={suggestion} busy={false} onSave={props.onSave}/>);
  expect(s).toContain('value="" selected=""');expect(s).not.toContain('value="accepted" selected');
 });
 it('a failed source does not substitute another report',()=>{
  const s=renderToStaticMarkup(<InsightsReader {...props} value={null} error="报告内容哈希冲突"/>);
  expect(s).toContain('报告内容哈希冲突');expect(s).not.toContain('data-layer="results"');
 });
});
