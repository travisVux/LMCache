"""Phase B of the PR Inspector: flow animation of the impact direction + interactive sequence diagrams.

- Flow (Inspector, Forward): modules -> code areas -> features -> CI gates, drawn as SVG links between the chips.
  Each link is routed from the measured chip / column rects: chip right edge -> column right edge, a cubic curve across
  the gap, column left edge -> target chip left edge (arrowhead there); a link that skips a column runs below it.
  One ResizeObserver per render (flow + columns + sequence grids) redraws the links and the lane geometry.
  Animation is OFF by default; "Play the impact flow" walks 4 flow steps (one column after the other, unreached
  columns dimmed) and then the open sequence diagrams one message per tick (1.1 s), then loops. Pause freezes it.
  Clicking a chip pauses the timer and highlights every chip and link on its path. prefers-reduced-motion: no moving
  dashes, no auto-advance (each Play press advances one step).
- Sequence diagram, generated for multi-step changes:
    new.CI   : a PR that edits a CI pipeline with many conditional steps (piData.seq, ci_seq.py): trigger -> groups /
               jobs, one message per step, [if: ...] shown, steps this PR edited highlighted. At most 6 named lanes,
               the rest share a last lane "other jobs (+N)" (real job name kept in the label)
    pipeline : a PR whose features sit on 2+ steps of a critical-path journey (multi-stage cache pipeline, sheet
               "00 Critical Path"): a "found" message into the first touched step, then one message per step
  Lane x positions are measured from the header cells (--x0..--xN on .pi-sg); arrows, labels and the lifeline layer
  use them, so the arrows end exactly on their lifelines at any width.
  Click a step -> payload / condition / code location (file:line at the clone HEAD, or the PR files of that feature).
- Phone (< 600 px): the diagram is replaced by a numbered list of cards with the same details (CSS only).
Loaded after pr_inspector_ui.py; it listens to the 'pirender' event and uses window.PI (model, data).
"""

CSS = r"""
/* PISEQ:CSS:START */
.pi-anim{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:2px 0 6px}
.pi-flow{position:relative}
.pi-flow>.pi-col{position:relative;z-index:1}
.pi-flow>.pi-col.dim>h5{opacity:.6}
.pi-links{position:absolute;left:0;top:0;pointer-events:none;z-index:0;overflow:visible}
.pi-links path{fill:none;stroke:var(--border-strong,var(--text-muted));stroke-width:1.4;opacity:.75;marker-end:url(#piAr)}
.pi-links polygon{fill:var(--border-strong,var(--text-muted))}
.pi-links #piArH polygon{fill:var(--series-2)}
.pi-links path.hot,.pi-links path.done{stroke:var(--series-2);stroke-width:2;opacity:1;marker-end:url(#piArH)}
.pi-links path.hot{stroke-width:2.2}
.pi-links.dimrest path:not(.hot):not(.done){opacity:.2}
.pi-links.run path.hot{stroke-dasharray:6 6;animation:piDash 1s linear infinite}
.pi-links.paused path{animation-play-state:paused}
@keyframes piDash{to{stroke-dashoffset:-24}}
.pi-chip[data-pn]{cursor:pointer}
.pi-chip.hot{border-color:var(--series-2);box-shadow:0 0 0 2px color-mix(in srgb,var(--series-2) 35%,transparent)}
.pi-chip.dim{opacity:.45}
.pi-seqbox{margin:8px 0 12px;border:1px solid var(--border);border-radius:10px;padding:8px 10px}
.pi-seqbox>summary{cursor:pointer;font-size:12.5px;font-weight:650;color:var(--text-secondary)}
.pi-seq h5{margin:10px 0 4px;font-size:12px;color:var(--text-primary)}
.pi-seqsvg{overflow:auto;max-width:100%;max-height:70vh}
/* sequence diagram as HTML (2026-11-27): header cells set the lane x (--x0..), one row per message, absolute arrows */
.pi-sg{position:relative;min-width:calc(var(--n) * 86px);padding-bottom:2px}
.pi-sh{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));position:sticky;top:0;z-index:2;background:var(--surface-1)}
.pi-sh span{margin:0 3px;padding:4px;border:1px solid var(--border);border-radius:6px;background:var(--surface-2);font-size:11px;font-weight:600;text-align:center;line-height:1.25;overflow-wrap:anywhere}
.pi-sg .pi-lfl{position:absolute;left:0;right:0;top:0;bottom:2px;z-index:0;pointer-events:none}
.pi-sg .pi-lfl i{position:absolute;top:0;bottom:0;width:0;margin-left:-.5px;border-left:1px dashed var(--border)}
.pi-sg .pi-msg{position:relative;display:block;padding:5px 0 4px;cursor:pointer;border-radius:6px;outline:none}
.pi-sg .pi-msg:hover,.pi-sg .pi-msg.sel,.pi-sg .pi-msg:focus-visible{background:color-mix(in srgb,var(--series-1) 9%,transparent)}
.pi-sg .pi-msg.hot{background:color-mix(in srgb,var(--series-1) 16%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--series-1) 45%,transparent)}
.pi-sg .lf{position:absolute;top:0;bottom:0;width:0;pointer-events:none}
.pi-sg .lab,.pi-sg .cd{display:block;padding:0 6px 2px max(0px,min(var(--xa),100% - 220px));overflow-wrap:anywhere}
.pi-sg .lab{font-size:11.5px;line-height:1.35;color:var(--text-secondary)}
.pi-sg .lw{background:var(--surface-1);border-radius:3px;box-decoration-break:clone;-webkit-box-decoration-break:clone;padding:0 2px}
.pi-sg .lab b{color:var(--text-primary)}
.pi-sg .arw{display:block;position:relative;height:12px}
.pi-sg .ar{position:absolute;top:0;height:12px;left:var(--xa);width:calc(var(--xb) - var(--xa))}
.pi-sg .ar::before{content:"";position:absolute;left:0;right:0;top:5.5px;border-top:1px solid var(--text-secondary)}
.pi-sg .ar::after{content:"";position:absolute;right:0;top:1px;border-style:solid;border-width:5px 0 5px 8px;border-color:transparent transparent transparent var(--text-secondary)}
.pi-sg .ar.back::after{right:auto;left:0;border-width:5px 8px 5px 0;border-color:transparent var(--text-secondary) transparent transparent}
.pi-sg .ar.self{width:26px}
.pi-sg .ar.self::before{box-sizing:border-box;top:0;height:12px;border:1px solid var(--text-secondary);border-left:0;border-radius:0 6px 6px 0}
.pi-sg .ar.self::after{right:auto;left:0;top:7.5px;border-width:4px 7px 4px 0;border-color:transparent var(--text-secondary) transparent transparent}
.pi-sg .ar.found{left:0;width:var(--x0);background:radial-gradient(circle at 4px 6px,var(--text-secondary) 3.5px,transparent 4px)}
.pi-sg .pi-msg.chg .lab{color:var(--text-primary);font-weight:650}
.pi-sg .pi-msg.chg .ar::before{top:5px;border-top:2px solid var(--series-1)}
.pi-sg .pi-msg.chg .ar.self::before{top:0;border:2px solid var(--series-1);border-left:0}
.pi-sg .pi-msg.chg .ar.self::after{top:7px}
.pi-sg .pi-msg.chg .ar::after{border-left-color:var(--series-1)}
.pi-sg .pi-msg.chg .ar.back::after,.pi-sg .pi-msg.chg .ar.self::after{border-left-color:transparent;border-right-color:var(--series-1)}
.pi-sg .pi-msg.chg .ar.found{background:radial-gradient(circle at 4px 6px,var(--series-1) 3.5px,transparent 4px)}
.pi-sg .cd{font-size:10.5px;color:var(--text-muted)}
.pi-sg .tag{font-size:10px;font-weight:700;color:var(--series-1);background:var(--surface-1);border:1px solid currentColor;border-radius:999px;padding:0 5px;margin-left:4px}
.pi-seqmore{all:unset;cursor:pointer;font-size:12px;color:var(--series-1);text-decoration:underline;margin:4px 0}
.pi-seqlist{display:none;list-style:none;margin:6px 0 0;padding:0;flex-direction:column;gap:6px}
.pi-seqlist li{border:1px solid var(--border);border-radius:8px;padding:6px 8px;font-size:12.5px;overflow-wrap:anywhere}
.pi-seqlist li.chg{border-color:var(--series-1)}
.pi-seqlist li.hot{border-color:var(--series-1);box-shadow:0 0 0 2px color-mix(in srgb,var(--series-1) 35%,transparent)}
.pi-seqlist button{all:unset;cursor:pointer;color:var(--series-1);font-size:12px}
.pi-seqdet{margin-top:8px;border-left:3px solid var(--series-1);padding:6px 10px;font-size:12.5px;background:var(--surface-2);border-radius:0 8px 8px 0;overflow-wrap:anywhere}
.pi-seqdet dt{font-weight:650;color:var(--text-secondary);margin-top:4px}
.pi-seqdet dd{margin:0 0 2px}
.pi-seqdet code{font-size:11px;white-space:pre-wrap}
@media (max-width:600px){.pi-links{display:none}.pi-seqsvg{display:none}.pi-seqlist{display:flex}}
@media (prefers-reduced-motion:reduce){.pi-links.run path.hot{animation:none;stroke-dasharray:none}}
/* PISEQ:CSS:END */
"""

JS = r"""
<!-- PISEQ:JS:START -->
<script>
/* PR Inspector phase B (pr_inspector_seq.py): flow links + animation (off by default, pause) + sequence diagrams. */
(function(){
  if(!window.PI) return;
  const D=PI.data, GH='https://github.com/LMCache/LMCache', NS='http://www.w3.org/2000/svg';
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en;
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const code=s=>`<code class="obsraw">${esc(s)}</code>`, ext=(h,t)=>`<a href="${esc(h)}" target="_blank" rel="noopener">${t}</a>`;
  const unk=w=>`<span class="pi-unk">${T('unknown','chưa biết')}</span> <span class="pi-why">${w}</span>`;
  const STEPS=[['modules → code areas','module → code area'],['code areas → features / gates','code area → feature / gate'],['features → CI gates','feature → CI gate'],['CI gates','CI gate']];
  const RM=matchMedia('(prefers-reduced-motion: reduce)');
  // animation is OFF until the reviewer starts it; phase 'flow' (step 0..3) or 'seq' (step = message index over the open diagrams)
  let anim=false,paused=false,timer=null,tick=0,phase='flow',step=0,ctx=null,ro=null,raf=0,seqOpen=false;
  const DR=()=>document.getElementById('piDrawer');

  // ---------------------------------------------------------------- flow graph of one PR
  function graph(M){const E=[];const add=(a,b)=>{if(!E.some(e=>e[0]===a&&e[1]===b))E.push([a,b]);};
    M.codeF.forEach(f=>{const m=f[0].split('/').slice(0,-1).slice(-2).join('/');if(f[6]&&M.areas.includes(f[6])&&D.areas[f[6]])add('m:'+m,'a:'+f[6]);});
    M.areas.forEach(a=>{(D.areas[a].F||[]).forEach(F=>add('a:'+a,'f:'+F));
      const C=D.classes[D.areas[a].cls]||{tiers:{}};
      const gs=[...new Set(Object.keys(C.tiers).map(t=>(D.tiers[t]||{}).job||t))];
      const Fs=D.areas[a].F||[];
      gs.forEach(g=>{if(Fs.length)Fs.forEach(F=>add('f:'+F,'g:'+g));else add('a:'+a,'g:'+g);});});
    return E;}
  const order=k=>'mafg'.indexOf(k[0]);
  const f1=v=>Math.round(v*100)/100;
  // links routed from the measured rects: chip right -> column right, cubic across the gap, column left -> chip left (arrowhead)
  function drawLinks(flow,E){
    const old=flow.querySelector('svg.pi-links');if(old)old.remove();
    const box=flow.getBoundingClientRect();if(!box.width)return null;
    const svg=document.createElementNS(NS,'svg');svg.setAttribute('class','pi-links');svg.setAttribute('aria-hidden','true');
    const W=Math.max(flow.scrollWidth,box.width),H=Math.max(flow.scrollHeight,box.height);
    const cols=[...flow.querySelectorAll(':scope>.pi-col')].map(c=>{const r=c.getBoundingClientRect();return {el:c,l:r.left-box.left,r:r.right-box.left,b:r.bottom-box.top};});
    let low=H;
    const pos=k=>{const el=flow.querySelector(`[data-pn="${CSS.escape(k)}"]`);if(!el)return null;const r=el.getBoundingClientRect();if(!r.width)return null;
      const ci=cols.findIndex(c=>c.el===el.closest('.pi-col'));return {l:r.left-box.left,r:r.right-box.left,y:r.top-box.top+r.height/2,ci};};
    let html='<defs><marker id="piAr" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="7" markerHeight="7" markerUnits="userSpaceOnUse" orient="auto"><polygon points="0,0 8,4 0,8"/></marker>'+
      '<marker id="piArH" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto"><polygon points="0,0 8,4 0,8"/></marker></defs>';
    E.forEach(([a,b])=>{const p=pos(a),q=pos(b);if(!p||!q||p.ci<0||q.ci<=p.ci)return;
      const A=cols[p.ci],B=cols[q.ci];let d;
      if(q.ci===p.ci+1){const mx=(A.r+B.l)/2;d=`M${f1(p.r)},${f1(p.y)} L${f1(A.r)},${f1(p.y)} C${f1(mx)},${f1(p.y)} ${f1(mx)},${f1(q.y)} ${f1(B.l)},${f1(q.y)} L${f1(q.l)},${f1(q.y)}`;}
      else{   // skips a column: drop below the skipped column(s), run under them, rise into the target column
        const mid=cols.slice(p.ci+1,q.ci),yf=Math.max(...mid.map(c=>c.b))+6,M1=mid[0],M2=mid[mid.length-1],m1=(A.r+M1.l)/2,m2=(M2.r+B.l)/2;low=Math.max(low,yf+4);
        d=`M${f1(p.r)},${f1(p.y)} L${f1(A.r)},${f1(p.y)} C${f1(m1)},${f1(p.y)} ${f1(m1)},${f1(yf)} ${f1(M1.l)},${f1(yf)} L${f1(M2.r)},${f1(yf)} C${f1(m2)},${f1(yf)} ${f1(m2)},${f1(q.y)} ${f1(B.l)},${f1(q.y)} L${f1(q.l)},${f1(q.y)}`;}
      html+=`<path d="${d}" data-a="${esc(a)}" data-b="${esc(b)}"></path>`;});
    svg.innerHTML=html;
    svg.setAttribute('width',W);svg.setAttribute('height',low);svg.style.width=W+'px';svg.style.height=low+'px';
    flow.prepend(svg);return svg;}
  function reach(E,k){const f=new Set([k]),b=new Set([k]),q1=[k],q2=[k];   // everything downstream and upstream of k
    while(q1.length){const x=q1.pop();E.forEach(([a,c])=>{if(a===x&&!f.has(c)){f.add(c);q1.push(c);}});}
    while(q2.length){const x=q2.pop();E.forEach(([a,c])=>{if(c===x&&!b.has(a)){b.add(a);q2.push(a);}});}
    return new Set([...f,...b]);}
  // visible sequence diagrams (seqbox open; the diagram on desktop, the card list on phone), in document order
  function seqTargets(){const dr=DR();if(!dr)return [];const out=[];
    dr.querySelectorAll('.pi-seqbox[open] .pi-seq').forEach(sq=>{const g=sq.querySelector('.pi-seqsvg'),l=sq.querySelector('.pi-seqlist');let els=[];
      if(g&&getComputedStyle(g).display!=='none')els=[...g.querySelectorAll('.pi-msg')];else if(l&&getComputedStyle(l).display!=='none')els=[...l.children];
      if(els.length)out.push(els);});
    const flat=[];out.forEach((els,d)=>els.forEach((el,j)=>flat.push({el,d,j,nd:out.length,nm:els.length})));return flat;}
  function paint(){if(!ctx)return;const {flow,svg,E}=ctx;
    const chips=[...flow.querySelectorAll('[data-pn]')];let hot=null,hotE=null,doneE=[],label='',seqEl=null,c=-1;
    if(ctx.sel){hot=reach(E,ctx.sel);hotE=E.filter(([a,b])=>hot.has(a)&&hot.has(b));label=T('Path of ','Đường đi của ')+ctx.sel.slice(2);}
    else if(anim){
      if(phase==='seq'){const L=seqTargets();if(!L.length){phase='flow';step=0;}
        else{const t=L[Math.min(step,L.length-1)];seqEl=t.el;label=T(`Sequence ${t.d+1}/${t.nd} · step ${t.j+1}/${t.nm}`,`Tuần tự ${t.d+1}/${t.nd} · bước ${t.j+1}/${t.nm}`);}}
      if(phase==='flow'){c=step;hot=new Set(chips.filter(x=>order(x.dataset.pn)===c).map(x=>x.dataset.pn));
        hotE=c<3?E.filter(([a])=>order(a)===c):E.filter(([a,b])=>order(b)===3);
        if(!hotE.length)hotE=E.filter(([a,b])=>order(b)===c);
        doneE=E.filter(e=>!hotE.includes(e)&&(c===3||order(e[0])<c));
        label=T(`Step ${c+1}/4: `,`Bước ${c+1}/4: `)+T(...STEPS[c]);}}
    chips.forEach(x=>{const o=order(x.dataset.pn);x.classList.toggle('hot',!!hot&&hot.has(x.dataset.pn));
      x.classList.toggle('dim',ctx.sel?!hot.has(x.dataset.pn):c>=0&&o>c);});
    flow.querySelectorAll(':scope>.pi-col').forEach((col,i)=>col.classList.toggle('dim',!ctx.sel&&c>=0&&i>c));
    if(svg){svg.classList.toggle('run',anim&&!ctx.sel&&c>=0);svg.classList.toggle('paused',paused);svg.classList.toggle('dimrest',!!hotE&&hotE.length>0);
      svg.querySelectorAll('path').forEach(p=>{const is=L=>!!L&&L.some(e=>e[0]===p.dataset.a&&e[1]===p.dataset.b);p.classList.toggle('hot',is(hotE));p.classList.toggle('done',!is(hotE)&&is(doneE));});}
    const st=document.querySelector('#piDrawer [data-pa-step]');if(st)st.textContent=label;
    document.querySelectorAll('#piDrawer .pi-seq .pi-msg,#piDrawer .pi-seqlist>li').forEach(m=>m.classList.toggle('hot',m===seqEl));}
  function advance(){tick++;
    if(phase==='flow'){if(step<3)step++;else if(seqTargets().length){phase='seq';step=0;}else step=0;}
    else{if(step+1<seqTargets().length)step++;else{phase='flow';step=0;}}
    paint();}
  function run(){clearInterval(timer);timer=null;if(anim&&!paused&&!(ctx&&ctx.sel)&&!RM.matches)timer=setInterval(advance,1100);paint();}
  function stop(){clearInterval(timer);timer=null;}
  // lane x of every header cell -> --x0..--x{n-1} (px from the left of .pi-sg)
  function measureSg(sg){const b=sg.getBoundingClientRect();if(!b.width)return;
    sg.querySelectorAll('.pi-sh>span').forEach((s,j)=>{const r=s.getBoundingClientRect();sg.style.setProperty('--x'+j,f1(r.left+r.width/2-b.left)+'px');});}
  function redrawNow(){document.querySelectorAll('#piDrawer .pi-sg').forEach(measureSg);
    if(ctx&&ctx.flow.isConnected){ctx.svg=drawLinks(ctx.flow,ctx.E);paint();}}
  function redraw(){if(raf)return;raf=requestAnimationFrame(()=>{raf=0;redrawNow();});}   // coalesce bursts into one frame
  function unobserve(){if(ro){ro.disconnect();ro=null;}}

  // ---------------------------------------------------------------- sequence models
  function ciSeqs(n){return (D.seq[n]||[]).map(e=>{
    const isGha=e.file.startsWith('.github/');
    const st=e.steps.filter(s=>s.kind!=='trigger'&&s.kind!=='group');
    const laneOf=s=>isGha?s.label:(s.g||T('top level','cấp ngoài'));
    const depOf=s=>{if(!isGha)return null;const k=(s.deps||'').replace(/[\[\]\s]/g,'').split(',').filter(Boolean)[0];return k?e.steps.find(x=>x.key===k)||null:null;};
    // a job never borrows another job's lane: at most 6 named lanes (trigger + 5, edited steps and their sources first),
    // every other job goes to one last lane "other jobs (+N)" and keeps its real name in the label
    const want=[],add=x=>{if(!want.includes(x))want.push(x);};
    st.filter(s=>s.chg).forEach(s=>add(laneOf(s)));st.filter(s=>s.chg).forEach(s=>{const d=depOf(s);if(d)add(laneOf(d));});st.forEach(s=>add(laneOf(s)));
    const named=want.length>6?want.slice(0,5):want,rest=want.filter(x=>!named.includes(x));
    const docOrder=[];st.forEach(s=>{const l=laneOf(s);if(named.includes(l)&&!docOrder.includes(l))docOrder.push(l);});
    const parts=[isGha?T('trigger (on:)','trigger (on:)'):T('build trigger','trigger build'),...docOrder];
    const OTHER=rest.length?parts.push(T(`other jobs (+${rest.length})`,`job khác (+${rest.length})`))-1:-1;
    const lane=l=>{const i=docOrder.indexOf(l);return i>=0?i+1:OTHER;};
    const msgs=[];
    st.forEach(s=>{const to=lane(laneOf(s)),d=depOf(s),from=d?lane(laneOf(d)):0;
      let label=s.label;
      if(!isGha&&to===OTHER)label=laneOf(s)+' › '+label;
      if(d&&from===OTHER)label=d.label+' → '+label;
      msgs.push({from,to,label,cond:s.cond,chg:s.chg,other:to===OTHER||from===OTHER,payload:[[T('command','lệnh'),s.cmd],[T('key','key'),s.key],[T('depends on','phụ thuộc'),s.deps]],
        loc:{file:e.file,line:s.line,end:s.end},kind:'ci'});});
    const trig=e.steps.find(s=>s.kind==='trigger');
    return {title:(n=>T(`new.CI · ${e.file} · ${n} steps, ${e.n_cond} conditional, ${e.n_chg} edited by this PR`,`new.CI · ${e.file} · ${n} bước, ${e.n_cond} có điều kiện, ${e.n_chg} bị PR này sửa`))(st.length),
      note:(trig&&trig.cond?T('Trigger: ','Trigger: ')+trig.cond:'')+(e.at==='merge'?' · '+T('edited steps from the merge diff; line numbers at the clone HEAD','bước bị sửa lấy từ diff lúc merge; số dòng tại HEAD của clone'):''),parts,msgs:msgs.slice(0,24)};});}
  // review P1-9: only the journey steps this PR touches are drawn (participants = touched steps, in journey order);
  // the untouched steps are counted in the note, not drawn. The first step is a "found" message (from the left gutter).
  function journeySeqs(M){const out=[];
    D.journeys.forEach(j=>{const hit=j.f.map(s=>(s||[]).filter(f=>M.F.includes(f)));const idx=hit.map((x,i)=>x.length?i:-1).filter(i=>i>=0);if(idx.length<2)return;
      const use=idx.slice(0,7),parts=use.map(i=>j.steps[i]||('#'+(i+1)));
      const msgs=use.map((si,k)=>{const Fs=j.f[si]||[];const x=Fs.map(f=>D.F[f]||{});
        const files=M.codeF.filter(f=>f[6]&&D.areas[f[6]]&&(D.areas[f[6]].F||[]).some(F=>Fs.includes(F)));
        return {from:k?k-1:-1,to:k,label:T(`step ${si+1}`,`bước ${si+1}`)+' · '+(Fs.join(' ')||'—')+' · '+(x[0]&&x[0].name||''),cond:[...new Set(x.map(y=>y.crit).filter(Boolean))].join(' · '),chg:true,kind:'cache',
          payload:[[T('CPU check','Check CPU'),x.map(y=>y.cpu).filter(Boolean).join(' | ')],[T('GPU check','Check GPU'),x.map(y=>y.gpu).filter(Boolean).join(' | ')],[T('hands on','chuyển tiếp'),x.map(y=>y.dep).filter(Boolean).join(' | ')],[T('risk','rủi ro'),x.map(y=>y.risk).filter(Boolean).join(' | ')]],
          files};});
      const skip=j.steps.length-use.length;
      out.push({title:T(`Multi-stage cache pipeline · journey ${j.id} ${j.name} · this PR touches ${idx.length} of ${j.steps.length} steps`,`Pipeline cache nhiều chặng · hành trình ${j.id} ${j.name} · PR này chạm ${idx.length} / ${j.steps.length} bước`),
        note:T(`Only the touched steps are drawn (${skip} other steps hidden). Steps and F-ids from the critical-path sheet (draft F map).`,`Chỉ vẽ các bước bị chạm (ẩn ${skip} bước khác). Bước và F-id từ sheet critical path (map F nháp).`),parts,msgs});});
    return out.slice(0,2);}

  // ---------------------------------------------------------------- sequence rendering (HTML diagram + phone list)
  const pretty=s=>String(s==null?'':s).replace(/\{\{\s*matrix\.([a-z0-9_]+)\s*\}\}/g,(m,k)=>'‹'+({inference_engine:'engine',request_transport:'transport',async_scheduling:'async',p2p_rpc_port_mode:'port mode'}[k]||k)+'›').replace(/:[a-z_]+:\s*/g,'');
  function seqNode(S,si,M,all){const S0=S;S={...S,parts:S.parts.map(pretty),msgs:S.msgs.map(m=>({...m,label:pretty(m.label)}))};
    const full=S.msgs.length;let hidden=0;
    if(!all&&full>12&&S.msgs.some(m=>m.chg)){const keep=new Set();S.msgs.forEach((m,i)=>{if(m.chg){keep.add(i-1);keep.add(i);keep.add(i+1);}});
      const ms=S.msgs.filter((m,i)=>keep.has(i));hidden=full-ms.length;S={...S,msgs:ms};}
    const wrap=document.createElement('div');wrap.className='pi-seq';wrap.dataset.seq=si;
    const n=S.parts.length,clean=t=>String(t).replace(/:[a-z_]+:\s*/g,'');
    let svg=`<div class="pi-sg" style="--n:${n}" role="group" aria-label="${esc(S.title)}"><div class="pi-sh">${S.parts.map(p=>`<span class="obsraw" title="${esc(clean(p))}">${esc(clean(p))}</span>`).join('')}</div>`+
      `<div class="pi-lfl" aria-hidden="true">${S.parts.map((_,j)=>`<i style="left:var(--x${j})"></i>`).join('')}</div>`;
    S.msgs.forEach((m,i)=>{const found=m.from<0,a=found?0:Math.min(m.from,m.to),b=Math.max(m.from,m.to),self=!found&&m.from===m.to,L=clean(m.label);
      const kind=found?' found':self?' self':m.to<m.from?' back':'';
      svg+=`<div class="pi-msg${m.chg?' chg':''}" tabindex="0" role="button" data-m="${i}" aria-label="${esc((i+1)+'. '+L)}" style="--xa:${found?'0px':`var(--x${a})`};--xb:var(--x${b})">`+
        S.parts.map((_,j)=>`<i class="lf" style="left:var(--x${j})"></i>`).join('')+
        `<span class="lab obsraw"><span class="lw"><b>${i+1}.</b> ${esc(L)}${m.chg?`<span class="tag">${T('edited','bị sửa')}</span>`:''}</span></span>`+
        `<span class="arw"><span class="ar${kind}" style="grid-column:${a+1} / ${b+2}"></span></span>`+
        (m.cond?`<span class="cd obsraw"><span class="lw">${m.kind==='ci'?T('if','nếu')+' ':''}${esc(m.cond)}</span></span>`:'')+`</div>`;});
    svg+='</div>';
    const src=m=>m.from<0?T('start','bắt đầu'):S.parts[m.from];
    const list=`<ol class="pi-seqlist">${S.msgs.map((m,i)=>`<li class="${m.chg?'chg':''}"><b>${i+1}.</b> <span class="obsraw">${esc(src(m))} → ${esc(S.parts[m.to])}: ${esc(m.label)}</span>${m.chg?' ✎':''}${m.cond?`<div class="pi-why obsraw">[${esc(m.cond)}]</div>`:''}<button type="button" data-m="${i}">${T('Details','Chi tiết')} →</button></li>`).join('')}</ol>`;
    wrap.innerHTML=`<h5 class="obsraw">${esc(S.title)}</h5>${S.note?`<div class="pi-why obsraw">${esc(S.note)}</div>`:''}`+
      (hidden?`<div class="pi-why">${T(`Showing the ${S.msgs.length} steps around the edited ones; ${hidden} unchanged steps hidden.`,`Đang hiện ${S.msgs.length} bước quanh các bước bị sửa; ẩn ${hidden} bước không đổi.`)} <button type="button" class="pi-seqmore" data-seqall>${T(`Show all ${full} steps`,`Hiện cả ${full} bước`)}</button></div>`:'')+
      `<div class="pi-seqsvg">${svg}</div>${list}<div class="pi-seqdet" hidden></div>`;
    wrap.addEventListener('click',e=>{if(e.target.closest('[data-seqall]')){const n=seqNode(S0,si,M,true);wrap.replaceWith(n);redraw();}});
    const det=wrap.querySelector('.pi-seqdet');
    const show=i=>{const m=S.msgs[i];wrap.querySelectorAll('.pi-msg').forEach(g=>g.classList.toggle('sel',+g.dataset.m===i));
      const pay=m.payload.filter(p=>p[1]).map(p=>`<div><b>${esc(p[0])}</b>: ${code(p[1])}</div>`).join('')||unk(T('no payload recorded for this step','không có payload cho bước này'));
      let loc;
      if(m.kind==='ci') loc=ext(`${GH}/blob/${D.head||'dev'}/${m.loc.file}#L${m.loc.line}-L${m.loc.end}`,code(`${m.loc.file}:${m.loc.line}-${m.loc.end}`)+' ↗')+(m.chg?` <span class="pi-g risk">${T('edited by this PR','PR này sửa')}</span>`:'');
      else loc=m.files.length?m.files.slice(0,5).map(f=>ext(M.p&&M.p.st==='open'?`${GH}/pull/${M.n}/files`:`${GH}/blob/${D.head||'dev'}/${f[0]}`,code(f[0])+' ↗')+(f[4].length?' '+f[4].slice(0,3).map(code).join(' '):'')).join('<br>'):unk(T('this PR changes no file of this step','PR này không sửa file nào của bước này'));
      det.innerHTML=`<b class="obsraw">${i+1}. ${esc(m.label)}</b><dl><dt>${T('Payload','Payload')}</dt><dd>${pay}</dd><dt>${T('Condition','Điều kiện')}</dt><dd>${m.cond?code(m.cond):T('always (no condition)','luôn chạy (không điều kiện)')}</dd><dt>${T('Code location','Vị trí code')}</dt><dd>${loc}</dd></dl>`;
      det.hidden=false;};
    wrap.addEventListener('click',e=>{const g=e.target.closest('[data-m]');if(g){e.preventDefault();show(+g.dataset.m);}});
    wrap.addEventListener('keydown',e=>{const g=e.target.closest('.pi-msg');if(g&&(e.key==='Enter'||e.key===' ')){e.preventDefault();show(+g.dataset.m);}});
    const sg=wrap.querySelector('.pi-sg');if(ro)ro.observe(sg);
    return wrap;}

  // ---------------------------------------------------------------- hook into the Inspector render
  function bar(){const b=document.querySelector('#piDrawer .pi-anim');if(!b)return;
    const t=b.querySelector('[data-pa="toggle"]'),p=b.querySelector('[data-pa="pause"]');
    t.textContent=anim?T('Stop animation','Tắt hoạt ảnh'):T('Play the impact flow','Chạy luồng ảnh hưởng');t.setAttribute('aria-pressed',String(anim));
    p.hidden=!anim;p.textContent=RM.matches?T('Play one step','Chạy một bước'):paused?T('Play','Chạy tiếp'):T('Pause','Tạm dừng');p.setAttribute('aria-pressed',String(paused));}
  addEventListener('pirender',e=>{stop();unobserve();ctx=null;anim=false;paused=false;tick=0;phase='flow';step=0;const d=e.detail||{};
    if(!d.key||!d.key.startsWith('pr:')||d.dir!=='fwd')return;
    const dr=DR(),flow=dr.querySelector('#piFlow');if(!flow)return;
    const n=d.key.slice(3),M=PI.model(n);
    ro=new ResizeObserver(redraw);ro.observe(flow);flow.querySelectorAll(':scope>.pi-col').forEach(c=>ro.observe(c));
    const bx=document.createElement('div');bx.className='pi-anim';
    bx.innerHTML=`<button type="button" class="pi-btn" data-pa="toggle" aria-pressed="false"></button><button type="button" class="pi-btn" data-pa="pause" aria-pressed="false" hidden></button><span class="pi-why" data-pa-step></span>`;
    flow.before(bx);bar();
    const seqs=[...ciSeqs(n),...journeySeqs(M)];
    if(seqs.length){const box=document.createElement('details');box.className='pi-seqbox';box.open=seqOpen;   // review P1-9: closed by default; kept across re-renders
      box.innerHTML=`<summary>${T(`Sequence diagram · ${seqs.length} multi-step change(s) · open, then click a step`,`Sơ đồ tuần tự · ${seqs.length} thay đổi nhiều bước · mở ra rồi bấm vào một bước`)}</summary>`;
      seqs.forEach((S,i)=>box.appendChild(seqNode(S,i,M)));flow.after(box);}
    const E=graph(M);
    requestAnimationFrame(()=>{if(!flow.isConnected)return;ctx={flow,E,svg:null,sel:null};redrawNow();run();});
    bx.addEventListener('click',ev=>{const b=ev.target.closest('[data-pa]');if(!b)return;
      if(b.dataset.pa==='toggle'){anim=!anim;paused=anim&&RM.matches;tick=0;phase='flow';step=0;}
      else if(RM.matches&&anim)advance();   // reduced motion: each Play press advances one step
      else paused=!paused;
      bar();run();});
    flow.addEventListener('click',ev=>{const c=ev.target.closest('[data-pn]');if(!c||!ctx)return;ctx.sel=ctx.sel===c.dataset.pn?null:c.dataset.pn;run();});
    flow.addEventListener('keydown',ev=>{const c=ev.target.closest('[data-pn]');if(c&&(ev.key==='Enter'||ev.key===' ')){ev.preventDefault();c.click();}});
  });
  addEventListener('resize',redraw);
  document.fonts&&document.fonts.ready.then(redraw);
  document.addEventListener('toggle',e=>{const t=e.target;if(!t||!t.closest||!t.closest('#piDrawer'))return;if(t.classList&&t.classList.contains('pi-seqbox'))seqOpen=t.open;redraw();},true);
  addEventListener('piclose',()=>{stop();unobserve();anim=false;paused=false;});
  window.PISEQ={ciSeqs,journeySeqs,state:()=>({anim,paused,tick,sel:ctx&&ctx.sel,phase,step})};
})();
</script>
<!-- PISEQ:JS:END -->
"""
