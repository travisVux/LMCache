"""Restructure 06_PR_TO_CI_VISUAL.html into 3 views and wire them to gates.py (idempotent).

Views: gates (Gates & tiers, shared) · cpu (Unit tests) · gpu (E2E workloads).
- Injects gates.py data, the Gates view sections, the E2E workload matrix, and one JS block that
  renders jobs, tier glossary, impact lookup, workload matrix, section descriptions and cross-links.
- Rewires the old hard-coded JS arrays (staircase steps, class matrix, workload bars, mindmap
  classes) to read from gates.py, so tiers / gates are defined once.
Run after build_page.py (build_page calls it).
"""
import json
import re

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # sibling modules also under python -I
from gates import AREA_CLASS, CLASSES, DESC, JOBS, TIER_WORKLOADS, TIERS, WL_COST, WORKLOADS

from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")

GATES_HTML = r"""
<!-- GATES:HTML:START -->
<section class="card" data-view="gates" data-tab="guide">
  <div class="head"><h2>1 · Merge &amp; release gates</h2>
  <p class="sub">Every check a PR meets on dev today, grouped by what it blocks.</p></div>
  <table class="gate" id="gJobs"><thead><tr><th>Job</th><th>Blocks</th><th>Tier</th><th>Runs on</th><th>What it runs</th><th class="r">Time</th></tr></thead><tbody></tbody></table>
</section>
<!-- GATES:HTML:END -->
"""

IMPACT_HTML = r"""
<!-- GATES:IMPACT:START -->
<section class="card" data-view="gates" data-tab="tiers">
  <div class="head"><h2>5 · Change impact: feature area → what must run</h2>
  <p class="sub">Pick a feature area (same numbering as the Unit-test view) to see its P8 target tiers.</p></div>
  <div class="ex-bar"><select id="impA" aria-label="Feature area"></select></div>
  <div class="imp" id="impOut"></div>
</section>
<!-- GATES:IMPACT:END -->
"""

WLM_HTML = r"""
<!-- GATES:WLM:START -->
<section class="card" data-view="gpu" data-tab="tiers">
  <div class="head"><h2>3 · E2E workload matrix</h2>
  <p class="sub">One row per MP workload: what it checks, what only it catches, where it moves.</p></div>
  <div style="overflow-x:auto"><table class="wlm" id="wlm"><thead><tr><th>Workload</th><th class="r">GPU</th><th class="r">GPU-min / 30 d</th><th>What it checks</th><th>Only it catches</th><th>Already covered by</th><th>Moves to</th></tr></thead><tbody></tbody></table></div>
</section>
<!-- GATES:WLM:END -->
"""

CSS = r"""
/* GATES:CSS:START */
.gate tr.grp td{background:var(--surface-2);font-weight:700;font-size:11px;color:var(--text-secondary);letter-spacing:.04em;text-transform:uppercase;padding:6px 8px}
.tierchip{display:inline-block;font:11px ui-monospace,Consolas,monospace;font-weight:700;padding:1px 6px;border-radius:5px;color:#fff}
.tierchip.t-cpu{background:var(--series-3)}.tierchip.t-gpu{background:var(--series-1)}.tierchip.t-full{background:var(--series-2)}
/* planned (P8) tier = hollow + dashed in its own colour; applied tier = solid. "?" suffix = only when the sub-path matches */
.tierchip.plan{background:transparent;color:var(--text-primary);border:1.5px dashed var(--series-3);padding:0 5px}
.tierchip.plan.t-gpu{border-color:var(--series-1)}.tierchip.plan.t-full{border-color:var(--series-2)}
.stepcol.planned .step{background:transparent!important;border:2px dashed var(--c);border-bottom:none}
.stepcol.planned .steplab{opacity:.8}
.planpill{display:inline-block;margin-top:3px;font-size:10px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;padding:0 6px;border-radius:999px;border:1px dashed var(--text-muted);color:var(--text-secondary)}
.gloss tr.grp td{background:var(--surface-2);font-weight:700;font-size:11px;color:var(--text-secondary);letter-spacing:.04em;text-transform:uppercase;padding:6px 8px}
.gloss tr.planned td{color:var(--text-secondary)}
.matrix th.plan{border-bottom:2px dashed var(--text-muted);color:var(--text-muted);font-style:italic}
.matrix td.plan{background:repeating-linear-gradient(135deg,transparent 0 6px,color-mix(in oklab,var(--text-muted) 9%,transparent) 6px 8px)}
.matrix td.plan .dot{opacity:.55}
.legend .hatch{display:inline-block;width:14px;height:12px;border:1px dashed var(--text-muted);vertical-align:middle;margin-right:4px;background:repeating-linear-gradient(135deg,transparent 0 3px,color-mix(in oklab,var(--text-muted) 25%,transparent) 3px 5px)}
.imp{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:6px}
.imp .box{border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:12.5px;background:var(--surface-1)}
.imp .box h4{margin:0 0 6px;font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em}
.imp .box .chips{display:flex;flex-wrap:wrap;gap:4px}
.imp .box ul{margin:0;padding-left:16px}
.imp a,.impline a,.xlink{color:var(--series-1);cursor:pointer;text-decoration:none}
.imp a:hover,.impline a:hover,.xlink:hover{text-decoration:underline}
.impline{margin-top:10px;font-size:12px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.impline b{color:var(--text-secondary);font-weight:650}
.wlm th,.wlm td{padding:6px 8px;border-bottom:1px solid var(--grid);font-size:12px;text-align:left;vertical-align:top}
.wlm th{color:var(--text-secondary);font-weight:600;font-size:11.5px}
.wlm td.n{font:12px ui-monospace,Consolas,monospace;font-weight:600;white-space:nowrap}
.wlm td.r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.wlm td.only{color:var(--text-primary);font-weight:600}
.wlm td.cov{color:var(--text-secondary)}
.ffc .sd,.imp .sd{margin-top:4px;color:var(--text-muted);font-size:11.5px}
.imp .warn{margin-top:4px;color:var(--warning);font-size:12px;font-weight:600}
.gloss .pill{white-space:normal;display:inline-block;max-width:220px}
@media (max-width:700px){table.gloss{display:block;overflow-x:auto;max-width:100%}}
.gloss td:nth-child(5) code{white-space:normal;word-break:break-word}
.sdesc .sd{margin-top:3px;color:var(--text-muted);font-size:11.5px}
@media (max-width:980px){.imp{grid-template-columns:1fr 1fr}}
/* GATES:CSS:END */
"""

JS = r"""
<!-- GATES:JS:START -->
<script>
(function(){
  const GD=JSON.parse(document.getElementById('gatesData').textContent);
  const CD=JSON.parse(document.getElementById('cpuData').textContent);
  const $=s=>document.querySelector(s);
  const el=(t,a={},x)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==='style')e.style.cssText=v;else if(k==='class')e.className=v;else e.setAttribute(k,v);}if(x!==undefined)e.textContent=x;return e;};
  const V=()=>(window.I18N&&I18N.lang==='vi')?1:0;
  const fmt=n=>Number(n).toLocaleString('en-US');
  const TN=Object.fromEntries(GD.tiers.map(t=>[t.id,t]));
  const PL=id=>TN[id].status==='planned';
  const chip=(id,cond)=>el('span',{class:'tierchip t-'+TN[id].color+(PL(id)?' plan':''),title:TN[id].name+(PL(id)?' · planned (P8)':' · applied today')+(cond?' · only when the sub-path matches':'')},id+(cond?'?':''));
  const GL={merge:['blocks merge','chặn merge','req'],release:['blocks release','chặn release','rel'],advisory:['advisory','tham khảo','adv']};
  // area numbering identical to the Unit-test view (group.index)
  const AC={};{let gi=0,ii=0,last=null;CD.areas.forEach(a=>{if(a.group!==last){last=a.group;gi++;ii=0;}AC[a.id]=gi+'.'+(++ii);});}

  function jobs(){const tb=$('#gJobs tbody');if(!tb)return;const v=V();tb.replaceChildren();
    [['merge','Blocks merge','Chặn merge'],['release','Blocks release (not merge)','Chặn release (không chặn merge)'],['advisory','Advisory only','Chỉ tham khảo']].forEach(([g,en,vn])=>{
      const js=GD.jobs.filter(j=>j.gate[0]===g);if(!js.length)return;
      const h=el('tr',{class:'grp'});h.appendChild(el('td',{colspan:'6'},v?vn:en));tb.appendChild(h);
      js.forEach(j=>{const tr=el('tr'),c1=el('td'),c2=el('td'),c3=el('td');c1.append(el('b',{},j.name),el('small',{},j.where));
        j.gate.forEach(x=>c2.appendChild(el('span',{class:'badge '+GL[x][2]},GL[x][v])));if(j.tier)c3.appendChild(chip(j.tier));
        tr.append(c1,c2,c3,el('td',{},j.runs[v]),el('td',{},j.what[v]),el('td',{class:'r'},j.time[v]));tb.appendChild(tr);});});}

  function gloss(){const tb=$('#tierGloss');if(!tb)return;const v=V();tb.replaceChildren();
    [['applied','Applied today (a job runs it)','Đang áp dụng (có job chạy)'],['planned','Planned (P8 target, no job yet)','Kế hoạch (mục tiêu P8, chưa có job)']].forEach(([s,en,vn])=>{
    const h=el('tr',{class:'grp'});h.appendChild(el('td',{colspan:'6'},v?vn:en));tb.appendChild(h);
    GD.tiers.filter(t=>t.status===s).forEach(t=>{const tr=el('tr',{class:s}),k=el('td',{class:'k'});k.append(chip(t.id),document.createTextNode(' '+t.name));
      const ex=el('td');ex.appendChild(el('code',{},t.example));const st=el('td');st.appendChild(el('span',{class:'pill '+t.exists[0]},t.exists[1+v]));
      tr.append(k,el('td',{},t.plain[v]),el('td',{},t.hw[v]+' · '+t.cost[v]),el('td',{},t.catches[v]),ex,st);tb.appendChild(tr);});});}

  function impactOf(aid){const cls=GD.area_class[aid]||'core';const C=GD.classes.find(c=>c.id===cls);
    const req=Object.entries(C.tiers).filter(([,x])=>x===1).map(([k])=>k),cond=Object.entries(C.tiers).filter(([,x])=>x===2).map(([k])=>k);
    const wl=[];[...req,...cond].forEach(t=>(GD.tier_workloads[t]||[]).forEach(w=>{if(!wl.includes(w))wl.push(w);}));return{cls,C,req,cond,wl};}

  function impact(){const sel=$('#impA'),out=$('#impOut');if(!sel)return;const v=V();
    if(!sel.dataset.init){sel.dataset.init=1;CD.areas.forEach(a=>sel.appendChild(el('option',{value:a.id},`${AC[a.id]} · ${a.name}`)));sel.addEventListener('change',impact);}
    const a=CD.areas.find(x=>x.id===sel.value)||CD.areas[0],I=impactOf(a.id);out.replaceChildren();
    const box=(title)=>{const b=el('div',{class:'box'});b.appendChild(el('h4',{},title));out.appendChild(b);return b;};
    const b1=box(v?'1 · Loại thay đổi':'1 · Change class');b1.append(el('code',{},I.cls),el('div',{class:'sd'},I.C.paths));
    const b2=box(v?'2 · Tầng mục tiêu (P8)':'2 · Target tiers (P8)');const ch=el('div',{class:'chips'});I.req.forEach(t=>ch.appendChild(chip(t)));I.cond.forEach(t=>ch.appendChild(chip(t,true)));b2.appendChild(ch);
    b2.appendChild(el('div',{class:'sd'},v?'Nét đứt = kế hoạch, chưa chạy · ? = chỉ khi sub-path khớp. Hôm nay: 4 check bắt buộc + MP smoke cho mọi PR code ready.':'Dashed = planned, not running yet · ? = only when the sub-path matches. Today: the 4 required checks + MP smoke on every ready code PR.'));
    const b3=box(v?'3 · Unit test bảo vệ':'3 · Unit tests guarding it');b3.appendChild(el('div',{},`${fmt(a.passed)} ${v?'test trong':'tests in'} ${a.files} ${v?'file':'files'}`));
    if(a.notrun)b3.appendChild(el('div',{class:'sd'},`+${a.notrun} ${v?'file chỉ chạy trên GPU pod':'files only on the GPU pod'}`));
    const nv=(a.sm||{})['vLLM import']||0;if(nv)b3.appendChild(el('div',{class:'warn'},v?`⚠ ${nv}/${a.files} file import vLLM → chỉ chạy ở GHA Test, không cổng merge nào bao phủ`:`⚠ ${nv}/${a.files} files import vLLM → run only on GHA Test, no merge gate covers them`));
    const l3=el('a',{href:'#cpu/explore'},v?'Mở trong Khám phá →':'Open in the explorer →');l3.addEventListener('click',e=>{e.preventDefault();const q=document.getElementById('exQ');if(q)q.value='';const s=document.getElementById('exA');if(s){s.value=a.id;s.dispatchEvent(new Event('input'));}window.vizNav&&vizNav.show('cpu','explore');});b3.appendChild(l3);
    const b4=box(v?'4 · Workload E2E':'4 · E2E workloads');if(I.wl.length){const ul=el('ul');I.wl.forEach(w=>ul.appendChild(el('li',{},w)));b4.appendChild(ul);}else b4.appendChild(el('div',{class:'sd'},v?'không có (chưa cần GPU E2E)':'none (no GPU E2E needed)'));
    const l4=el('a',{href:'#gpu/tiers'},v?'Ma trận workload →':'Workload matrix →');l4.addEventListener('click',e=>{e.preventDefault();window.vizNav&&vizNav.show('gpu','tiers');});b4.appendChild(l4);}

  function fmLinks(){const v=V();const dets=[...document.querySelectorAll('#fm tr.det')];dets.forEach((d,i)=>{const a=CD.areas[i];if(!a)return;const I=impactOf(a.id);
    const cell=d.querySelector('td');let ln=cell.querySelector('.impline');if(ln)ln.remove();ln=el('div',{class:'impline'});
    ln.append(el('b',{},v?'Đổi code ở đây →':'Change here →'),el('code',{},I.cls),document.createTextNode('→'));I.req.forEach(t=>ln.appendChild(chip(t)));I.cond.forEach(t=>ln.appendChild(chip(t,true)));
    if(I.wl.length)ln.appendChild(document.createTextNode('→ '+I.wl.join(', ')));
    const a2=el('a',{},v?'Xem tác động →':'Impact →');a2.addEventListener('click',ev=>{ev.stopPropagation();const s=$('#impA');if(s){s.value=a.id;impact();}window.vizNav&&vizNav.show('gates','tiers');});ln.appendChild(a2);cell.appendChild(ln);});}

  function wlm(){const tb=$('#wlm tbody');if(!tb)return;const v=V();tb.replaceChildren();const G={cpu:'series-3',gpu:'series-1',cond:'series-2'};
    GD.workloads.forEach(w=>{const tr=el('tr'),h=el('td');h.append(el('i',{class:'sw',style:`display:inline-block;margin-right:6px;background:var(--${G[w.group]})`}),document.createTextNode(w.home));
      tr.append(el('td',{class:'n'},w.name),el('td',{class:'r'},w.gpus),el('td',{class:'r'},w.gpumin?fmt(w.gpumin):'0'),el('td',{},w.checks[v]),el('td',{class:'only'},w.only[v]||'—'),el('td',{class:'cov'},w.covered[v]||'—'),h);tb.appendChild(tr);});}

  function desc(){const v=V();document.querySelectorAll('section[data-view]').forEach(sec=>{const h=sec.querySelector('h2'),hd=sec.querySelector('.head');if(!h||!hd)return;
    const m=h.textContent.match(/^(\d+)/),it=m&&GD.desc[sec.dataset.view]&&GD.desc[sec.dataset.view][m[1]];let b=hd.querySelector('.sdesc');
    if(!it){if(b)b.remove();return;}if(!b){b=el('div',{class:'sdesc'});hd.appendChild(b);}b.replaceChildren();
    // gates.py DESC: (takeaway EN, takeaway VI, data EN, data VI). The <p class="sub"> above already says what the section is.
    const p=el('div',{class:'sk'});p.append(el('b',{},v?'Điểm chính':'Key takeaway'),document.createTextNode(it[v]));b.append(p);
    if(it[2])b.appendChild(el('div',{class:'sd'},(v?'Dữ liệu: ':'Data: ')+it[2+v]));});}

  // descriptions on/off switch in the nav (remembered)
  const row=document.querySelector('.vnav .row'),all=row&&row.querySelector('label.all');
  if(row&&!document.getElementById('vDesc')){let on=false;try{on=localStorage.getItem('ciMapHelp')==='1';}catch(e){}   // round 3: help text, off by default
    const lab=el('label',{class:'all'}),cb=el('input',{type:'checkbox',id:'vDesc'});cb.checked=on;lab.append(cb,document.createTextNode('Help text'));row.insertBefore(lab,all||null);
    const ap=()=>{document.body.classList.toggle('nodesc',!cb.checked);try{localStorage.setItem('ciMapHelp',cb.checked?'1':'0');}catch(e){}};cb.addEventListener('change',ap);ap();}

  // round 2 G4: window + reconciliation chip next to the workload GPU-min values (gates.py WL_COST, read from P1 at build time)
  function wlWin(){const W=GD.wl_cost;if(!W)return;const v=V(),win=`${W.since} → ${W.last}`;
    const th=document.querySelector('#wlm thead th:nth-child(3)');if(th)th.textContent=(v?'GPU-phút · ':'GPU-min · ')+win;
    const put=(anchor,id,txt)=>{const a=$(anchor);if(!a)return;let n=document.getElementById(id);if(!n){n=el('p',{class:'note',id});a.after(n);}n.textContent=txt;};
    const oth=W.other.length?(v?` · chưa có trong bảng: ${W.other.join(', ')}`:` · not in the chart: ${W.other.join(', ')}`):'';
    const rec=v?`Khung ${win} (P1, UTC) · ${W.n_shown} workload = ${fmt(W.shown)} GPU-phút · cả ${W.n_all} workload = ${fmt(W.all)} · tổng PR của MP ${fmt(W.pr_total)} GPU-phút = ${fmt(W.pr_total_h)} GPU-giờ (bảng chi phí CI)${oth}`
               :`Window ${win} (P1, UTC) · ${W.n_shown} workloads = ${fmt(W.shown)} GPU-min · all ${W.n_all} workloads = ${fmt(W.all)} · MP PR total ${fmt(W.pr_total)} GPU-min = ${fmt(W.pr_total_h)} GPU-h (CI cost home)${oth}`;
    put('#wlm','wlWinT',rec);put('#bars + details','wlWinB',rec);
    if(W.p8&&W.p8.gpu_min)put('#compare','wlWinC',v?`"Hôm nay" = bản chụp P8 (${W.p8.date}, ${W.p8.prs} PR, ${win}): ${fmt(W.p8.gpu_min)} GPU-phút. Bản xuất P1 hiện tại: ${fmt(W.pr_total)} GPU-phút cùng khung.`
      :`"Today" = P8 snapshot (${W.p8.date}, ${W.p8.prs} PRs, ${win}): ${fmt(W.p8.gpu_min)} GPU-min. Current P1 export: ${fmt(W.pr_total)} GPU-min for the same window.`);}

  const renderAll=()=>{jobs();gloss();impact();fmLinks();wlm();wlWin();desc();};
  addEventListener('langchange',renderAll);renderAll();
})();
</script>
<!-- GATES:JS:END -->
"""


def put(page, start, end, block, anchor):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:]


def _flex(s):
    """Regex for s that ignores whitespace between tokens (the page may be reformatted by an editor)."""
    return r"\s*".join(re.escape(t) for t in re.findall(r"\w+|[^\w\s]", s))


def sub_block(page, start_pat, end_pat, new, label):
    """Replace text from start_pat up to (not incl.) end_pat; skip if `new` already present.
    start_pat must begin a line with its exact indent, so '    const steps=[' (another block) never matches '  const steps=['.
    Never crashes on a changed page: a missing end prints a skip line and leaves the page as it is."""
    if new in page or re.search(_flex(new), page):
        return page
    m = re.search(r"(?m)^" + re.escape(start_pat.lstrip("\n")), page)
    if not m:
        print("skip (not found):", label)
        return page
    i = m.start()
    j = page.find(end_pat, i)
    if j < 0:
        e = re.compile(_flex(end_pat)).search(page, i)
        if not e:
            print("skip (end not found):", label)
            return page
        j = e.start()
    return page[:i] + new + page[j:]


def retag(page, h2_old, h2_new, view, tab):
    """Change one GPU-static section: heading number and data-view / data-tab."""
    i = page.find(h2_old)
    if i < 0:
        return page
    s = page.rfind("<section", 0, i)
    tag_end = page.index(">", s) + 1
    tag = re.sub(r'data-view="\w+" data-tab="\w+"', f'data-view="{view}" data-tab="{tab}"', page[s:tag_end])
    page = page[:s] + tag + page[tag_end:]
    return page.replace(h2_old, h2_new, 1)


def swap(page, old, new):
    """Replace a static page fragment once (whitespace-tolerant, the page is editor-formatted); no-op when already done."""
    if new in page:
        return page
    m = re.search(_flex(old), page)
    if not m:
        print("skip (not found):", old[:60])
        return page
    return page[:m.start()] + new + page[m.end():]


H2_STAIRS = "2 · Early-fail staircase: applied today vs planned"
H2_MATRIX = "4 · Change class → target tiers (P8 plan)"
# static parts of §2–§4 (they live in the page, not in a generated block)
STATIC_SWAPS = [
    ("<h2>2 · Early-fail staircase (proposed)</h2>", f"<h2>{H2_STAIRS}</h2>"),
    ('<p class="sub">A PR climbs only as high as its change class needs. Height = relative cost. <span class="badge req">required today</span> jobs are named in the tooltip.</p>',
     '<p class="sub">Test tiers by relative cost: solid = runs today, dashed = planned (P8).</p>'),
    ('<span><i class="sw" style="background:var(--series-3);display:inline-block"></i>CPU only (every code PR)</span>',
     '<span><i class="sw" style="background:var(--series-3);display:inline-block"></i>CPU</span>'),
    ('<span><i class="sw" style="background:var(--series-1);display:inline-block"></i>GPU: L1 unit pod required today; others only on path match</span>',
     '<span><i class="sw" style="background:var(--series-1);display:inline-block"></i>GPU</span>'),
    ('<span><i class="sw" style="background:var(--series-2);display:inline-block"></i>Full: label or nightly</span>',
     '<span><i class="sw" style="background:var(--series-2);display:inline-block"></i>Full: weekly or label</span><span><i class="hatch"></i>dashed = planned (P8), no job yet</span>'),
    ('<p class="sub">Lower = cheaper and earlier. A failing step stops the climb.</p>',
     '<p class="sub">What each tier is and catches: applied tiers first, then planned (P8) ones.</p>'),
    ("<h2>4 · Change class → required tiers</h2>", f"<h2>{H2_MATRIX}</h2>"),
    ('<p class="sub">Union of tiers over the classes a PR touches (P8).</p>',
     '<p class="sub">P8 target tiers per change class; hatched columns are planned tiers that do not run today.</p>'),
    ('<div class="legend"><span><i class="dot"></i>required</span><span><i class="ring"></i>only when the matching sub-path changes</span></div>',
     '<div class="legend"><span><i class="dot"></i>target: required</span><span><i class="ring"></i>only when the matching sub-path changes</span><span><i class="hatch"></i>planned tier, not running today</span></div>'),
    # mindmap (E2E view → 8): dev CI on 2026-11-27
    ("'One function or class alone, fake inputs. GHA test.yml py3.10–3.14, not required'",
     "'One function or class alone, fake inputs. GHA test.yml py3.11–3.14 (drafts: 3.12), not required'"),
    ("'Required: Buildkite cpu_e2e_validation (in k3-multiprocess-test), ~3.6 min. Same script in GHA cpu_device.yml (advisory)'",
     "'Buildkite cpu_e2e_validation in MP smoke (k3-multiprocess-smoke, every ready PR), ~3.6 min. Same script in GHA cpu_device.yml, 6 legs (advisory)'"),
]

STEPS_JS = """      const steps = GD.tiers.filter(t => t.h).sort((a, b) => a.h - b.h).map(t => ({ id: t.id, name: t.name, hw: t.hw[0], cost: t.cost[0], h: t.h, c: CCOL[t.color], p: t.status === 'planned', d: (t.status === 'planned' ? 'Planned (P8), no job today. ' : 'Today: ' + t.job + '. ') + t.catches[0] }));
      const st = $('#stairs'), ax = $('#stairsAxis');
      steps.forEach(s => {
        const col = el('div', { class: 'stepcol' + (s.p ? ' planned' : '') });
        const lab = el('div', { class: 'steplab' }); lab.appendChild(el('b', {}, s.name)); lab.appendChild(document.createTextNode(s.hw + ' · ' + s.cost)); if (s.p) { lab.appendChild(document.createElement('br')); lab.appendChild(el('span', { class: 'planpill' }, 'planned')); }
        const d = el('div', { class: 'step', style: `height:${s.h * 0.62}%;--c:var(--${s.c});background:var(--${s.c})`, 'aria-label': s.name + ', ' + s.hw + ', ' + s.cost + (s.p ? ', planned' : '') });
        bindTip(d, s.name + ' · ' + s.hw, s.cost, s.d, `var(--${s.c})`);
        col.appendChild(lab); col.appendChild(d); st.appendChild(col);
        ax.appendChild(el('div', {}, s.id));
      });
"""

MATRIX_JS = """      // P8 columns only (MP smoke is a today-only tier); 1 = required, 2 = conditional (gates.py CLASSES); hatched = planned tier
      const TT = GD.tiers.filter(t => t.p8 !== false), tiers = TT.map(t => t.short);
      const rows = GD.classes.map(c => [c.id, c.paths, c.prs, c.gpumin, TT.map(t => c.tiers[t.id] || 0)]);
      const m = $('#matrix');
      const thead = el('thead'), hr = el('tr');
      hr.appendChild(el('th', {}, 'Change class'));
      hr.appendChild(el('th', {}, 'PRs / 100'));
      TT.forEach(t => hr.appendChild(el('th', t.status === 'planned' ? { class: 'plan', title: 'planned (P8), not running today' } : {}, t.short)));
      hr.appendChild(el('th', {}, 'MP GPU-min / build'));
      thead.appendChild(hr); m.appendChild(thead);
      const tb = el('tbody');
      rows.forEach(r => {
        const tr = el('tr');
        const c = el('td', { class: 'cls' }, r[0]); c.appendChild(el('small', {}, r[1])); tr.appendChild(c);
        tr.appendChild(el('td', { class: 'num' }, String(r[2])));
        r[4].forEach((v, i) => { const pl = TT[i].status === 'planned', td = el('td', pl ? { class: 'plan' } : {}); if (v) { const s = el('i', { class: v === 1 ? 'dot' : 'ring', 'aria-label': (v === 1 ? 'required' : 'conditional') + (pl ? ', planned' : '') }); bindTip(s, r[0] + ' → ' + tiers[i], (v === 1 ? 'required' : 'only on matching sub-path') + (pl ? ' · planned tier' : ''), null, 'var(--series-1)'); td.appendChild(s); } tr.appendChild(td); });
        tr.appendChild(el('td', { class: 'num' }, r[3]));
        tb.appendChild(tr);
      });"""


def take_section(page, h2):
    """Cut the <section> that contains h2 out of the page; return (page, section_html)."""
    i = page.find(h2)
    if i < 0:
        return page, ""
    st = page.rfind("<section", 0, i)
    en = page.index("</section>", i) + len("</section>")
    return page[:st] + page[en:], page[st:en]


def take_block(page, start, end):
    i = page.find(start)
    if i < 0:
        return page, ""
    j = page.index(end, i) + len(end)
    return page[:i] + page[j:], page[i:j]


def move_sections(page, block):
    """Reading order: Gates 1 → 2..4 (static tier sections) → 5 impact; E2E 2 → 3 matrix → 4 CPU E2E."""
    page, _ = take_block(page, "<!-- GATES:IMPACT:START -->", "<!-- GATES:IMPACT:END -->")
    page, _ = take_block(page, "<!-- GATES:WLM:START -->", "<!-- GATES:WLM:END -->")
    moved = []
    for h2 in (H2_STAIRS + "</h2>", "3 · What L0 … Full mean</h2>", H2_MATRIX + "</h2>"):
        page, sec = take_section(page, h2)
        moved.append(sec)
    # build_page re-inserts this section inside the CPU block on every run: take ALL copies, keep one
    cpue2e = ""
    while True:
        page, sec = take_section(page, "4 · CPU E2E: one script, two runners</h2>")
        if not sec:
            break
        cpue2e = cpue2e or sec
    i = page.index("<!-- GATES:HTML:END -->") + len("<!-- GATES:HTML:END -->")
    page = page[:i] + "\n" + "\n".join(m for m in moved if m) + "\n" + IMPACT_HTML.strip() + page[i:]
    _, e2 = take_section(page, "2 · Where one PR build's GPU time goes today</h2>")
    j = page.index(e2) + len(e2) if e2 else page.index("<!-- KPI tiles -->")
    page = page[:j] + "\n" + WLM_HTML.strip() + "\n" + cpue2e + page[j:]
    return page


def main():
    page = open(PAGE, encoding="utf-8").read()
    data = dict(jobs=JOBS, tiers=TIERS, classes=CLASSES, tier_workloads=TIER_WORKLOADS, area_class=AREA_CLASS,
                workloads=WORKLOADS, wl_cost=WL_COST, desc={v: {str(k): x for k, x in d.items()} for v, d in DESC.items()})
    dj = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    data_block = f'<!-- GATES:DATA:START -->\n<script id="gatesData" type="application/json">{dj}</script>\n<!-- GATES:DATA:END -->'
    page = put(page, "<!-- GATES:DATA:START -->", "<!-- GATES:DATA:END -->", data_block, "<!-- NAV:HTML:END -->")
    page = put(page, "<!-- GATES:HTML:START -->", "<!-- GATES:HTML:END -->", GATES_HTML, "<!-- CPU-TESTS:START -->")
    page = put(page, "/* GATES:CSS:START */", "/* GATES:CSS:END */", CSS, "@media (max-width:980px)")
    page = put(page, "<!-- GATES:JS:START -->", "<!-- GATES:JS:END -->", JS, "<!-- NAV:JS:START -->")

    # --- move the shared tier sections from the E2E view into the Gates view (and renumber) ---
    page = retag(page, "<h2>3 · Early-fail staircase (proposed)</h2>", "<h2>2 · Early-fail staircase (proposed)</h2>", "gates", "tiers")
    page = retag(page, "<h2>4 · What L0 … Full mean</h2>", "<h2>3 · What L0 … Full mean</h2>", "gates", "tiers")
    page = retag(page, "<h2>5 · Change class → required tiers</h2>", "<h2>4 · Change class → required tiers</h2>", "gates", "tiers")
    # E2E view renumber (3 = workload matrix, 4 = CPU E2E come from generated blocks)
    page = retag(page, "<h2>6 · GPU cost per MP workload, and where it moves</h2>", "<h2>5 · GPU cost per MP workload, and where it moves</h2>", "gpu", "cost")
    page = retag(page, "<h2>7 · PR GPU-min in 30 days</h2>", "<h2>6 · PR GPU-min in 30 days</h2>", "gpu", "cost")
    page = retag(page, "<h2>8 · Findings by layer</h2>", "<h2>7 · Findings by layer</h2>", "gpu", "findings")
    page = retag(page, "<h2>9 · Mindmap: PR → tier → test → check → function</h2>", "<h2>8 · Mindmap: PR → tier → test → check → function</h2>", "gpu", "explore")

    # tier glossary body -> rendered from gates.py
    # stay inside the gloss table: never let the pattern run past its own </thead> / </tbody>
    page = re.sub(r'(<table class="gloss">\s*<thead>(?:(?!</thead>).)*</thead>)\s*<tbody(?: id="tierGloss")?>(?:(?!</tbody>).)*</tbody>',
                  r'\1<tbody id="tierGloss"></tbody>', page, count=1, flags=re.S)
    # E2E findings table -> cards
    page = re.sub(r'<table class="find">.*?</table>', '<div class="ffg" id="gfind"></div>', page, count=1, flags=re.S)

    # --- old hard-coded arrays -> gates.py ---
    # staircase (§2) + matrix (§4): applied tiers solid, planned (P8) tiers dashed / hatched (gates.py TIERS status)
    page = sub_block(page, "      const steps = GD.tiers", "\n      // 4. matrix", STEPS_JS, "steps")
    page = sub_block(page, "      const tiers = GD.tiers.map(t => t.short);", "\n      m.appendChild(tb);", MATRIX_JS, "matrix")
    for old, new in STATIC_SWAPS:
        page = swap(page, old, new)
    page = sub_block(page, "  const W=[", "\n  const max=Math.max(...W.map",
                     "  const W=GD.workloads.filter(w=>w.gpumin>0).map(w=>[w.name,w.gpumin,w.group,w.home]);", "workloads")
    page = sub_block(page, "  const fb=$('#find');", "\n})();",
                     "  const fb=$('#gfind');const TB={security:'req',regression:'req',bug:'req',flake:'part','quick fix':'fix'};\n"
                     "  F.forEach(f=>{const crit=['security','regression','bug'].includes(f[3]);const c=el('div',{class:'ffc',tabindex:'0'});\n"
                     "    c.append(el('span',{class:'badge '+(TB[f[3]]||'new')},(crit?'⚠ ':'')+f[3]),el('span',{class:'tag',style:'margin-left:6px'},f[0]),el('div',{class:'t'},f[1]),el('div',{class:'a'},f[2]));\n"
                     "    const s=el('div',{class:'sd'});s.append(el('b',{},'Source'),document.createTextNode(' '),el('span',{},f[4]));c.appendChild(s);fb.appendChild(c);});",
                     "findings")
    page = sub_block(page, "  const classes=[", "\n  const tierOrder",
                     "  const classes=JSON.parse(document.getElementById('gatesData').textContent).classes.map(c=>[c.id,c.paths,Object.entries(c.tiers).map(([k,x])=>k+(x===2?'?':''))]);",
                     "mindmap classes")
    page = move_sections(page, None)
    page = re.sub(r"\n{3,}", "\n\n", page)  # cut/paste leaves blank lines; keep the file stable across rebuilds
    open(PAGE, "w", encoding="utf-8").write(page)
    views = re.findall(r'data-view="(\w+)" data-tab="(\w+)"', page)
    print("gates: views", {v: sum(1 for x in views if x[0] == v) for v in ("gates", "cpu", "gpu")})


if __name__ == "__main__":
    main()
