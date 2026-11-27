"""Regression checks for expert review round 3 ("less text, calmer UI"). Headless Chrome on a temp copy of the built page,
loaded in an iframe of exact size (1440 x 900) so the viewport is the real one.

  python -X utf8 ux_round3.py            # exit 1 on any failure

Checks (plan-2026-11/outputs/expert_review/round3/A_visual.md, B_content.md, C_ia.md):
  R3-1  #obs/today first viewport (1440 x 900, VI) holds <= 200 visible words
  R3-2  header + nav take <= 22 % of the first viewport (1440 x 900)
  R3-3  no data-age chip is green or red (class ok / fail) on the Management tabs
  R3-4  help text is off by default and then hides the section subtitles (p.sub)
  R3-5  the Today banner shows at most 3 rows; the rest sits in a closed "Details" <details>
  R3-6  the "Refresh data" button and the data-age item sit on the build-stamp line
  R3-7  "Refresh data": no /api/refresh request on a static / file page; on the web copy the button stays hidden when
        /api/refresh is absent (404) and shows when it answers {enabled: true}
"""
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE.parents[1] / "06_PR_TO_CI_VISUAL.html"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
W, H = 1440, 900

PROBE = r"""<script>window.__e=[];addEventListener('error',e=>__e.push(String(e.message)));
setTimeout(async()=>{const Wt=ms=>new Promise(r=>setTimeout(r,ms)),q=s=>document.querySelector(s),R={};try{
vizNav.show('obs','today');await Wt(600);scrollTo(0,0);await Wt(200);
const VH=innerHeight,VW=innerWidth;R.vh=VH;R.vw=VW;
const vis=el=>{if(!el||!el.getBoundingClientRect)return false;const cs=getComputedStyle(el);if(cs.visibility==='hidden'||cs.display==='none'||+cs.opacity===0)return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
const inVP=r=>r.width>0&&r.height>0&&r.bottom>0&&r.top<VH&&r.right>0&&r.left<VW;
const shown=el=>{for(let e=el,pv=null;e&&e!==document.body;pv=e,e=e.parentElement){const cs=getComputedStyle(e);if(cs.display==='none'||cs.visibility==='hidden')return false;if(e.tagName==='DETAILS'&&!e.open&&!(pv&&pv.tagName==='SUMMARY'))return false;}return true;};   // content of a closed <details> is not visible
let words=0;const tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;const rg=document.createRange();
while(n=tw.nextNode()){const t=n.nodeValue.trim();if(!t)continue;const p=n.parentElement;if(!p||p.closest('script,style,#RR,noscript'))continue;
  rg.selectNodeContents(n);if(![...rg.getClientRects()].some(inVP))continue;if(!shown(p))continue;
  words+=t.split(/\s+/).filter(x=>/[\p{L}\p{N}]/u.test(x)).length;}
R.words=words;
const bot=s=>{const e=q(s);if(!e||!vis(e))return 0;return e.getBoundingClientRect().bottom;};
R.chromePx=Math.round(Math.max(bot('header'),bot('#hdrBuilt'),bot('.vnav')));R.chromePct=Math.round(1000*R.chromePx/VH)/10;
const chipSel='.ux-chip,.dk-chip,.dk-stale,.tdy-v,.ux-gate,.st';
R.chips=[...document.querySelectorAll(chipSel)].filter(e=>shown(e)&&inVP(e.getBoundingClientRect())&&!e.parentElement.closest(chipSel)).length;
const ban=q('#uxDecision .ux-banner');R.bannerRows=ban?[...ban.querySelectorAll(':scope>.row')].filter(shown).length:-1;
const det=ban&&ban.querySelector(':scope>details');R.bannerDetails=det?{open:det.open,rows:det.querySelectorAll('.row').length}:null;
R.bannerWords=ban?ban.innerText.split(/\s+/).filter(x=>/[\p{L}\p{N}]/u.test(x)).length:-1;
// R3-4: help text
const cb=q('#vDesc');R.helpChecked=cb?cb.checked:null;R.helpLabel=cb&&cb.parentElement?cb.parentElement.textContent.trim():'';
const subs=[...document.querySelectorAll('section[data-view] p.sub')].filter(x=>shown(x.closest('section[data-view]')));R.subsTotal=subs.length;R.subsShown=subs.filter(shown).length;
if(cb){cb.click();await Wt(100);R.subsShownOn=subs.filter(shown).length;cb.click();await Wt(100);}
// R3-3: age chips on the Management tabs
const ageRe=/(<\s*1\s*(h|giờ)|\b\d+\s*(h|d|giờ|ngày|min|phút)\b|cũ\s*\d+)/;R.ageBad=[];
for(const t of ['today','hist','release','coming','cost','overlap']){vizNav.show('obs',t);await Wt(250);
  document.querySelectorAll('.ux-chip.ok,.ux-chip.fail,[data-age].ok,[data-age].fail,.obs-bar .src span.ok,.obs-bar .src span.err').forEach(e=>{if(!shown(e))return;
    if(e.hasAttribute('data-age')||ageRe.test(e.textContent))R.ageBad.push(t+': '+e.textContent.trim().slice(0,60));});}
vizNav.show('obs','today');await Wt(250);
// R3-6
const hb=q('#hdrBuilt'),rb=q('#hdrRefresh'),ag=q('#uxAge');R.stamp=hb?hb.textContent.trim():'';R.ageItem=ag?ag.querySelector('summary').textContent.trim():'';
const mid=e=>{const r=e.getBoundingClientRect();return (r.top+r.bottom)/2;};
R.oneLine=!!(hb&&ag&&Math.abs(mid(hb)-mid(ag))<14&&(!rb||rb.hidden||Math.abs(mid(hb)-mid(rb))<14));
}catch(e){R.err=String(e&&e.stack||e)}R.jsErr=__e;parent.postMessage('RR:'+JSON.stringify(R),'*');},4500);</script>"""

# R3-7: "Refresh data" on the web copy. Test hooks __rdProto / __rdHost fake the location; fetch of /api/refresh is stubbed.
STUB = ("<script>window.__rdCalls=[];{const f0=window.fetch.bind(window);window.fetch=(u,o)=>{const s=String(u);window.__rdCalls.push(s);"
        "if(s.includes('/api/refresh')&&window.__rdApi!==undefined)return Promise.resolve(window.__rdApi===404?new Response('not found',{status:404}):"
        "new Response(JSON.stringify(window.__rdApi),{status:200,headers:{'Content-Type':'application/json'}}));return f0(u,o);};}%s</script>")
PROBE_RF = r"""<script>setTimeout(()=>{const b=document.getElementById('hdrRefresh');parent.postMessage('RR:'+JSON.stringify({hidden:!b||b.hidden,
calls:(window.__rdCalls||[]).filter(u=>u.includes('/api/refresh')).length,text:b?b.textContent:''}),'*');},3500);</script>"""

PROBE_PG = r"""<script>setTimeout(()=>{const t=document.getElementById('hdrRefreshMore');if(t)t.click();setTimeout(()=>{const p=document.getElementById('rdRfPop');
parent.postMessage('RR:'+JSON.stringify({more:!!t&&!t.hidden,open:!!p&&!p.hidden,rows:p?p.querySelectorAll('tr[class^="rd-"]:not(.rd-g)').length:0,
running:p?p.querySelectorAll('tr.rd-running').length:0,bar:!!(p&&p.querySelector('[role=progressbar]')),st:(document.getElementById('hdrRefreshSt')||{}).textContent||'',
first:p&&p.querySelector('tr.rd-done td:nth-child(3)')?p.querySelector('tr.rd-done td:nth-child(3)').textContent:'',
over:p?p.getBoundingClientRect().right>innerWidth+1:null}),'*');},600);},3500);</script>"""
PG_RUN = ("{enabled:true,queued:false,status:{state:'running',at:'2026-11-26T01:15:00Z',progress:{running:true,done:2,total:4,elapsed_s:95,outcome:null,steps:["
          "{id:'observe_collect',en:'Open PRs',vi:'PR đang mở',src:'GitHub',state:'done',secs:35,note:'100 open PRs'},"
          "{id:'git_fetch',en:'Tags',vi:'Tag',src:'git',state:'done',secs:0,note:'fetched'},"
          "{id:'build_page',en:'Rebuild every tab',vi:'Build lại các tab',src:'build',state:'running',secs:20,note:null},"
          "{id:'pages_deploy',en:'Upload',vi:'Upload lên bản web',src:'Cloudflare Pages',state:'pending',secs:null,note:null}]}}}")


def run(lang, head="", probe=None):
    src = PAGE.read_text(encoding="utf-8").replace(
        "<head>", "<head><script>try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','%s')}catch(e){}</script>" % lang + head, 1)
    i = src.rindex("</body>")
    d = Path(tempfile.mkdtemp())
    (d / "p.html").write_text(src[:i] + (probe or PROBE) + src[i:], encoding="utf-8")
    lst = ("<script>addEventListener('message',e=>{if(String(e.data).startsWith('RR:')){const x=document.createElement('pre');"
           "x.id='RR';x.textContent=String(e.data).slice(3);document.body.appendChild(x);}})</script>")
    (d / "w.html").write_text(f'<!doctype html><html><body style="margin:0">{lst}<iframe src="p.html#obs/today" width="{W}" height="{H}" '
                              f'style="border:0;display:block"></iframe></body></html>', encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={W + 80},{H + 200}",
                          "--virtual-time-budget=30000", "--dump-dom", (d / "w.html").as_uri()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    m = re.search(r'<pre id="RR"[^>]*>(.*?)</pre>', dom, re.S)
    return json.loads(html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))) if m else {"err": "no result"}


def main():
    vi, en = run("vi"), run("en")
    rf_file = run("vi", STUB % "", PROBE_RF)
    rf_404 = run("vi", STUB % "window.__rdProto='https:';window.__rdHost='desk.example';window.__rdApi=404;", PROBE_RF)
    rf_on = run("en", STUB % "window.__rdProto='https:';window.__rdHost='desk.example';window.__rdApi={enabled:true,queued:false,status:null};", PROBE_RF)
    pg = run("vi", STUB % ("window.__rdProto='https:';window.__rdHost='desk.example';window.__rdApi=" + PG_RUN + ";"), PROBE_PG)
    res, fails = {}, []
    for r in (vi, en):
        if r.get("err"):
            fails.append("probe error: " + str(r["err"])[:300])

    def ck(cid, ok, info):
        res[cid] = ("PASS" if ok else "FAIL", info)
        if not ok:
            fails.append(cid)
    ck("R3-1", 0 < vi.get("words", 999) <= 200, f"Today first viewport words VI {vi.get('words')} / EN {en.get('words')} (viewport {vi.get('vw')}x{vi.get('vh')})")
    ck("R3-2", 0 < vi.get("chromePct", 99) <= 22 and 0 < en.get("chromePct", 99) <= 22,
       f"header + nav {vi.get('chromePx')} px = {vi.get('chromePct')} % (VI) / {en.get('chromePct')} % (EN)")
    bad = (vi.get("ageBad") or []) + (en.get("ageBad") or [])
    ck("R3-3", not bad, f"green / red age chips: {bad[:6] or 'none'}")
    ck("R3-4", vi.get("helpChecked") is False and vi.get("subsShown", 1) == 0 and vi.get("subsShownOn", 0) > 0,
       f"help text checked={vi.get('helpChecked')} label={vi.get('helpLabel')!r} · p.sub shown {vi.get('subsShown')} of {vi.get('subsTotal')} (on: {vi.get('subsShownOn')})")
    bd = vi.get("bannerDetails") or {}
    ck("R3-5", 0 < vi.get("bannerRows", 99) <= 3 and bd.get("open") is False and bd.get("rows", 0) >= 1,
       f"banner rows {vi.get('bannerRows')} · details {bd} · banner words VI {vi.get('bannerWords')} / EN {en.get('bannerWords')}")
    ck("R3-6", vi.get("oneLine") is True, f"stamp {vi.get('stamp')!r} · data {vi.get('ageItem')!r} / {en.get('ageItem')!r}")
    ck("R3-7", rf_file.get("hidden") is True and rf_file.get("calls") == 0 and rf_404.get("hidden") is True and rf_on.get("hidden") is False,
       f"file page: hidden={rf_file.get('hidden')} api calls={rf_file.get('calls')} · web, no function: hidden={rf_404.get('hidden')} · web, enabled: hidden={rf_on.get('hidden')} text={rf_on.get('text')!r}")
    ck("R3-8", pg.get("more") and pg.get("open") and pg.get("rows") == 4 and pg.get("running") == 1 and pg.get("bar") and "2/4" in pg.get("st", "")
       and pg.get("first") == "100 PR đang mở" and pg.get("over") is False,
       f"refresh progress panel: {pg}")
    print(f"info   chips in the Today first viewport: VI {vi.get('chips')} / EN {en.get('chips')}")
    if vi.get("jsErr") or en.get("jsErr"):
        fails.append("JS errors")
    for k, (s, info) in res.items():
        print(f"{k:6} {s:5} {str(info)[:260]}")
    print("JS errors:", (vi.get("jsErr") or []) + (en.get("jsErr") or []) or "none")
    print("RESULT:", "PASS" if not fails else f"FAIL {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
