<script>
/* Next release cockpit: sections 3A–3E of the "Next release" tab (data: opsData.coming.nr, built by next_release.py).
   3A cockpit (runbook phase + what to decide / do) is the main flow; 3B–3E are the evidence it links to. */
(function(){
  let OD=null;try{OD=JSON.parse(document.getElementById('opsData').textContent);}catch(e){return;}
  const N=(OD.coming||{}).nr;
  const V=()=>(window.I18N&&I18N.lang==='vi')?1:0, T=(en,vi)=>V()?vi:en;
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const sec=k=>document.querySelector(`section[data-ops="${k}"]`);
  const head=(n,en,vi,sen,svi)=>`<div class="head"><h2>${n} · ${esc(T(en,vi))}</h2>${sen?`<p class="sub">${T(sen,svi)}</p>`:''}</div>`;
  if(!N||N.error){const s=sec('nr-ck');if(s)s.innerHTML=head('3A','Release cockpit','Release cockpit')+`<div class="ops-empty">${esc(N?N.error:T('No data: run build_ops_tabs.py with the local clone and the ROADMAP of the next release.','Chưa có dữ liệu: chạy build_ops_tabs.py với clone local và ROADMAP của release tới.'))}</div>`;
    ['nr-scope','nr-cp','nr-fm','nr-cut'].forEach(k=>{const x=sec(k);if(x)x.remove();});return;}
  const J=id=>{try{return JSON.parse(document.getElementById(id).textContent);}catch(e){return null;}};
  const CPU=J('cpuData')||{areas:[]}, GD=J('gatesData')||{tiers:[],classes:[],tier_workloads:{},area_class:{}};
  const GH=n=>`https://github.com/LMCache/LMCache/pull/${n}`;
  const RANK={none:0,ok:1,ch:1,warn:2,bad:3}, worst=a=>a.reduce((x,y)=>RANK[y]>RANK[x]?y:x,'ok');
  const CHIP={ok:'s-ok',warn:'s-run',bad:'s-fail',none:'s-none'};

  /* Feature matrix rows (same numbering as Release Exploration -> CPU tests -> 3 · Feature matrix) */
  const FM={};{let last=null,gi=0,ii=0;CPU.areas.forEach(a=>{if(a.group!==last){last=a.group;gi++;ii=0;}FM[a.id]=Object.assign({},a,{code_path:a.code,code:`${gi}.${++ii}`,vllm_import:(a.sm||{})['vLLM import']||0});});}
  const AN=a=>a?((FM[a]||{}).name||((OD.coming||{}).area_names||{})[a]||a):T('Internal','Nội bộ');
  const TIER=Object.fromEntries((GD.tiers||[]).map(t=>[t.id,t]));
  const CT=Object.fromEntries((GD.classes||[]).map(c=>[c.id,c.tiers]));
  const tiersOf=a=>{const t=CT[(GD.area_class||{})[a]||'core']||{};return{req:Object.keys(t).filter(k=>t[k]===1),cond:Object.keys(t).filter(k=>t[k]===2)};};
  const wlOf=a=>{const{req,cond}=tiersOf(a),w=[];[...req,...cond].forEach(t=>((GD.tier_workloads||{})[t]||[]).forEach(x=>{if(!w.includes(x))w.push(x);}));return w;};

  /* stages of the request path (flow of build_ops_tabs.py) and who breaks */
  const FLOW=(OD.coming||{}).flow||[];
  const IMPACT=[[3,'Every request: vLLM / SGLang cannot reach LMCache, or gets wrong KV','Mọi request: vLLM / SGLang không gọi được LMCache, hoặc nhận về KV sai'],
    [3,'Every request through the MP server (ZMQ / gRPC / HTTP)','Mọi request đi qua MP server (ZMQ / gRPC / HTTP)'],
    [3,'Every lookup: a wrong hit means wrong output','Mọi lookup: cache hit sai thì output cũng sai'],
    [3,'Every store / retrieve; bugs here corrupt KV silently','Mọi store / retrieve; bug ở đây làm hỏng KV mà không báo lỗi'],
    [2,'Users with CPU offload (L1)','Người dùng bật CPU offload (L1)'],
    [1,'Only users of that L2 / P2P / GDS adapter','Chỉ người dùng bật đúng adapter L2 / P2P / GDS đó']];
  const stageTxt=s=>s==null?T('Off the request path: only users of that feature.','Ngoài đường đi request: chỉ người dùng tính năng đó.'):`B${s} · ${esc(((FLOW[s]||{}).name||[])[V()]||'')}: ${esc(IMPACT[s][1+V()])}.`;

  const SCOPE=new Set(N.items.flatMap(i=>i.prs)), PR=Object.fromEntries(N.prs.map(p=>[p.num,p]));
  const MIN_CUT=Math.max(...[...SCOPE].map(n=>PR[n]?PR[n].i:-1)), HEAD_CUT=N.prs.length-1;
  let cut=MIN_CUT,pick=null,selArea=null,rideLimit=10,ckPhase=1,cpJ='A',cpMode='scope',cpBug=null,cpNode=null;
  const CODE_T=new Set(['bug','feature','perf','refactor','other']);
  const weight=p=>p.stage!=null?IMPACT[p.stage][0]:(p.area==='build'?2:1);
  const mpReq=p=>[...p.cpu_tiers,...p.gpu_tiers].some(t=>['L2','CE','AO','FULL'].includes(t));
  const mpTxt=p=>p.mp_ci==='ran'?T('ran','đã chạy'):p.mp_ci==='skip'?'skip':T('unknown','không rõ');

  /* risk of a PR outside the scope that ships because it is before the cut */
  const calcRide=()=>N.prs.forEach(p=>{const why=[],code=CODE_T.has(p.type)&&!['docs','tests'].includes(p.risk),w=weight(p);
    if(p.breaking)why.push(['bad',T('Breaking: users must change setup or flags; not in scope or notes','Breaking: người dùng phải đổi cài đặt hoặc flag; chưa có trong scope và note')]);
    if(code&&w===3&&p.mp_ci!=='ran'&&mpReq(p))why.push(['bad',T(`Changes code at stage ${p.stage} and ${p.mp_ci==='skip'?'skipped MP CI on the PR':'MP CI on the PR is unknown'}`,`Đổi code ở bước ${p.stage} và ${p.mp_ci==='skip'?'đã skip MP CI ở PR':'không rõ đã chạy MP CI chưa'}`)]);
    else if(code&&w===3)why.push(['warn',T(`Changes code at stage ${p.stage}: every request`,`Đổi code ở bước ${p.stage}: ảnh hưởng mọi request`)]);
    else if(code&&w===2)why.push(['warn',p.stage===4?T('Changes L1 memory code','Đổi code ở L1 memory'):T('Changes build / packaging: everyone who installs','Đổi build / packaging: ảnh hưởng mọi người cài đặt')]);
    p.ride={lvl:why.length?worst(why.map(x=>x[0])):'ok',why};});
  calcRide();

  function itemRow(it){const ps=it.prs.map(n=>PR[n]).filter(Boolean),st=Math.min(...ps.map(p=>p.stage==null?99:p.stage)),r=[];
    ps.filter(p=>p.i>cut).forEach(p=>r.push(['bad',T(`#${p.num} is after the cut: cherry-pick it`,`#${p.num} nằm sau điểm cắt: phải cherry-pick`)]));
    ps.filter(p=>p.breaking).forEach(p=>r.push(['bad',T(`#${p.num} is breaking but listed under '${it.section}': move it to 'Breaking changes'`,`#${p.num} breaking nhưng nằm ở mục '${it.section}': chuyển lên 'Breaking changes'`)]));
    ps.filter(p=>p.mp_ci==='skip'&&mpReq(p)).forEach(p=>r.push(['warn',T(`#${p.num} skipped MP CI on the PR`,`#${p.num} skip MP CI ở PR`)]));
    ps.filter(p=>p.mp_ci==null&&mpReq(p)).forEach(p=>r.push(['warn',T(`#${p.num}: MP CI on the PR unknown`,`#${p.num}: không rõ đã chạy MP CI chưa`)]));
    ps.forEach(p=>{const a=FM[p.area];if(a&&a.notrun)r.push(['warn',T(`${a.code} ${a.name}: ${a.notrun} test files do not run on CPU`,`${a.code} ${a.name}: ${a.notrun} test file không chạy trên CPU`)]);});
    const seen=new Set(),rs=r.filter(x=>!seen.has(x[1])&&seen.add(x[1]));
    return{it,ps,stage:st===99?null:st,reasons:rs,lvl:rs.length?worst(rs.map(x=>x[0])):'ok'};}

  /* ---------- critical path model (xlsx) ---------- */
  const CP=N.cp, FF=CP?Object.fromEntries(CP.features.map(f=>[f.id,f])):{};
  function fOfPR(p){const o={},wide=Object.keys(p.a_src).length>=8;Object.keys(p.a_src).forEach(a=>{if(wide&&a!==p.area)return;((CP||{}).area_f[a]||[]).forEach(f=>{const mk=a===p.area?'●':'○';if(o[f]!=='●')o[f]=mk;});});return o;}
  function fTouch(prs){const t={};prs.forEach(p=>Object.entries(fOfPR(p)).forEach(([f,mk])=>{const r=t[f]||(t[f]={scope:[],ride:[]});(SCOPE.has(p.num)?r.scope:r.ride).push({p,mk});}));return t;}
  function fLevel(r){if(!r)return null;const all=[...r.scope,...r.ride];if(all.some(x=>x.mk==='●'&&x.p.breaking)||r.ride.some(x=>x.p.ride.lvl==='bad'))return'bad';if(all.some(x=>x.p.mp_ci==='skip'&&mpReq(x.p)))return'warn';return'ch';}
  const shipping=()=>N.prs.filter(p=>p.i<=cut);
  const pickedPRs=()=>pick===null?shipping():pick==='ride'?shipping().filter(p=>!SCOPE.has(p.num)&&p.ride.lvl==='bad'):N.items[pick].prs.map(n=>PR[n]).filter(Boolean);
  const nodesOfPR=p=>{const fs=Object.keys(fOfPR(p)),o=[];(CP?CP.journeys:[]).forEach(j=>CP.node_f[j.id].forEach((nf,i)=>{if(nf.some(f=>fs.includes(f)))o.push(`${j.id}:${j.steps[i]}`);}));return o;};

  const tierChip=(id,cond)=>{const t=TIER[id]||{short:id,plain:['',''],exists:['no','','']};const real=t.exists[0]==='yes';
    return `<span class="nr-tier${cond?' cond':''}${real?'':' prop'}" data-tier="${esc(id)}" data-cond="${cond?1:0}">${esc(id)}</span>`;};
  const mkLink=(x,area)=>`<span class="nr-mk"><span class="nr-mkm" data-mk="${x.mk}" data-pr="${x.p.num}" data-aref="${area||''}">${x.mk}</span><a href="${GH(x.p.num)}" target="_blank" rel="noopener" title="${esc(x.p.title)}">#${x.p.num}</a>${x.p.mp_ci==='skip'&&mpReq(x.p)?'<span class="nr-warn" title="skip MP CI">!</span>':''}</span>`;
  const evb=(id,en,vi,extra)=>`<button class="nr-ev" data-goto="${id}" ${extra||''} type="button">${esc(T(en,vi))} ↓</button>`;

  /* ================= 3A · cockpit ================= */
  const PREP=N.prep||[], PH=[[0,'Daily check','Daily check','daily_release_check.sh'],[1,'Prepare','Chuẩn bị',T('decisions, blockers, scope','quyết định, blocker, scope')],[2,'Cut rc1','Cắt rc1','gh release create'],
    [3,'Verify rc','Verify rc','gate G1–G8'],[4,'Go / No-Go','Go / No-Go',T('T-1, 13-item checklist','T-1, checklist 13 mục')],[5,'Ship stable','Ship stable','T'],[6,'Watch','Theo dõi','T+1 → T+7']];
  function p1Items(){const it=[],prep=N.prep_rel||'RELEASE_PREP.md',rmp=N.roadmap.rel||'ROADMAP.md';
    PREP.filter(r=>r.id[0]==='D').forEach(r=>{const done=/^(decided|done|xong|đã)/i.test(r.cols[3]||'');
      it.push({g:T('Release Lead decisions','Quyết định của Release Lead'),lvl:done?'ok':'bad',id:r.id,raw:1,title:r.cols[0],owner:'Release Lead',
        body:`<b>${T('Options','Lựa chọn')}:</b> <span class="obsraw">${esc(r.cols[1]||'')}</span>${r.cols[2]?`<br><span class="nr-mute obsraw">${esc(r.cols[2])}</span>`:''}`,
        ev:r.id==='D3'?evb('nr-scope','Scope: #6254','Scope: #6254')+evb('nr-cp','Critical path','Critical path','data-pick="'+N.items.findIndex(i=>i.prs.includes(6254))+'"'):'',
        rec:T(`Write the choice in <code>${esc(prep)}</code> (section 2), then re-run the generator`,`Ghi lựa chọn vào <code>${esc(prep)}</code> (mục 2), rồi chạy lại generator`)});});
    N.items.map(itemRow).filter(r=>r.lvl==='bad').forEach(r=>r.reasons.filter(x=>x[0]==='bad').forEach(x=>it.push({g:T('Fix scope and release notes','Sửa scope và release note'),lvl:'bad',
      id:r.ps.map(p=>'#'+p.num).join(' '),raw:1,title:r.it.text,owner:'Release Lead',body:esc(x[1]),ev:evb('nr-scope','Scope','Scope'),rec:T(`Edit <code>${esc(rmp)}</code>`,`Sửa <code>${esc(rmp)}</code>`)})));
    const ride=N.prs.filter(p=>p.i<=cut&&!SCOPE.has(p.num)),G3=T('Risky PRs that ship with the rc: keep or revert before the cut','PR đi kèm rủi ro cao: giữ hay revert trước khi cắt');
    ride.filter(p=>p.ride.lvl==='bad').forEach(p=>{const nd=nodesOfPR(p);it.push({g:G3,lvl:'bad',id:'#'+p.num,raw:1,title:p.title,owner:T('Release Lead + PR author','Release Lead + tác giả PR'),
      body:`${p.ride.why.map(w=>esc(w[1])).join('. ')}.${nd.length?`<br><b>${T('Changed nodes','Node bị đổi')}:</b> <span class="obsraw">${esc(nd.slice(0,4).join(', '))}${nd.length>4?'…':''}</span>`:''}<br><b>${T('Choose','Chọn')}:</b> ${T('(a) keep: add to the ROADMAP and run full MP CI on the rc · (b) revert before the cut','(a) giữ: thêm vào ROADMAP và chạy MP CI đầy đủ trên rc · (b) revert trước khi cắt')}`,
      ev:evb('nr-cut','Cut point','Điểm cắt')+evb('nr-cp','Critical path','Critical path','data-pick="ride"'),rec:T(`<code>${esc(rmp)}</code> (Should add / Internal) or a revert PR`,`<code>${esc(rmp)}</code> (Should add / Internal) hoặc PR revert`)});});
    const rw=ride.filter(p=>p.ride.lvl==='warn');
    if(rw.length)it.push({g:G3,lvl:'warn',id:`${rw.length} PR`,title:T('Other PRs that ship on the hot path / build','PR đi kèm khác trên hot path / build'),owner:'Release Lead',
      body:T('Add to the notes or mark internal: ','Ghi vào release note hoặc đánh dấu nội bộ: ')+rw.map(p=>`<a href="${GH(p.num)}" target="_blank" rel="noopener">#${p.num}</a>`).join(' '),ev:evb('nr-cut','Cut point','Điểm cắt'),rec:`<code>${esc(rmp)}</code>`});
    PREP.filter(r=>r.id[0]==='C').forEach(r=>{const done=/^(merged|done|fixed|xong|đã)/i.test(r.cols[2]||'');
      it.push({g:T('Carry-over blockers from the last release (merge before the cut)','Blocker mang từ bản trước (merge trước khi cắt)'),lvl:done?'ok':'warn',id:r.id,raw:1,title:r.cols[0],owner:'Release Signal',
        body:`<b>${T('Fix','Sửa')}:</b> <span class="obsraw">${esc(r.cols[1]||'')}</span><br><b>${T('Now','Hiện tại')}:</b> <span class="obsraw">${esc(r.cols[2]||'')}</span>`,ev:'',rec:T("PR with label <code>full</code>, CI green","PR có nhãn <code>full</code>, CI xanh")});});
    return it;}
  function p3Items(){const t=fTouch(N.items.flatMap(i=>i.prs).map(n=>PR[n]).filter(Boolean)),nd=[];
    (CP?CP.journeys:[]).forEach(j=>CP.node_f[j.id].forEach((nf,i)=>{const fs=nf.filter(f=>t[f]);if(fs.length)nd.push(`${j.id}:${j.steps[i]} (${fs.join(' ')})`);}));
    return[{lvl:'none',id:'G1',title:T('Versions and all 3 packages present','Version và đủ 3 package'),owner:'Release Signal',body:'verify_release_versions.py',ev:'',rec:'Runbook Phase 3'},
      {lvl:'none',id:'G3–G5',title:T('Images build and smoke on both arches; native code loads; Python 3.10 / 3.12 / 3.14','Image build và smoke trên 2 arch; load native code; Python 3.10 / 3.12 / 3.14'),owner:'Release Signal',body:T('Needs C1 (pinned images) and C4 (smoke loads native code)','Cần C1 (pin image) và C4 (smoke load native code)'),ev:'',rec:'Runbook Phase 3'},
      {lvl:'bad',id:'G6',title:T('GPU CI green on the rc commit with the FULL k3-multiprocess-test (no skip label)','GPU CI xanh trên commit rc, chạy ĐỦ k3-multiprocess-test (không nhãn skip)'),owner:'Release Signal',
        body:T(`dev has not run the MP workloads since 10-28 (only the scheduled engine-nightly check; checked on Buildkite 2026-11-12), so this is the only integration proof. Critical nodes the scope changes: ${esc(nd.join(' · '))}`,`dev không chạy MP workload từ 10-28 (chỉ còn build định kỳ verify engine nightly; kiểm trên Buildkite 2026-11-12), nên đây là bằng chứng tích hợp duy nhất. Node critical mà scope đổi: ${esc(nd.join(' · '))}`),
        ev:evb('nr-cp','Critical path','Critical path')+evb('nr-fm','Tests per feature','Test theo feature'),rec:T('Buildkite link in the tracker issue','Link Buildkite vào tracker issue')},
      {lvl:'none',id:'G7',title:T('Controllers RC green','Controllers RC xanh'),owner:'Release Signal',body:'Coordinator / Kafka (F09)',ev:'',rec:'Runbook Phase 3'},
      {lvl:'none',id:'G8',title:T('XPU wheel imports in a clean env','XPU wheel import trong môi trường sạch'),owner:'Intel contact',body:'C6 / #6281',ev:'',rec:'Runbook Phase 3'}];}
  function rCockpit(){const s=sec('nr-ck');if(!s)return;const items=p1Items(),open=items.filter(x=>x.lvl==='bad'||x.lvl==='warn'),nb=items.filter(x=>x.lvl==='bad').length,cur=open.length?1:2;
    const c=N.prs[cut];
    const card=x=>`<div class="nr-card lv-${x.lvl}"><div class="nr-ct"><span class="nr-id">${esc(x.id)}</span><b${x.raw?' class="obsraw"':''}>${esc(x.title)}</b><span class="obs-lab">${esc(x.owner)}</span></div><div class="nr-cb">${x.body}</div><div class="nr-cf"><span>${T('Write the result','Ghi kết quả')}: ${x.rec}</span>${x.ev?`<span class="nr-evs">${T('Evidence','Bằng chứng')}: ${x.ev}</span>`:''}</div></div>`;
    let body='';
    if(ckPhase===1){const gs=[...new Set(items.map(x=>x.g))];
      body=gs.map((g,i)=>{const xs=items.filter(x=>x.g===g),l=xs.filter(x=>x.lvl!=='ok').length;return`<div class="nr-grp"><h3><span class="nr-gi">${i+1}</span>${esc(g)} <span class="gch ${l?(xs.some(x=>x.lvl==='bad')?'s-fail':'s-run'):'s-ok'}">${l?T(`${l} open`,`${l} còn mở`):T('done','xong')}</span></h3>${xs.map(card).join('')}</div>`;}).join('')+
        `<div class="nr-next"><b>${T('When groups 1–4 are done → Phase 2:','Khi nhóm 1–4 xong → Phase 2:')}</b> ${T(`cut rc1 at the selected cut point (after #${c.num}, ${esc(c.sha)})`,`cắt rc1 tại điểm cắt đang chọn (sau #${c.num}, ${esc(c.sha)})`)} ${evb('nr-cut','change the cut','đổi điểm cắt')}
          <pre class="nr-cmd">gh release create v${esc(((N.roadmap.rel||'').match(/release-([\d.]+)/)||[])[1]||'X')}rc1 -R LMCache/LMCache --target ${esc(c.sha)} --prerelease \\\n  --title "LMCache rc1" --generate-notes --notes-start-tag ${esc(N.stable)}</pre><span class="ops-src">${T('Command of Runbook Phase 2; use the full SHA when you run it.','Lệnh theo Runbook Phase 2; dùng SHA đầy đủ khi chạy thật.')}</span></div>`;}
    else if(ckPhase===3)body=`<div class="nr-grp"><h3><span class="nr-gi">G</span>${T('The rc must pass these gates (Runbook Phase 3)','rc phải qua các gate này (Runbook Phase 3)')}</h3>${p3Items().map(card).join('')}</div><div class="nr-next">${T('A gate is red → ','Gate đỏ → ')}${evb('nr-cp','Trace bug','Trace bug','data-cpmode="bug"')} ${T('to find the node, the suspect PRs and the tests; fix, cherry-pick, cut the next rc.','để tìm node, PR nghi ngờ và test; sửa, cherry-pick, cắt rc tiếp theo.')}</div>`;
    else body=`<div class="nr-next">${esc({0:T('Run daily_release_check.sh every day until T; new PRs go to the ROADMAP (Gaps or Internal). This page does not read that output yet.','Chạy daily_release_check.sh mỗi ngày tới T; PR mới vào ROADMAP (Gaps hoặc Internal). Trang chưa đọc output của script này.'),
      2:T('Cut the rc at the chosen cut point, then cancel the image push run as in the runbook.','Cắt rc tại điểm cắt đã chọn, rồi huỷ run push image như runbook.'),
      4:T('Write the release notes (breaking first) and go through the 13-item checklist of Runbook section 7. One No-Go = no release: fix, cut the next rc.','Viết release note (breaking trước), đi qua checklist 13 mục của Runbook mục 7. Một mục No-Go là không release: sửa, cắt rc tiếp.'),
      5:T('Tag stable, publish, re-run G1 with the stable version, check every Docker tag.','Tag stable, publish, chạy lại G1 với version stable, kiểm mọi Docker tag.'),
      6:T('Watch new issues T+1 → T+7; SEV-1 → Runbook section 8 (yank, move tags back).','Theo dõi issue mới T+1 → T+7; SEV-1 → Runbook mục 8 (yank, trả tag về).')}[ckPhase])}</div>`;
    s.innerHTML=head('3A','Release cockpit','Release cockpit',
      open.length?T(`In <b>Phase 1 · Prepare</b>. <b>${open.length}</b> items left (${nb} to decide) before cutting rc1. Each card: who, where to write the answer, and the evidence below.`,`Đang ở <b>Phase 1 · Chuẩn bị</b>. Còn <b>${open.length}</b> việc (${nb} phải quyết) trước khi cắt rc1. Mỗi thẻ: ai làm, ghi kết quả vào đâu, bằng chứng ở phần nào bên dưới.`):T('Ready to cut rc1.','Sẵn sàng cắt rc1.'))+
      `<ol class="nr-phases">${PH.map(([n,en,vi,sub])=>{const st=n<cur?(n===0?'unk':'done'):n===cur?'cur':'lock';
        const b=n===1?`<span class="gch ${open.length?'s-fail':'s-ok'}">${open.length?T(`${open.length} items`,`${open.length} việc`):T('done','xong')}</span>`:st==='unk'?`<span class="gch s-none">${T('no data','chưa có dữ liệu')}</span>`:st==='lock'?`<span class="gch s-none">${T('after the previous phase','chờ phase trước')}</span>`:'';
        return`<li><button class="nr-ph ${st}${ckPhase===n?' sel':''}" data-ph="${n}" type="button" aria-pressed="${ckPhase===n}"><span class="nr-pn">Phase ${n}</span><b>${esc(T(en,vi))}</b><span class="nr-ps">${esc(sub)}</span>${b}</button></li>`;}).join('')}</ol>`+body;}

  /* ================= 3B · scope ================= */
  function kpis(){const inRc=[...SCOPE].filter(n=>PR[n]&&PR[n].i<=cut).length,ride=N.prs.filter(p=>p.i<=cut&&!SCOPE.has(p.num)),rb=ride.filter(p=>p.ride.lvl==='bad').length,rw=ride.filter(p=>p.ride.lvl==='warn').length,after=N.prs.length-1-cut;
    const k=(v,l,cls,i)=>`<div class="ops-kpi${cls?' '+cls:''}" data-kpi="${i}"><div class="v">${v}</div><div class="l">${l}</div></div>`;
    return`<div class="ops-kpis">${k(`${inRc}/${SCOPE.size}`,T('scope PRs in the rc','PR scope có trong rc'),inRc===SCOPE.size?'good':'bad',0)}${k(ride.length,T(`ship but not in scope · ${rb} risky · ${rw} to review`,`đi kèm ngoài scope · ${rb} rủi ro cao · ${rw} cần xem`),rb?'bad':rw?'warn':'',1)}${k(after,T('after the cut (cherry-pick only)','sau điểm cắt (chỉ cherry-pick)'),'',2)}${k('rc',T('MP E2E proof: run it on the rc commit','Bằng chứng MP E2E: chạy trên commit rc'),'warn',3)}</div>`;}
  /* decision per scope item: verb + rule tooltip from decisions.py (opsData.dec), evidence = newest MP build of each PR (PR CI, not dev) */
  const DECV=(OD.dec||{}).verbs||{},DECR=(OD.dec||{}).rules||{};
  const decChip=v=>{const x=DECV[v];return x?`<span class="tdy-v t-${x[2]}" tabindex="0" data-rule="${esc(T('Rule · ','Luật · ')+(DECR[v]?T(DECR[v][0],DECR[v][1]):''))}">${esc(T(x[0],x[1]))}</span>`:'';};
  const ST_={passed:['s-ok',T('passed','pass')],failed:['s-fail',T('failed','fail')]};
  function decCell(r){const d=r.it.dec;if(!d)return'';const ev=r.ps.filter(p=>p.mp_ev).map(p=>{const e=p.mp_ev,s=ST_[e.state]||['s-none',esc(e.state||'?')];return`<div class="nr-mute">#${p.num} MP <a data-ev href="${esc(e.url)}" target="_blank" rel="noopener">#${esc(e.key.split('/').pop())} ↗</a> <span class="gch ${s[0]}">${s[1]}</span></div>`;}).join('');
    return `${decChip(d.verb)}<div>${esc(T(d.short[0],d.short[1]))}</div>${ev}`;}
  function rScope(){const s=sec('nr-scope');if(!s)return;const rows=N.items.map(itemRow),secs=[...new Set(N.items.map(i=>i.section))];
    let h=`<thead><tr><th>${T('Scope item','Mục trong scope')}</th><th>PR</th><th>${T('Stage · who breaks','Bước · ai bị ảnh hưởng')}</th><th>${T('MP CI on the PR (from labels)','MP CI ở PR (theo nhãn)')}</th><th>${T('CPU tests of the area','Test CPU của nhóm')}</th><th>${T('Verdict','Kết luận')}</th><th>${T('Decision · evidence','Quyết định · bằng chứng')}</th></tr></thead><tbody>`;
    secs.forEach(sc=>{h+=`<tr class="ops-grp"><td colspan="7"><b>${esc(sc)}</b></td></tr>`;rows.filter(r=>r.it.section===sc).forEach(r=>{
      const mp=r.ps.map(p=>`<span class="gch ${p.mp_ci==='ran'?'s-ok':p.mp_ci==='skip'&&mpReq(p)?'s-run':'s-none'}" title="#${p.num}">${mpTxt(p)}</span>`).join(' ');
      const ts=[...new Set(r.ps.map(p=>p.area))].map(a=>{const x=FM[a];return x?`<span class="ops-files">${esc(x.code)} ${esc(x.name)}: ${x.files} file${x.notrun?` · <span class="nr-warn">${x.notrun} ${T('not on CPU','không chạy CPU')}</span>`:''}</span>`:`<span class="nr-mute">${esc(AN(a))}: –</span>`;}).join('<br>');
      h+=`<tr data-item="${N.items.indexOf(r.it)}"><td data-col="item"><span class="gch ${CHIP[r.lvl]}">${r.lvl==='ok'?'✓':r.lvl==='bad'?'!':'•'}</span> ${esc(r.it.text)}</td>
        <td data-col="pr">${r.ps.map(p=>`<a href="${GH(p.num)}" target="_blank" rel="noopener">#${p.num}</a>`).join(' ')}</td>
        <td data-col="stage">${r.stage==null?T('Off the path','Ngoài đường đi'):`B${r.stage} · ${esc(((FLOW[r.stage]||{}).name||[])[V()]||'')}`}<div class="nr-mute">${r.stage==null?T('Users of that feature','Người dùng tính năng đó'):esc(IMPACT[r.stage][1+V()])}</div></td>
        <td data-col="mp">${mp}</td><td data-col="tests">${ts}</td>
        <td data-col="verdict">${r.reasons.length?r.reasons.map(x=>`<div class="ops-rule lv-${x[0]==='bad'?'bad':'warn'}">${esc(x[1])}</div>`).join(''):`<span class="nr-mute">${T('Ready; waiting for the rc proof','Sẵn sàng; chờ bằng chứng trên rc')}</span>`}</td>
        <td data-col="dec">${decCell(r)}</td></tr>`;});});
    s.innerHTML=head('3B','Evidence A · Scope: what this release promises','Bằng chứng A · Scope: release cam kết gì',
      T(`Items of <code>${esc(N.roadmap.rel||'')}</code>. Release = rc cut from dev + cherry-picks: every PR merged before the cut ships. Click any cell for its meaning.`,`Các mục trong <code>${esc(N.roadmap.rel||'')}</code>. Release = rc cắt từ dev + cherry-pick: mọi PR merge trước điểm cắt đều ship. Bấm vào ô bất kỳ để xem định nghĩa.`))+kpis()+`<div class="obs-scroll"><table class="obs-t nr-t">${h}</tbody></table></div>`;}

  /* ================= 3C · critical path trace ================= */
  function rCP(){const s=sec('nr-cp');if(!s)return;
    const H=head('3C','Evidence B · Critical path: where the change sits, and how to trace a bug','Bằng chứng B · Critical path: thay đổi nằm ở đâu, và trace bug thế nào',
      T('Journeys and features F01–F17 come from the Feature Matrix xlsx. <b>By change</b>: pick a scope item; changed nodes are the critical stages to test. <b>Trace bug</b>: pick a symptom; the page shows the node, the feature, the suspect PRs in the rc and the CPU / GPU tests.','Journey và feature F01–F17 lấy từ Feature Matrix xlsx. <b>Theo thay đổi</b>: chọn mục scope; node bị đổi là critical stage cần test. <b>Trace bug</b>: chọn triệu chứng; trang chỉ ra node, feature, PR nghi ngờ trong rc và test CPU / GPU.'));
    if(!CP){s.innerHTML=H+`<div class="ops-empty">${T('Feature Matrix xlsx not found in knowledge/inputs.','Không thấy Feature Matrix xlsx trong knowledge/inputs.')}</div>`;return;}
    const Jn=CP.journeys.find(j=>j.id===cpJ),nodes=CP.node_f[cpJ],touch=fTouch(cpMode==='bug'?shipping():pickedPRs()),bugF=cpMode==='bug'&&cpBug?cpBug:null;
    const tabs=CP.journeys.map(j=>{const n=CP.node_f[j.id].filter(fs=>bugF?fs.includes(bugF):fs.some(f=>touch[f])).length;return`<button type="button" data-cpj="${j.id}" aria-pressed="${cpJ===j.id}">${j.id} · ${esc(j.name)} <span class="nr-mute">${n}/${CP.node_f[j.id].length}</span></button>`;}).join('');
    const sel=cpMode==='scope'?`<label class="nr-mute" for="nrPick">${T('Change','Thay đổi')}:</label><select id="nrPick" class="nr-sel"><option value="all"${pick===null?' selected':''}>${T('Whole rc (selected cut)','Toàn bộ rc (điểm cắt đang chọn)')}</option>${N.items.map((it,i)=>`<option value="${i}"${pick===i?' selected':''}>${esc(it.text)} (${it.prs.map(n=>'#'+n).join(' ')})</option>`).join('')}<option value="ride"${pick==='ride'?' selected':''}>${T('Risky PRs that ship','PR đi kèm rủi ro cao')}</option></select>`
      :`<label class="nr-mute" for="nrBug">${T('Symptom','Triệu chứng')}:</label><select id="nrBug" class="nr-sel"><option value="">${T('Pick what users / CI see…','Chọn điều người dùng / CI thấy…')}</option>${CP.features.map(f=>`<option value="${f.id}"${cpBug===f.id?' selected':''}>${esc(f.risk)} · ${f.id} ${esc(f.step)}</option>`).join('')}</select>`;
    const seq=Jn.steps.map((st_,i)=>{const fs=nodes[i]||[];let c='';if(bugF)c=fs.includes(bugF)?'bug':'';else{const lv=fs.map(f=>fLevel(touch[f])).filter(Boolean);c=lv.includes('bad')?'bad':lv.includes('warn')?'warn':lv.length?'ch':'';}
      const sc=new Set(fs.flatMap(f=>touch[f]?touch[f].scope.map(x=>x.p.num):[])).size,al=new Set(fs.flatMap(f=>touch[f]?[...touch[f].scope,...touch[f].ride].map(x=>x.p.num):[])).size;
      return`${i?'<span class="ops-farr">→</span>':''}<button type="button" class="nr-node ${c}${cpNode===i?' sel':''}" data-cpnode="${i}" aria-pressed="${cpNode===i}"><span class="t">${esc(st_)}</span><span class="nr-fs">${fs.map(f=>`<span class="nr-f" data-fid="${f}">${f}</span>`).join('')}</span>${!bugF&&al?`<span class="nr-mute">${sc?T(`${sc} scope`,`${sc} scope`):''}${sc&&al-sc?' · ':''}${al-sc?T(`${al-sc} ship-along`,`${al-sc} đi kèm`):''}</span>`:''}</button>`;}).join('');
    const fids=bugF?[bugF]:cpNode!=null?(nodes[cpNode]||[]):[...new Set(nodes.flat())].filter(f=>touch[f]);
    const areasOfF=fid=>Object.entries(CP.area_f).filter(([,fs])=>fs.includes(fid)).map(([a])=>a);
    const prl=xs=>xs.sort((a,b)=>(b.mk==='●')-(a.mk==='●')||RANK[b.p.ride.lvl]-RANK[a.p.ride.lvl]||b.p.i-a.p.i).slice(0,6).map(x=>mkLink(x,x.p.area)).join('')+(xs.length>6?`<span class="nr-mute"> +${xs.length-6}</span>`:'');
    const rows=fids.map(fid=>{const f=FF[fid],r=touch[fid]||{scope:[],ride:[]},lv=bugF?'bug':(fLevel(r)||'none');
      return`<tr><td data-col="cpf"><span class="gch ${lv==='bad'||lv==='bug'?'s-fail':lv==='warn'||lv==='ch'?'s-run':'s-none'}">${fid}</span></td>
        <td data-col="cpfeat"><b>${esc(f.name)}</b><div class="nr-mute">${esc(f.step)} · ${esc(f.dep)}</div>${areasOfF(fid).map(a=>`<button type="button" class="ops-feat" onclick="opsOpenFeature&&opsOpenFeature('${a}')">${esc((FM[a]||{}).code||'')} ${esc(AN(a))}</button>`).join('')}</td>
        <td data-col="cpcpu">${esc(f.cpu)}</td><td data-col="cpgpu">${esc(f.gpu)}</td><td data-col="cpcrit"><span class="nr-crit">${esc(f.crit)}</span></td><td data-col="cprisk">${esc(f.risk)}</td>
        <td data-col="cppr">${r.scope.length?`<div><span class="nr-mute">scope</span> ${prl(r.scope)}</div>`:''}${r.ride.length?`<div><span class="nr-mute">${T('ship-along','đi kèm')}</span> ${prl(r.ride)}</div>`:''}${!r.scope.length&&!r.ride.length?`<span class="nr-mute">${T('no PR in the rc','không PR nào trong rc')}</span>`:''}</td></tr>`;}).join('');
    let dbg='';if(fids.length){const sus=[...new Map(fids.flatMap(fid=>touch[fid]?[...touch[fid].scope,...touch[fid].ride]:[]).map(x=>[x.p.num,x])).values()].sort((a,b)=>RANK[b.p.ride.lvl]-RANK[a.p.ride.lvl]||(b.mk==='●')-(a.mk==='●')||b.p.i-a.p.i);
      const ar=[...new Set(fids.flatMap(areasOfF))],tf=ar.reduce((s_,a)=>s_+((FM[a]||{}).files||0),0),wl=[...new Set(ar.flatMap(wlOf))];
      const where=cpNode!=null?`"${Jn.steps[cpNode]}"`:bugF?T(`the node with ${bugF}`,`node chứa ${bugF}`):T('the changed nodes','các node bị đổi');
      dbg=`<ol class="nr-dbg"><li><b>${T('Reproduce on CPU','Reproduce trên CPU')}</b> (${T('cheap, first','rẻ, làm trước')}): ${fids.map(fid=>`${fid}: ${esc(FF[fid].cpu)}`).join(' · ')}. ${T('Unit tests','Unit test sẵn có')}: ${tf} file (${ar.map(a=>esc((FM[a]||{}).code||a)).join(', ')}).</li>
        <li><b>Trace</b> ${T('at','tại')} ${esc(where)}, journey ${esc(Jn.id)}: ${esc(Jn.steps.join(' → '))}. ${T('Logs and events of that step first, then the next one.','Xem log và event ở bước đó trước, rồi bước ngay sau.')}</li>
        <li><b>Isolate</b>: ${sus.length?T('suspect PRs, in order: ','PR nghi ngờ, theo thứ tự: ')+sus.slice(0,8).map(x=>`<a href="${GH(x.p.num)}" target="_blank" rel="noopener">#${x.p.num}</a>${SCOPE.has(x.p.num)?'':`<span class="nr-mute">(${T('ship-along','đi kèm')})</span>`}`).join(', '):T('no PR in the rc touches it; suspect the environment (engine, image).','không PR nào trong rc chạm; nghi môi trường (engine, image).')}</li>
        <li><b>${T('Verify on GPU','Verify trên GPU')}</b>: <span class="obsraw">${fids.map(fid=>`${fid}: ${esc(FF[fid].gpu)}`).join(' · ')}. Workload: ${wl.length?esc(wl.join(', ')):'–'}.</span> ${T('On the rc commit, no skip label.','Trên commit rc, không gắn nhãn skip.')}</li></ol>`;}
    s.innerHTML=H+`<div class="ops-filter">${tabs}</div><div class="ops-filter"><button type="button" data-cpmode="scope" aria-pressed="${cpMode==='scope'}">${T('By change','Theo thay đổi')}</button><button type="button" data-cpmode="bug" aria-pressed="${cpMode==='bug'}">Trace bug</button>${sel}</div>
      <div class="obs-scroll"><div class="nr-seq">${seq}</div></div><p class="ops-src"><b>${esc(Jn.name)}</b>: ${esc(Jn.test)}. ${esc(Jn.impact)}.${cpNode!=null?` <button type="button" class="nr-link" data-cpnode="${cpNode}">${T('clear node','bỏ chọn node')}</button>`:''}</p>
      ${fids.length?`<div class="obs-scroll"><table class="obs-t nr-t"><thead><tr><th>F</th><th>${T('Feature · code areas','Feature · nhóm code')}</th><th>${T('CPU test proves','CPU test chứng minh')}</th><th>${T('GPU test proves','GPU test chứng minh')}</th><th>Critical</th><th>${T('Symptom when broken','Triệu chứng khi hỏng')}</th><th>${T('PRs in the rc','PR trong rc')}</th></tr></thead><tbody>${rows}</tbody></table></div>${dbg}`:`<div class="ops-empty">${bugF?'':T('No node of this journey is touched by the selection.','Không node nào trên journey này bị chạm bởi lựa chọn hiện tại.')}</div>`}
      <p class="ops-src">${T(`Model: <code>${esc(CP.src)}</code>. Node → F and code area → F maps are drafts (next_release.py). Gates in the xlsx are proposals, not test results.`,`Mô hình: <code>${esc(CP.src)}</code>. Bảng nối node → F và nhóm code → F là bản nháp (next_release.py). Gate trong xlsx là đề xuất, không phải kết quả test.`)}</p>`;}

  /* ================= 3D · tests per feature ================= */
  function areaRows(prs){const r={};prs.forEach(p=>{const o=Object.entries(p.a_src).map(([a,n])=>({a,n,mk:a===p.area?'●':'○'}));Object.entries(p.a_test).forEach(([a,n])=>{if(!(a in p.a_src))o.push({a,n,mk:'△'});});
    o.forEach(t=>{const x=r[t.a]||(r[t.a]={scope:[],ride:[]});(SCOPE.has(p.num)?x.scope:x.ride).push({p,mk:t.mk,n:t.n});});});return r;}
  function areaVerdict(id,r){const a=FM[id],w=[],all=[...r.scope,...r.ride].filter(x=>x.mk!=='△'),sk=all.filter(x=>x.p.mp_ci==='skip'&&mpReq(x.p));
    const bk=all.filter(x=>x.p.breaking&&x.mk==='●');if(bk.length)w.push(['bad',T(`Breaking PR changes its main code: ${bk.map(x=>'#'+x.p.num).join(' ')}`,`PR breaking đổi code chính của nhóm: ${bk.map(x=>'#'+x.p.num).join(' ')}`)]);
    const wide=all.filter(x=>x.mk==='○'&&Object.keys(x.p.a_src).length>=8);if(wide.length)w.push(['warn',T(`Touched by wide PRs (${wide.map(x=>'#'+x.p.num).join(', ')})`,`Bị chạm phụ bởi PR thay đổi rộng (${wide.map(x=>'#'+x.p.num).join(', ')})`)]);
    if(sk.length)w.push(['warn',T(`${sk.length} PRs change it but skipped MP CI: ${sk.map(x=>'#'+x.p.num).join(' ')}`,`${sk.length} PR đổi code nhóm này nhưng skip MP CI: ${sk.map(x=>'#'+x.p.num).join(' ')}`)]);
    if(!a||!a.files)w.push(['warn',T('No CPU unit tests for this area','Không có unit test CPU cho nhóm')]);else{if(a.notrun)w.push(['warn',T(`${a.notrun} test files do not run on CPU`,`${a.notrun} test file không chạy trên CPU`)]);if(a.vllm_import)w.push(['warn',T(`${a.vllm_import}/${a.files} test files import vLLM: only GHA Test runs them, no merge gate`,`${a.vllm_import}/${a.files} test file import vLLM: chỉ GHA Test chạy, không chặn merge`)]);}
    return{lvl:w.length?worst(w.map(x=>x[0])):'ok',why:w};}
  function rFM(){const s=sec('nr-fm');if(!s)return;const rows=areaRows(pickedPRs()),groups=[...new Set(CPU.areas.map(a=>a.group))];let h='',shown=0;
    groups.forEach(g=>{const as=CPU.areas.filter(a=>a.group===g&&rows[a.id]);if(!as.length)return;h+=`<tr class="ops-grp"><td colspan="9"><b>${esc(g)}</b></td></tr>`;
      as.forEach(a0=>{shown++;const a=FM[a0.id],r=rows[a.id],v=areaVerdict(a.id,r),st=(N.prs.find(p=>p.area===a.id)||{}).stage,t=tiersOf(a.id),wl=wlOf(a.id),rb=r.ride.filter(x=>x.p.ride.lvl==='bad').length,rc=r.ride.filter(x=>x.mk!=='△');
        h+=`<tr class="nr-arow${selArea===a.id?' sel':''}" data-area="${a.id}"><td data-col="code" class="ops-files">${a.code}</td><td data-col="feature"><span class="gch ${CHIP[v.lvl]}">${v.lvl==='ok'?'✓':v.lvl==='bad'?'!':'•'}</span> ${esc(a.name)}</td>
          <td data-col="stage">${st==null?'–':`<span class="nr-stg w${IMPACT[st][0]}" data-stg="${st}">B${st}</span>`}</td><td data-col="scope">${r.scope.map(x=>mkLink(x,a.id)).join('')||'–'}</td>
          <td data-col="ride">${r.ride.length?`${r.ride.length} PR${rb?` <span class="gch s-fail">${rb} ${T('risky','rủi ro cao')}</span>`:''}<div>${rc.slice(0,4).map(x=>mkLink(x,a.id)).join('')}${rc.length>4?'…':''}</div>`:'–'}</td>
          <td data-col="tests" class="ops-files">${a.files?`${a.files} file · ${a.passed} test${a.notrun?`<br><span class="nr-warn">${a.notrun} ${T('not on CPU','không chạy CPU')}</span>`:''}`:`<span class="nr-warn">${T('none','không có')}</span>`}</td>
          <td data-col="tiers">${t.req.map(x=>tierChip(x)).join('')}${t.cond.map(x=>tierChip(x,true)).join('')}</td><td data-col="wl" class="nr-mute">${wl.length?esc(wl.join(', ')):'–'}</td>
          <td data-col="verdict">${v.why.length?v.why.map(x=>`<div class="ops-rule lv-${x[0]==='bad'?'bad':'warn'}">${esc(x[1])}</div>`).join(''):`<span class="nr-mute">${T('OK','Ổn')}</span>`}</td></tr>`;});});
    const pk=`<div class="ops-filter"><button type="button" data-pick="all" aria-pressed="${pick===null}">${T('Whole rc','Toàn bộ rc')}</button>${N.items.map((it,i)=>`<button type="button" data-pick="${i}" aria-pressed="${pick===i}" title="${esc(it.text)}">${esc(it.text.length>30?it.text.slice(0,29)+'…':it.text)}</button>`).join('')}<button type="button" data-pick="ride" aria-pressed="${pick==='ride'}">${T('Risky ship-along','Đi kèm rủi ro cao')}</button></div>`;
    s.innerHTML=head('3D','Evidence C · Tests per feature: what each PR touches and what must run','Bằng chứng C · Test theo feature: PR chạm gì và phải chạy gì',
      T('Rows = Feature matrix areas (same codes as Release Exploration). ● main code of the area, ○ other code, △ tests only. Faded tier with * = proposed, no real job today. Click a row to filter the ship-along list in 3E; click any cell or chip for its meaning.','Hàng = nhóm của Feature matrix (cùng mã với Khám phá Release). ● code chính của nhóm, ○ code phụ, △ chỉ test. Tier mờ có * = đề xuất, chưa có job thật. Bấm một hàng để lọc danh sách đi kèm ở 3E; bấm ô hoặc chip bất kỳ để xem định nghĩa.'))+pk+
      `<div class="obs-scroll"><table class="obs-t nr-t"><thead><tr><th>${T('Code','Mã')}</th><th>Feature</th><th>${T('Stage','Bước')}</th><th>${T('Scope PRs','PR scope')}</th><th>${T('Ship-along','Đi kèm')}</th><th>${T('Unit tests','Unit test')}</th><th>${T('Tiers','Tier')}</th><th>${T('E2E workloads','Workload E2E')}</th><th>${T('Verdict','Kết luận')}</th></tr></thead><tbody>${h}<tr><td colspan="9" class="nr-mute">${T(`${CPU.areas.length-shown} other areas are not touched.`,`${CPU.areas.length-shown} nhóm khác không bị chạm.`)}</td></tr></tbody></table></div>`;}

  /* ================= 3E · rc cut ================= */
  function rCut(){const s=sec('nr-cut');if(!s)return;const c=N.prs[cut],a0=N.prs[0];
    const strip=N.prs.map(p=>{const sc=SCOPE.has(p.num),k=sc?'scope':p.breaking?'bk':(CODE_T.has(p.type)&&weight(p)===3&&!['docs','tests'].includes(p.risk))?'hi':'lo';
      return`<button type="button" class="nr-tick ${k}${p.i>cut?' after':''}${p.i===cut?' cut':''}" data-cut="${p.i}" title="#${p.num} · ${esc(p.at)} · ${esc(p.title)}${sc?' · SCOPE':''}"></button>`;}).join('');
    const f=p=>selArea===null||(selArea in p.a_src)||(selArea in p.a_test);
    const ride=N.prs.filter(p=>p.i<=cut&&!SCOPE.has(p.num)&&f(p)).sort((x,y)=>RANK[y.ride.lvl]-RANK[x.ride.lvl]||weight(y)-weight(x)||y.i-x.i),show=ride.filter(p=>p.ride.lvl!=='ok');
    const after=N.prs.filter(p=>p.i>cut&&f(p)),pk=after.filter(p=>p.breaking||(p.type==='bug'&&weight(p)===3));
    const row=(p,why,lv)=>`<div class="ops-rule lv-${lv}"><a href="${GH(p.num)}" target="_blank" rel="noopener">#${p.num}</a> <b class="obsraw">${esc(p.title)}</b><div class="nr-mute">${esc(p.stage==null?T('off the path','ngoài đường đi'):'B'+p.stage)} · ${esc(AN(p.area))} · ${esc(p.type)} · ${esc(p.at.slice(0,10))} · MP CI: ${mpTxt(p)}</div>${why.map(w=>`<div>${esc(w[1])}</div>`).join('')}</div>`;
    const fa=selArea?` · ${T('touching','chạm')} ${esc((FM[selArea]||{}).code||'')} ${esc(AN(selArea))} <button type="button" class="nr-link" data-clear="1">${T('clear','bỏ lọc')}</button>`:'';
    s.innerHTML=head('3E','Evidence D · rc cut point: what really ships','Bằng chứng D · Điểm cắt rc: thực sự ship những gì',
      T('One bar per PR on dev after the stable tag, oldest left. Cut the rc at a bar: everything left of it ships, everything right of it needs a cherry-pick. Click a bar to try another cut.','Mỗi vạch là một PR trên dev sau tag stable, cũ ở bên trái. Cắt rc tại một vạch: mọi PR bên trái đều ship, PR bên phải phải cherry-pick. Bấm vào vạch để thử điểm cắt khác.'))+
      `<div class="ops-filter"><span class="nr-mute">${T('Cut','Điểm cắt')}:</span> <b>${T(`after #${c.num}`,`sau #${c.num}`)}</b> <code>${esc(c.sha)}</code> <span class="nr-mute">${esc(c.at)}</span><button type="button" data-cut="${MIN_CUT}" aria-pressed="${cut===MIN_CUT}">${T('Minimum: after the last scope PR','Tối thiểu: sau PR scope cuối')}</button><button type="button" data-cut="${HEAD_CUT}" aria-pressed="${cut===HEAD_CUT}">${T('dev HEAD','HEAD của dev')}</button></div>
      <div class="obs-scroll"><div class="nr-strip">${strip}</div><div class="nr-axis"><span>${esc(a0.at.slice(0,10))} · ${esc(N.stable)}</span><span>${esc(N.prs[HEAD_CUT].at.slice(0,10))} · HEAD</span></div></div>
      <div class="ops-leg"><span><i style="background:var(--series-1)"></i>${T('In scope','Trong scope')}</span><span><i style="background:var(--critical)"></i>${T('Breaking, not in scope','Breaking, ngoài scope')}</span><span><i style="background:var(--warning)"></i>${T('Not in scope, code on the hot path','Ngoài scope, đổi code trên hot path')}</span><span><i style="background:var(--border)"></i>${T('Other','Khác')}</span><span>${T('faded = after the cut','mờ = sau điểm cắt')}</span></div>
      <div class="ops-split"><div><h3>${T(`Ships with the rc: ${ride.length} PRs`,`Đi kèm vào rc: ${ride.length} PR`)}${fa}</h3><p class="ops-why">${T('Not in scope but ships. Each needs a decision in the cockpit (3A).','Ngoài scope nhưng vẫn ship. Mỗi PR cần một quyết định ở cockpit (3A).')}</p>
        ${show.slice(0,rideLimit).map(p=>row(p,p.ride.why,p.ride.lvl)).join('')}${show.length>rideLimit?`<button type="button" class="nr-link" data-more="1">${T(`show ${Math.min(10,show.length-rideLimit)} more`,`xem thêm ${Math.min(10,show.length-rideLimit)}`)}</button>`:''}<p class="ops-src">${T(`${ride.length-show.length} low-risk PRs hidden (docs, tests, CI, one feature).`,`${ride.length-show.length} PR rủi ro thấp được ẩn (docs, test, CI, một tính năng).`)}</p></div>
        <div><h3>${T(`After the cut: ${after.length} PRs · ${pk.length} worth a cherry-pick`,`Sau điểm cắt: ${after.length} PR · ${pk.length} đáng cân nhắc cherry-pick`)}</h3><p class="ops-why">${T('Only hot-path bug fixes and breaking PRs are listed.','Chỉ liệt kê bugfix trên hot path và PR breaking.')}</p>
        ${pk.slice(0,12).map(p=>row(p,[[0,p.breaking?T('Breaking: if picked, add to scope and notes','Breaking: nếu cherry-pick thì đưa vào scope và note'):T('Hot-path bug fix: consider a cherry-pick','Bugfix trên hot path: cân nhắc cherry-pick')]],p.breaking?'bad':'warn')).join('')||`<div class="ops-empty">–</div>`}</div></div>`;}

  /* ================= click → definition popover ================= */
  const COL={item:['Scope item','Mục trong scope','One line of the ROADMAP. The chip is its verdict.','Một dòng trong ROADMAP. Chip là kết luận của mục.'],pr:['PRs of the item','PR của mục','PRs the ROADMAP links to this item.','PR mà ROADMAP gắn với mục này.'],
    stage:['Stage on the request path','Bước trên đường đi request','Where the changed code sits: B0 engine connector → B1 transport → B2 lookup → B3 KV transfer → B4 L1 → B5 L2. Earlier = wider impact.','Vị trí code bị đổi: B0 engine connector → B1 transport → B2 lookup → B3 chuyển KV → B4 L1 → B5 L2. Càng ở đầu thì ảnh hưởng càng rộng.'],
    mp:['MP CI on the PR','MP CI ở PR',"Did the PR run k3-multiprocess-test before merge? 'skip' = label 'skip expensive ci'. dev runs no MP workloads since 10-28, so this is the only proof before the rc.","PR đã chạy k3-multiprocess-test trước khi merge chưa? 'skip' = nhãn 'skip expensive ci'. dev không chạy MP workload từ 10-28, nên trước rc đây là bằng chứng duy nhất."],
    tests:['CPU unit tests of the area','Unit test CPU của nhóm','Test files and tests of the area in the local CPU run (same source as the Feature matrix). "not on CPU" = needs a GPU, runs only in k3-unit-tests.','Test file và test của nhóm trong lần chạy CPU local (cùng nguồn với Feature matrix). "không chạy CPU" = cần GPU, chỉ chạy trong k3-unit-tests.'],
    verdict:['Verdict','Kết luận','Red: breaking in the wrong section, after the cut, or a breaking PR changes the main code. Amber: skipped MP CI, tests not on CPU, vLLM-import tests without a merge gate, or a wide PR.','Đỏ: breaking sai mục, sau điểm cắt, hoặc PR breaking đổi code chính. Cam: skip MP CI, test không chạy CPU, test import vLLM không có cổng merge, hoặc PR thay đổi rộng.'],
    code:['Feature code','Mã feature','Code of the area in the Feature matrix (Release Exploration → CPU tests → 3).','Mã của nhóm trong Feature matrix (Khám phá Release → CPU tests → 3).'],feature:['Feature area','Nhóm feature','A functional area of LMCache, mapped from file paths.','Một vùng chức năng của LMCache, map từ đường dẫn file.'],
    scope:['Scope PRs touching it','PR scope chạm nhóm','● main code of the area · ○ other code · △ tests only.','● code chính của nhóm · ○ code phụ · △ chỉ test.'],ride:['Ship-along PRs','PR đi kèm','Not in scope but before the cut, so they ship. "risky" = hot-path code with skipped MP CI, or breaking.','Ngoài scope nhưng trước điểm cắt nên vẫn ship. "rủi ro cao" = code hot path đã skip MP CI, hoặc breaking.'],
    tiers:['Tiers to pass','Tier phải qua','Test layers this area needs (gates.py AREA_CLASS → CLASSES). Solid = required, dashed = only when the sub-path changes, faded * = proposed.','Các tầng test nhóm này cần (gates.py AREA_CLASS → CLASSES). Viền liền = bắt buộc, nét đứt = chỉ khi sub-path đổi, mờ * = đề xuất.'],
    wl:['E2E workloads','Workload E2E','k3-multiprocess-test workloads of those tiers (gates.py TIER_WORKLOADS). Coarse: most areas are class core.','Workload của k3-multiprocess-test gắn với các tier đó (gates.py TIER_WORKLOADS). Còn thô: phần lớn nhóm thuộc class core.'],
    cpf:['F-id','F-id','Feature id of the Feature Matrix xlsx (sheet 01).','Mã feature trong Feature Matrix xlsx (sheet 01).'],cpfeat:['Feature · code areas','Feature · nhóm code','The xlsx feature and the code areas mapped to it (draft).','Feature trong xlsx và các nhóm code nối vào (bản nháp).'],
    cpcpu:['CPU test proves','CPU test chứng minh','Contract / logic you can prove on CPU, cheap: reproduce here first.','Contract / logic chứng minh được trên CPU, rẻ: reproduce ở đây trước.'],cpgpu:['GPU test proves','GPU test chứng minh','What only a real GPU proves (data plane): confirm on the rc commit.','Điều chỉ GPU thật chứng minh được (data plane): xác nhận trên commit rc.'],
    cpcrit:['Critical','Critical','Which path the feature is on; critical = the journey breaks, conditional = only when enabled.','Feature thuộc đường nào; critical = journey hỏng, conditional = chỉ khi bật.'],cprisk:['Symptom when broken','Triệu chứng khi hỏng','What users or CI see. Entry point of Trace bug.','Người dùng hoặc CI thấy gì. Điểm vào của Trace bug.'],cppr:['PRs in the rc','PR trong rc','PRs before the cut that change this feature. ! = skipped MP CI.','PR trước điểm cắt đổi feature này. ! = skip MP CI.']};
  const KPI=[[T('Scope PRs in the rc','PR scope trong rc'),T('Must be all; a missing one needs a cherry-pick.','Phải đủ; thiếu PR nào thì phải cherry-pick.')],[T('Ship-along','Đi kèm'),T('Not in the ROADMAP but before the cut, so they ship. Each needs a decision.','Không có trong ROADMAP nhưng trước điểm cắt nên vẫn ship. Mỗi PR cần một quyết định.')],[T('After the cut','Sau điểm cắt'),T('Only with a cherry-pick.','Chỉ vào bằng cherry-pick.')],[T('MP E2E proof','Bằng chứng MP E2E'),T('dev only runs the scheduled engine-nightly check; run the full MP suite on the rc commit.','dev chỉ chạy build định kỳ verify engine nightly; phải chạy đủ bộ MP trên commit rc.')]];
  const prLine=n=>{const p=PR[n];return p?`#${n} · ${esc(p.title)} · ${esc(p.at.slice(0,10))} · MP CI: ${mpTxt(p)}`:'#'+n;};
  function defOf(e){
    const ti=e.closest('[data-tier]');if(ti){const t=TIER[ti.dataset.tier]||{};const v=V();return[`${ti.dataset.tier} · ${t.short||''}`,`${esc((t.plain||[])[v]||'')}.<br><b>${T('Catches','Bắt được')}:</b> ${esc((t.catches||[])[v]||'')}.<br><b>${T('Runs on','Chạy trên')}:</b> ${esc((t.hw||[])[v]||'')} · ${esc((t.cost||[])[v]||'')}.<br><b>${T('Real job today','Job thật hôm nay')}:</b> ${esc((t.exists||[])[1+v]||'')}${t.job?` (${esc(t.job)})`:''}.${ti.dataset.cond==='1'?`<br><i>${T('Dashed: only when its sub-path changes.','Nét đứt: chỉ khi sub-path tương ứng đổi.')}</i>`:''}`];}
    const fc=e.closest('[data-fid]');if(fc){const f=FF[fc.dataset.fid];return[`${f.id} · ${f.name}`,`<b>${T('Step','Bước')}:</b> ${esc(f.step)} · ${esc(f.dep)}<br><b>CPU:</b> ${esc(f.cpu)}<br><b>GPU:</b> ${esc(f.gpu)}<br><b>Critical:</b> ${esc(f.crit)}<br><b>${T('When broken','Hỏng thì')}:</b> ${esc(f.risk)}<br><b>${T('Proposed gate','Gate đề xuất')}:</b> ${esc(f.gate)}`];}
    const sg=e.closest('[data-stg]');if(sg)return[T('Stage on the request path','Bước trên đường đi request'),stageTxt(+sg.dataset.stg)];
    const mk=e.closest('[data-mk]');if(mk){const p=PR[+mk.dataset.pr],a=FM[mk.dataset.aref],m={'●':T('changes the main code of','đổi code chính của'),'○':T('changes other code of','đổi code phụ của'),'△':T('changes only the tests of','chỉ đổi test của')}[mk.dataset.mk];
      return[`${mk.dataset.mk} #${mk.dataset.pr}`,`${T('This PR','PR này')} ${m} <b>${a?esc(a.code+' '+a.name):''}</b>.<br>${prLine(+mk.dataset.pr)}${p?`<br>${T('Code areas','Nhóm code')}: ${esc(Object.entries(p.a_src).map(([k,n])=>`${(FM[k]||{}).code||'–'} ${AN(k)} (${n})`).join(', '))}`:''}`];}
    const kp=e.closest('[data-kpi]');if(kp)return KPI[+kp.dataset.kpi];
    const td=e.closest('td[data-col]');if(!td)return null;const c=COL[td.dataset.col];if(!c)return null;let x='';const tr=td.closest('tr');
    if(tr&&tr.dataset.item!=null){const it=N.items[+tr.dataset.item],r=itemRow(it),col=td.dataset.col;
      x=col==='pr'||col==='mp'?it.prs.map(prLine).join('<br>'):col==='stage'?stageTxt(r.stage):col==='verdict'?r.reasons.map(y=>'• '+esc(y[1])).join('<br>'):'';}
    else if(tr&&tr.dataset.area){const a=FM[tr.dataset.area],col=td.dataset.col,r=areaRows(pickedPRs())[a.id]||{scope:[],ride:[]};
      x=col==='code'||col==='feature'?`<b>${esc(a.code+' '+a.name)}</b> · ${esc(a.group)}<br>${esc(a.what||'')}<br><code>${esc(a.code_path||a.code||'')}</code>`:col==='scope'?r.scope.map(y=>`${y.mk} ${prLine(y.p.num)}`).join('<br>'):col==='ride'?r.ride.map(y=>`${y.mk} #${y.p.num} ${esc(y.p.title)}`).join('<br>'):
        col==='tiers'?`${T('Change class','Change class')}: <b>${esc((GD.area_class||{})[a.id]||'core')}</b>`:col==='wl'?(()=>{const t=tiersOf(a.id);return[...t.req,...t.cond].filter(k=>(GD.tier_workloads||{})[k]).map(k=>`${k} → ${esc(GD.tier_workloads[k].join(', '))}`).join('<br>');})():col==='verdict'?areaVerdict(a.id,r).why.map(y=>'• '+esc(y[1])).join('<br>'):'';}
    return[T(c[0],c[1]),T(c[2],c[3])+(x?`<hr>${x}`:'')];}
  const pop=document.createElement('div');pop.className='nr-pop';pop.setAttribute('role','dialog');pop.hidden=true;document.body.append(pop);
  const hide=()=>{pop.hidden=true;};
  function show(d,x,y){pop.innerHTML=`<div class="nr-ph2"><b>${esc(d[0])}</b><button type="button" class="nr-x" aria-label="${T('Close','Đóng')}">×</button></div><div class="nr-pb">${d[1]}</div>`;pop.hidden=false;
    const r=pop.getBoundingClientRect(),m=12;pop.style.left=Math.max(m,Math.min(x+10,innerWidth-r.width-m))+'px';pop.style.top=(y+14+r.height<innerHeight-m?y+14:Math.max(m,y-r.height-10))+'px';}

  function render(){calcRide();rCockpit();rScope();rCP();rFM();rCut();}
  const inNr=e=>e.target.closest('section[data-ops^="nr-"]');
  document.addEventListener('click',e=>{
    if(e.target.closest('.nr-x'))return hide();if(e.target.closest('.nr-pop'))return;if(!inNr(e)){hide();return;}if(e.target.closest('a'))return;
    const b=e.target.closest('[data-ph],[data-goto],[data-cut],[data-pick],[data-more],[data-clear],[data-cpj],[data-cpmode],[data-cpnode]');
    if(b){hide();const d=b.dataset;
      if(d.ph!=null){ckPhase=+d.ph;return rCockpit();}
      if(d.goto){if(d.pick!=null){pick=d.pick==='ride'?'ride':+d.pick;cpMode='scope';cpNode=null;rCP();rFM();}if(d.cpmode){cpMode=d.cpmode;rCP();}const t=sec(d.goto);if(t)t.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});return;}
      if(d.cut!=null){cut=+d.cut;rideLimit=10;return render();}
      if(d.pick!=null){pick=d.pick==='all'?null:d.pick==='ride'?'ride':+d.pick;selArea=null;cpNode=null;rCP();rFM();return rCut();}
      if(d.more){rideLimit+=10;return rCut();}
      if(d.clear){selArea=null;rFM();return rCut();}
      if(d.cpj){cpJ=d.cpj;cpNode=null;return rCP();}
      if(d.cpmode){cpMode=d.cpmode;cpNode=null;return rCP();}
      if(d.cpnode!=null){if(e.target.closest('[data-fid]')){const df=defOf(e.target);if(df)show(df,e.clientX,e.clientY);return;}const i=+d.cpnode;cpNode=cpNode===i?null:i;return rCP();}}
    const df=defOf(e.target);if(df)show(df,e.clientX,e.clientY);else hide();
    const row=e.target.closest('tr.nr-arow');if(row&&row.dataset.area!==selArea){selArea=row.dataset.area;rFM();rCut();}
  });
  document.addEventListener('change',e=>{if(e.target.id==='nrPick'){const v=e.target.value;pick=v==='all'?null:v==='ride'?'ride':+v;selArea=null;cpNode=null;rCP();rFM();rCut();}
    if(e.target.id==='nrBug'){cpBug=e.target.value||null;cpNode=null;if(cpBug&&CP){const j=CP.journeys.find(j=>CP.node_f[j.id].some(fs=>fs.includes(cpBug)));if(j)cpJ=j.id;}rCP();}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')hide();});
  addEventListener('scroll',hide,{passive:true});
  render();addEventListener('langchange',()=>{hide();render();});
})();
</script>
