import {it,expect} from 'vitest';
import {shouldPollResearch} from './useResearch';
import type {ResearchView} from '../api';
const value=(status:string,active=false,jobs:object[]=[])=>( {task:{status},active,jobs} as ResearchView);
it('keeps reading a stop request after the job settles until the task terminal state arrives',()=>{expect(shouldPollResearch(value('cancel_requested',false,[{status:'cancelled'}]))).toBe(true);expect(shouldPollResearch(value('pause_requested',false,[{status:'paused'}]))).toBe(true)});
it('does not mistake between-step approved for final completion of an existing job',()=>{expect(shouldPollResearch(value('approved',false,[{status:'completed'}]))).toBe(true);expect(shouldPollResearch(value('approved'))).toBe(false)});
it('stops polling coherent terminal states and never creates a new task',()=>{for(const status of ['cancelled','completed','paused','blocked'])expect(shouldPollResearch(value(status))).toBe(false);expect(shouldPollResearch(null)).toBe(false)});
