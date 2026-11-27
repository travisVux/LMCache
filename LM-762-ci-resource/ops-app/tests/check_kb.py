"""Acceptance test of the living knowledge base (backend/kb.py + the RFC / FRS panel of the PR Inspector).

Works on a COPY of data/ops.db (the real one is not touched):
  1. build            : every FRS / RFC exists with a version; a second build with the same facts changes nothing
  2. human edit       : `kb.py edit frs:<area>` -> new version, author 'human'
  3. simulated CI change (a workload added with a condition, one removed) -> an open proposal for every FRS gated by
     that pipeline, with the changed facts and a diff; the current versions are NOT changed; the human note is kept
  4. accept           : the proposal becomes the next version; the same simulation again creates no duplicate
  5. page             : the export of this copy, put into the page, shows the proposal (diff + changed facts), the
     editable text and the version history in the Inspector panel; no console error; VI leaves no English sentence;
     at 390 px the panel does not overflow

  python -X utf8 tests/check_kb.py [--area smcore] [--pr 6572]
"""
import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
KB = APP / "backend" / "kb.py"
PAGE = APP.parent / "plan-2026-11" / "06_PR_TO_CI_VISUAL.html"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SIM = {"ci": {"k3-multiprocess-test": {"add": [["vllm / kv_offload_stress / zmq", 'build.env("CI_STRESS") == "1"']], "drop": ["deadlock"]}}}
NOTE = "Invariant: a chunk is never evicted while a prefetch holds it."


def kb_rc(db, *args):
    r = subprocess.run([sys.executable, "-X", "utf8", str(KB), "--db", str(db), *args], cwd=KB.parent, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def lifecycle(src_db, tmp):
    """Expert review 2026-11-25 (K1, K3, K4, K8-K11): proposal lifecycle, audit columns and DB guards."""
    bad = []
    db = tmp / "life.db"
    shutil.copy2(src_db, db)
    kb_rc(db, "build")
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    # K4: a simulated proposal is marked and cannot be accepted by mistake
    sim = tmp / "life_sim.json"
    sim.write_text(json.dumps(SIM), encoding="utf-8")
    kb_rc(db, "build", "--simulate", str(sim))
    sp = con.execute("SELECT proposal_id,doc_id,base_version FROM kb_proposal WHERE status='open' AND source='simulate' LIMIT 1").fetchone()
    if not sp: bad.append("K4 simulate not marked")
    else:
        rc, out = kb_rc(db, "accept", str(sp[0]))
        if rc == 0: bad.append("K4 simulated proposal accepted without --allow-simulated")
        # K1: a human edit makes the open proposal outdated: it is superseded, and build makes a new one on the new base
        doc = sp[1]
        body = kb_rc(db, "show", doc)[1]
        f = tmp / "life_edit.md"
        f.write_text(body.replace("## Notes (edit)\n", "## Notes (edit)\nLIFE NOTE\n", 1) + "\n## Invariants\nLIFE INVARIANT\n", encoding="utf-8")
        rc, out = kb_rc(db, "edit", doc, "--file", str(f), "--by", "tester")
        if rc: bad.append("K2 edit with an (edit) note and a new section refused: " + out[-120:])
        st = con.execute("SELECT status FROM kb_proposal WHERE proposal_id=?", (sp[0],)).fetchone()[0]
        if st != "superseded": bad.append(f"K1 outdated proposal is {st}, not superseded")
        kb_rc(db, "build", "--simulate", str(sim))
        np_ = con.execute("SELECT proposal_id,base_version,new_body_md FROM kb_proposal WHERE doc_id=? AND status='open'", (doc,)).fetchone()
        if not np_ or np_[1] != sp[2] + 1: bad.append("K1 no new proposal on the edited version")
        else:
            if "LIFE NOTE" not in np_[2] or "LIFE INVARIANT" not in np_[2]: bad.append("K2 human text not carried")
            rc, out = kb_rc(db, "accept", str(np_[0]), "--allow-simulated", "--by", "tester", "--reason", "looks right")
            v = con.execute("SELECT author,proposal_id,decided_by,reason FROM kb_version WHERE doc_id=? ORDER BY version DESC LIMIT 1", (doc,)).fetchone()
            if rc or not v or v["proposal_id"] != np_[0] or v["decided_by"] != "tester" or "looks right" not in (v["reason"] or ""): bad.append("K3 accept audit")
        # K2: changing a generated section is refused
        body = kb_rc(db, "show", doc)[1]
        f.write_text(body.replace("## Scope\n", "## Scope\nSCOPE EDIT\n", 1), encoding="utf-8")
        if "## Scope" in body and kb_rc(db, "edit", doc, "--file", str(f))[0] == 0: bad.append("K2 edit of a generated section accepted")
    # K3: reject reason and who are kept
    rp = con.execute("SELECT proposal_id FROM kb_proposal WHERE status='open' LIMIT 1").fetchone()
    if rp:
        kb_rc(db, "reject", str(rp[0]), "--reason", "WHY", "--by", "tester")
        r = con.execute("SELECT decided_by,decision_reason FROM kb_proposal WHERE proposal_id=?", (rp[0],)).fetchone()
        if tuple(r) != ("tester", "WHY"): bad.append("K3 reject audit")
        if kb_rc(db, "accept", str(rp[0]))[0] == 0: bad.append("K10 decided proposal decided again")
    # K11: empty edit, unknown ids
    e = tmp / "empty.md"; e.write_text("", encoding="utf-8")
    if kb_rc(db, "edit", "frs:smcore", "--file", str(e))[0] == 0: bad.append("K11 empty edit accepted")
    if kb_rc(db, "show", "frs:nope")[0] == 0 or "Traceback" in kb_rc(db, "diff", "99999")[1]: bad.append("K11 unknown id")
    # K9: versions are append-only at the DB level
    for sql in ("UPDATE kb_version SET body_md='x' WHERE version=1", "DELETE FROM kb_version WHERE version=1",
                "UPDATE kb_doc SET current_version=999"):
        try:
            con.execute(sql); con.commit(); bad.append("K9 allowed: " + sql)
        except sqlite3.DatabaseError:
            con.rollback()
    # K8: a rebuild with the same facts makes no proposal (list order is not a change)
    kb_rc(db, "build")   # the accepted simulated version differs from the real facts: this build proposes the way back
    n0 = con.execute("SELECT COUNT(*) FROM kb_proposal").fetchone()[0]
    kb_rc(db, "build")
    if con.execute("SELECT COUNT(*) FROM kb_proposal").fetchone()[0] != n0: bad.append("K8 same facts made a proposal")
    con.close()
    print("0. lifecycle (expert review K1-K11):", "OK" if not bad else bad)
    return bad


def kb(db, *args):
    r = subprocess.run([sys.executable, "-X", "utf8", str(KB), "--db", str(db), *args], cwd=KB.parent, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(f"kb.py {' '.join(args)} failed: {r.stderr[-500:]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="smcore")
    ap.add_argument("--pr", default="6572")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="check_kb_"))
    db = tmp / "ops.db"
    shutil.copy2(APP / "data" / "ops.db", db)
    bad = lifecycle(db, tmp)
    doc = f"frs:{a.area}"

    print("1.", kb(db, "build").strip())
    out = kb(db, "build").strip()
    print("  ", out)
    if re.search(r"proposed \d|created", out):   # "proposed (already open)" = nothing new
        bad.append("second build with the same facts changed something")
    con = sqlite3.connect(db)
    # round 2: the live KB may still have open proposals from real fact changes (fresh PR data); accept them in this
    # temp copy first, so the simulated CI change below is measured against an up-to-date base
    for (pid,) in con.execute("SELECT proposal_id FROM kb_proposal WHERE status='open' AND source!='simulate'").fetchall():
        kb(db, "accept", str(pid), "--by", "check_kb", "--reason", "baseline for the scenario test")
    n_docs = con.execute("SELECT COUNT(*) FROM kb_doc").fetchone()[0]
    v0 = con.execute("SELECT current_version FROM kb_doc WHERE doc_id=?", (doc,)).fetchone()
    print(f"   documents {n_docs}; {doc} v{v0[0] if v0 else '?'}")
    if not v0:
        bad.append(f"no {doc}")
        print("RESULT: FAIL", bad); return 1

    body = kb(db, "show", doc)
    f = tmp / "edit.md"
    f.write_text(body.replace("_Write design decisions, invariants and links here._", NOTE), encoding="utf-8")
    print("2.", kb(db, "edit", doc, "--file", str(f), "--reason", "test: human note").strip())
    v1 = con.execute("SELECT current_version FROM kb_doc WHERE doc_id=?", (doc,)).fetchone()[0]

    sim = tmp / "sim.json"
    sim.write_text(json.dumps(SIM), encoding="utf-8")
    print("3.", kb(db, "build", "--simulate", str(sim)).strip())
    props = con.execute("SELECT proposal_id, trigger, diff, new_body_md, changes_json FROM kb_proposal WHERE doc_id=? AND status='open'", (doc,)).fetchall()
    v_after = con.execute("SELECT current_version FROM kb_doc WHERE doc_id=?", (doc,)).fetchone()[0]
    n_open = con.execute("SELECT COUNT(*) FROM kb_proposal WHERE status='open' AND source='simulate' AND doc_id LIKE 'frs:%'").fetchone()[0]
    gated = con.execute("SELECT COUNT(DISTINCT doc_id) FROM kb_link WHERE doc_id LIKE 'frs:%' AND ref='gate:k3-multiprocess-test'").fetchone()[0]
    print(f"   open proposals {n_open} (FRS gated by k3-multiprocess-test: {gated}); {doc} still v{v_after}")
    if len(props) != 1:
        bad.append(f"{doc}: {len(props)} open proposals, expected 1")
    else:
        pid, trig, diff, new_body, changes = props[0]
        ch = json.loads(changes)
        print(f"   proposal {pid}: trigger {trig}, {len(ch)} changed facts; diff +{diff.count(chr(10) + '+') - 1} / -{diff.count(chr(10) + '-') - 1} lines")
        for line in diff.splitlines():
            if line.startswith(("+ ", "- ", "+  ", "-  ")):
                print("     ", line[:150])
        if trig != "ci_change": bad.append("trigger is not ci_change")
        if "kv_offload_stress" not in diff or "deadlock" not in diff: bad.append("diff misses the added / removed step")
        if NOTE not in new_body: bad.append("the human note is not carried into the proposal")
        if v_after != v1: bad.append("the current version changed without a decision")
    if n_open != gated:
        bad.append(f"{n_open} proposals for {gated} gated FRS")

    print("4.", kb(db, "accept", str(props[0][0]) if props else "0", "--reason", "test: CI change reviewed", "--allow-simulated").strip())
    v2 = con.execute("SELECT current_version FROM kb_doc WHERE doc_id=?", (doc,)).fetchone()[0]
    cur = con.execute("SELECT body_md FROM kb_version WHERE doc_id=? AND version=?", (doc, v2)).fetchone()[0]
    again = kb(db, "build", "--simulate", str(sim)).strip()
    print(f"   {doc} v{v1} -> v{v2}; added step in it: {'kv_offload_stress' in cur}; human note kept: {NOTE in cur}")
    print("  ", again)
    if v2 != v1 + 1 or "kv_offload_stress" not in cur or NOTE not in cur: bad.append("accept")
    if con.execute("SELECT COUNT(*) FROM kb_proposal WHERE doc_id=? AND status='open'", (doc,)).fetchone()[0]: bad.append("duplicate proposal after accept")
    # leave one open proposal on another FRS for the page test: it was proposed in step 3 and is still open
    con.close()

    # 5. page: put this copy's export into the page and open the panel
    exp = kb(db, "export")
    src = PAGE.read_text(encoding="utf-8")
    src = re.sub(r'<script id="kbData" type="application/json">.*?</script>', lambda _: '<script id="kbData" type="application/json">'
                 + exp.replace("</", "<\\/") + "</script>", src, count=1, flags=re.S)
    other = next(r for r in json.loads(exp)["docs"] if r.startswith("frs:") and json.loads(exp)["docs"][r]["proposals"])
    probe = r"""<script>(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1500);const R={err:window.__err};const dr=document.getElementById('piDrawer');
piOpen('pr:%s');await wait(60);const b=dr.querySelector('[data-kbopen]');R.button=b?b.textContent:null;if(b){b.click();await wait(40);}
R.tabs=[...dr.querySelectorAll('[data-kb]')].map(x=>x.dataset.kb);
const pick=async id=>{const t=dr.querySelector('[data-kb="'+id+'"]');if(t){t.click();await wait(40);}return {sel:!!t,props:dr.querySelectorAll('.pi-kb-prop').length,add:dr.querySelectorAll('.pi-kb-diff .add').length,
  del:dr.querySelectorAll('.pi-kb-diff .del').length,ch:dr.querySelectorAll('.pi-kb-ch').length,ta:(document.getElementById('piKbTa')||{}).value||'',versions:dr.querySelectorAll('.pi-gt tr').length,links:dr.querySelectorAll('.pi-kb-links .pi-chip').length};};
R.main=await pick('%s');R.main.note=R.main.ta.includes(%s);R.main.ta=R.main.ta.slice(0,80);
R.rfc=await pick('rfc:%s');R.rfc.ta=R.rfc.ta.slice(0,60);
I18N.setLang('vi');await wait(40);dr.querySelector('[data-kbopen]')&&dr.querySelector('[data-kbopen]').click();await wait(40);
const SKIP='code,pre,script,style,textarea,.obsraw,.pi-why,.pi-kb-cmd';const left=[];const w=document.createTreeWalker(dr,NodeFilter.SHOW_TEXT);let n;
while(n=w.nextNode()){const t=n.nodeValue.trim(),p=n.parentElement;if(!t||!p||p.closest(SKIP))continue;if(((t.match(/(?<![\p{L}\-_])(the|is|are|and|of|to|on|when|only|with|for|runs|files|passed|show|see|per|not|in|a)(?![\p{L}\-_])/giu)||[]).length)>=2)left.push(t.slice(0,80));}
R.vi=left;I18N.setLang('en');await wait(30);dr.querySelector('[data-kbback]')&&dr.querySelector('[data-kbback]').click();await wait(30);R.back=dr.querySelectorAll('[data-pi-v]').length;
R.err=window.__err;const x=document.createElement('script');x.type='application/json';x.id='Rout';x.textContent=JSON.stringify(R);document.body.appendChild(x);})();</script>"""
    pr_of_other = a.pr
    page = src.replace("<head>", '<head><script>try{localStorage.setItem("obsOnOpen","false");localStorage.setItem("ciMapLang","en")}catch(e){}'
                       'window.__err=[];addEventListener("error",e=>__err.push(e.message));</script>', 1)
    i = page.rindex("</body>")
    page = page[:i] + probe % (pr_of_other, other, json.dumps(NOTE), a.pr) + page[i:]
    pf = tmp / "probe.html"
    pf.write_text(page, encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=40000", "--dump-dom", pf.as_uri()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    m = re.search(r'<script type="application/json" id="Rout">(.*?)</script>', dom, re.S)
    R = json.loads(m.group(1)) if m else {}
    print(f"5. page: Inspector #{a.pr} button {R.get('button')!r}; documents {R.get('tabs')}")
    print(f"   {other} (open proposal from step 3): {R.get('main')}")
    print(f"   rfc:{a.pr}: {R.get('rfc')}")
    print(f"   VI untranslated in the panel: {len(R.get('vi') or [])} {(R.get('vi') or [])[:3]}; back to the 5 views: {R.get('back')}; JS errors: {R.get('err') or 'none'}")
    mm = R.get("main") or {}
    if not R.get("button") or other not in (R.get("tabs") or []): bad.append("panel button / tabs")
    if not (mm.get("props") and mm.get("add") and mm.get("del") and mm.get("ch") and mm.get("ta") and mm.get("versions")): bad.append("proposal / diff / text / versions in the page")
    if not (R.get("rfc") or {}).get("ta", "").startswith("# RFC"): bad.append("RFC text in the page")
    if R.get("vi") or R.get("err") or R.get("back") != 5: bad.append("VI / errors / back")

    # 390 px: the panel stays inside the drawer
    frame = tmp / "frame.html"
    pg2 = tmp / "page390.html"
    pg2.write_text(src.replace("<head>", '<head><style>.pi-drawer{transition:none!important}</style>', 1), encoding="utf-8")
    frame.write_text(f"""<html><body style="margin:0"><iframe id="f" src="{pg2.as_uri()}#obs/today" style="width:390px;height:1400px;border:0"></iframe><pre id="R"></pre><script>
document.getElementById('f').onload=()=>setTimeout(()=>{{const w=document.getElementById('f').contentWindow,d=w.document;w.piOpen('pr:{pr_of_other}');
setTimeout(()=>{{d.querySelector('[data-kbopen]').click();const t=d.querySelector('[data-kb="{other}"]');if(t)t.click();
const dr=d.getElementById('piDrawer'),W=Math.min(dr.getBoundingClientRect().right,d.documentElement.clientWidth),o=[];
dr.querySelectorAll('*').forEach(e=>{{const r=e.getBoundingClientRect();if(r.width&&r.right>W+1){{const p=e.parentElement.getBoundingClientRect();if(p.right<=W+1)o.push(e.tagName+'.'+String(e.className).slice(0,24)+' +'+Math.round(r.right-W));}}}});
document.getElementById('R').textContent=JSON.stringify(o.slice(0,5));}},500);}},2500);</script></body></html>""", encoding="utf-8")
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--virtual-time-budget=20000",
                          "--window-size=1000,1500", "--dump-dom", frame.as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    mo = re.search(r'<pre id="R">(.*?)</pre>', out, re.S)
    over = json.loads(mo.group(1).replace("&quot;", '"')) if mo and mo.group(1).strip() else None
    print(f"   390 px panel overflow: {over}")
    if over is None or over:
        bad.append("390 px")
    shutil.rmtree(tmp, ignore_errors=True)
    print("RESULT:", "PASS" if not bad else "FAIL " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
