"""Checks of the Weekly full build tab (#obs/weekly, build_weekly.py) in headless Chrome.

The built page is loaded in an iframe of exact width (1280 and 390 px; headless Chrome cannot make a window narrower
than ~500 px), in EN and VI, light and dark. Per combination:
  W-1  hero status present (PASSED / FAILED / RUNNING / TIMED OUT / CANCELLED or VI)
  W-2  4 tiles in the hero
  W-3  device matrix shows 4 devices (CUDA, XPU, AMD, RBLN)
  W-4  strip cells >= number of runs in the data
  W-5  clicking another strip cell changes the run shown in the hero; a history row does too; arrow keys move focus
  W-6  no horizontal overflow (page and every element of the tab)
  W-7  no JS errors
  W-8  VI: no untranslated English sentence in the tab;  #weekly short link lands on #obs/weekly
  python -X utf8 ux_weekly.py [--shots DIR] [--pick RUN_ID]     exit 1 on any failure (--pick: screenshots show that run)
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
PICK = sys.argv[sys.argv.index("--pick") + 1] if "--pick" in sys.argv else None

PROBE = r"""<script>window.__e=window.__e||[];
setTimeout(async()=>{const Wt=ms=>new Promise(r=>setTimeout(r,ms)),q=s=>document.querySelector(s),R={};try{
vizNav.show('obs','weekly');await Wt(500);
R.hash=location.hash;R.tab=vizNav.state.t;
const st=q('#wkHero [data-wk="status"]');R.status=st?st.textContent.trim():'';R.run0=st?st.dataset.run:'';
R.tiles=document.querySelectorAll('#wkHero [data-wk="tiles"] > .dk-tile').length;
R.devices=[...document.querySelectorAll('#wkDev [data-dev]')].map(e=>e.dataset.dev);
R.cells=document.querySelectorAll('#wkTrend .wk-cell').length;R.runs=(window.WEEKLY&&WEEKLY.runs.length)||0;
const other=[...document.querySelectorAll('#wkTrend .wk-cell')].find(c=>c.dataset.wkRun!==R.run0);
if(other){other.click();await Wt(150);const s2=q('#wkHero [data-wk="status"]');R.run1=s2?s2.dataset.run:'';R.want1=other.dataset.wkRun;
  R.pressed=(q('#wkTrend .wk-cell[aria-pressed="true"]')||{dataset:{}}).dataset.wkRun;
  R.focusKept=document.activeElement&&document.activeElement.dataset?document.activeElement.dataset.wkRun:'';}
const row=[...document.querySelectorAll('#wkTrend tr[data-wk-row]')].find(r=>r.dataset.wkRow!==(q('#wkHero [data-wk="status"]')||{dataset:{}}).dataset.run);
if(row){row.querySelector('td:nth-child(2)').click();await Wt(150);R.rowRun=(q('#wkHero [data-wk="status"]')||{dataset:{}}).dataset.run;R.rowWant=row.dataset.wkRow;}
const cs=[...document.querySelectorAll('#wkTrend .wk-cell')];if(cs.length>1){cs[1].focus();cs[1].dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}));await Wt(50);R.arrow=document.activeElement===document.querySelectorAll('#wkTrend .wk-cell')[0];}else R.arrow=true;
// a run with problems: the problem labels must keep a readable width (phones stack the row)
{const rp=[...WEEKLY.runs].sort((x,y)=>JSON.stringify(y).split('"kind"').length-JSON.stringify(x).split('"kind"').length)[0];if(rp){WEEKLY.pick(rp.run_id);await Wt(150);
  const L=[...document.querySelectorAll('#wkProb .wk-prob .lab')].map(e=>e.closest('td').getBoundingClientRect().width);R.labMin=L.length?Math.round(Math.min(...L)):-1;
  const VW0=document.documentElement.clientWidth;R.overP=[...document.querySelectorAll('#wkProb *')].filter(e=>{const b=e.getBoundingClientRect();return b.width&&b.right>VW0+1&&!e.closest('.dk-scroll');}).length;}}
// back to the default run for the screenshot / overflow check
const bk=q('#wkHero [data-wk-run]');if(window.WEEKLY&&R.run0)WEEKLY.pick(R.run0);await Wt(150);scrollTo(0,0);
R.problemsOrOk=!!q('#wkProb [data-wk="problems"],#wkProb [data-wk="allok"],#wkProb [data-wk="noreport"]');
const VW=document.documentElement.clientWidth;R.vw=VW;R.sw=document.documentElement.scrollWidth;
R.over=[];document.querySelectorAll('section[data-tab="weekly"] *').forEach(e=>{const b=e.getBoundingClientRect();if(!b.width)return;
  if(b.right>VW+1){const sc=e.closest('.dk-scroll');if(sc&&sc!==e&&sc.getBoundingClientRect().right<=VW+1)return;R.over.push((e.tagName+'.'+String(e.className).split(' ')[0]).toLowerCase()+' +'+Math.round(b.right-VW));}});
R.over=R.over.slice(0,6);
if(window.I18N&&I18N.lang==='vi'){const left=[];const tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
  while(n=tw.nextNode()){const t=n.nodeValue.trim(),p=n.parentElement;if(!t||!p||!p.closest('section[data-tab="weekly"]')||p.closest('code,pre,script,style,.obsraw'))continue;
    const hits=(t.match(/(?<![\p{L}\-_])(the|is|are|and|of|to|on|when|only|with|for|runs|files|passed|show|see|per|not|in|a)(?![\p{L}\-_])/giu)||[]).length;if(hits>=2)left.push(t.slice(0,80));}
  R.untranslated=left;}
location.hash='#weekly';await Wt(200);R.short=location.hash+' '+vizNav.state.v+'/'+vizNav.state.t;
vizNav.show('obs','weekly');await Wt(100);if(window.__wkPick)WEEKLY.pick(__wkPick);await Wt(100);scrollTo(0,0);
}catch(e){R.err=String(e&&e.stack||e)}R.jsErr=__e;parent.postMessage('RR:'+JSON.stringify(R),'*');},3500);</script>"""


def run(width, lang, theme, shot=None):
    head = ("<head><script>window.__e=[];addEventListener('error',e=>__e.push(String(e.message)));"
            "try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','%s')}catch(e){}"
            "document.documentElement.dataset.theme='%s';window.__wkPick=%s;</script>" % (lang, theme, json.dumps(PICK)))
    src = PAGE.read_text(encoding="utf-8").replace("<head>", head, 1)
    i = src.rindex("</body>")
    d = Path(tempfile.mkdtemp(prefix="ux_weekly_"))
    (d / "p.html").write_text(src[:i] + PROBE + src[i:], encoding="utf-8")
    h = 2600 if shot else 1400
    lst = ("<script>addEventListener('message',e=>{if(String(e.data).startsWith('RR:')){const x=document.createElement('pre');"
           "x.id='RR';x.style.display='none';x.textContent=String(e.data).slice(3);document.body.appendChild(x);}})</script>")
    (d / "w.html").write_text(f'<!doctype html><html><body style="margin:0;background:#888">{lst}<iframe src="p.html#obs/weekly" width="{width}" '
                              f'height="{h}" style="border:0;display:block"></iframe></body></html>', encoding="utf-8")
    win = f"--window-size={max(width, 520)},{h}"
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", win, "--virtual-time-budget=20000",
                          "--dump-dom", (d / "w.html").as_uri()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    if shot:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", win, "--virtual-time-budget=20000",
                        f"--screenshot={shot}", (d / "w.html").as_uri()], capture_output=True, timeout=300)
    m = re.search(r'<pre id="RR"[^>]*>(.*?)</pre>', dom, re.S)
    return json.loads(html.unescape(m.group(1))) if m else {"err": "no result"}


def main():
    shots = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
    fails = 0
    for width in (1280, 390):
        for lang in ("en", "vi"):
            for theme in ("light", "dark"):
                shot = str(Path(shots) / f"weekly_{width}_{lang}_{theme}.png") if shots else None
                r = run(width, lang, theme, shot)
                ck = {
                    "W-1 status": bool(r.get("status")) and r.get("tab") == "weekly",
                    "W-2 tiles": r.get("tiles") == 4,
                    "W-3 devices": r.get("devices") == ["cuda", "xpu", "amd", "rbln"],
                    "W-4 strip": r.get("cells", 0) >= r.get("runs", 1) > 0,
                    "W-5 drill-down": r.get("run1") == r.get("want1") and r.get("pressed") == r.get("want1") and r.get("focusKept") == r.get("want1")
                                      and r.get("rowRun") == r.get("rowWant") and r.get("arrow") is True and r.get("problemsOrOk"),
                    "W-6 overflow": r.get("sw", 9999) <= r.get("vw", 0) and not r.get("over") and not r.get("overP") and r.get("labMin", 0) != 0
                                    and (r.get("labMin", -1) == -1 or r.get("labMin") >= 120),
                    "W-7 js": not r.get("jsErr") and not r.get("err"),
                    "W-8 vi / link": not r.get("untranslated") and str(r.get("short", "")).startswith("#obs/weekly obs/weekly"),
                }
                bad = [k for k, v in ck.items() if not v]
                fails += bool(bad)
                print(f"{width:4} {lang} {theme:5} {'PASS' if not bad else 'FAIL ' + ', '.join(bad)} · status {r.get('status')!r} run {r.get('run0')} · "
                      f"tiles {r.get('tiles')} · devices {r.get('devices')} · cells {r.get('cells')}/{r.get('runs')} runs · "
                      f"click {r.get('run1')}=={r.get('want1')} row {r.get('rowRun')}=={r.get('rowWant')} arrow {r.get('arrow')} · "
                      f"width {r.get('sw')}/{r.get('vw')} problem labels >= {r.get('labMin')} px {r.get('over') or ''}{' · ' + str(r.get('untranslated')) if r.get('untranslated') else ''}"
                      f"{' · ERR ' + str(r.get('err') or r.get('jsErr')) if (r.get('err') or r.get('jsErr')) else ''}")
    if shots:
        print("screenshots ->", shots)
    print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
