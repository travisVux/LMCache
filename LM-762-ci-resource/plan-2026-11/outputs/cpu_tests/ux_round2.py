"""Regression checks for expert review round 2 (product). Headless Chrome on a temp copy of the built page.

  python -X utf8 ux_round2.py            # exit 1 on any failure

Checks (IDs from plan-2026-11/outputs/expert_review/round2/IMPROVEMENT_PLAN.md):
  R2-1  #now merge-queue line is not green "none must rebase" when the overlap data is older than 24 h   (A3 B1 D1 F2)
  R2-2  UX.mergeVerdict never says Safe for draft / mergeable unknown / older check sha / other check failed /
        old overlap data / p3 overlap, even with a fresh snapshot                                          (F1)
  R2-3  #obs/coming in VI has no literal "undefined"                                                        (A7 E3)
  R2-4  #pr:5673 opens the PR Inspector                                                                     (B D F)
  R2-5  Track chart has no better / worse legend                                                            (G1)
  R2-6  gates/tiers 4 and 5 carry the "proposed policy" tag                                                 (D4)
  R2-7  snapshot strip shows no "Buildkite ✓" when the snapshot is older than 48 h                          (C3 D5)
  R2-8  print of #now is not blank (PDF has text)                                                           (C1)
  R2-10 the page opens at its top (no scroll to the tab's own section)
  R2-9  release-notes scope of a tagged release ends at the tag (no PR merged after v0.5.8 in 3E-3G)        (A1)
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE.parents[1] / "06_PR_TO_CI_VISUAL.html"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
LMC = HERE.parents[3] / "third_party" / "LMCache"

PROBE = r"""<script>window.__e=[];addEventListener('error',e=>__e.push(String(e.message)));
setTimeout(async()=>{const W=ms=>new Promise(r=>setTimeout(r,ms)),q=s=>document.querySelector(s),R={};R.scrollAtLoad=scrollY;try{
vizNav.show('obs','today');await W(400);
const ql=[...document.querySelectorAll('.row')].find(r=>/MERGE QUEUE|Merge queue|Hàng đợi merge/i.test(r.textContent));
R.queue=ql?ql.textContent.replace(/\s+/g,' ').slice(0,220):'(no row)';
R.queueGreenNone=!!(ql&&[...ql.querySelectorAll('.ux-chip.ok')].some(c=>/none must rebase|không PR nào phải rebase/.test(c.textContent)));
// F1: run the page's own verdict on variants of a real open PR with a fresh snapshot and fresh overlap
const D=PI.data,keys=Object.keys(D.prs).filter(k=>D.prs[k].st==='open'&&D.prs[k].ck);const n=keys[0];const base=JSON.parse(JSON.stringify(D.prs[n]));
const save={snap:D.snap_at,ov:D.ov_at,p:D.prs[n]};const iso=new Date(Date.now()-36e5).toISOString();D.snap_at=iso;D.ov_at=iso;
const mk=f=>{const p=JSON.parse(JSON.stringify(base));p.ck=p.ck||{};p.ck.g={dco:'ok',quality:'ok',unit:'ok',mp:'ok'};p.rv=null;p.ck.rd='APPROVED';p.ck.mg='MERGEABLE';p.ck.state='SUCCESS';p.ck.sha=p.sha;p.c24=[];f(p);return p;};
const V={baseline:p=>{},draft:p=>{p.st='draft';},mgUnknown:p=>{p.ck.mg='UNKNOWN';},mgNull:p=>{p.ck.mg=null;},oldSha:p=>{p.ck.sha='deadbeef';},otherFail:p=>{p.ck.state='FAILURE';},p3:p=>{p.c24=[{lv:'p3',m:1,sh:[],same:[]}];}};
R.verdict={};for(const [k,f] of Object.entries(V)){D.prs[n]=mk(f);const h=UX.mergeVerdict(n);R.verdict[k]=/Safe to merge|An toàn để merge/.test(h);}
D.snap_at=save.snap;D.ov_at=iso;D.prs[n]=mk(p=>{});D.ov_at=new Date(Date.now()-50*36e5).toISOString();R.verdict.oldOverlap=/Safe to merge|An toàn để merge/.test(UX.mergeVerdict(n));
D.snap_at=save.snap;D.ov_at=save.ov;D.prs[n]=save.p;
vizNav.show('r1130','track');await W(300);R.trackLegend=/now: better|now: worse|tốt hơn|xấu hơn/.test((q('section[data-r11="track"]')||{}).textContent||'');
vizNav.show('gates','tiers');await W(300);R.proposed=document.querySelectorAll('section[data-view="gates"] .ux-prop').length;
vizNav.show('obs','release');await W(300);const bar=q('#obsBar');R.bar=bar?bar.textContent.replace(/\s+/g,' ').slice(0,200):'';R.bkTick=/Buildkite ✓/.test(R.bar);
const sc=(window.opsData||null);
vizNav.show('obs','coming');await W(500);R.comingText=(q('section[data-view="obs"][data-tab="coming"]')||{}).textContent||'';R.undef=[...document.querySelectorAll('section[data-tab="coming"] .sub')].filter(x=>/undefined/.test(x.textContent)).length;
}catch(e){R.err=String(e&&e.stack||e)}R.jsErr=__e;const x=document.createElement('pre');x.id='RR';x.textContent=JSON.stringify(R);document.body.appendChild(x);},4000);</script>"""

PROBE_HASH = r"""<script>setTimeout(()=>{const d=document.getElementById('piDrawer');const x=document.createElement('pre');x.id='RR';
x.textContent=JSON.stringify({open:!!(d&&d.classList.contains('on')),hash:location.hash});document.body.appendChild(x);},4000);</script>"""


def run(src_extra, lang="en", hash_="#obs/today", size="1440,1000"):
    src = PAGE.read_text(encoding="utf-8").replace(
        "<head>", "<head><script>try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','%s')}catch(e){}</script>" % lang, 1)
    i = src.rindex("</body>")
    f = Path(tempfile.mkdtemp()) / "p.html"
    f.write_text(src[:i] + src_extra + src[i:], encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", f"--window-size={size}", "--virtual-time-budget=30000", "--dump-dom",
                          f.as_uri() + hash_], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    m = re.search(r'<pre id="RR">(.*?)</pre>', dom, re.S)
    import html
    return json.loads(html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))) if m else {"err": "no result"}, f


def main():
    res, fails = {}, []
    en, f = run(PROBE)
    vi, _ = run(PROBE, "vi")
    hs, _ = run(PROBE_HASH, hash_="#pr:5673")
    for k in ("err",):
        if en.get(k) or vi.get(k):
            fails.append(f"probe error: {en.get(k) or vi.get(k)}")
    def ck(cid, ok, info):
        res[cid] = ("PASS" if ok else "FAIL", info)
        if not ok:
            fails.append(cid)
    ck("R2-1", not en.get("queueGreenNone"), en.get("queue"))
    ck("R2-2", en.get("verdict", {}).get("baseline") is True and not any(v for k, v in en.get("verdict", {}).items() if k != "baseline"), en.get("verdict"))
    ck("R2-3", vi.get("undef", 1) == 0 and en.get("undef", 1) == 0, f"VI undefined subs: {vi.get('undef')}")
    ck("R2-4", hs.get("open") is True, hs)
    ck("R2-5", en.get("trackLegend") is False, en.get("trackLegend"))
    ck("R2-6", en.get("proposed", 0) >= 2, en.get("proposed"))
    try:   # the tick is wrong only while the Buildkite half is older than 48 h (fresh data since the token was added)
        import datetime as _dt, os
        _bk = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "observe_snapshot.json"), encoding="utf-8")).get("bk_at")
        bk_old = (_dt.datetime.now(_dt.timezone.utc) - _dt.datetime.fromisoformat(_bk.replace("Z", "+00:00"))).total_seconds() > 48 * 3600
    except Exception:  # noqa: BLE001
        bk_old = True
    ck("R2-7", en.get("bkTick") is False or not bk_old, f"bk old={bk_old} · " + str(en.get("bar")))
    # R2-8 print
    pdf = Path(tempfile.mkdtemp()) / "now.pdf"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=15000", "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    f.as_uri() + "#obs/today"], capture_output=True, timeout=300)
    b = pdf.read_bytes() if pdf.exists() else b""
    pages = len(re.findall(rb"/Type\s*/Page[^s]", b))
    fonts = len(re.findall(rb"/FontFile|/Font\b", b))
    ck("R2-8", pages >= 1 and fonts > 0 and len(b) > 30000, f"{pages} page(s), {len(b)} bytes, font refs {fonts}")
    # R2-9 notes scope
    after = set(re.findall(r"#(\d+)\)", subprocess.run(["git", "-C", str(LMC), "log", "--format=%s", "v0.5.8..origin/dev"],
                                                       capture_output=True, text=True).stdout))
    txt = en.get("comingText", "")
    bad = sorted(n for n in after if re.search(r"#%s\b" % n, txt) and re.search(r"ships in v0\.5\.8[^#]{0,80}#%s|#%s[^#]{0,300}ships in v0\.5\.8" % (n, n), txt))
    ck("R2-9", not bad, f"post-tag PRs said to ship in v0.5.8: {bad}")
    ck("R2-10", en.get("scrollAtLoad") == 0 and vi.get("scrollAtLoad") == 0, f"scrollY at load: {en.get('scrollAtLoad')} / {vi.get('scrollAtLoad')}")   # the page opens at its top
    if en.get("jsErr") or vi.get("jsErr"):
        fails.append("JS errors")
    for k, (s, info) in res.items():
        print(f"{k:6} {s:5} {str(info)[:200]}")
    print("JS errors:", (en.get("jsErr") or []) + (vi.get("jsErr") or []) or "none")
    print("RESULT:", "PASS" if not fails else f"FAIL {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
