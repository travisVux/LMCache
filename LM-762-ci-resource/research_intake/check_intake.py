"""Acceptance test of the Research intake contract (validate.py + build_research.py + the page tab).

  1. validator: the 3 samples pass; 9 broken reports fail with the expected reason (context, required field,
     e-mail, local path, token, http artifact, unknown field, gpus > 8, file name != id)
  2. drop folder: a valid report and a broken one are dropped into inbox/; the loader shows the valid one and lists
     the broken one as refused; both files are removed again and the page is rebuilt (nothing left behind)
  3. page: each of the 3 contexts shows at least one report; samples carry the SAMPLE badge; the PR link opens the
     PR Inspector; the Inspector's "Research" button lands on the report; no console error; no English left in VI

  python -X utf8 check_intake.py
"""
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CPU = HERE.parent / "plan-2026-11" / "outputs" / "cpu_tests"
PAGE = HERE.parent / "plan-2026-11" / "06_PR_TO_CI_VISUAL.html"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
sys.path.insert(0, str(HERE))
import validate as V  # noqa: E402


def build():
    r = subprocess.run([sys.executable, "-I", "-X", "utf8", "build_research.py"], cwd=CPU, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(r.stderr[-600:])
    return r.stdout.strip()


def main():
    bad = []
    samples = sorted((HERE / "samples").glob("*.json"))
    for f in samples:
        _, errs = V.validate(f)
        print(f"1. sample {f.name}: {'OK' if not errs else errs}")
        if errs:
            bad.append("sample " + f.name)
    base = json.loads(samples[0].read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="check_intake_"))
    cases = {
        "context": (lambda d: d.update(context="Other"), "$.context"),
        "required": (lambda d: d.pop("verdict"), "$.verdict: required"),
        "email": (lambda d: d.update(summary=d["summary"] + " Contact: someone@" + "example.org"), "e-mail"),
        "local path": (lambda d: d.update(summary=d["summary"] + " Log in C:" + "\\" + "Users\\me\\run.log"), "local path"),
        "token": (lambda d: d.update(summary=d["summary"] + " ghp_" + "A" * 20), "token"),
        "http artifact": (lambda d: d.update(artifacts=[{"label": "log", "url": "http://example.org/x"}]), "$.artifacts[0].url"),
        "unknown field": (lambda d: d.update(owner="someone"), "$.owner: not allowed"),
        "gpus": (lambda d: d["environment"].update(gpus=9), "$.environment.gpus: above 8"),
    }
    for name, (mut, expect) in cases.items():
        d = copy.deepcopy(base); mut(d)
        f = tmp / f"{d['id']}.json"
        f.write_text(json.dumps(d), encoding="utf-8")
        _, errs = V.validate(f)
        ok = any(expect in e for e in errs)
        print(f"1. broken ({name}): {'refused' if ok else 'NOT refused as expected'} -> {errs[:2]}")
        if not ok:
            bad.append("validator " + name)
    f = tmp / "rr-wrong-name.json"
    f.write_text(json.dumps(base), encoding="utf-8")
    _, errs = V.validate(f)
    print(f"1. broken (file name): {'refused' if any('file name' in e for e in errs) else 'NOT refused'}")
    if not any("file name" in e for e in errs):
        bad.append("validator file name")

    # 2. drop folder
    inbox = HERE / "inbox"
    good = copy.deepcopy(base)
    good.update(id="rr-test-drop-folder-check", sample=False, title="Test: drop folder check (removed after the test)", context="LMCache optimization")
    gf, bf = inbox / f"{good['id']}.json", inbox / "rr-test-broken.json"
    try:
        gf.write_text(json.dumps(good), encoding="utf-8")
        bf.write_text('{"schema": "lmcache.research_report/v1", "id": "rr-test-broken"}', encoding="utf-8")
        out = build()
        D = json.loads((CPU / "research.json").read_text(encoding="utf-8"))
        shown = any(r["id"] == good["id"] for r in D["reports"])
        refused = any(r["file"] == "inbox/rr-test-broken.json" for r in D["rejected"])
        print(f"2. drop folder: {out} · dropped report shown: {shown} · broken file refused: {refused}")
        if not (shown and refused):
            bad.append("drop folder")
    finally:
        gf.unlink(missing_ok=True); bf.unlink(missing_ok=True)
        print("   cleaned:", build())

    # 3. page
    probe = r"""<script>(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1500);const R={err:window.__err,ctx:{}};
vizNav.show('obs','research',false);await wait(60);
for(const k of ['ci','opt','feat']){const s=document.querySelector('section[data-research="'+k+'"]');R.ctx[k]={visible:!!s&&!s.classList.contains('vhide'),cards:s?s.querySelectorAll('.rs-card').length:0,
  sample:s?s.querySelectorAll('.rs-badge').length:0,rows:s?s.querySelectorAll('.rs-tab tbody tr').length:0,good:s?s.querySelectorAll('.rs-good').length:0};}
const a=document.querySelector('section[data-research] [data-pi^="pr:"]');if(a){a.click();await wait(40);const dr=document.getElementById('piDrawer');R.prLink={open:dr.classList.contains('on'),title:(dr.querySelector('#piTitle')||{}).textContent||''};
  const b=dr.querySelector('[data-rsgo]');R.prLink.researchBtn=!!b;if(b){b.click();await wait(200);R.prLink.landed=vizNav.state.t;R.prLink.focus=document.querySelectorAll('.rs-card.focus').length;R.prLink.closed=!dr.classList.contains('on');}}
I18N.setLang('vi');await wait(50);const SKIP='code,pre,script,style,.obsraw,.pi-why';const left=[];
document.querySelectorAll('section[data-research]').forEach(sec=>{const w=document.createTreeWalker(sec,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){const t=n.nodeValue.trim(),p=n.parentElement;if(!t||!p||p.closest(SKIP))continue;
  if(((t.match(/(?<![\p{L}\-_])(the|is|are|and|of|to|on|when|only|with|for|runs|files|passed|show|see|per|not|in|a)(?![\p{L}\-_])/giu)||[]).length)>=2)left.push(t.slice(0,80));}});
R.vi=left;I18N.setLang('en');R.err=window.__err;const x=document.createElement('script');x.type='application/json';x.id='Rout';x.textContent=JSON.stringify(R);document.body.appendChild(x);})();</script>"""
    src = PAGE.read_text(encoding="utf-8").replace("<head>", '<head><script>try{localStorage.setItem("obsOnOpen","false");localStorage.setItem("ciMapLang","en")}catch(e){}'
                                                  'window.__err=[];addEventListener("error",e=>__err.push(e.message));</script>', 1)
    i = src.rindex("</body>")
    pf = tmp / "probe.html"
    pf.write_text(src[:i] + probe + src[i:], encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=30000", "--dump-dom", pf.as_uri()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    m = re.search(r'<script type="application/json" id="Rout">(.*?)</script>', dom, re.S)
    R = json.loads(m.group(1)) if m else {}
    for k, v in (R.get("ctx") or {}).items():
        print(f"3. context {k}: {v}")
        if not (v["visible"] and v["cards"] >= 1 and v["rows"] >= 1 and v["sample"] >= 1):
            bad.append("context " + k)
    print(f"3. PR link -> Inspector -> Research button: {R.get('prLink')}")
    pl = R.get("prLink") or {}
    if not (pl.get("open") and pl.get("researchBtn") and pl.get("landed") == "research" and pl.get("focus") == 1):
        bad.append("PR link / Research button")
    print(f"3. VI untranslated: {len(R.get('vi') or [])} {(R.get('vi') or [])[:3]} · JS errors: {R.get('err') or 'none'}")
    if R.get("vi") or R.get("err") or not R:
        bad.append("VI / errors")
    print("RESULT:", "PASS" if not bad else "FAIL " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
