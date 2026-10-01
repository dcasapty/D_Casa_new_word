// node resumen.js dir -> tabla de medianas por etiqueta (y resumen.json)
const fs=require('fs'),path=require('path');const dir=process.argv[2];
const files=fs.readdirSync(dir).filter(f=>f.endsWith('.json')&&/-\d+\.json$/.test(f));
const by={};
for(const f of files){const tag=f.replace(/-\d+\.json$/,'');const r=JSON.parse(fs.readFileSync(path.join(dir,f)));
 const a=r.audits;const items=(a['network-requests']?.details?.items)||[];
 const byType={};let total=0;for(const it of items){const t=it.resourceType||'Other';byType[t]=(byType[t]||0)+(it.transferSize||0);total+=it.transferSize||0;}
 const origins=new Set(items.map(i=>{try{return new URL(i.url).origin}catch{return''}}));
 (by[tag]=by[tag]||[]).push({perf:Math.round(r.categories.performance.score*100),a11y:Math.round(r.categories.accessibility.score*100),bp:Math.round(r.categories['best-practices'].score*100),seo:Math.round(r.categories.seo.score*100),
 fcp:a['first-contentful-paint'].numericValue,lcp:a['largest-contentful-paint'].numericValue,tbt:a['total-blocking-time'].numericValue,cls:a['cumulative-layout-shift'].numericValue,si:a['speed-index'].numericValue,
 ttfb:a['server-response-time']?.numericValue,kb:Math.round(total/1024),req:items.length,origins:origins.size,
 kbType:Object.fromEntries(Object.entries(byType).map(([k,v])=>[k,Math.round(v/1024)])),
 lcpEl:(a['largest-contentful-paint-element']?.details?.items?.[0]?.items?.[0]?.node?.snippet||'').slice(0,120),
 unusedJsKb:Math.round((a['unused-javascript']?.details?.overallSavingsBytes||0)/1024),
 renderBlocking:(a['render-blocking-resources']?.details?.items||a['render-blocking-insight']?.details?.items||[]).map(i=>i.url).slice(0,5)});}
const med=v=>{const s=[...v].sort((x,y)=>x-y);return s[Math.floor(s.length/2)]};
const out={};
for(const [tag,runs] of Object.entries(by)){const m={runs:runs.length};for(const k of ['perf','a11y','bp','seo','fcp','lcp','tbt','cls','si','ttfb','kb','req','origins','unusedJsKb'])m[k]=med(runs.map(r=>r[k]??0));
 m.perfRuns=runs.map(r=>r.perf);m.lcpRuns=runs.map(r=>Math.round(r.lcp));
 const mid=runs.find(r=>r.perf===m.perf)||runs[0];m.kbType=mid.kbType;m.lcpEl=mid.lcpEl;m.renderBlocking=mid.renderBlocking;out[tag]=m;}
fs.writeFileSync(path.join(dir,'resumen.json'),JSON.stringify(out,null,1));
console.log('| Página | Perf (3 corridas) | LCP ms | FCP ms | TBT ms | CLS | SI ms | TTFB ms | KB | Pet. | Orígenes |');
for(const [t,m] of Object.entries(out))console.log(`| ${t} | ${m.perf} (${m.perfRuns.join('/')}) | ${Math.round(m.lcp)} | ${Math.round(m.fcp)} | ${Math.round(m.tbt)} | ${m.cls.toFixed(3)} | ${Math.round(m.si)} | ${Math.round(m.ttfb)} | ${m.kb} | ${m.req} | ${m.origins} |`);
for(const [t,m] of Object.entries(out))console.log(t,JSON.stringify(m.kbType),'LCP:',m.lcpEl,'| JS no usado KB:',m.unusedJsKb,'| a11y/bp/seo',m.a11y,m.bp,m.seo);
