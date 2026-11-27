"""CSS + JS of the PR Inspector drawer (data: build_pr_inspector.py -> <script id="piData">).

Plain JS with JSDoc types (no TypeScript: the page is built by Python stdlib scripts, no Node toolchain in the chain).
Class prefix pi- (the page has global .no .hit .badge .lit). Mounted inside #root so the .viz-root colour tokens apply.
UI strings go through T(en, vi); raw data (titles, paths, author names) is wrapped in .obsraw.
"""

CSS = r"""
/* PI:CSS:START */
.pi-drawer{position:fixed;top:0;right:0;bottom:0;width:min(780px,100vw);z-index:55;background:var(--surface-1);color:var(--text-primary);border-left:1px solid var(--border);box-shadow:-8px 0 28px rgba(0,0,0,.2);display:flex;flex-direction:column;transform:translateX(102%);transition:transform .18s ease;visibility:hidden}
.pi-drawer.on{transform:none;visibility:visible;box-shadow:-8px 0 28px rgba(0,0,0,.2),0 0 0 100vmax rgba(0,0,0,.22)}
.pi-hd{padding:14px 18px 10px;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:6px}
.pi-hd .pi-row{display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap}
.pi-hd h3{margin:0;font-size:15px;line-height:1.35;flex:1;min-width:0;overflow-wrap:anywhere}
.pi-x{all:unset;cursor:pointer;font-size:18px;line-height:1;padding:4px 8px;border-radius:8px;color:var(--text-secondary)}
.pi-x:hover,.pi-x:focus-visible{background:var(--surface-2);color:var(--text-primary)}
.pi-meta{font-size:12px;color:var(--text-secondary);display:flex;flex-wrap:wrap;gap:4px 12px}
.pi-meta a{color:var(--series-1)}
.pi-st{font-size:11px;font-weight:700;border-radius:999px;padding:1px 8px;border:1px solid var(--border)}
.pi-st.open{color:var(--series-1)}.pi-st.merged{color:var(--series-3)}.pi-st.closed{color:var(--text-muted)}
.pi-bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.pi-seg{display:inline-flex;background:var(--surface-2);border-radius:10px;padding:3px;gap:3px;flex-wrap:wrap}
.pi-seg button{all:unset;cursor:pointer;font-size:12.5px;padding:5px 11px;border-radius:8px;color:var(--text-secondary)}
.pi-seg button[aria-selected="true"]{background:var(--surface-1);color:var(--text-primary);font-weight:650;box-shadow:0 0 0 1px var(--border)}
.pi-seg button:focus-visible,.pi-btn:focus-visible{outline:2px solid var(--series-1)}
.pi-btn{all:unset;cursor:pointer;font-size:12px;padding:4px 10px;border-radius:8px;border:1px solid var(--border);color:var(--text-secondary);background:var(--surface-1)}
.pi-btn:hover{border-color:var(--series-1);color:var(--text-primary)}
.pi-btn[hidden],.pi-x[hidden]{display:none}
.pi-body{flex:1;overflow:auto;padding:12px 18px 40px}
.pi-flow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:30px;margin:4px 0 12px;align-items:start}
.pi-col{background:transparent;border:1px solid var(--border);border-radius:10px;padding:8px;min-width:0}
.pi-col .pi-chip{position:relative;z-index:1}
.pi-flow .pi-col .pi-chip{display:block;width:fit-content;max-width:100%;margin:3px 0}
.pi-col h5{margin:0 0 6px;font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--text-muted)}
.pi-chip{display:inline-block;font-size:11.5px;border:1px solid var(--border);border-radius:999px;padding:1px 8px;margin:2px 3px 2px 0;background:var(--surface-1);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle}
.pi-chip.focus{border-color:var(--series-2);box-shadow:0 0 0 1px var(--series-2)}
.pi-flow .pi-col:last-child .pi-chip{white-space:normal;max-width:100%}
.pi-draft{font-size:10px;color:var(--text-muted);border:1px dashed var(--border);border-radius:6px;padding:0 4px;margin-left:4px}
.pi-tabs{margin:6px 0 10px}
.pi-view h4{margin:14px 0 6px;font-size:12.5px;color:var(--text-secondary)}
.pi-items{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.pi-items>li{border:1px solid var(--border);border-radius:10px;padding:8px 10px;font-size:13px;line-height:1.45;overflow-wrap:anywhere}
.pi-items>li.focus{border-color:var(--series-2)}
.pi-ev{margin-top:4px;font-size:11.5px;color:var(--text-secondary);display:flex;flex-wrap:wrap;gap:2px 10px}
.pi-ev a{color:var(--series-1)}
.pi-ev code,.pi-items code{font-size:11px}
.pi-unk{display:inline-block;font-size:11px;font-weight:700;color:var(--warning,#b7791f);border:1px dashed currentColor;border-radius:6px;padding:0 6px}
.pi-why{font-size:11.5px;color:var(--text-muted)}
.pi-check{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px}
.pi-check li{display:flex;gap:8px;align-items:flex-start;font-size:13px;line-height:1.4}
.pi-check input{margin-top:3px;flex:none}
.pi-check .q{color:var(--text-secondary)}
.pi-gt{width:100%;border-collapse:collapse;font-size:12.5px}
.pi-gt td{border-top:1px solid var(--border);padding:5px 6px;vertical-align:top;overflow-wrap:anywhere}
.pi-g{font-size:11px;font-weight:700;border-radius:999px;padding:1px 8px;white-space:nowrap}
.pi-g.req{color:var(--series-1);border:1px solid currentColor}
.pi-g.cond{color:var(--text-secondary);border:1px dashed currentColor}
.pi-g.risk{color:var(--critical,#c0392b);border:1px solid currentColor}
.pi-g.adv{color:var(--text-muted);border:1px dotted currentColor}
.pi-s{display:inline-block;white-space:nowrap;font-size:11px;line-height:1.5;border-radius:6px;padding:0 5px;border:1px solid var(--border);vertical-align:1px}
.pi-col .pi-s{display:block;width:fit-content;margin:2px 0 0;font-size:10.5px}
.pi-s.ok{color:var(--series-3)}.pi-s.bad{color:var(--critical,#c0392b)}.pi-s.wait{color:var(--text-muted)}
.pi-st+.pi-why{overflow-wrap:anywhere}
.pi-src{font-size:11.5px;color:var(--text-muted);margin-top:14px;border-top:1px dashed var(--border);padding-top:8px}
.pi-list{display:flex;flex-direction:column;gap:6px}
.pi-start{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
@media (max-width:600px){.pi-drawer{left:0;width:auto;border-left:0}.pi-flow{grid-template-columns:minmax(0,1fr)}.pi-hd,.pi-body{padding-left:12px;padding-right:12px}.pi-gt td{display:block;border-top:0;padding:2px 4px}.pi-gt tr{display:block;border-top:1px solid var(--border);padding:4px 0}}
@media (prefers-reduced-motion:reduce){.pi-drawer{transition:none}}
/* PI:CSS:END */
"""

JS = r"""
<!-- PI:JS:START -->
<script>
/* PR Inspector (build_pr_inspector.py, pr_inspector_ui.py). window.piOpen(key, opts) -> true when it opened.
   key: 'pr:<num>' | 'bug:<signature id>' | 'reg:<index>' ; opts: {dir:'fwd'|'back', view:1..5, focus:'<code area>'} */
(function(){
  /** @typedef {[string,string,number,number,string[],string[],string,number]} PiFile  path, status, +lines, -lines, functions, classes, area, first new line */
  const D=JSON.parse(document.getElementById('piData').textContent);
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en, L=a=>Array.isArray(a)?T(a[0],a[1]):(a||'');
  const hotC=a=>(a||[]).filter(c=>!c.lv||/^p[0-3]$/.test(c.lv));   // review m3: p4 (imports / config only) does not put a gate at risk
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const GH='https://github.com/LMCache/LMCache';
  const raw=s=>`<span class="obsraw">${esc(s)}</span>`, code=s=>`<code class="obsraw">${esc(s)}</code>`;
  const ext=(h,t)=>h?`<a href="${esc(h)}" target="_blank" rel="noopener">${t}</a>`:t;
  const prA=m=>`<a href="#" class="pi-pr" data-pi="pr:${esc(m)}">#${esc(m)}</a>`;
  const entA=(k,t)=>`<a href="#" class="ent-l" data-ent="${esc(k)}" role="link">${t}</a>`;
  const unk=why=>`<span class="pi-unk">${T('unknown','chưa biết')}</span> <span class="pi-why">${why}</span>`;
  const short=p=>{const a=String(p).split('/');return a.length>2?'…/'+a.slice(-2).join('/'):p;};
  const GKEY={'DCO':'dco','Check code quality':'quality','k3-unit-tests':'unit','k3-multiprocess-test':'mp','k3-multiprocess-smoke':'smoke'};
  // review 2026-11-26 P0-3: ONE vocabulary for check states, used by the merge verdict (ux_ui.py), the gate tables (chk) and
  // the flow chips. Data: build_pr_inspector.py (ck.g, head-commit rollup) and build_ops_tabs.py (rv.g, review queue);
  // stateNorm folds their spellings (run / running, cancel / cancelled, SKIPPED / NEUTRAL = ok ...).
  const stateNorm=v=>{const s=String(v==null?'':v).toLowerCase();
    return /^(ok|pass|passed|success|skip|skipped|neutral)$/.test(s)?'ok':/^(fail|failed|failure|error|timed_out|action_required|startup_failure)$/.test(s)?'fail':
      /^(cancel|cancelled|canceled|stale)$/.test(s)?'cancel':/^(run|running|pending|expected|wait|waiting|in_progress|queued|scheduled|started|creating)$/.test(s)?'running':
      /^(missing|label|bypass|draft)$/.test(s)?s:'none';};
  /** word of a state: t = text, pi = .pi-s class, ux = .ux-chip class, ic = icon, tip = tooltip; key = gate key (dco, quality, unit, mp, smoke) */
  const stateWord=(v,key)=>{const s=stateNorm(v),mp=key==='mp'||key==='smoke';
    const W={ok:[T('passed','đạt'),'ok','ok','✓'],fail:[T('failed','thất bại'),'bad','fail','✗'],cancel:[T('cancelled','đã huỷ'),'bad','fail','✗'],
      running:[T('running','đang chạy'),'wait','warn','…'],missing:[T('not reported','chưa báo'),'wait','warn','–'],
      label:[T('waits for label','chờ nhãn'),'wait','warn','◌'],bypass:[T('bypassed','bỏ qua'),'wait','warn','↷'],
      draft:[T('draft: not built','nháp: không build'),'wait','unk','◌'],
      none:[T('no result','chưa có'),'wait','unk','–']}[s];
    const tip={label:T('the full MP run needs the label full, force-ci or mp (#6731)','bộ MP đầy đủ cần nhãn full, force-ci hoặc mp (#6731)'),
      bypass:T('#6731: the heavy MP suite is skipped on ordinary PRs (green in about 5 s); k3-multiprocess-smoke is the PR signal','#6731: bộ MP nặng được bỏ qua trên PR thường (xanh sau khoảng 5 s); k3-multiprocess-smoke là tín hiệu của PR'),
      missing:T('a required check that never reported on the head commit','check bắt buộc chưa từng báo kết quả trên commit head'),cancel:T('cancelled: re-run it','đã huỷ: cần chạy lại'),none:T('no result in the local data','không có kết quả trong dữ liệu local'),
      draft:T('#6730 / #6731: k3-unit-tests and the MP pipelines build ready (non-draft) commits only','#6730 / #6731: k3-unit-tests và các pipeline MP chỉ build commit sẵn sàng (không nháp)')}[s]||'';
    return {s,t:W[0],pi:W[1],ux:W[2],ic:W[3],tip};};
  /** gate states of a PR: rv.g (review queue) and ck.g (snapshot rollup) merged key by key, ck first (it also knows draft / bypass) */
  const gstates=p=>{const o={},rv=(p&&p.rv&&p.rv.g)||{},ck=(p&&p.ck&&p.ck.g)||{};
    new Set([...Object.keys(rv),...Object.keys(ck)]).forEach(k=>{if(k[0]==='_'){o[k]=ck[k]!=null?ck[k]:rv[k];return;}
      const a=ck[k]!=null?stateNorm(ck[k]):'none',b=rv[k]!=null?stateNorm(rv[k]):'none';o[k]=a!=='none'?a:b;});
    return o;};
  // review P2-13: glossary of codes the drawer shows (queue codes, overlap levels, tiers)
  const QW={ci_fail:['a required check failed','một check bắt buộc thất bại'],ci_missing:['a required check has not reported','một check bắt buộc chưa báo kết quả'],
    ci_run:['CI is running','CI đang chạy'],wait_full:['waits for an MP label (full, force-ci or mp)','chờ nhãn MP (full, force-ci hoặc mp)'],
    wait_review:['waits for review','chờ review'],adapt:['changes requested: the author must update','được yêu cầu sửa: tác giả cần cập nhật'],
    ready:['approved, ready to merge','đã approve, sẵn sàng merge'],conflict:['merge conflict with dev','xung đột merge với dev'],old:['older than 30 days','cũ hơn 30 ngày'],
    draft:['draft','nháp'],queue:['in the review queue','trong hàng đợi review'],running:['CI is running','CI đang chạy']};
  const LV={p0:['p0: a symbol this PR uses was removed or renamed','p0: một symbol PR này dùng đã bị xoá hoặc đổi tên'],p1:['p1: both edit the same function','p1: cả hai sửa cùng một hàm'],
    p2:['p2: edits on nearby lines','p2: sửa các dòng gần nhau'],p3:['p3: same file, different lines (check, not urgent)','p3: cùng file, khác dòng (cần xem, chưa gấp)'],p4:['p4: imports / config only','p4: chỉ import / config']};
  const tierTip=g=>(g.tiers||[]).map(t=>{const x=D.tiers[t]||{};return (x.name||t)+((x.plain||[]).length?': '+L(x.plain):'');}).join('\n')||(g.smoke?T('every ready PR (#6731), not required yet','mọi PR sẵn sàng (#6731), chưa bắt buộc'):'');
  const KINDS={lock:['lock','khoá (lock)'],thread:['thread','luồng (thread)'],async:['asyncio / await','asyncio / await'],process:['process / shared memory','process / shared memory'],
    queue:['queue','hàng đợi (queue)'],event:['event / wait','event / wait'],cuda_stream:['CUDA stream / sync','CUDA stream / sync'],atomic:['atomic','atomic'],
    sleep:['sleep','sleep'],clock:['wall clock','đồng hồ thực'],random:['random / uuid','random / uuid'],timeout:['fixed timeout','timeout cố định'],
    port:['fixed port / socket','port cố định / socket'],env:['environment variable','biến môi trường'],set_order:['set iteration order','thứ tự duyệt set'],gc:['gc / weakref','gc / weakref']};
  const VIEWS=[['feature.internal','feature.internal'],['among features','giữa các feature'],['flaky & non-deterministic','flaky & không tất định'],['race & concurrency','race & đồng thời'],['semantic conflict','xung đột ngữ nghĩa']];

  const root=document.getElementById('root')||document.body;
  const dr=document.createElement('aside');dr.id='piDrawer';dr.className='pi-drawer';dr.setAttribute('role','dialog');dr.setAttribute('aria-hidden','true');dr.setAttribute('aria-labelledby','piTitle');
  root.appendChild(dr);
  let cur=null,dir='fwd',view=1,focus=null,opener=null;

  // ---------------------------------------------------------------- model of one PR (forward direction)
  function model(n){
    const p=D.prs[n]||null, files=p?p.f:[];
    const isDoc=f=>/^docs\//.test(f[0])||/\.(md|rst|txt)$/i.test(f[0]);
    const codeF=files.filter(f=>!/^tests\//.test(f[0])&&!isDoc(f));
    const areas=[...new Set((p&&p.ar||[]).map(x=>x[0]).concat(codeF.map(f=>f[6]).filter(Boolean)))].filter(a=>D.areas[a]);
    const strong=new Set((p&&p.ar||[]).filter(x=>x[1]==='strong').map(x=>x[0]));
    areas.sort((a,b)=>(strong.has(b)-strong.has(a)));
    const cls=new Set();
    if(files.length){ if(!codeF.length) cls.add(files.some(f=>/^tests\//.test(f[0]))?'tests_only':'docs'); else codeF.forEach(f=>cls.add(f[6]&&D.areas[f[6]]?D.areas[f[6]].cls:'core')); }
    else areas.forEach(a=>cls.add(D.areas[a].cls||'core'));
    const tiers={}; cls.forEach(c=>{const C=D.classes[c]; if(C) Object.entries(C.tiers).forEach(([t,l])=>{tiers[t]=Math.min(tiers[t]||9,l);});});
    const gates={}; Object.entries(tiers).forEach(([t,l])=>{const ti=D.tiers[t]||{},j=ti.job||t,g=gates[j]||(gates[j]={name:j,tiers:[],lvl:9,req:!!ti.req});g.tiers.push(t);g.lvl=Math.min(g.lvl,l);});
    const F=[...new Set(areas.flatMap(a=>D.areas[a].F||[]))].sort();
    const gl=Object.values(gates);
    if(gl.some(g=>g.name==='k3-multiprocess-test')&&!gl.some(g=>g.name==='k3-multiprocess-smoke'))gl.push({name:'k3-multiprocess-smoke',tiers:[],lvl:1,req:false,smoke:true});   // #6731: per ready PR
    return {n,p,files,codeF,areas,strong,cls:[...cls],tiers,gates:gl,F};
  }
  const fileA=(M,f,line)=>{const p=f[0];
    if(M.p&&M.p.st==='open') return ext(`${GH}/pull/${M.n}/files`,code(short(p))+' ↗');
    return ext(`${GH}/blob/${D.head||'dev'}/${p}${line?'#L'+line:''}`,code(short(p)+(line?':'+line:''))+' ↗');};
  const chk=(s,key)=>{const w=stateWord(s,key);return `<span class="pi-s ${w.pi}" data-st="${w.s}"${w.tip?` title="${esc(w.tip)}"`:''}>${w.ic} ${esc(w.t)}</span>`;};
  const gstate=(M,name)=>M.p?gstates(M.p)[GKEY[name]]:undefined;
  /** gate row: kind = req | cond | risk | adv */
  const G=(name,kind,why)=>({name,kind,why});
  const tierTxt=g=>g.tiers.map(t=>{const x=D.tiers[t]||{};return (x.name||t)+((x.wl||[]).length?' ('+x.wl.join(', ')+')':'');}).join(' · ');
  const baseGates=M=>M.gates.map(g=>G(g.name,g.req&&g.lvl===1?'req':g.lvl===2?'cond':'adv',g.smoke?T('MP smoke: runs on every ready PR (#6731), not required yet','smoke MP: chạy trên mọi PR sẵn sàng (#6731), chưa bắt buộc'):
    T(`change class ${M.cls.join(', ')} → ${tierTxt(g)}`,`nhóm thay đổi ${M.cls.join(', ')} → ${tierTxt(g)}`)));
  const item=(html,ev,cls)=>`<li${cls?` class="${cls}"`:''}>${html}${ev?`<div class="pi-ev">${ev}</div>`:''}</li>`;
  const scanOf=p=>D.scan[p];

  // ---------------------------------------------------------------- the 5 views: findings (evidence or unknown), checklist, gates
  function v1(M){const I=[],C=[],GS=baseGates(M);
    if(!M.files.length) I.push(item(T('Changed files and functions','File và hàm thay đổi')+': '+unk(M.p&&M.p.st==='open'?T('this open PR is not among the 100 patches in overlap_patches.json','PR mở này không nằm trong 100 patch của overlap_patches.json'):T('no diff in local data (merge commit not in the local clone)','không có diff trong dữ liệu local (merge commit không có trong clone local)'))));
    else{const by={};M.files.forEach(f=>{const a=/^tests\//.test(f[0])?'tests':(f[6]&&D.areas[f[6]]?f[6]:(/^docs\/|\.md$/.test(f[0])?'docs':'other'));(by[a]=by[a]||[]).push(f);});
      const order=[...M.areas.filter(a=>by[a]),...Object.keys(by).filter(a=>!M.areas.includes(a))];
      order.forEach(a=>{const A=D.areas[a],fs=by[a];
        const head=A?`<b>${raw(A.t)}</b> <span class="pi-why">(${esc(a)} · ${T('class','nhóm')} ${esc(A.cls)})</span> ${(A.F||[]).map(f=>`<span class="pi-chip${focus===a?' focus':''}">${esc(f)}</span>`).join('')}${A.F&&A.F.length?`<span class="pi-draft">${T('F map: draft','map F: nháp')}</span>`:''}`
          :`<b>${a==='tests'?T('Tests','Test'):a==='docs'?T('Docs','Tài liệu'):T('Other files','File khác')}</b>`;
        const body=fs.map(f=>`${fileA(M,f,(scanOf(f[0])&&scanOf(f[0]).d&&f[4][0]&&scanOf(f[0]).d[f[4][0]])||f[7])} <span class="pi-why">+${f[2]} −${f[3]}</span>${f[4].length?' · '+T('functions','hàm')+': '+f[4].map(code).join(' '):''}${f[5].length?' · '+T('classes','lớp')+': '+f[5].map(code).join(' '):''}`).join('<br>');
        I.push(item(head,body,focus===a?'focus':''));});}
    // review m1: tests edited = entity edges, else the test files in this PR's own file list
    const TESTF=/(^|\/)tests?\/|(^|\/)test_[^/]*\.py$|_test\.(py|rs|cc|cpp)$/;
    const te=((M.p&&M.p.te)||[]).length?M.p.te:(M.files||[]).filter(f=>TESTF.test(f[0])).map(f=>'test:'+f[0]);
    I.push(te.length?item(T(`Tests edited by this PR (${te.length})`,`Test được PR này sửa (${te.length})`),te.slice(0,12).map(t=>entA(t,code(short(t.slice(5))))).join(' ')):
      item(!M.files.length?unk(T('No file list for this PR: what it changes is not known here.','Không có danh sách file của PR này: chưa biết PR đổi gì.')):M.codeF.length?T('No test file was edited in this PR.','PR này không sửa file test nào.'):T('No code outside tests and docs changed.','Không đổi code ngoài test và tài liệu.'),M.files.length?(M.p.st==='open'?ext(`${GH}/pull/${M.n}/files`,T('Files','File')+' ↗'):code('git show '+(M.p.sha||''))):unk(T('no file list','không có danh sách file'))));
    {const tp=te.map(t=>t.slice(5)).filter(x=>/\.py$/.test(x)).slice(0,10);   // round 2 F10: which tests to run locally for this PR
      if(tp.length)I.push(item(T('Run these tests before you push','Chạy các test này trước khi push'),`<code class="obsraw">pytest -q ${tp.map(esc).join(' ')}</code> <button type="button" class="ux-btn" data-ux-copy="pytest -q ${esc(tp.join(' '))}">${T('Copy','Sao chép')}</button>`));}
    const fn=[...new Set(M.codeF.flatMap(f=>f[4]))].slice(0,6);
    C.push(T('Each edited function keeps its contract: inputs, return value, errors raised, side effects.','Mỗi hàm bị sửa giữ nguyên hợp đồng: đầu vào, giá trị trả về, lỗi ném ra, tác dụng phụ.'));
    if(fn.length) C.push(T(`Who calls ${fn.join(', ')}? Were those callers checked or tested?`,`Ai gọi ${fn.join(', ')}? Các chỗ gọi đó đã được xem hoặc test chưa?`));
    if(M.codeF.length&&!te.length) C.push(T('No test was edited: ask for a test that fails without this change.','Không sửa test nào: yêu cầu một test fail khi không có thay đổi này.'));
    if(M.codeF.some(f=>f[5].length)) C.push(T('A class changed: check its subclasses and every place it is constructed.','Một lớp thay đổi: kiểm tra lớp con và mọi chỗ khởi tạo nó.'));
    if(M.areas.some(a=>['cli','http','frontend'].includes(a))) C.push(T('User-visible behaviour (CLI, HTTP API) changed: is it in the release note?','Hành vi người dùng thấy (CLI, HTTP API) thay đổi: đã có trong release note chưa?'));
    return {I,C,G:GS};}

  function v2(M){const I=[],C=[],GS=[];
    if(!M.areas.length) I.push(item(T('Features touched','Feature bị chạm')+': '+unk(T('no code area for this PR in local data','không có code area cho PR này trong dữ liệu local'))));
    else I.push(item(M.areas.length>1?T(`Touches ${M.areas.length} code areas: a cross-feature change.`,`Chạm ${M.areas.length} code area: thay đổi xuyên feature.`):T('Touches one code area.','Chạm một code area.'),
      M.areas.map(a=>entA('feature:'+a,raw(D.areas[a].t))).join(' · ')));
    M.F.forEach(f=>{const x=D.F[f]||{};const pos=[];
      D.journeys.forEach(j=>j.f.forEach((s,i)=>{if((s||[]).includes(f)){const pv=(j.f[i-1]||[]).filter(y=>y!==f),nx=(j.f[i+1]||[]).filter(y=>y!==f);
        pos.push(T(`journey ${j.id} ${j.name} step ${i+1} "${j.steps[i]||''}"`,`hành trình ${j.id} ${j.name} bước ${i+1} "${j.steps[i]||''}"`)+(pv.length?T(' · after ',' · sau ')+pv.join(', '):'')+(nx.length?T(' · before ',' · trước ')+nx.join(', '):''));}}));
      I.push(item(`<b>${esc(f)}</b> ${raw(x.name||'')} <span class="pi-draft">${T('draft map','map nháp')}</span>`+(x.dep?`<div class="pi-why">${T('Hands data','Chuyển dữ liệu')}: ${raw(x.dep)}</div>`:''),
        (pos.length?`<span class="obsraw">${esc(pos.join(' | '))}</span> · `:unk(T('not on a critical-path journey','không nằm trên hành trình critical path'))+' · ')+`<button type="button" class="pi-btn" data-goto="obs/coming">${T('Critical path','Critical path')} →</button> ${code(D.cp_src||'LMCache_CPU_GPU_Feature_Matrix.xlsx')}`));
      if(x.gate) GS.push(G(x.gate,'cond',T(`${f}: gate named in the feature matrix`,`${f}: gate ghi trong feature matrix`)));
      if(x.dep) C.push(T(`${f}: does the change alter what it hands on (${x.dep})?`,`${f}: thay đổi có làm khác dữ liệu nó chuyển đi (${x.dep}) không?`));});
    const others=[...new Set(M.areas.flatMap(a=>D.areas[a].open||[]))].filter(m=>String(m)!==String(M.n));
    if(M.areas.length) I.push(item(T(`Other open PRs on the same code areas (${others.length})`,`PR mở khác trên cùng code area (${others.length})`),others.length?others.slice(0,12).map(prA).join(' '):T('none in the snapshot','không có trong snapshot')));
    I.push(item(T('Import / call links between features','Liên kết import / gọi hàm giữa các feature')+': '+unk(T('no import graph is built from local data yet','chưa dựng đồ thị import từ dữ liệu local'))));
    if(M.areas.length>1) C.push(T('Which feature owns the behaviour change? Split the PR if two features change independently.','Feature nào sở hữu thay đổi hành vi? Tách PR nếu hai feature thay đổi độc lập.'));
    C.push(T('Run the paired CPU / GPU check named for each feature before merge.','Chạy check CPU / GPU đi cặp của từng feature trước khi merge.'));
    const wait=M.p&&M.p.rv&&/wait_full/.test(M.p.rv.sub||'');
    M.gates.filter(g=>g.lvl===2).forEach(g=>GS.push(G(g.name,wait?'risk':'cond',wait?T('conditional suite has not run yet (waits for the label full, force-ci or mp)','bộ có điều kiện chưa chạy (chờ nhãn full, force-ci hoặc mp)'):T(`conditional for tiers ${g.tiers.join(', ')}`,`có điều kiện cho tier ${g.tiers.join(', ')}`))));
    if(!GS.length) GS.push(...baseGates(M));
    return {I,C,G:GS};}

  function hitsOf(M,cat){const out=[],none=[],miss=[];
    M.files.forEach(f=>{if(Array.isArray(f[8])){const ad=f[8].filter(x=>x[0]===cat);if(ad.length)out.push({f,inEd:ad,other:[],added:true});else none.push(f[0]);return;}   // round 2 F4: the PR's own added lines
      const s=scanOf(f[0]);if(!s){if(!/\.(md|rst|txt|ya?ml|json|toml|cfg|ini|sh)$/i.test(f[0]))miss.push(f[0]);return;}
      const h=(s.h||[]).filter(x=>x[0]===cat);if(!h.length){none.push(f[0]);return;}
      const inEd=h.filter(x=>f[4].includes(x[3])||f[5].includes(x[3]));out.push({f,inEd,other:h.filter(x=>!inEd.includes(x))});});
    return {out,none,miss};}
  const allAdded=M=>M.files.length>0&&M.files.every(f=>Array.isArray(f[8]));
  const kindsOf=hs=>[...new Set(hs.map(x=>x[1]))].map(k=>L(KINDS[k]||[k,k]));

  function v3(M){const I=[],C=[],GS=[];const H=hitsOf(M,'n');
    H.out.forEach(({f,inEd,other,added})=>{const hs=inEd.length?inEd:other;const fn=[...new Set(hs.map(x=>x[3]).filter(Boolean))];
      I.push(item((inEd.length?T('Heuristic scan (text match, may hit comments): edited code mentions ','Quét heuristic (so khớp chữ, có thể trúng comment): code bị sửa nhắc tới '):T('Heuristic scan: same file (not the edited lines) mentions ','Quét heuristic: cùng file (không phải dòng bị sửa) nhắc tới '))+kindsOf(hs).join(', ')+(fn.length?' '+T('in','trong')+' '+fn.slice(0,4).map(code).join(' '):''),
        hs.slice(0,4).map(x=>fileA({...M,p:{st:'merged'}},f,x[2])).join(' ')+` <span class="pi-why">${added?T('in lines this PR adds','trong các dòng PR thêm'):T('scan of the file at','quét file tại')+' '+esc((D.head||'').slice(0,8))}</span>`,inEd.length?'focus':''));
      if(inEd.some(x=>['sleep','clock'].includes(x[1]))&&/^tests\//.test(f[0])) C.push(T(`${short(f[0])}: replace sleep / wall-clock waits with an event or a fake clock.`,`${short(f[0])}: thay sleep / chờ theo đồng hồ thực bằng event hoặc đồng hồ giả.`));
      if(inEd.some(x=>x[1]==='random')) C.push(T('Random values in the edited code: is a seed set in the tests?','Giá trị ngẫu nhiên trong code bị sửa: test đã đặt seed chưa?'));
      if(inEd.some(x=>x[1]==='port')) C.push(T('Fixed port or socket: bind port 0 or use a free-port helper in tests.','Port hoặc socket cố định: bind port 0 hoặc dùng helper lấy port trống trong test.'));});
    if(!H.out.length) I.push(item(!M.files.length?unk(T('not scanned: no file list for this PR','chưa quét: không có danh sách file của PR')):H.miss.length&&!H.none.length?T('Sleep, clock, random, port use','Dùng sleep, đồng hồ, random, port')+': '+unk(T('files are not in the local clone at HEAD','file không có trong clone local tại HEAD')):
      allAdded(M)?T('No sleep, wall clock, random, fixed port or env read in the lines this PR adds (heuristic text match).','Không có sleep, đồng hồ thực, random, port cố định hay đọc env trong các dòng PR thêm (heuristic so khớp chữ).'):T('No sleep, wall clock, random, fixed port or env read found in these files at dev HEAD (heuristic: not the PR\'s own lines).','Không thấy sleep, đồng hồ thực, random, port cố định hay đọc env trong các file này tại dev HEAD (heuristic: không phải dòng của PR).'),H.none.length?H.none.slice(0,4).map(p=>code(short(p))).join(' '):''));
    const rt=(M.p&&M.p.rt)||[];
    if(rt.length) I.push(item(T(`This PR needed ${rt.length} CI retries in the 30-day baselines`,`PR này cần ${rt.length} lần chạy lại CI trong baseline 30 ngày`),rt.slice(0,6).map(r=>`${ext(r[4],raw(r[0]+' · '+r[1]))} <span class="obsraw">${esc(r[2])}: ${esc((r[3]||'').slice(0,90))} → ${esc(r[6]||'')}</span>`).join('<br>')));
    else I.push(item(T('Retries of this PR in the 30-day baselines: none found.','Chạy lại CI của PR này trong baseline 30 ngày: không có.'),code('P1*/retry_events_30d.csv')));
    const bad=((M.p&&M.p.b)||[]).filter(b=>(D.builds[b]||{}).st==='failed');
    bad.forEach(b=>{const B=D.builds[b];I.push(item(T('Failed build of this PR','Build fail của PR này')+' '+ext(B.url,raw(b.slice(6))+' ↗'),(B.sig||[]).length?B.sig.map(s=>`<button type="button" class="pi-btn" data-pi="bug:${esc(s)}">${raw((D.bugs[s]||{}).t||s)}</button>`).join(' '):unk(T('no failure signature sampled for this build','chưa lấy mẫu signature lỗi cho build này'))));});
    const mp=M.gates.find(g=>g.name==='k3-multiprocess-test');
    if(mp&&D.flaky.length){I.push(item(T('The MP suite this PR must pass has known flaky workloads','Bộ MP mà PR này phải qua có workload flaky đã biết'),D.flaky.slice(0,6).map(w=>`<span class="obsraw">${esc(w.name)} ${esc(w.rate)}% / ${esc(w.runs)}</span>`).join(' · ')+` <button type="button" class="pi-btn" data-goto="r1130/retry">${T('Report 1130 · Ran again','Report 1130 · Chạy lại')} →</button>`));
      GS.push(G('k3-multiprocess-test','risk',T(`known flaky: ${D.flaky.slice(0,3).map(w=>w.name.split(' ')[0]+' '+w.rate+'%').join(', ')}`,`flaky đã biết: ${D.flaky.slice(0,3).map(w=>w.name.split(' ')[0]+' '+w.rate+'%').join(', ')}`)));
      C.push(T('If MP fails on a known flaky workload, compare the failure signature with Report 1130 before asking the author for a fix.','Nếu MP fail ở workload flaky đã biết, so signature lỗi với Report 1130 trước khi yêu cầu tác giả sửa.'));}
    const ut=M.gates.find(g=>g.name==='k3-unit-tests');
    const tNd=H.out.some(o=>/^tests\//.test(o.f[0])&&o.inEd.length);
    if(ut) GS.push(G('k3-unit-tests',tNd?'risk':'req',tNd?T('edited tests use sleep / clock / random / ports','test bị sửa dùng sleep / đồng hồ / random / port'):T('runs the unit tests of the touched areas','chạy unit test của các area bị chạm')));
    C.push(T('Does any new or edited test depend on timing, ordering, randomness or a fixed port?','Có test mới hoặc bị sửa nào phụ thuộc thời gian, thứ tự, ngẫu nhiên hay port cố định không?'));
    if(rt.length) C.push(T('This PR already needed a retry: was the first failure a known flaky signature or caused by the change?','PR này đã phải chạy lại: lần fail đầu là signature flaky đã biết hay do thay đổi gây ra?'));
    if(!GS.length) GS.push(...baseGates(M));
    return {I,C,G:GS};}

  function v4(M){const I=[],C=[],GS=[];const H=hitsOf(M,'c');const ks=new Set();
    H.out.forEach(({f,inEd,other,added})=>{const hs=inEd.length?inEd:other;hs.forEach(x=>ks.add(x[1]));const fn=[...new Set(hs.map(x=>x[3]).filter(Boolean))];
      I.push(item((inEd.length?T('Heuristic scan (text match, may hit comments): edited code mentions ','Quét heuristic (so khớp chữ, có thể trúng comment): code bị sửa nhắc tới '):T('Heuristic scan: same file (not the edited lines) mentions ','Quét heuristic: cùng file (không phải dòng bị sửa) nhắc tới '))+kindsOf(hs).join(', ')+(fn.length?' '+T('in','trong')+' '+fn.slice(0,4).map(code).join(' '):''),
        hs.slice(0,4).map(x=>fileA({...M,p:{st:'merged'}},f,x[2])).join(' '),inEd.length?'focus':''));});
    if(!H.out.length) I.push(item(!M.files.length?unk(T('not scanned: no file list for this PR','chưa quét: không có danh sách file của PR')):H.miss.length&&!H.none.length?T('Locks, threads, asyncio, processes, CUDA streams','Lock, thread, asyncio, process, CUDA stream')+': '+unk(T('files are not in the local clone at HEAD','file không có trong clone local tại HEAD')):
      allAdded(M)?T('No lock, thread, asyncio, process or CUDA stream use in the lines this PR adds (heuristic text match).','Không có lock, thread, asyncio, process hay CUDA stream trong các dòng PR thêm (heuristic so khớp chữ).'):T('No lock, thread, asyncio, process or CUDA stream use found in these files at dev HEAD (heuristic: not the PR\'s own lines).','Không thấy lock, thread, asyncio, process hay CUDA stream trong các file này tại dev HEAD (heuristic: không phải dòng của PR).'),M.files.length?ext(`${GH}/pull/${M.n}/files`,T('Files','File')+' ↗'):''));
    const c24=(M.p&&M.p.c24)||[];
    if(c24.length) I.push(item(T('Merge race (not thread safety): CI of this PR ran before these overlapping merges landed','Merge race (không phải thread safety): CI của PR này chạy trước khi các merge chồng lấn này vào'),c24.slice(0,6).map(c=>`${prA(c.m)} <span class="pi-why">${esc((c.at||'').slice(0,16).replace('T',' '))} · ${c.sh.length} ${T('shared files','file chung')}</span>`).join('<br>')));
    const ct=[...new Set(M.areas.flatMap(a=>D.areas[a].ct||[]))];
    I.push(item(T(`Concurrency tests on the touched areas (${ct.length})`,`Test đồng thời trên các area bị chạm (${ct.length})`),ct.length?ct.slice(0,8).map(t=>entA('test:'+t,code(short(t)))).join(' '):(M.areas.length?T('none: no test of these areas uses threads, asyncio or processes','không có: không test nào của các area này dùng thread, asyncio hay process'):unk(T('no code area','không có code area')))));
    if(ks.has('lock')) C.push(T('Is every read and write of the changed state under the same lock? Does the change add a new lock order (deadlock)?','Mọi đọc / ghi của trạng thái bị đổi có cùng một lock không? Thay đổi có tạo thứ tự lock mới (deadlock) không?'));
    if(ks.has('async')) C.push(T('Can the coroutine be cancelled or interleaved between a check and the use of its result? Is cleanup in finally?','Coroutine có thể bị huỷ hoặc xen giữa lúc kiểm tra và lúc dùng kết quả không? Dọn dẹp có nằm trong finally không?'));
    if(ks.has('thread')||ks.has('event')||ks.has('queue')) C.push(T('Who stops and joins the thread? Can a consumer wait forever (timeout, sentinel)?','Ai dừng và join thread? Bên nhận có thể chờ mãi không (timeout, sentinel)?'));
    if(ks.has('process')) C.push(T('Which process owns and frees the shared buffer? What happens if the other side dies?','Process nào sở hữu và giải phóng buffer chung? Chuyện gì xảy ra nếu phía kia chết?'));
    if(ks.has('cuda_stream')) C.push(T('Is a tensor used on another CUDA stream without wait_stream / record_stream?','Có tensor nào được dùng trên CUDA stream khác mà thiếu wait_stream / record_stream không?'));
    if(!ks.size) C.push(T('Confirm the edited functions are never called from a worker thread, a callback or another process.','Xác nhận các hàm bị sửa không bao giờ được gọi từ worker thread, callback hay process khác.'));
    if(c24.length) C.push(T('Rebase and re-run CI: the green result predates overlapping merges.','Rebase và chạy lại CI: kết quả xanh có trước các merge chồng lấn.'));
    const ut=M.gates.find(g=>g.name==='k3-unit-tests'),mp=M.gates.find(g=>g.name==='k3-multiprocess-test');
    if(ut) GS.push(G('k3-unit-tests',ks.size&&!ct.length?'risk':'req',ks.size&&!ct.length?T('concurrent code changed, no concurrency test on these areas','code đồng thời bị sửa, không có test đồng thời trên các area này'):T(`runs ${ct.length} concurrency tests of these areas`,`chạy ${ct.length} test đồng thời của các area này`)));
    if(mp) GS.push(G('k3-multiprocess-test',hotC(c24).length?'risk':'req',hotC(c24).length?T('result older than overlapping merges','kết quả cũ hơn các merge chồng lấn'):T('multi-process end-to-end run','chạy end-to-end nhiều process')));
    if(!GS.length) GS.push(...baseGates(M));
    return {I,C,G:GS};}

  function v5(M){const I=[],C=[],GS=[];const p=M.p||{},c24=p.c24||[],oc=p.oc||[];
    c24.forEach(c=>I.push(item(`<span class="pi-g ${/p[0-2]/.test(c.lv||'')?'risk':'cond'}" title="${esc(L(LV[c.lv]||[c.lv||'','']))}">${esc(c.lv||'')}</span> ${prA(c.m)} ${raw(c.t||'')} <div class="pi-why obsraw">${esc(L(c.same))}</div>`,
      c.sh.slice(0,6).map(f=>`${code(short(f))} ${ext(`${GH}/pull/${M.n}/files`,T('this PR','PR này')+' ↗')} · ${ext(`${GH}/pull/${c.m}/files`,'#'+c.m+' ↗')}`).join('<br>'))));
    const ovH=(Date.now()-Date.parse(String(D.ov_at||'').replace(' ','T')+(/(Z|[+-]\d\d:?\d\d)$/.test(D.ov_at||'')?'':'Z')))/36e5;
    if(!c24.length&&p.st!=='merged'&&!(ovH<=24)) I.push(item(unk(T(`Overlap unknown: the overlap data is ${isFinite(ovH)?Math.round(ovH/24)+' d':'of unknown age'} old.`,`Chưa biết chồng lấn: dữ liệu chồng lấn đã ${isFinite(ovH)?Math.round(ovH/24)+' ngày':'không rõ tuổi'}.`))));
    else if(!c24.length&&p.st!=='open'&&p.st!=='draft'&&p.st!=='merged') I.push(item(unk(T(`PR state ${p.st||'unknown'}: no overlap check.`,`Trạng thái PR ${p.st||'chưa rõ'}: không kiểm tra chồng lấn.`))));
    else if(!c24.length) I.push(item(p.st==='open'||p.st==='draft'?T(`No overlap with the merges of the last 24 h (window from ${D.w0||'?'}).`,`Không chồng lấn với các merge 24 giờ qua (cửa sổ từ ${D.w0||'?'}).`):T('Merged PR: the 24 h overlap check is for open PRs.','PR đã merge: kiểm tra chồng lấn 24 giờ dành cho PR mở.'),code('ops_tabs.json · overlap.groups')));
    if(oc.length) oc.forEach(c=>I.push(item(T(`Open PR ${'#'}${c.m} edits the same files`,`PR mở #${c.m} sửa cùng file`)+(c.funcs.length?T(' and the same functions ',' và cùng hàm ')+c.funcs.map(code).join(' '):''),prA(c.m)+' · '+c.files.slice(0,4).map(f=>code(short(f))).join(' '),c.funcs.length?'focus':'')));
    else I.push(item(T('Other open PRs editing the same files','PR mở khác sửa cùng file')+': '+(p.st==='open'&&p.src==='patch'?T('none among the 100 open-PR patches.','không có trong 100 patch PR mở.'):unk(p.st==='open'?T('no patch for this PR','không có patch cho PR này'):T('only open PRs are compared','chỉ so các PR mở'))),p.st==='open'&&p.src==='patch'?ext(`${GH}/pull/${M.n}/files`,T('Files','File')+' ↗'):''));
    I.push(item(T('Invariants this PR relies on','Bất biến mà PR này dựa vào')+': '+unk(T('no list of invariants in local data (cache key format, chunk size, KV layout …)','chưa có danh sách bất biến trong dữ liệu local (định dạng cache key, chunk size, KV layout …)'))));
    if(c24.some(c=>/p[0-2]/.test(c.lv||''))) C.push(T('Rebase on dev, then re-run required checks (p0–p2 overlap).','Rebase lên dev, rồi chạy lại check bắt buộc (chồng lấn p0–p2).'));
    if(c24.length) C.push(T('Does a merged PR change the meaning (default, unit, return value) of a function this PR calls or changes?','PR đã merge có đổi ý nghĩa (mặc định, đơn vị, giá trị trả về) của hàm mà PR này gọi hoặc sửa không?'));
    oc.filter(c=>c.funcs.length).slice(0,2).forEach(c=>C.push(T(`Agree the merge order with #${c.m}: both edit ${c.funcs.join(', ')}.`,`Thống nhất thứ tự merge với #${c.m}: cả hai sửa ${c.funcs.join(', ')}.`)));
    C.push(T('Name the invariant this change relies on and the test that guards it.','Nêu bất biến mà thay đổi này dựa vào và test bảo vệ nó.'));
    M.gates.filter(g=>g.req&&g.lvl===1).forEach(g=>{const st=gstate(M,g.name);GS.push(G(g.name,hotC(c24).length&&st==='ok'?'risk':'req',hotC(c24).length&&st==='ok'?T('green before overlapping merges: re-run after rebase','xanh trước các merge chồng lấn: chạy lại sau rebase'):T('required for merge','bắt buộc để merge')));});
    if(!GS.length) GS.push(...baseGates(M));
    return {I,C,G:GS};}
  const VFN=[v1,v2,v3,v4,v5];

  // ---------------------------------------------------------------- rendering
  const KIND={req:['required','bắt buộc'],cond:['conditional','có điều kiện'],risk:['at risk','có rủi ro'],adv:['advisory','tham khảo']};
  const KDESC={req:['● required: branch protection blocks the merge until it passes','● bắt buộc: branch protection chặn merge tới khi nó đạt'],cond:['◐ conditional: runs only when its paths or a label match','◐ có điều kiện: chỉ chạy khi path hoặc nhãn khớp'],
    risk:['at risk: likely to fail or out of date for this PR','có rủi ro: dễ thất bại hoặc đã cũ với PR này'],adv:['○ advisory: shown for information, does not block the merge','○ tham khảo: để biết thêm, không chặn merge']};
  function gatesTable(M,gs){const seen=new Set();gs=gs.filter(g=>{const k=g.name+g.kind;if(seen.has(k))return false;seen.add(k);return true;});
    const tipOf=name=>{const x=M.gates.find(y=>y.name===name);return x?tierTip(x):'';};
    return `<table class="pi-gt"><tbody>${gs.map(g=>`<tr><td><span class="pi-g ${g.kind}" title="${esc(L(KDESC[g.kind]))}">${esc(L(KIND[g.kind]))}</span></td><td><b class="obsraw">${esc(g.name)}</b> ${chk(gstate(M,g.name),GKEY[g.name])}</td><td class="pi-why"${tipOf(g.name)?` title="${esc(tipOf(g.name))}"`:''}>${esc(g.why||'')}</td></tr>`).join('')}</tbody></table>`;}
  function viewHtml(M,i){const r=VFN[i-1](M);
    return `<section class="pi-view" data-pi-view="${i}"><ol class="pi-items">${r.I.join('')}</ol>`+
      `<h4>${T('Reviewer checklist','Checklist cho reviewer')}</h4><ul class="pi-check">${r.C.map((c,j)=>`<li><input type="checkbox" id="piC${i}_${j}"><label for="piC${i}_${j}" class="q">${esc(c)}</label></li>`).join('')}</ul>`+
      `<h4>${T('CI gates that cover it','Các CI gate bao phủ')}</h4>${gatesTable(M,r.G)}</section>`;}
  function flowHtml(M){const g=M.gates.slice().sort((a,b)=>a.lvl-b.lvl);
    const col=(h,body)=>`<div class="pi-col"><h5>${h}</h5>${body||unk(T('no data','không có dữ liệu'))}</div>`;
    const mods=[...new Set(M.codeF.map(f=>f[0].split('/').slice(0,-1).slice(-2).join('/')))].slice(0,8);
    return `<div class="pi-flow" id="piFlow">`+
      col(T('Modules','Module'),mods.map(m=>`<span class="pi-chip obsraw" data-pn="m:${esc(m)}" tabindex="0" title="${esc(m)}">${esc(m)}</span>`).join(''))+
      col(T('Code areas','Code area'),M.areas.map(a=>`<span class="pi-chip${focus===a?' focus':''}" data-pn="a:${esc(a)}" tabindex="0" title="${esc(D.areas[a].t)}">${esc(a)}</span>`).join(''))+
      col(T('Features (F-ids, draft)','Feature (F-id, nháp)'),M.F.map(f=>`<span class="pi-chip" data-pn="f:${esc(f)}" tabindex="0" title="${esc((D.F[f]||{}).name||'')}">${esc(f)}</span>`).join(''))+
      col(T('CI gates · ● required ◐ conditional ○ advisory','CI gate · ● bắt buộc ◐ có điều kiện ○ tham khảo'),g.map(x=>{const kd=x.lvl===1&&x.req?'req':x.lvl===2?'cond':'adv';return `<span class="pi-chip" data-pn="g:${esc(x.name)}" tabindex="0" title="${esc(L(KDESC[kd])+(tierTip(x)?'\n'+tierTip(x):''))}">${kd==='req'?'● ':kd==='cond'?'◐ ':'○ '}<span class="obsraw">${esc(x.name)}</span> ${chk(gstate(M,x.name),GKEY[x.name])}</span>`;}).join(''))+`</div>`;}
  function backHtml(M){const p=M.p||{},parts=[];
    const bs=(p.b||[]).map(b=>[b,D.builds[b]||{}]);
    parts.push(item(T(`CI builds of this PR in the index (${bs.length})`,`Build CI của PR này trong index (${bs.length})`),bs.length?bs.slice(0,10).map(([b,B])=>`${ext(B.url,raw(b.slice(6))+' ↗')} ${chk(B.st)} <span class="pi-why">${esc(B.sha||'')}</span>${(B.sig||[]).map(s=>` <button type="button" class="pi-btn" data-pi="bug:${esc(s)}">${raw((D.bugs[s]||{}).t||s)}</button>`).join('')}`).join('<br>'):unk(T('no build of this PR in the entity index','không có build của PR này trong entity index'))));
    const fixes=Object.entries(D.bugs).filter(([s,b])=>(b.fx||[]).includes(String(M.n)));
    if(fixes.length) parts.push(item(T('This PR fixes these failure signatures','PR này sửa các signature lỗi này'),fixes.map(([s,b])=>`<button type="button" class="pi-btn" data-pi="bug:${esc(s)}">${raw(b.t)}</button>`).join(' ')));
    const regs=D.reg.map((r,i)=>[r,i]).filter(([r])=>r.prs.includes(+M.n));
    parts.push(item(regs.length?T('This PR is inside the commit range of a dev regression','PR này nằm trong khoảng commit của một regression trên dev'):T('Not inside any dev regression range found locally.','Không nằm trong khoảng regression dev nào tìm được ở local.'),
      regs.length?regs.map(([r,i])=>`<button type="button" class="pi-btn" data-pi="reg:${i}">${raw(r.pipe)} #${esc(r.green.num)} → #${esc(r.red.num)}</button>`).join(' '):code('ops.db bk_build (dev) + git log')));
    const rt=p.rt||[];
    if(rt.length) parts.push(item(T(`Retries of this PR (${rt.length})`,`Lần chạy lại của PR này (${rt.length})`),rt.slice(0,6).map(r=>`${ext(r[4],raw(r[0]+' · '+r[1]))} <span class="obsraw">${esc(r[2])}: ${esc((r[3]||'').slice(0,80))}</span>`).join('<br>')));
    return `<ol class="pi-items">${parts.join('')}</ol>`+startHtml();}
  function startHtml(){const top=Object.entries(D.bugs).sort((a,b)=>(b[1].n||0)-(a[1].n||0)).slice(0,8);
    return `<h4>${T('Start from a failure','Bắt đầu từ một lỗi')}</h4><div class="pi-start">${D.reg.map((r,i)=>`<button type="button" class="pi-btn" data-pi="reg:${i}">${T('dev red','dev đỏ')}: ${raw(r.pipe)} #${esc(r.red.num)}</button>`).join('')}</div>`+
      `<div class="pi-start">${top.map(([s,b])=>`<button type="button" class="pi-btn" data-pi="bug:${esc(s)}">${raw(b.t)} <span class="pi-why">${esc(b.n||'')}</span></button>`).join('')}</div>`;}
  const suspect=(n,why)=>{const M=model(n);const fn=[...new Set(M.codeF.flatMap(f=>f[4]))].slice(0,5);
    return item(`${prA(n)} ${raw((M.p||{}).t||'')} <span class="pi-why">${esc(why||'')}</span>`,
      `${T('commit','commit')} ${code((M.p||{}).sha||'?')} · ${T('features','feature')}: ${M.areas.length?M.areas.map(a=>entA('feature:'+a,raw(a))).join(' '):unk(T('no code area','không có code area'))} · ${T('logic','logic')}: ${fn.length?fn.map(code).join(' '):unk(T('no edited function in local data','không có hàm bị sửa trong dữ liệu local'))}`);};
  function bugHtml(sig){const b=D.bugs[sig];if(!b)return `<p>${unk(T('signature not in the local index','signature không có trong index local'))}</p>`;
    const prs=new Map();(b.b||[]).forEach(k=>{const B=D.builds[k]||{};(B.pr||[]).forEach(n=>{if(!prs.has(n))prs.set(n,[]);prs.get(n).push(k);});});
    return `<div class="pi-hd" style="padding:0 0 10px;border:0"><h3 id="piTitle">${T('Failure signature','Signature lỗi')}: ${raw(b.t)}</h3><div class="pi-meta"><span>${T('class','loại')} ${raw(b.cls||'?')}</span><span>${esc(b.n||0)} ${T('jobs in 30 days','job trong 30 ngày')}</span><span class="obsraw">${esc(b.line||'')}</span></div></div>`+
      `<h4>${T('Failing gate → builds','Gate fail → build')}</h4><ol class="pi-items">${(b.b||[]).slice(0,10).map(k=>{const B=D.builds[k]||{};return item(`${ext(B.url,raw(k.slice(6))+' ↗')} <span class="pi-why">${esc(B.at||'')} · ${raw(B.br||'')}</span>`,`${T('commit','commit')} ${code(B.sha||'?')} · PR ${(B.pr||[]).map(prA).join(' ')||unk(T('no PR (dev or nightly build)','không có PR (build dev hoặc nightly)'))}`);}).join('')||item(unk(T('no build','không có build')))}</ol>`+
      `<h4>${T('→ PR, commit, feature, logic (suspects)','→ PR, commit, feature, logic (nghi vấn)')}</h4><ol class="pi-items">${[...prs.entries()].slice(0,10).map(([n,ks])=>suspect(n,T(`${ks.length} failing build(s)`,`${ks.length} build fail`))).join('')||item(unk(T('no PR build carries this signature','không có build PR nào mang signature này')))}</ol>`+
      `<h4>${T('Tests and fixes','Test và bản sửa')}</h4><ol class="pi-items">${item(T('Tests that fail with it','Test fail với nó'),(b.te||[]).map(t=>entA(t,code(short(t.slice(5))))).join(' ')||unk(T('no test linked','chưa nối test nào')))}${item(T('Fixed by','Được sửa bởi'),(b.fx||[]).map(prA).join(' ')||unk(T('no fixing PR found (closing issue link)','không tìm thấy PR sửa (liên kết closing issue)')))}</ol>`;}
  function regHtml(i){const r=D.reg[i];if(!r)return '';
    return `<div class="pi-hd" style="padding:0 0 10px;border:0"><h3 id="piTitle">${T('Dev regression','Regression trên dev')}: ${raw(r.pipe)}</h3><div class="pi-meta">${ext(r.green.url,T('last green','xanh cuối')+' #'+esc(r.green.num)+' ↗')} ${code(r.green.sha)} → ${ext(r.red.url,T('first red','đỏ đầu')+' #'+esc(r.red.num)+' ↗')} ${code(r.red.sha)} <span>${esc((r.red.at||'').replace('T',' ').slice(0,16))}</span></div>`+
      ((r.green.approx||r.red.approx)?`<div class="pi-why">${T('Approximate range: ops.db has no commit for these dev builds, so the dev commit just before each build was created is used (local clone).','Khoảng ước lượng: ops.db không có commit cho các build dev này nên dùng commit dev ngay trước lúc tạo build (clone local).')}</div>`:'')+`</div>`+
      `<h4>${T(`Commits in the range (${r.commits.length})`,`Commit trong khoảng (${r.commits.length})`)}</h4><ol class="pi-items">${!r.commits.length&&r.why?item(unk(esc(r.why))):r.commits.length?r.commits.map(c=>{const m=(c[1].match(/\(#(\d+)\)/)||[])[1];return m?suspect(m,c[0]):item(`${code(c[0])} ${raw(c[1])}`,unk(T('no PR number in the commit subject','không có số PR trong tiêu đề commit')));}).join(''):item(unk(T('same commit or not in the local clone: the failure may be flaky or infrastructure','cùng commit hoặc không có trong clone local: lỗi có thể do flaky hoặc hạ tầng')))}</ol>`;}

  function setHash(){if(!cur)return;let h=null;
    if(cur.startsWith('pr:'))h='#e/pr/'+cur.slice(3)+(dir==='back'?'/back':view>1?'/v'+view:'');else if(cur.startsWith('doc:'))h='#e/doc/'+cur.slice(4);
    if(h&&location.hash!==h)history.replaceState(null,'',h);}
  function render(){const k=cur;if(!k)return;
    let h='';
    if(k.startsWith('doc:')) h=`<div class="pi-hd"><div class="pi-row"><span class="pi-why" style="flex:1">${T('Knowledge base · RFC / FRS','Knowledge base · RFC / FRS')}</span><button type="button" class="pi-x" data-pi-close aria-label="${T('Close','Đóng')}">✕</button></div><div class="pi-bar"></div></div><div class="pi-body" id="piBody">${window.PIKB?PIKB.docHtml(k.slice(4)):''}</div>`;
    else if(k.startsWith('bug:')) h=`<div class="pi-hd"><div class="pi-row"><span class="pi-why" style="flex:1">${T('Backward · failure → PR, commit, feature, logic','Ngược · lỗi → PR, commit, feature, logic')}</span><button type="button" class="pi-x" data-pi-close aria-label="${T('Close','Đóng')}">✕</button></div></div><div class="pi-body">${bugHtml(k.slice(4))}${startHtml()}${srcHtml()}</div>`;
    else if(k.startsWith('reg:')) h=`<div class="pi-hd"><div class="pi-row"><span class="pi-why" style="flex:1">${T('Backward · dev regression → PR, commit, feature, logic','Ngược · regression dev → PR, commit, feature, logic')}</span><button type="button" class="pi-x" data-pi-close aria-label="${T('Close','Đóng')}">✕</button></div></div><div class="pi-body">${regHtml(+k.slice(4))}${startHtml()}${srcHtml()}</div>`;
    else{const n=k.slice(3),M=model(n),p=M.p||{};
      const rv=p.rv?`<span>${T('queue','hàng đợi')}: <b title="${esc(p.rv.sub)}" data-q="${esc(p.rv.sub)}">${esc(L(QW[p.rv.sub]||[p.rv.sub,p.rv.sub]))}</b></span>`:'';
      // review P0-4: "title not in snapshot" when the PR is indexed without a title; "not in the local index" only when it is absent
      const ttl=p.t?raw(p.t):`<span class="pi-why">${M.p?T('title not in snapshot','không có tiêu đề trong snapshot'):T('not in the local index','không có trong index local')}</span>`;
      const noSt=M.p?`<span class="pi-st closed" title="${T('the PR is in the local index, but no state was recorded','PR có trong index local nhưng không ghi trạng thái')}">${T('state missing','thiếu trạng thái')}</span>`:`<span class="pi-st closed">${T('absent from the index','không có trong index')}</span>`;
      h=`<div class="pi-hd"><div class="pi-why">${T('PR check','Kiểm tra PR')}</div><div class="pi-row"><h3 id="piTitle">#${esc(n)} ${ttl}</h3><button type="button" class="pi-x" data-pi-close aria-label="${T('Close','Đóng')}">✕</button></div>`+
        `<div class="pi-meta">${p.st?((p.st==='open'||p.st==='draft')&&(p.rel||[]).length?`<span class="pi-st merged" title="${T('a release contains it','một release chứa nó')}">merged</span><span class="pi-why">${T(`in ${p.rel.join(', ')}; the PR snapshot of ${(D.snap_at||'?').slice(0,10)} still said ${p.st}`,`có trong ${p.rel.join(', ')}; snapshot PR ngày ${(D.snap_at||'?').slice(0,10)} vẫn ghi ${p.st}`)}</span>`:`<span class="pi-st ${esc(p.st)}" title="${T('state in the PR snapshot','trạng thái trong snapshot PR')}">${esc(p.st)}</span><span class="pi-why">${T('as of','tính đến')} ${esc((D.snap_at||'?').slice(0,10))}</span>`):noSt}${p.au?`<span>${T('author','tác giả')} ${raw(p.au)}</span>`:''}${p.sha?`<span>${code(p.sha)}</span>`:''}${(p.rel||[]).length?`<span>${T('shipped in','phát hành trong')} ${p.rel.map(r=>entA('release:'+r,raw(r))).join(' ')}</span>`:''}${(p.lab||[]).length?`<span class="obsraw">${esc(p.lab.join(', '))}</span>`:''}${rv}`+
        `<span>${ext(`${GH}/pull/${n}`,'GitHub ↗')} ${ext(`${GH}/pull/${n}/files`,T('Files','File')+' ↗')} ${ext(`${GH}/pull/${n}/checks`,'Checks ↗')}</span></div>`+
        `<div class="pi-bar"><div class="pi-seg" role="tablist" aria-label="${T('Direction','Chiều')}"><button type="button" role="tab" data-pi-dir="fwd" aria-selected="${dir==='fwd'}">${T('Impact of this PR','Ảnh hưởng của PR')}</button><button type="button" role="tab" data-pi-dir="back" aria-selected="${dir==='back'}">${T('Failures → cause','Lỗi → nguyên nhân')}</button></div>`+
        (window.openPrMap?`<button type="button" class="pi-btn" data-pi-map="${esc(n)}">${T('PR map','PR map')} ↗</button>`:'')+`</div></div>`;
      let body='';
      if(dir==='back') body=backHtml(M);
      else body=flowHtml(M)+`<div class="pi-seg pi-tabs" role="tablist" aria-label="${T('Views','Góc nhìn')}">${VIEWS.map((v,i)=>`<button type="button" role="tab" data-pi-v="${i+1}" aria-selected="${view===i+1}">${i+1} · ${esc(L(v))}</button>`).join('')}</div>`+viewHtml(M,view);
      h+=`<div class="pi-body" id="piBody">${body}${srcHtml(M)}</div>`;}
    dr.innerHTML=h;setHash();
    dispatchEvent(new CustomEvent('pirender',{detail:{key:cur,dir,view,focus}}));}   // phase B (pr_inspector_seq.py) adds flow animation + sequence diagrams
  function srcHtml(M){const s=M&&M.p?({patch:T('patch of the open PR (overlap_patches.json)','patch của PR mở (overlap_patches.json)'),git:T('merge commit diff from the local clone','diff của merge commit từ clone local')}[M.p.src]||T('no file list','không có danh sách file')):'';
    return `<div class="pi-src">${T('Local data only','Chỉ dữ liệu local')}: ${T('built','dựng lúc')} ${esc(D.made)} UTC · ${T('entities','entities')} ${esc(D.snap_at||'?')} · ${T('patches','patch')} ${esc((D.patches_at||'?').slice(0,16))} · ${T('clone','clone')} ${code((D.head||'?').slice(0,8))}${s?' · '+T('files from','file lấy từ')+' '+s:''}. ${T('F map is a draft (next_release.py AREA_F).','Map F là bản nháp (next_release.py AREA_F).')}</div>`;}

  // ---------------------------------------------------------------- open / close / events
  const WS=window.WSTACK||(window.WSTACK=(function(){const S=[];const z=()=>S.forEach((x,i)=>{x.el.style.zIndex=String(80+i);});const drop=el=>{const i=S.findIndex(x=>x.el===el);if(i>=0)S.splice(i,1);};const live=()=>{for(let i=S.length-1;i>=0;i--){if(S[i].el.isConnected&&S[i].on())return S[i];S.splice(i,1);}return null;};addEventListener('keydown',e=>{if(e.key!=='Escape'||e.defaultPrevented)return;const t=e.target;if(t&&t.closest&&t.closest('input,textarea,select'))return;const top=live();if(!top)return;e.preventDefault();e.stopImmediatePropagation();top.close();},true);return{push(el,close,on){drop(el);S.push({el,close,on:on||(()=>el.classList.contains('on'))});el.inert=false;z();},pop(el){drop(el);el.style.zIndex='';z();},top(){const t=live();return t&&t.el;},has(el){return S.some(x=>x.el===el);}};})());
  function open(k,o){o=o||{};
    const sm=String(k).match(/^(pr:\d+)\/(v[1-5]|back|docs)$/);   // deep link of a state: #e/pr/N/v3, /back, /docs (UX round 1)
    if(sm){k=sm[1];if(sm[2]==='back')o.dir='back';else if(sm[2]==='docs')o.docs=true;else o.view=+sm[2].slice(1);}
    if(/^pr:\d+$/.test(k)){}else if(/^bug:/.test(k)){if(!D.bugs[k.slice(4)])return false;}else if(/^reg:\d+$/.test(k)){if(!D.reg[+k.slice(4)])return false;}
    else if(/^doc:/.test(k)){if(!window.PIKB||!PIKB.docs[k.slice(4)])return false;}else return false;
    if(!dr.classList.contains('on'))opener=document.activeElement;
    cur=k;dir=o.dir||(k.startsWith('pr:')?'fwd':'back');view=o.view||1;focus=o.focus||null;
    render();dr.classList.add('on');dr.setAttribute('aria-hidden','false');WS.push(dr,close);
    const x=dr.querySelector('[data-pi-close]');if(x)x.focus({preventScroll:true});
    if(focus){const f=dr.querySelector('.pi-items>li.focus');if(f)f.scrollIntoView({block:'nearest'});}
    if(o.docs){const b=dr.querySelector('[data-kbopen]');if(b)b.click();}
    dispatchEvent(new CustomEvent('piopen',{detail:{key:k,dir,view}}));return true;}
  function close(){if(!dr.classList.contains('on'))return;dr.classList.remove('on');dr.setAttribute('aria-hidden','true');WS.pop(dr);cur=null;dispatchEvent(new Event('piclose'));
    const s=window.vizNav&&vizNav.state;if(s&&/^#e\/(pr|doc)\//.test(location.hash))history.replaceState(null,'','#'+s.v+'/'+s.t);
    if(opener&&opener.isConnected&&opener.focus)opener.focus({preventScroll:true});opener=null;}
  dr.addEventListener('click',e=>{
    if(e.target.closest('[data-pi-close]'))return close();
    const d=e.target.closest('[data-pi-dir]');if(d){dir=d.dataset.piDir;render();return;}
    const v=e.target.closest('[data-pi-v]');if(v){view=+v.dataset.piV;render();dispatchEvent(new CustomEvent('piopen',{detail:{key:cur,dir,view}}));const b=dr.querySelector(`[data-pi-v="${view}"]`);if(b)b.focus();return;}
    const m=e.target.closest('[data-pi-map]');if(m&&window.openPrMap){openPrMap(m.dataset.piMap);return;}
    if(e.target.closest('[data-goto]'))close();
  });
  // any [data-pi] anywhere; a feature chip in a row that names exactly one PR opens that PR focused on the feature (PR.feature)
  window.addEventListener('click',e=>{   // window capture: runs before the entity card's document handler
    if(e.ctrlKey||e.metaKey||e.shiftKey||e.button)return;
    const a=e.target.closest&&e.target.closest('[data-pi]');
    if(a){e.preventDefault();e.stopPropagation();open(a.dataset.pi,{view:+a.dataset.piView||undefined,dir:a.dataset.piDir});return;}
    if(e.target.closest&&e.target.closest('#piDrawer,#entDrawer,.ent-drawer,#pmOv'))return;
    const f=e.target.closest&&e.target.closest('[data-ent^="feature:"]');if(!f)return;
    const row=f.closest('tr,li,.tdy-row');if(!row)return;
    const ps=[...new Set([...row.querySelectorAll('[data-ent^="pr:"]')].map(x=>x.dataset.ent))];
    if(ps.length===1){e.preventDefault();e.stopPropagation();open(ps[0],{view:1,focus:f.dataset.ent.slice(8)});}
  },true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&dr.classList.contains('on')&&WS.top()===dr)close();});   // fallback; WSTACK closes the top window first
  addEventListener('langchange',()=>{if(cur)render();});
  window.piOpen=open;window.piClose=close;window.PI={open,close,model,data:D,views:VIEWS,stateNorm,stateWord,gstates,gkey:GKEY,queueWord:q=>L(QW[q]||[q,q]),levelWord:l=>L(LV[l]||[l,l])};
  // a shared #e/pr/N link: the entity card may have opened before this script; the Inspector is the PR view now
  window.PI.check=(M,i)=>VFN[i-1](M).C;   // checklist of a view (UX: "check first" in the merge verdict)
  {const m=location.hash.match(/^#e\/(pr\/\d+(?:\/(?:v[1-5]|back|docs))?|doc\/.+)$/);if(m){if(window.closeEntity)closeEntity();setTimeout(()=>open(m[1].replace('/',':')),0);}}
})();
</script>
<!-- PI:JS:END -->
"""
