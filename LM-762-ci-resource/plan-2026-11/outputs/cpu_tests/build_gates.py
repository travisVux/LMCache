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
from gates import AREA_CLASS, CLASSES, DESC, JOBS, TIER_WORKLOADS, TIERS, WORKLOADS

from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")

GATES_HTML = r"""
<!-- GATES:HTML:START -->
<section class="card" data-view="gates" data-tab="guide">
  <div class="head"><h2>1 · Merge &amp; release gates</h2>
  <p class="sub">Every check a PR meets, grouped by what it blocks. Defined once in <code>gates.py</code>.</p></div>
  <table class="gate" id="gJobs"><thead><tr><th>Job</th><th>Blocks</th><th>Tier</th><th>Runs on</th><th>What it runs</th><th class="r">Time</th></tr></thead><tbody></tbody></table>
</section>
<!-- GATES:HTML:END -->
"""

IMPACT_HTML = r"""
<!-- GATES:IMPACT:START -->
<section class="card" data-view="gates" data-tab="tiers">
  <div class="head"><h2>5 · Change impact: feature area → what must run</h2>
  <p class="sub">Pick a feature area (same numbering as the Unit-test view).</p></div>
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
.tierchip.cond{background:transparent;border:1.5px dashed var(--text-muted);color:var(--text-primary)}
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
  const chip=(id,cond)=>el('span',{class:'tierchip t-'+TN[id].color+(cond?' cond':''),title:TN[id].name},id);
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
    GD.tiers.forEach(t=>{const tr=el('tr'),k=el('td',{class:'k'});k.append(chip(t.id),document.createTextNode(' '+t.name));
      const ex=el('td');ex.appendChild(el('code',{},t.example));const st=el('td');st.appendChild(el('span',{class:'pill '+t.exists[0]},t.exists[1+v]));
      tr.append(k,el('td',{},t.plain[v]),el('td',{},t.hw[v]+' · '+t.cost[v]),el('td',{},t.catches[v]),ex,st);tb.appendChild(tr);});}

  function impactOf(aid){const cls=GD.area_class[aid]||'core';const C=GD.classes.find(c=>c.id===cls);
    const req=Object.entries(C.tiers).filter(([,x])=>x===1).map(([k])=>k),cond=Object.entries(C.tiers).filter(([,x])=>x===2).map(([k])=>k);
    const wl=[];[...req,...cond].forEach(t=>(GD.tier_workloads[t]||[]).forEach(w=>{if(!wl.includes(w))wl.push(w);}));return{cls,C,req,cond,wl};}

  function impact(){const sel=$('#impA'),out=$('#impOut');if(!sel)return;const v=V();
    if(!sel.dataset.init){sel.dataset.init=1;CD.areas.forEach(a=>sel.appendChild(el('option',{value:a.id},`${AC[a.id]} · ${a.name}`)));sel.addEventListener('change',impact);}
    const a=CD.areas.find(x=>x.id===sel.value)||CD.areas[0],I=impactOf(a.id);out.replaceChildren();
    const box=(title)=>{const b=el('div',{class:'box'});b.appendChild(el('h4',{},title));out.appendChild(b);return b;};
    const b1=box(v?'1 · Loại thay đổi':'1 · Change class');b1.append(el('code',{},I.cls),el('div',{class:'sd'},I.C.paths));
    const b2=box(v?'2 · Tầng phải qua':'2 · Tiers to pass');const ch=el('div',{class:'chips'});I.req.forEach(t=>ch.appendChild(chip(t)));I.cond.forEach(t=>ch.appendChild(chip(t,true)));b2.appendChild(ch);
    if(I.cond.length)b2.appendChild(el('div',{class:'sd'},v?'nét đứt = chỉ khi sub-path khớp':'dashed = only when the sub-path matches'));
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
    const full=it[v?2:0],first=full.split(/(?<=[.!?]) /)[0],rest=full.slice(first.length).trim();
    const p=el('div');p.append(el('b',{},v?'Mục đích':'Purpose'),document.createTextNode(first));b.append(p);
    const more=el('details',{class:'sdmore'});more.appendChild(el('summary',{},v?'Thêm':'More'));if(rest)more.appendChild(el('div',{},rest));more.appendChild(el('div',{class:'sk'},it[v?3:1]));
    if(it[4])more.appendChild(el('div',{class:'sd'},(v?'Dữ liệu: ':'Data: ')+it[v?5:4]));b.appendChild(more);});}

  // descriptions on/off switch in the nav (remembered)
  const row=document.querySelector('.vnav .row'),all=row&&row.querySelector('label.all');
  if(row&&!document.getElementById('vDesc')){let on=true;try{on=localStorage.getItem('ciMapDesc')!=='0';}catch(e){}
    const lab=el('label',{class:'all'}),cb=el('input',{type:'checkbox',id:'vDesc'});cb.checked=on;lab.append(cb,document.createTextNode('Descriptions'));row.insertBefore(lab,all||null);
    const ap=()=>{document.body.classList.toggle('nodesc',!cb.checked);try{localStorage.setItem('ciMapDesc',cb.checked?'1':'0');}catch(e){}};cb.addEventListener('change',ap);ap();}

  const renderAll=()=>{jobs();gloss();impact();fmLinks();wlm();desc();};
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
    for h2 in ("2 · Early-fail staircase (proposed)</h2>", "3 · What L0 … Full mean</h2>", "4 · Change class → required tiers</h2>"):
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
                workloads=WORKLOADS, desc={v: {str(k): x for k, x in d.items()} for v, d in DESC.items()})
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
    GDL = "const GD=JSON.parse(document.getElementById('gatesData').textContent);"
    page = sub_block(page, "  const steps=[", "\n  const st=$('#stairs')",
                     "  " + GDL + "\n  const CCOL={cpu:'series-3',gpu:'series-1',full:'series-2'};\n"
                     "  const steps=GD.tiers.filter(t=>t.h).sort((a,b)=>a.h-b.h).map(t=>({id:t.id,name:t.name,hw:t.hw[0],cost:t.cost[0],h:t.h,c:CCOL[t.color],d:(t.job?'Today: '+t.job+'. ':'Not a job today. ')+t.catches[0]}));",
                     "steps")
    page = sub_block(page, "  const tiers=['L0 lint'", "\n  const m=$('#matrix')",
                     "  const tiers=GD.tiers.map(t=>t.short);\n  // 1 = required, 2 = conditional (gates.py CLASSES)\n"
                     "  const rows=GD.classes.map(c=>[c.id,c.paths,c.prs,c.gpumin,GD.tiers.map(t=>c.tiers[t.id]||0)]);",
                     "matrix")
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
