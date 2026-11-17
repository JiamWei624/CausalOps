import {it,expect} from 'vitest';
import {completedControlNotice} from './useResearch';
import type {ResearchView} from '../api';
const expected={id:'task-a',plan_sha:'plan-a'};
const fresh={task:{...expected,status:'completed'}} as ResearchView;
it('a confirmed same-plan completion race is explicit for pause and cancel',()=>{
 expect(completedControlNotice('pause',expected,fresh,true)).toBe('研究已完成，本次暂停请求未生效。');
 expect(completedControlNotice('cancel',expected,fresh,true)).toContain('本次取消请求未生效');
});
it('never claims a control did not apply from uncertain network outcomes',()=>{
 expect(completedControlNotice('pause',expected,fresh,false)).toBeNull();
});
it('does not reinterpret a different task, plan, missing or incomplete source',()=>{
 for(const f of [null,{task:{...expected,id:'task-b',status:'completed'}},{task:{...expected,plan_sha:'other',status:'completed'}},{task:{...expected,status:'paused'}}]){
  expect(completedControlNotice('pause',expected,f as ResearchView|null,true)).toBeNull();
 }
 expect(completedControlNotice('start',expected,fresh,true)).toBeNull();
});
