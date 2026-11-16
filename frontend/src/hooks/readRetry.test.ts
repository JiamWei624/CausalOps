import {afterEach,it,expect,vi} from 'vitest';
import {request} from '../api';
const response=(code:string,status:number)=>new Response(JSON.stringify({error:{code,message:'test-only'}}),{status,headers:{'Content-Type':'application/json'}});
afterEach(()=>vi.unstubAllGlobals());
it('retries only a typed publishing read, then returns the verified response',async()=>{
 const f=vi.fn().mockResolvedValueOnce(response('research_updating',503)).mockResolvedValueOnce(new Response(JSON.stringify({schema:'verified-read'}),{status:200}));vi.stubGlobal('fetch',f);
 expect(await request('/chats/test/research')).toEqual({schema:'verified-read'});expect(f).toHaveBeenCalledTimes(2);
});
it('never automatically replays an approval or dispatch POST',async()=>{
 const f=vi.fn().mockResolvedValue(response('research_updating',503));vi.stubGlobal('fetch',f);
 await expect(request('/chats/test/research/start',{method:'POST',body:'{}'})).rejects.toMatchObject({code:'research_updating'});expect(f).toHaveBeenCalledTimes(1);
});
it('does not retry an integrity failure or substitute another study',async()=>{
 const f=vi.fn().mockResolvedValue(response('source_conflict',409));vi.stubGlobal('fetch',f);
 await expect(request('/chats/test/research')).rejects.toMatchObject({code:'source_conflict'});expect(f).toHaveBeenCalledTimes(1);
});
