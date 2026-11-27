"""Research intake (PR Inspector plan, phase D): load Research App reports from a drop folder into the page.

Contract: LM-762-ci-resource/research_intake/research_report.schema.json (lmcache.research_report/v1), checked by
research_intake/validate.py (stdlib). Drop folder: research_intake/inbox/*.json. Shipped examples:
research_intake/samples/*.json (shown with a SAMPLE badge; set RESEARCH_SAMPLES=0 to hide them).
No network service: the Research App (8-GPU pipeline) only writes files; this script only reads them.

Page: Release Management -> tab "Research intake" (#obs/research), one section per report context:
  CI Validation | LMCache optimization | New product feature
Each report: title, PR (opens the PR Inspector), features, verdict, benchmark table (baseline vs candidate, delta
coloured by the metric's "better" direction), CI gates, environment, artifacts. Invalid files are listed with their
errors (file name only), never shown as reports. The PR Inspector of a PR with reports gets a "Research" button.
Output: research.json (+ <script id="researchData">). Run in build_page.py after build_pr_inspector.py.
"""
import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
INTAKE = Path(__file__).resolve().parents[3] / "research_intake"
OUT = os.path.join(HERE, "research.json")
CONTEXTS = [("ci", "CI Validation"), ("opt", "LMCache optimization"), ("feat", "New product feature")]
ANCHOR = '<section class="card ops" data-view="obs" data-tab="overlap" data-ops="overlap"></section>'

HTML = """<!-- RESEARCH:HTML:START -->
<section class="card" data-view="obs" data-tab="research" data-research="ci" id="rsCi"></section>
<section class="card" data-view="obs" data-tab="research" data-research="opt" id="rsOpt"></section>
<section class="card" data-view="obs" data-tab="research" data-research="feat" id="rsFeat"></section>
<!-- RESEARCH:HTML:END -->"""

CSS = r"""
/* RESEARCH:CSS:START */
.rs-card{border:1px solid var(--border);border-radius:12px;padding:10px 12px;margin:10px 0;overflow-wrap:anywhere}
.rs-card.focus{border-color:var(--series-2);box-shadow:0 0 0 1px var(--series-2)}
.rs-hd{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.rs-hd b{font-size:14px}
.rs-badge{font-size:10.5px;font-weight:700;border-radius:6px;padding:1px 6px;border:1px dashed var(--text-muted);color:var(--text-muted)}
.rs-v{font-size:11px;font-weight:700;border-radius:999px;padding:1px 8px;border:1px solid currentColor}
.rs-v.improves{color:var(--series-3)}.rs-v.regresses{color:var(--critical,#c0392b)}.rs-v.neutral{color:var(--text-secondary)}.rs-v.inconclusive{color:var(--text-muted)}
.rs-meta{font-size:12px;color:var(--text-secondary);display:flex;flex-wrap:wrap;gap:2px 12px;margin:4px 0}
.rs-tab{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0}
.rs-tab th,.rs-tab td{border-top:1px solid var(--border);padding:4px 6px;text-align:left}
.rs-tab td.n{text-align:right;font-variant-numeric:tabular-nums}
.rs-good{color:var(--series-3);font-weight:650}.rs-bad{color:var(--critical,#c0392b);font-weight:650}
.rs-gates{display:flex;flex-wrap:wrap;gap:4px}
.rs-empty{font-size:12.5px;color:var(--text-muted)}
.rs-rej{font-size:12px;color:var(--text-secondary);border-top:1px dashed var(--border);margin-top:8px;padding-top:6px}
@media (max-width:600px){.rs-tab{display:block;overflow-x:auto;max-width:100%}}
/* RESEARCH:CSS:END */
"""

JS = r"""
<!-- RESEARCH:JS:START -->
<script>
/* Research intake (build_research.py): reports from research_intake/inbox (+ samples), 3 contexts. Local files only. */
(function(){
  let D;try{D=JSON.parse(document.getElementById('researchData').textContent);}catch(e){D={reports:[],rejected:[{file:'researchData',errors:['not valid JSON: '+e.message]}],contexts:[]};}
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en;
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const raw=s=>`<span class="obsraw">${esc(s)}</span>`;
  const CTX={ci:['CI Validation','Kiểm chứng CI','Does a CI change keep the gates honest (same coverage, pass rate, time)?','Thay đổi CI có giữ các gate đúng (cùng độ phủ, tỷ lệ pass, thời gian) không?'],
    opt:['LMCache optimization','Tối ưu LMCache','Does the change make LMCache faster or cheaper without losing correctness?','Thay đổi có làm LMCache nhanh hơn hoặc rẻ hơn mà không mất tính đúng không?'],
    feat:['New product feature','Tính năng sản phẩm mới','Does the new feature work end to end, and what does it cost?','Tính năng mới có chạy end-to-end không, và tốn bao nhiêu?']};
  const KEY={'CI Validation':'ci','LMCache optimization':'opt','New product feature':'feat'};
  const VERD={improves:['improves','cải thiện'],regresses:['regresses','thụt lùi'],neutral:['neutral','trung tính'],inconclusive:['inconclusive','chưa kết luận']};
  const fmt=x=>Number.isInteger(x)?String(x):String(Math.round(x*100)/100);
  function metric(m){const d=m.candidate-m.baseline,pct=m.baseline?d/Math.abs(m.baseline)*100:0;const good=m.better==='higher'?d>0:d<0;
    const cls=d===0?'':good?'rs-good':'rs-bad';
    return `<tr><td>${raw(m.name)}</td><td class="n">${fmt(m.baseline)} <span class="obsraw">${esc(m.unit)}</span></td><td class="n">${fmt(m.candidate)}</td><td class="n ${cls}">${d>0?'+':''}${fmt(d)} (${pct>0?'+':''}${pct.toFixed(1)}%)</td><td>${m.better==='higher'?T('higher is better','cao hơn là tốt'):T('lower is better','thấp hơn là tốt')}</td></tr>`;}
  function card(r){const e=r.environment||{},p=r.pr;
    return `<div class="rs-card" id="rs-${esc(r.id)}" data-rs="${esc(r.id)}"><div class="rs-hd">${r.sample?`<span class="rs-badge">${T('SAMPLE','MẪU')}</span>`:''}<b class="obsraw">${esc(r.title)}</b><span class="rs-v ${esc(r.verdict)}">${esc(T(...VERD[r.verdict]))}</span></div>`+
      `<div class="rs-meta">${p?`<span>PR <a href="#" data-pi="pr:${esc(p.number)}">#${esc(p.number)}</a>${p.state?' · '+raw(p.state):''}</span>`:`<span>${T('no PR yet','chưa có PR')}</span>`}`+
      `${(r.features||[]).length?`<span>${T('features','feature')} ${r.features.map(f=>`<span class="pi-chip">${esc(f)}</span>`).join('')}</span>`:''}`+
      `<span>${esc(r.created_at.replace('T',' ').slice(0,16))} UTC</span><span>${T('run','lần chạy')} ${raw(r.source.run_id)} · ${raw(r.source.app)}${r.source.pipeline?' · '+raw(r.source.pipeline):''}</span><span>${T('file','file')} <code>${esc(r._file)}</code></span></div>`+
      `<p class="obsraw" style="margin:4px 0">${esc(r.summary)}</p>${r.hypothesis?`<p class="rs-meta">${T('Hypothesis','Giả thuyết')}: <span class="obsraw">${esc(r.hypothesis)}</span></p>`:''}`+
      `<table class="rs-tab"><thead><tr><th>${raw(r.benchmark.name)} · ${esc(r.benchmark.runs)} ${T('runs','lần chạy')}</th><th>${T('baseline','baseline')}</th><th>${T('candidate','ứng viên')}</th><th>${T('change','thay đổi')}</th><th></th></tr></thead><tbody>${r.benchmark.metrics.map(metric).join('')}</tbody></table>`+
      ((r.ci&&r.ci.gates||[]).length?`<div class="rs-gates">${T('CI gates','CI gate')}: ${r.ci.gates.map(g=>`<span class="pi-chip"><span class="obsraw">${esc(g.name)}</span> · ${esc(g.result)}</span>`).join('')}</div>`:'')+
      `<div class="rs-meta">${T('environment','môi trường')}: <span class="obsraw">${esc([e.gpus+' GPU',e.gpu_model,e.engine,e.engine_version,e.model,e.lmcache_commit].filter(Boolean).join(' · '))}</span>`+
      `${(r.artifacts||[]).map(a=>` · <a href="${esc(a.url)}" target="_blank" rel="noopener">${raw(a.label)} ↗</a>`).join('')}</div></div>`;}
  function render(){
    Object.entries(CTX).forEach(([k,c])=>{const sec=document.querySelector(`section[data-research="${k}"]`);if(!sec)return;
      const rs=D.reports.filter(r=>KEY[r.context]===k);
      sec.innerHTML=`<h2>${T('Research intake','Tiếp nhận nghiên cứu')} · ${esc(T(c[0],c[1]))} <span class="pi-why">(${rs.length})</span></h2><p class="sub">${esc(T(c[2],c[3]))} ${T('Reports come as files from the Research App (8-GPU pipeline) into','Report đến dưới dạng file từ Research App (pipeline 8 GPU) vào')} <code>research_intake/inbox/</code> ${T('and are checked against','và được kiểm tra theo')} <code>research_report.schema.json</code>.</p>`+
        (rs.length?rs.map(card).join(''):`<p class="rs-empty">${T('No report for this context yet.','Chưa có report cho context này.')}</p>`)+
        (k==='feat'&&D.rejected.length?`<div class="rs-rej">${T('Files refused by the validator (not shown)','File bị validator từ chối (không hiển thị)')}: ${D.rejected.map(x=>`<code>${esc(x.file)}</code> <span class="obsraw">(${esc(x.errors.slice(0,2).join('; '))})</span>`).join(' · ')}</div>`:'');});}
  // PR Inspector: a "Research" button when reports name this PR
  addEventListener('pirender',e=>{const d=e.detail||{};if(!d.key||!d.key.startsWith('pr:'))return;const n=+d.key.slice(3);
    const rs=D.reports.filter(r=>r.pr&&r.pr.number===n);const bar=document.querySelector('#piDrawer .pi-bar');if(!rs.length||!bar||bar.querySelector('[data-rsgo]'))return;
    const b=document.createElement('button');b.type='button';b.className='pi-btn';b.dataset.rsgo=rs[0].id;b.dataset.goto='obs/research';b.textContent=T(`Research (${rs.length})`,`Research (${rs.length})`);bar.appendChild(b);});
  document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('[data-rsgo]');if(!b)return;const id=b.dataset.rsgo;
    setTimeout(()=>{const c=document.getElementById('rs-'+id);if(c){document.querySelectorAll('.rs-card.focus').forEach(x=>x.classList.remove('focus'));c.classList.add('focus');c.scrollIntoView({block:'center'});}},80);});
  const start=()=>{render();addEventListener('langchange',render);};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
  window.RESEARCH={data:D,render};
})();
</script>
<!-- RESEARCH:JS:END -->
"""


def load_validator():
    spec = importlib.util.spec_from_file_location("research_validate", INTAKE / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:] if before else page[:i + len(anchor)] + "\n" + block.strip() + page[i + len(anchor):]


def main():
    V = load_validator()
    reports, rejected = [], []
    folders = [INTAKE / "inbox"] + ([INTAKE / "samples"] if os.environ.get("RESEARCH_SAMPLES", "1") != "0" else [])
    seen = set()
    for folder in folders:
        for f in sorted(folder.glob("*.json")):
            doc, errs = V.validate(f, folder.name)
            rel = f"{folder.name}/{f.name}"
            if errs:
                rejected.append(dict(file=rel, errors=errs[:6]))
                continue
            if doc["id"] in seen:
                rejected.append(dict(file=rel, errors=[f"duplicate id {doc['id']}"]))
                continue
            seen.add(doc["id"])
            doc["_file"] = rel
            reports.append(doc)
    reports.sort(key=lambda r: r["created_at"], reverse=True)
    data = dict(made=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), schema="lmcache.research_report/v1",
                contexts=[c for _, c in CONTEXTS], reports=reports, rejected=rejected)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, allow_nan=False)
    page = open(PAGE, encoding="utf-8").read()
    if "PI:JS:END" not in page:
        raise SystemExit("build_research: run build_pr_inspector.py first")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    page = put(page, "<!-- RESEARCH:HTML:START -->", "<!-- RESEARCH:HTML:END -->", HTML, ANCHOR, before=False)
    page = put(page, "/* RESEARCH:CSS:START */", "/* RESEARCH:CSS:END */", CSS, "</style>")
    page = put(page, "<!-- RESEARCH:JS:START -->", "<!-- RESEARCH:JS:END -->",
               f'<!-- RESEARCH:JS:START -->\n<script id="researchData" type="application/json">{blob}</script>\n' + JS.strip().split("\n", 1)[1],
               "<!-- PIKB:JS:END -->", before=False)
    open(PAGE, "w", encoding="utf-8").write(page)
    by = {c: sum(1 for r in reports if r["context"] == c) for _, c in CONTEXTS}
    print(f"research intake: {len(reports)} reports ({', '.join(f'{k} {v}' for k, v in by.items())}) · {len(rejected)} refused")


if __name__ == "__main__":
    main()
