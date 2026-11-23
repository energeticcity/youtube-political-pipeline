// Independent clock for the existing GitHub-hosted publishing tools.
export async function dispatchTick(env, when, fetcher=fetch) {
  const localHour=(new Date(when).getUTCHours()+17)%24;
  if(localHour<7 || localHour>19)return {status:'outside_hours'};
  if(!env.GITHUB_DISPATCH_TOKEN)throw new Error('Repository-limited dispatch token is not configured');
  const response=await fetcher('https://api.github.com/repos/energeticcity/youtube-political-pipeline/actions/workflows/gta6-hourly.yml/dispatches',{
    method:'POST',
    headers:{Authorization:`Bearer ${env.GITHUB_DISPATCH_TOKEN}`,'User-Agent':'gta6-hourly-clock','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'},
    body:JSON.stringify({ref:'main',inputs:{operation:'tick',timer_source:'cloudflare'}})
  });
  if(response.status!==204)throw new Error(`GitHub dispatch failed: HTTP ${response.status}`);
  return {status:'dispatched',scheduled_time:new Date(when).toISOString()};
}
export default {
  async scheduled(event,env) {
    const result=await dispatchTick(env,event.scheduledTime);
    console.log(JSON.stringify(result));
  },
  async fetch(){return new Response('Not found',{status:404});}
};
