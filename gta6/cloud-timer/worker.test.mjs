import test from 'node:test';
import assert from 'node:assert/strict';
import {dispatchTick} from './worker.mjs';
test('uses Dawson Creek posting/discovery hours, including UTC date rollover',async()=>{
  for(const time of ['2026-11-23T13:57:00Z','2026-11-24T03:02:00Z']){
    assert.equal((await dispatchTick({},time,()=>{throw Error('Unexpected request')})).status,'outside_hours');
  }
  for(const time of ['2026-11-23T14:02:00Z','2026-11-24T02:57:00Z']){
    let calls=0;
    const result=await dispatchTick({GITHUB_DISPATCH_TOKEN:'fixture'},time,async(url,request)=>{
      calls++;
      assert.equal(url,'https://api.github.com/repos/energeticcity/youtube-political-pipeline/actions/workflows/gta6-hourly.yml/dispatches');
      assert.deepEqual(JSON.parse(request.body),{ref:'main',inputs:{operation:'tick',timer_source:'cloudflare'}});
      return {status:204};
    });
    assert.equal(calls,1);assert.equal(result.status,'dispatched');
  }
});
test('failed dispatch is an error rather than a successful timer check',async()=>{
  await assert.rejects(()=>dispatchTick({GITHUB_DISPATCH_TOKEN:'fixture'},'2026-11-23T19:07:00Z',async()=>({status:403})),/HTTP 403/);
  await assert.rejects(()=>dispatchTick({},'2026-11-23T19:07:00Z'),/not configured/);
});
