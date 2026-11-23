"""Entity card + linkify for 06_PR_TO_CI_VISUAL.html (v2, phase P2). Idempotent.

Needs the entity index embedded by build_entities.py (<script id="entData">).
Run after the tab generators and before build_i18n.py.

What it adds to the page:
  - window.ENT            the index: ENT.get(key), ENT.out(key), ENT.inn(key), ENT.has(key)
  - openEntity("pr:6041") one card for every kind, in a side drawer (full screen under 700 px). Esc closes.
  - #e/<kind>/<id>        hash route for a shared link (the tab hash comes back when the card closes)
  - ENT.linkify(root)     THE one linkify helper. It runs on every tab's output (also on what tabs render later):
                          GitHub PR / issue / release links, Buildkite build links, [data-pr] / [data-area] / [data-path],
                          and plain-text mentions (#1234, tests/…py, pipeline slugs, GPU workloads, release tags, feature names).
                          A plain click opens the card; Ctrl / middle click keeps the external link.
  - ENT.a(key, label)     HTML of one entity link, for generator JS that builds new rows (Today tab, P3).
  - "Links" block         link health in Report 1130 → Data quality.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path as _Path  # noqa: E402

PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")

CSS = r"""
/* ENTUI:CSS:START */
.ent-l{cursor:pointer;text-decoration:underline dotted;text-decoration-color:var(--text-muted);text-underline-offset:2px;border-radius:3px}
.ent-l:hover,a[data-ent]:hover{text-decoration:underline solid;text-decoration-color:currentColor}
.ent-l:focus-visible,.ent-i:focus-visible{outline:2px solid var(--series-1);outline-offset:1px}
.ent-i{all:unset;cursor:pointer;display:inline-grid;place-items:center;width:16px;height:16px;margin-left:6px;border-radius:50%;font-size:10px;font-weight:700;line-height:1;color:var(--text-muted);border:1px solid var(--border);vertical-align:middle;flex:none}
.ent-i:hover{color:var(--text-primary);border-color:var(--text-muted)}
.ent-flash{animation:entFlash 1.6s ease}
@keyframes entFlash{0%,60%{background:color-mix(in oklab,var(--series-1) 22%,transparent)}100%{background:transparent}}
.ent-drawer{position:fixed;top:0;right:0;bottom:0;width:min(440px,100vw);z-index:80;background:var(--surface-1);border-left:1px solid var(--border);box-shadow:-8px 0 28px rgba(0,0,0,.18);display:flex;flex-direction:column;transform:translateX(102%);transition:transform .18s ease;visibility:hidden}
.ent-drawer.on{transform:none;visibility:visible}
.ent-hd{display:flex;gap:8px;align-items:flex-start;padding:14px 16px 10px;border-bottom:1px solid var(--border)}
.ent-hd .tt{flex:1;min-width:0}
.ent-kind{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-secondary);background:var(--surface-2);border-radius:5px;padding:2px 7px;margin-right:6px}
.ent-id{font:600 12.5px ui-monospace,Consolas,monospace;color:var(--text-secondary);overflow-wrap:anywhere}
.ent-title{margin:6px 0 0;font-size:14.5px;font-weight:650;line-height:1.35;color:var(--text-primary);overflow-wrap:anywhere}
.ent-x,.ent-back{all:unset;cursor:pointer;width:28px;height:28px;display:grid;place-items:center;border-radius:7px;color:var(--text-secondary);font-size:16px;flex:none}
.ent-x:hover,.ent-back:hover{background:var(--surface-2);color:var(--text-primary)}
.ent-x:focus-visible,.ent-back:focus-visible{outline:2px solid var(--series-1)}
.ent-back[hidden]{display:none}
.ent-bd{flex:1;overflow:auto;padding:12px 16px 24px;font-size:12.5px;color:var(--text-primary)}
.ent-row{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin:0 0 10px}
.ent-lab{font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);min-width:64px}
.ent-st{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:650;color:var(--text-secondary);white-space:nowrap}
.ent-st i{width:8px;height:8px;border-radius:50%;background:var(--text-muted);flex:none}
.ent-st.green i{background:var(--good)}.ent-st.red i{background:var(--critical)}.ent-st.running i{background:var(--series-1)}
.ent-st.waiting i{background:var(--warning)}.ent-st.unknown i{background:transparent;border:1.5px solid var(--text-muted);box-sizing:border-box}
.ent-verb{display:inline-block;font-size:11px;font-weight:750;letter-spacing:.03em;padding:2px 8px;border-radius:6px;border:1.5px solid var(--text-secondary);color:var(--text-primary);white-space:nowrap}
.ent-verb.ta{border-style:dashed}
.ent-why{color:var(--text-secondary)}
.ent-sec{margin:16px 0 6px;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);display:flex;gap:6px;align-items:center}
.ent-sec::after{content:"";flex:1;height:1px;background:var(--border)}
.ent-grp{margin:0 0 8px}
.ent-grp>b{display:block;font-size:11.5px;font-weight:650;color:var(--text-secondary);margin:0 0 3px}
.ent-grp>b small{font-weight:500;color:var(--text-muted)}
.ent-nb{display:flex;gap:8px;align-items:center;padding:4px 6px;margin:0 -6px;border-radius:6px;cursor:pointer}
.ent-nb:hover{background:var(--surface-2)}
.ent-nb:focus-visible{outline:2px solid var(--series-1)}
.ent-nb .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ent-nb .nm code{font-size:11.5px;color:var(--text-secondary);margin-right:6px}
.ent-nb .sg{font-size:10px;color:var(--text-muted);border:1px solid var(--border);border-radius:4px;padding:0 4px}
.ent-more{all:unset;cursor:pointer;font-size:11.5px;color:var(--series-1);padding:2px 0}
.ent-more:hover{text-decoration:underline}
.ent-ev{border:1px solid var(--border);border-radius:8px;padding:0 10px;margin-top:6px}
.ent-ev>summary{cursor:pointer;padding:8px 0;font-weight:650;font-size:12px;color:var(--text-secondary)}
.ent-ev[open]>summary{border-bottom:1px solid var(--border);margin-bottom:8px}
.ent-kv{display:grid;grid-template-columns:max-content 1fr;gap:3px 12px;margin:0 0 8px}
.ent-kv dt{color:var(--text-muted)}.ent-kv dd{margin:0;overflow-wrap:anywhere}
.ent-log{display:block;font:11.5px ui-monospace,Consolas,monospace;background:var(--surface-2);border-radius:6px;padding:6px 8px;margin:0 0 8px;white-space:pre-wrap;overflow-wrap:anywhere}
.ent-ext{display:inline-block;margin:0 10px 8px 0;font-weight:600;color:var(--series-1)}
.ent-ev .ent-row{margin:0 0 4px}.ent-ev .ent-row .ent-ext{margin-bottom:0}
.ent-tabs{display:flex;gap:6px;flex-wrap:wrap}
.ent-tab{all:unset;cursor:pointer;font-size:11.5px;padding:3px 9px;border-radius:999px;border:1px solid var(--border);color:var(--text-secondary)}
.ent-tab:hover{border-color:var(--text-muted);color:var(--text-primary)}
.ent-tab:focus-visible{outline:2px solid var(--series-1)}
.ent-none{color:var(--text-muted)}
.ent-health{margin-top:18px;border-top:1px solid var(--border);padding-top:14px}
.ent-health h3{margin:0 0 4px;font-size:14px}
.ent-health p{margin:0 0 10px;color:var(--text-secondary);font-size:12.5px}
.ent-health .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}
.ent-health table{width:100%;border-collapse:collapse;font-size:12.5px}
.ent-health th{text-align:left;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);font-weight:700;padding:4px 0;border-bottom:1px solid var(--border)}
.ent-health td{padding:3px 0;border-bottom:1px solid color-mix(in oklab,var(--border) 55%,transparent)}
.ent-health td.r,.ent-health th.r{text-align:right;font-variant-numeric:tabular-nums}
@media (max-width:700px){.ent-drawer{width:100vw;border-left:0}}
@media (prefers-reduced-motion:reduce){.ent-drawer{transition:none}.ent-flash{animation:none}}
/* ENTUI:CSS:END */
"""

JS = r"""
<!-- ENTUI:JS:START -->
<aside class="ent-drawer" id="entDrawer" role="dialog" aria-modal="false" aria-labelledby="entTitle" aria-hidden="true">
  <div class="ent-hd"><button type="button" class="ent-back" id="entBack" hidden>←</button><div class="tt" id="entHead"></div><button type="button" class="ent-x" id="entClose">✕</button></div>
  <div class="ent-bd" id="entBody"></div>
</aside>
<script>
(function(){
  const src=document.getElementById('entData'); if(!src) return;
  let D; try{D=JSON.parse(src.textContent);}catch(e){return;}
  const N=D.nodes,K=D.K,OUT={},INN={};
  D.E.forEach(e=>{const a=K[e[0]],b=K[e[1]],x={a,b,rel:D.R[e[2]],s:D.S[e[3]]};(OUT[a]=OUT[a]||[]).push(x);(INN[b]=INN[b]||[]).push(x);});
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en;
  const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const LEVEL={sprint:0,release:1,pr:2,feature:3,ci:4,build:5,test:6,bug:7};
  const KIND={sprint:['Sprint item','Hạng mục sprint'],release:['Release','Release'],pr:['PR','PR'],feature:['Feature','Tính năng'],ci:['CI pipeline','CI pipeline'],build:['CI build','CI build'],test:['Test','Test'],bug:['Bug','Bug']};
  const KINDS={sprint:['Sprint items','Hạng mục sprint'],release:['Releases','Release'],pr:['PRs','PR'],feature:['Features','Tính năng'],ci:['CI pipelines','CI pipeline'],build:['CI builds','CI build'],test:['Tests','Test'],bug:['Bugs','Bug']};
  const STW={green:['green','xanh'],red:['red','đỏ'],running:['running','đang chạy'],waiting:['waiting','đang chờ'],unknown:['unknown','chưa rõ']};
  // relation -> [label seen from the "from" node, label seen from the "to" node]
  const REL={plans:[['plans','gồm'],['planned by','thuộc hạng mục']],targets:[['targets','nhắm tới'],['sprint items','hạng mục sprint']],
    contains:[['contains','chứa'],['first tagged in','gắn tag lần đầu ở']],shipped_in:[['shipped in','đã ship trong'],['ships','ship']],
    changes:[['changes','sửa'],['changed by','bị sửa bởi']],edits:[['edits test','sửa test'],['edited by','bị sửa bởi']],ran:[['ran','đã chạy'],['ran for','chạy cho']],of:[['pipeline','pipeline'],['builds','build']],
    runs:[['ran','đã chạy'],['run in','chạy trong']],runs_suite:[['runs','chạy'],['run by','được chạy bởi']],covered_by:[['tested by','được test bởi'],['tests','test cho']],
    fails_with:[['fails with','lỗi kiểu'],['seen in','gặp ở']],failed_with:[['failed with','lỗi kiểu'],['seen in','gặp ở']],fixed_by:[['fixed by','sửa bởi'],['fixes','sửa']]};
  const SG={likely:['likely','có thể'],weak:['weak','yếu']};
  const TABN={'obs/release':'Releases','obs/trace':'Release trace','obs/coming':'Next release','obs/opt_cpu':'CI cost · CPU','obs/opt_gpu':'CI cost · GPU','obs/overlap':'Rebase risk','obs/today':'Today',
    'r1130/baseline':'GPU baseline','r1130/cpu':'CPU baseline','r1130/green':'Time to green','r1130/retry':'Ran again','r1130/prs':'Per PR','r1130/track':'Track vs baseline','r1130/quality':'Data quality',
    'gates/guide':'Guide & gates','gates/tiers':'Tiers & Impact','cpu/overview':'CPU overview','cpu/tiers':'CPU coverage','cpu/cost':'CPU cost','cpu/findings':'CPU findings','cpu/explore':'Test Explorer',
    'gpu/overview':'GPU overview','gpu/tiers':'GPU workloads','gpu/cost':'GPU cost','gpu/findings':'GPU findings','gpu/explore':'Mindmap'};
  const st=s=>`<span class="ent-st ${esc(s)}"><i></i>${T(...(STW[s]||STW.unknown))}</span>`;
  const label=n=>n.kind==='pr'?'#'+n.id:n.kind==='bug'?n.id.replace(/^issue\//,'#').replace(/^sig\//,''):n.kind==='test'?n.id.replace(/^gpu\//,''):n.id;
  const key=(kind,id)=>kind+':'+id;

  // ---------------------------------------------------------------- the index API
  const ENT=window.ENT={data:D,get:k=>N[k],has:k=>!!N[k],out:k=>OUT[k]||[],inn:k=>INN[k]||[],
    a:(k,lab)=>N[k]?`<span class="ent-l" data-ent="${esc(k)}" role="link" tabindex="0">${esc(lab==null?label(N[k]):lab)}</span>`:esc(lab==null?k:lab)};

  // ---------------------------------------------------------------- linkify (one helper for every tab)
  const ALIAS={};   // whole-text matches: feature names, workflow names, signature names
  const WL=[],CI=[],WF=[],TDA={};   // TDA: one-word workflow names, linked only when they fill a whole table cell
  for(const k of K){const n=N[k];
    if(n.kind==='feature'&&n.title) ALIAS[n.title]=k;
    else if(n.kind==='test'&&n.hw==='gpu'){ALIAS[n.title]=k; if(n.title.includes('_')) WL.push(n.title);}
    else if(n.kind==='ci'){ if(n.id.startsWith('gha/')){ WF.push(n.title); if(/\s/.test(n.title)) ALIAS[n.title]=k; else TDA[n.title]=k; } else {ALIAS[n.id]=k; if(n.id.includes('-')) CI.push(n.id);} }
    else if(n.kind==='release') ALIAS[n.id]=k;
  }
  try{const r=JSON.parse(document.getElementById('r11Data').textContent);((r.retry||{}).sigs||[]).forEach(s=>{const n=N['bug:sig/'+s.sig];if(!n||!s.name)return;const nm=Array.isArray(s.name)?s.name:[s.name,s.name];n.names=nm;nm.forEach(x=>{ALIAS[x]='bug:sig/'+s.sig;});});}catch(e){}
  const nameOf=n=>n.names?T(n.names[0],n.names[1]):(n.title||n.id);
  const rx=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const byLen=a=>a.slice().sort((x,y)=>y.length-x.length).map(rx).join('|');
  const RX=new RegExp('(tests/[\\w/.\\-]+\\.py)|(?<![\\w&/])#(\\d{3,5})\\b|(?<![\\w\\-.])('+byLen(CI)+')(?![\\w\\-])(?:\\s+#(\\d{2,6})\\b)?|(?<![\\w/\\-.])('+byLen(WL)+')(?![\\w\\-])|\\b(v\\d+\\.\\d+\\.\\d+(?:rc\\d+)?)(?![\\w\\-]|\\.\\d)|\\b(?:GHA|GitHub Actions ·) ('+byLen(WF)+')(?![\\w\\-])','g');
  const NO_TEXT='script,style,textarea,input,select,option,svg,a,button,summary,label,[onclick],[data-ent],[contenteditable],.no-ent,.ent-drawer,.vnav,#mm,h1';
  const groupEn=new WeakMap();   // wrapper span -> English source of the text node it replaced
  function matchKey(m){
    if(m[1]) return N['test:'+m[1]]?'test:'+m[1]:null;
    if(m[2]) return N['pr:'+m[2]]?'pr:'+m[2]:N['bug:issue/'+m[2]]?'bug:issue/'+m[2]:null;
    if(m[3]) return m[4]&&N['build:'+m[3]+'/'+m[4]]?'build:'+m[3]+'/'+m[4]:(N['ci:'+m[3]]?'ci:'+m[3]:null);
    if(m[5]) return N['test:gpu/'+m[5]]?'test:gpu/'+m[5]:null;
    if(m[6]) return N['release:'+m[6]]?'release:'+m[6]:null;
    if(m[7]) return N['ci:gha/'+m[7]]?'ci:gha/'+m[7]:null;
    return null;
  }
  function span(k,txt){const s=document.createElement('span');s.className='ent-l';s.dataset.ent=k;s.setAttribute('role','link');s.tabIndex=0;s.textContent=txt;return s;}
  function linkText(n){
    const p=n.parentElement; if(!p||p.closest(NO_TEXT)) return;
    const v=n.nodeValue; if(!v||v.length<3) return;
    const whole=ALIAS[v.trim()]||(p.tagName==='TD'&&TDA[v.trim()]);
    let parts=null;
    if(whole){const lead=v.match(/^\s*/)[0],tail=v.match(/\s*$/)[0];parts=[lead,span(whole,v.trim()),tail];}
    else{
      RX.lastIndex=0; let m,last=0;
      while((m=RX.exec(v))){const k=matchKey(m); if(!k) continue; parts=parts||[]; if(m.index>last) parts.push(v.slice(last,m.index));
        let txt=m[0]; if(m[3]&&m[4]&&!k.startsWith('build:')){txt=m[3];RX.lastIndex=m.index+m[3].length;}
        parts.push(span(k,txt)); last=m.index+txt.length;}
      if(!parts) return; if(last<v.length) parts.push(v.slice(last));
    }
    const g=document.createElement('span'); g.className='ent-t';
    groupEn.set(g,(window.I18N&&I18N.origOf&&I18N.origOf(n))||v);
    parts.forEach(x=>{if(x!=='')g.append(x);}); n.replaceWith(g);
  }
  function infoBtn(host,k){
    if(!N[k]||host.querySelector(':scope > .ent-i')) return;
    const b=document.createElement('button'); b.type='button'; b.className='ent-i'; b.dataset.ent=k; b.textContent='i';
    b.setAttribute('aria-label',T('Open card','Mở thẻ')+' '+label(N[k])); host.append(b);
  }
  function linkAttrs(root){
    const q=s=>(root.matches&&root.matches(s)?[root]:[]).concat([...root.querySelectorAll(s)]);
    q('a[href]').forEach(a=>{ if(a.dataset.ent||a.closest('.ent-drawer')) return; const h=a.getAttribute('href'); let m,k=null;
      if(a.hasAttribute('data-ev')||/\/pull\/\d+\/(files|checks|commits)/.test(h)||/\/(builds\/\d+)#/.test(h)) return;   // evidence links stay external
      if((m=h.match(/github\.com\/LMCache\/LMCache\/pull\/(\d+)/))) k='pr:'+m[1];
      else if((m=h.match(/github\.com\/LMCache\/LMCache\/issues\/(\d+)/))) k='bug:issue/'+m[1];
      else if((m=h.match(/github\.com\/LMCache\/LMCache\/releases\/tag\/([\w.\-]+)/))) k='release:'+m[1];
      else if((m=h.match(/buildkite\.com\/lmcache\/([\w\-]+)\/builds\/(\d+)/))) k=N['build:'+m[1]+'/'+m[2]]?'build:'+m[1]+'/'+m[2]:'ci:'+m[1];
      else if((m=h.match(/buildkite\.com\/lmcache\/([\w\-]+)\/?$/))) k='ci:'+m[1];
      if(k&&N[k]){a.dataset.ent=k; if(!a.title) a.title=T('Click: card · Ctrl+click: open the source','Click: thẻ · Ctrl+click: mở nguồn');} });
    q('[data-pr]').forEach(e=>{ if(e.tagName==='A'||e.dataset.ent||e.closest('.ent-drawer')||e.querySelector('a[data-ent]')) return; const k='pr:'+e.dataset.pr; if(N[k]&&!e.closest('svg')) infoBtn(e.tagName==='TR'?e.cells[0]:e,k); });
    q('[data-area]').forEach(e=>{ if(e.closest('.ent-drawer,svg')) return; const k='feature:'+e.dataset.area; infoBtn(e.tagName==='TR'?e.cells[0]:e,k); });
    q('[onclick*="opsOpenFeature("]').forEach(e=>{ const m=(e.getAttribute('onclick')||'').match(/opsOpenFeature\('([\w\-]+)'\)/); if(m&&!e.closest('svg')&&e.parentElement&&!e.parentElement.querySelector(':scope > .ent-i[data-ent="feature:'+m[1]+'"]')){ if(N['feature:'+m[1]]){const b=document.createElement('button');b.type='button';b.className='ent-i';b.dataset.ent='feature:'+m[1];b.textContent='i';b.setAttribute('aria-label',T('Open card','Mở thẻ')+' '+m[1]);e.after(b);} } });
    q('details[data-path]').forEach(e=>{ const s=e.querySelector(':scope > summary'); if(s) infoBtn(s,'test:'+e.dataset.path); });
  }
  let busy=false;
  function linkify(root){
    if(!root||busy) return; busy=true;
    try{
      if(root.nodeType===3){linkText(root);return;}
      if(root.nodeType!==1||root.closest('.ent-drawer')) return;
      linkAttrs(root);
      const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),list=[]; let n; while((n=w.nextNode())) if(n.nodeValue.length>2) list.push(n);
      list.forEach(linkText);
    }finally{busy=false;}
  }
  ENT.linkify=linkify;
  // language switch: put the English text node back (i18n translates it), then link again
  addEventListener('langchange',()=>{
    document.querySelectorAll('.ent-t').forEach(g=>{const en=groupEn.get(g); const t=document.createTextNode(en!=null?(window.I18N?I18N.t(en):en):g.textContent); if(en!=null&&window.I18N&&I18N.adopt) I18N.adopt(t,en); busy=true; g.replaceWith(t); busy=false;});
    setTimeout(()=>linkify(document.body),0);   // after i18n has translated what the tabs re-rendered
    if(cur) render(cur);
  });

  // ---------------------------------------------------------------- the card
  const drawer=document.getElementById('entDrawer'),head=document.getElementById('entHead'),body=document.getElementById('entBody'),back=document.getElementById('entBack');
  let cur=null,stack=[],opener=null;
  // decisions come from decisions.py through the Today data (build_today.py): rule chip solid, Trace Agent chip dashed
  function decision(n){
    const k=n.kind+':'+n.id,td=window.TODAY,d=td&&td.dec&&td.dec[k],out=[],why=s=>`<span class="ent-why">${esc(s?T(s[0],s[1]):'')}</span>`;
    if(d&&d.verb) out.push(td.chip(d.verb,d.by)+' '+why(d.short));
    if(d&&d.block) out.push(td.chip('block','agent')+' '+why(d.block.short));
    const ta=(d&&d.ta)||n.ta;
    if(ta&&!(d&&d.block)) out.push(`<span class="ent-verb ta" title="Trace Agent">✦ ${esc(ta.cls||'')}</span> <span class="ent-why">${esc(ta.tag||'')}${ta.fix_pr?' · '+T('fix','sửa ở')+' '+ENT.a('pr:'+ta.fix_pr):''}</span>`);
    return out.length?out.join('<br>'):`<span class="ent-none">${T('no decision rule for this object','không có luật quyết định cho đối tượng này')}</span>`;
  }
  function neighbours(k){
    const up={},down={},me=LEVEL[N[k].kind];
    const add=(other,rel,side,s)=>{const o=N[other]; if(!o) return; const lv=LEVEL[o.kind]; const box=lv<me?up:down; const lab=REL[rel]?REL[rel][side]:[rel,rel];
      const id=o.kind+'|'+lab[0]; (box[id]=box[id]||{kind:o.kind,lab,items:[]}).items.push({k:other,s});};
    (OUT[k]||[]).forEach(e=>add(e.b,e.rel,0,e.s)); (INN[k]||[]).forEach(e=>add(e.a,e.rel,1,e.s));
    const order={red:0,running:1,waiting:2,unknown:3,green:4};
    const fin=box=>Object.values(box).map(g=>{g.items.sort((x,y)=>(order[N[x.k].status]-order[N[y.k].status])||String(N[y.k].at||'').localeCompare(String(N[x.k].at||'')));return g;});
    return {up:fin(up).sort((a,b)=>LEVEL[b.kind]-LEVEL[a.kind]),down:fin(down).sort((a,b)=>LEVEL[a.kind]-LEVEL[b.kind])};
  }
  const nbRow=it=>{const o=N[it.k];return `<div class="ent-nb" data-open="${esc(it.k)}" role="link" tabindex="0"><span class="nm obsraw"><code>${esc(label(o))}</code>${esc(o.kind==='test'||o.kind==='build'||o.kind==='release'?'':nameOf(o))}</span>${it.s!=='strong'?`<span class="sg">${T(...SG[it.s])}</span>`:''}${st(o.status)}</div>`;};
  function groups(list,empty){
    if(!list.length) return `<div class="ent-none">${empty}</div>`;
    return list.map((g,i)=>{const n=g.items.length,first=g.items.slice(0,6),rest=g.items.slice(6,60);
      const red=g.items.filter(x=>N[x.k].status==='red').length;
      return `<div class="ent-grp"><b>${T(...KINDS[g.kind])} · ${T(...g.lab)} <small>${n}${red?' · '+red+' '+T('red','đỏ'):''}</small></b>${first.map(nbRow).join('')}`+
        (rest.length?`<div hidden>${rest.map(nbRow).join('')}</div><button type="button" class="ent-more">${T('show','hiện')} ${Math.min(n,60)-6} ${T('more','nữa')}${n>60?' ('+T('of','trên')+' '+n+')':''}</button>`:'')+`</div>`;}).join('');
  }
  const CHK=[['dco','DCO'],['quality','Check code quality'],['unit','buildkite/k3-unit-tests'],['mp','buildkite/k3-multiprocess-test']];
  const CST={ok:'green',fail:'red',run:'running',cancel:'unknown',skip:'unknown'};
  const ext=(u,t)=>u?`<a class="ent-ext" href="${esc(u)}" target="_blank" rel="noopener">${esc(t)} ↗</a>`:'';
  const kv=rows=>{const r=rows.filter(x=>x[1]!=null&&x[1]!=='');return r.length?`<dl class="ent-kv">${r.map(([a,b])=>`<dt>${a}</dt><dd class="obsraw">${b}</dd>`).join('')}</dl>`:'';};
  function evidence(k,n){
    let h='';
    if(n.kind==='pr'){
      if(n.checks||n.state==='open'||n.state==='draft') h+=kv(CHK.map(([id,nm])=>[esc(nm),st(n.checks&&n.checks[id]?CST[n.checks[id]]||'unknown':'waiting')+(n.checks&&n.checks[id]?'':' <span class="ent-none">'+T('not started','chưa chạy')+'</span>')]));
      h+=kv([[T('State','Trạng thái'),esc(n.state)],[T('Review','Review'),esc(n.review)],[T('Author','Tác giả'),esc(n.author)],[T('Head','Head'),n.sha?'<code>'+esc(n.sha)+'</code>':null],[T('Labels','Label'),n.labels?esc(n.labels.join(', ')):null],[T('Files','File'),n.nfiles]]);
      const bs=(OUT[k]||[]).filter(e=>e.rel==='ran').map(e=>N[e.b]).sort((a,b)=>String(b.at).localeCompare(String(a.at))).slice(0,5);
      bs.forEach(b=>{h+=`<div class="ent-row">${st(b.status)} ${ext(b.url,b.title)} <span class="ent-none">${esc(b.at||'')}</span></div>`;});
      (n.tests_changed||[]).slice(0,6).forEach(t=>{h+=`<div class="obsraw">${ENT.a('test:'+t,t)}</div>`;});
      const dd=window.TODAY&&TODAY.dec&&TODAY.dec[k];   // clashes with the merges of the last 24 h: each shared file opens at its diff
      ((dd&&dd.clash)||[]).forEach(c=>{h+=`<div class="ent-row"><span class="ent-verb">${esc(c.level.toUpperCase())}</span> ${ENT.a('pr:'+c.m,'#'+c.m)} <span class="ent-none">${esc(T(c.same[0],c.same[1]))}</span></div>`+
        (c.files||[]).map(([f,hh])=>`<div class="ent-row"><code>${esc(f.split('/').pop())}</code> ${ext(n.url+'/files#diff-'+hh,T('this PR','PR này'))}${ext('https://github.com/LMCache/LMCache/pull/'+c.m+'/files#diff-'+hh,'#'+c.m)}</div>`).join('');});
      h+='<div style="margin-top:8px">'+ext(n.url,'GitHub PR')+ext(n.url?n.url+'/files':null,T('Diff','Diff'))+ext(n.url?n.url+'/checks':null,T('Checks','Checks'))+'</div>';
    }else if(n.kind==='build'){
      h+=kv([[T('State','Trạng thái'),esc(n.state)],[T('Branch','Nhánh'),esc(n.branch)],[T('Commit','Commit'),n.sha?'<code>'+esc(n.sha)+'</code>':null]]);
      (OUT[k]||[]).filter(e=>e.rel==='failed_with').forEach(e=>{const b=N[e.b];h+=`<div>${ENT.a(e.b,nameOf(b))}</div><code class="ent-log">${esc(b.line||'')}</code>`;});
      h+=ext(n.url,'Buildkite build');
    }else if(n.kind==='test'){
      h+=n.hw==='gpu'?kv([[T('GPUs','Số GPU'),esc(n.gpus)],[T('Runs, 30 days','Lượt chạy, 30 ngày'),n.runs_30d],[T('First-try fail','Fail lần đầu'),n.fail_pct!=null?n.fail_pct+' %':null],[T('Pass after retry','Pass sau khi chạy lại'),n.pass_after_retry_pct!=null?n.pass_after_retry_pct+' %':null],[T('GPU-min, median (p50)','GPU-min, trung vị (p50)'),n.gpu_min_p50],[T('Last finished job','Job xong gần nhất'),esc(n.at)]])
        :kv([[T('Passed','Pass'),n.passed],[T('Failed','Fail'),n.failed],[T('Skipped','Bỏ qua'),n.skipped],[T('Seconds','Giây'),n.secs],[T('Not run because','Không chạy vì'),esc(n.why_not_run)],[T('File','File'),'<code>'+esc(n.id)+'</code>']]);
      h+=ext(n.url,T('Test file on GitHub','File test trên GitHub'));
      if(n.hw==='cpu'&&window.cpuOpenFile) h+=`<button type="button" class="ent-more" data-explore="${esc(n.id)}">${T('Open in Test Explorer','Mở trong Test Explorer')}</button>`;
    }else if(n.kind==='bug'){
      h+=kv([[T('Class','Loại'),esc(n.cls)],[T('Jobs, 30 days','Job, 30 ngày'),n.n_30d]]);
      if(n.line) h+=`<code class="ent-log">${esc(n.line)}</code>`;
      (INN[k]||[]).filter(e=>e.rel==='failed_with').map(e=>N[e.a]).sort((a,b)=>String(b.at).localeCompare(String(a.at))).slice(0,5).forEach(b=>{h+=`<div class="ent-row">${st(b.status)} ${ext(b.url,b.title)} <span class="ent-none">${esc(b.at||'')}</span></div>`;});
      h+=ext(n.url,'GitHub issue');
    }else if(n.kind==='release'){
      h+=kv([[T('Kind','Loại'),esc(n.state)],[T('Previous tag','Tag trước'),esc(n.prev)],[T('Tagged','Gắn tag'),esc(n.at)]])+ext(n.url,'GitHub release');
    }else if(n.kind==='feature'){
      h+=kv([[T('KV-flow stage','Chặng KV-flow'),esc(n.stage)],[T('Change class','Nhóm thay đổi'),esc(n.klass)]]);
      if(window.opsOpenFeature) h+=`<button type="button" class="ent-more" data-feature="${esc(n.id)}">${T('Open in CPU coverage','Mở trong CPU coverage')}</button>`;
    }else if(n.kind==='ci'){
      h+=kv([[T('System','Hệ thống'),esc(n.system)],[T('Required check','Check bắt buộc'),n.required?T('yes','có'):T('no','không')],[T('Last dev run','Lần chạy dev gần nhất'),esc(n.at)]])+ext(n.url,n.system||'CI');
    }else if(n.kind==='sprint'){
      h+=kv([[T('Section','Mục'),esc(n.section)],[T('Source','Nguồn'),'<code>'+esc(n.src)+'</code>'],[T('File saved','File lưu lúc'),esc(n.at)]]);
    }
    return h||`<span class="ent-none">${T('no evidence in local data','không có bằng chứng trong dữ liệu local')}</span>`;
  }
  function seenIn(k,n){
    const set=new Set((n.tabs||[]).map(x=>x.replace(/^#/,'')));
    document.querySelectorAll('[data-ent="'+CSS.escape(k)+'"]').forEach(e=>{const s=e.closest('section[data-view]'); if(s&&s.dataset.tab) set.add(s.dataset.view+'/'+s.dataset.tab);});
    const ok=[...set].filter(h=>TABN[h]&&document.querySelector('section[data-view="'+h.split('/')[0]+'"][data-tab="'+h.split('/')[1]+'"]'));
    return ok.length?`<div class="ent-tabs">${ok.map(h=>`<button type="button" class="ent-tab" data-tabgo="${esc(h)}">${esc(TABN[h])}</button>`).join('')}</div>`:`<span class="ent-none">${T('no tab','không có tab')}</span>`;
  }
  function render(k){
    const n=N[k]; if(!n) return false; cur=k;
    head.innerHTML=`<span class="ent-kind">${T(...KIND[n.kind])}</span><span class="ent-id obsraw">${esc(label(n))}</span><p class="ent-title obsraw" id="entTitle">${esc(nameOf(n))}</p>`;
    const nb=neighbours(k);
    body.innerHTML=`<div class="ent-row"><span class="ent-lab">${T('Status','Trạng thái')}</span>${st(n.status)}${n.state?` <span class="ent-none obsraw">${esc(n.state)}</span>`:''}${n.at?` <span class="ent-none">${esc(n.at)} UTC</span>`:''}</div>`+
      `<div class="ent-row"><span class="ent-lab">${T('Decision','Quyết định')}</span><span>${decision(n)}</span></div>`+
      `<div class="ent-sec">${T('Up','Cấp trên')}</div>${groups(nb.up,`<span class="ent-none">${T('no link above','không có liên kết cấp trên')}</span>`)}`+
      `<div class="ent-sec">${T('Down','Cấp dưới')}</div>${groups(nb.down,`<span class="ent-none">${T('no link below','không có liên kết cấp dưới')}</span>`)}`+
      `<details class="ent-ev"><summary>${T('Evidence','Bằng chứng')}</summary>${evidence(k,n)}</details>`+
      `<div class="ent-sec">${T('Seen in','Xuất hiện ở')}</div>${seenIn(k,n)}`;
    back.hidden=!stack.length; back.setAttribute('aria-label',T('Back','Quay lại')); document.getElementById('entClose').setAttribute('aria-label',T('Close','Đóng'));
    body.scrollTop=0; return true;
  }
  function open(k,push){
    if(!N[k]) return false;
    if(!drawer.classList.contains('on')){opener=document.activeElement;stack=[];}
    else if(push!==false&&cur&&cur!==k) stack.push(cur);
    render(k); drawer.classList.add('on'); drawer.setAttribute('aria-hidden','false');
    const h='#e/'+N[k].kind+'/'+encodeURIComponent(N[k].id).replace(/%2F/g,'/'); if(location.hash!==h) history.replaceState(null,'',h);
    document.getElementById('entClose').focus({preventScroll:true}); return true;
  }
  function close(){
    if(!drawer.classList.contains('on')) return;
    drawer.classList.remove('on'); drawer.setAttribute('aria-hidden','true'); cur=null; stack=[];
    const s=window.vizNav&&vizNav.state; if(s) history.replaceState(null,'','#'+s.v+'/'+s.t);
    if(opener&&opener.isConnected&&opener.focus) opener.focus({preventScroll:true}); opener=null;
  }
  window.openEntity=open; window.closeEntity=close; ENT.open=open; ENT.close=close;
  back.addEventListener('click',()=>{const k=stack.pop(); if(k) open(k,false);});
  document.getElementById('entClose').addEventListener('click',close);
  function goTab(h,k){const [v,t]=h.split('/'); close(); if(window.vizNav) vizNav.show(v,t);
    setTimeout(()=>{const sec=[...document.querySelectorAll('section[data-view="'+v+'"][data-tab="'+t+'"]')]; for(const s of sec){const e=s.querySelector('[data-ent="'+CSS.escape(k)+'"]'); if(e){const d=e.closest('details'); if(d) d.open=true; e.scrollIntoView({block:'center'}); const row=e.closest('tr')||e; row.classList.remove('ent-flash'); void row.offsetWidth; row.classList.add('ent-flash'); break;}}},80);}
  body.addEventListener('click',e=>{
    const m=e.target.closest('.ent-more'); if(m&&m.dataset.explore){close(); vizNav.show('cpu','explore'); cpuOpenFile(m.dataset.explore); return;}
    if(m&&m.dataset.feature){close(); opsOpenFeature(m.dataset.feature); return;}
    if(m){const box=m.previousElementSibling; if(box) box.hidden=false; m.remove(); return;}
    const tb=e.target.closest('[data-tabgo]'); if(tb){goTab(tb.dataset.tabgo,cur); return;}
    const nb=e.target.closest('[data-open]'); if(nb) open(nb.dataset.open);
  });
  // one click handler for every entity link on the page
  document.addEventListener('click',e=>{
    const el=e.target.closest&&e.target.closest('[data-ent]'); if(!el||el.closest('[data-open]')) return;
    if(el.tagName==='A'&&(e.ctrlKey||e.metaKey||e.shiftKey||e.button)) return;   // keep "open in new tab"
    if(!N[el.dataset.ent]) return;
    e.preventDefault(); e.stopPropagation(); open(el.dataset.ent);
  },true);
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'&&drawer.classList.contains('on')){e.preventDefault();close();return;}
    if(e.key!=='Enter'&&e.key!==' ') return;
    const el=e.target.closest&&e.target.closest('.ent-l,[data-open]'); if(!el) return;
    e.preventDefault(); open(el.dataset.ent||el.dataset.open);
  });
  // a shared link to an object that is not in this build of the index: say so instead of landing silently on a tab
  function notFound(kind,id){opener=document.activeElement;stack=[];cur=null;
    head.innerHTML=`<span class="ent-kind">${esc(KIND[kind]?T(...KIND[kind]):kind)}</span><span class="ent-id obsraw">${esc(id)}</span><p class="ent-title" id="entTitle">${T('Not in the local index','Không có trong chỉ mục local')}</p>`;
    body.innerHTML=`<p class="ent-none">${T(`The entity index was built ${D.made} UTC from local files; this object is not in it. Its source file may be older than the object (oldest input: ${D.health.oldest_input.path}, ${D.health.oldest_input.made} UTC).`,`Chỉ mục được dựng lúc ${D.made} UTC từ file local; đối tượng này không có trong đó. File nguồn có thể cũ hơn đối tượng (input cũ nhất: ${D.health.oldest_input.path}, ${D.health.oldest_input.made} UTC).`)}</p>`;
    back.hidden=true;drawer.classList.add('on');drawer.setAttribute('aria-hidden','false');document.getElementById('entClose').focus({preventScroll:true});return true;}
  function route(h){const m=(h||'').match(/^#e\/(\w+)\/(.+)$/); if(!m) return false; let id=m[2]; try{id=decodeURIComponent(id);}catch(e){} return open(key(m[1],id),false)||notFound(m[1],id);}
  addEventListener('hashchange',()=>{ if(/^#e\//.test(location.hash)) route(location.hash); });

  // ---------------------------------------------------------------- link health block (Report 1130 → Data quality)
  const MISS={pr_without_feature:['PRs with no feature','PR không có tính năng'],pr_without_files:['PRs with no local file list','PR không có danh sách file local'],pr_without_build:['PRs with no indexed build','PR không có build trong index'],
    pr_open_without_build:['Open PRs with no build','PR đang mở không có build'],pr_merged_without_release:['Merged PRs outside every release range','PR đã merge ngoài mọi khoảng release'],
    builds_30d_not_indexed:['30-day builds left out of the index','Build 30 ngày không đưa vào index'],gpu_job_without_workload:['24 h Buildkite jobs with no workload','Job Buildkite 24 h không có workload'],
    bk_job_30d_without_workload:['30-day Buildkite jobs with no workload','Job Buildkite 30 ngày không có workload'],build_without_pr:['PR builds with no PR node','Build PR không có node PR'],build_with_unknown_pr:['Builds of a PR not in the index','Build của PR không có trong index'],
    bug_sig_without_test:['Signatures with no test','Signature không có test'],bug_sig_without_fix_pr:['Signatures with no fixing PR','Signature không có PR sửa'],bug_issue_without_test:['Issues with no test','Issue không có test'],
    feature_without_test:['Features with no test','Tính năng không có test'],cpu_test_without_feature:['CPU test files with no feature','File test CPU không có tính năng'],gpu_test_without_feature:['GPU workloads with no feature','Workload GPU không có tính năng'],
    gpu_test_without_ci:['GPU workloads with no pipeline','Workload GPU không có pipeline'],sprint_item_without_pr:['Sprint items with no PR','Hạng mục sprint không có PR']};
  function health(){
    const sec=document.querySelector('section[data-view="r1130"][data-tab="quality"]'); if(!sec) return;
    let box=document.getElementById('entHealth'); if(!box){box=document.createElement('div');box.id='entHealth';box.className='ent-health';sec.append(box);}
    const H=D.health,num=x=>Number(x).toLocaleString('en-US');
    const tbl=(h1,rows)=>`<table><thead><tr><th>${h1}</th><th class="r">${T('Count','Số lượng')}</th></tr></thead><tbody>${rows.map(([a,b])=>`<tr><td>${a}</td><td class="r">${num(b)}</td></tr>`).join('')}</tbody></table>`;
    const tot=o=>Object.values(o).reduce((a,b)=>a+b,0);
    box.innerHTML=`<h3>${T('Links','Liên kết')}</h3><p>${T('Entity index of the page','Chỉ mục thực thể của trang')}: ${num(tot(H.nodes))} ${T('nodes','node')}, ${num(tot(H.edges))} ${T('links','liên kết')}. ${T('Built','Dựng lúc')} ${esc(D.made)} UTC. ${T('Oldest input','Input cũ nhất')}: <code>${esc(H.oldest_input.path)}</code> (${esc(H.oldest_input.made)} UTC).</p>`+
      `<div class="cols"><div>${tbl(T('Nodes per kind','Node theo loại'),Object.entries(H.nodes).sort((a,b)=>LEVEL[a[0]]-LEVEL[b[0]]).map(([k,v])=>[T(...KINDS[k]),v]))}</div>`+
      `<div>${tbl(T('Links per relation','Liên kết theo quan hệ'),Object.entries(H.edges).map(([k,v])=>[`${T(...KIND[D.rels[k].frm])} → ${T(...KIND[D.rels[k].to])} <span class="ent-none">${esc(k)}</span>`,v]))}</div>`+
      `<div>${tbl(T('Missing links','Liên kết còn thiếu'),Object.entries(H.missing).sort((a,b)=>b[1]-a[1]).map(([k,v])=>[MISS[k]?T(...MISS[k]):esc(k),v]))}</div></div>`;
  }

  // ---------------------------------------------------------------- start
  function start(){
    const root=document.querySelector('.viz-root'); if(root) root.appendChild(drawer);   // colour tokens and the font live on .viz-root
    health(); linkify(document.body);
    new MutationObserver(ms=>{ if(busy) return; const seen=new Set();
      ms.forEach(m=>m.addedNodes.forEach(n=>{ if(n.nodeType===1){ if(n.classList.contains('ent-t')||n.classList.contains('ent-i')||n.closest('.ent-drawer')) return; seen.add(n);} else if(n.nodeType===3&&n.parentElement&&!n.parentElement.classList.contains('ent-t')) seen.add(n); }));
      seen.forEach(n=>{ if(n.isConnected) linkify(n); });
    }).observe(document.body,{childList:true,subtree:true});
    addEventListener('langchange',health);
    if(/^#e\//.test(location.hash)) route(location.hash);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',start); else start();
})();
</script>
<!-- ENTUI:JS:END -->
"""


def put(page, start, end, block, anchor):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:]


def main():
    page = open(PAGE, encoding="utf-8").read()
    if 'id="entData"' not in page:
        print("entity_ui: no entData in the page; run build_entities.py first")
        return 1
    page = put(page, "/* ENTUI:CSS:START */", "/* ENTUI:CSS:END */", CSS, "/* NAV:CSS:START */")   # top level: not inside OBS CSS
    page = put(page, "<!-- ENTUI:JS:START -->", "<!-- ENTUI:JS:END -->", JS, "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    print(f"entity_ui: drawer + linkify + link health, {len(JS) // 1024} KB JS, {len(CSS) // 1024} KB CSS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
