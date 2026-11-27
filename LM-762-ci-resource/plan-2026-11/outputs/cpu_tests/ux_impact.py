"""Checks of the CI impact tab (#obs/impact, build_impact.py v4, redesign 2026-11-26) in headless Chrome.

The built page is loaded in an iframe of exact width (1280 and 390 px), in EN and VI, light and dark. Per combination:
  I-1  verdict strip: state + 3 chips (cost / speed / safety) + day progress + before / after windows;
       the state follows the rule (proven only when after >= min_days AND every key number has n >= min_n)
  I-2  one before -> after row per key number (every headline metric included), grouped cost / speed / safety
  I-3  trust: no change, no % and no good / bad colour when n < min_n (rows, table, watchlist); hollow after dot
  I-4  'where did the GPU time go': >= 5 parts, the written sum equals the after total, the explanation sentence is there
  I-5  table: one row per metric, always in the DOM, sortable; tooltip on keyboard focus
  I-6  no horizontal overflow (page and every element of the tab)
  I-7  no JS errors
  I-8  VI: no untranslated English sentence; the EN / VI switch re-renders the tab
  I-9  routes #obs/impact, #impact, #ci-impact, #before-after open the tab
  I-10 a part with n = 0 (post-merge builds): 'no data' + hatched, not in the sum, its share of before on the chart and in the text, sum closes
  I-11 numbers: VI format (1,78; no 1.78) in every tooltip / aria-label and the live tooltip; EN keeps 1.78
  I-12 percent rule everywhere in the tab: whole % when |x| >= 10, one decimal below
  I-13 plain words: no GPU-min / Runner-min / k3-multiprocess-* / convert-to-draft (EN); giờ GPU, chạy lại, lượt (VI); retry row renamed
  I-14 first screen: the windows are one line, the weekday warning is one sentence
  I-15 table: Cost / Speed / Safety column, sortable; unit in its own column, not in the number cells; watchlist says 'so far' once
  I-16 weekday rule on synthetic data (restored after): opposite signs -> Cost chip + row neutral 'unclear'; same sign -> not unclear
  python -X utf8 ux_impact.py [--shots DIR]      exit 1 on any failure
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

PROBE = r"""<script>window.__e=window.__e||[];
setTimeout(async()=>{const Wt=ms=>new Promise(r=>setTimeout(r,ms)),q=s=>document.querySelector(s),qa=s=>[...document.querySelectorAll(s)],R={};try{
vizNav.show('obs','impact');await Wt(500);
R.tab=vizNav.state.t;const D=(window.IMPACT&&IMPACT.data)||{},MS=D.metrics||[],VS=D.versions||[],A=VS[VS.length-1]||{},MIN=D.min_days||14;R.nm=MS.length;
const val=(m,id)=>((m&&m.values)||{})[id]||{},hasN=x=>!!x&&x.value!=null&&(x.n||0)>0,enough=(m,x)=>hasN(x)&&(x.n||0)>=(m.min_n||0),M=k=>MS.find(x=>x.key===k);
// I-1 verdict strip
const V=q('#imWin [data-im="verdict"]');R.verdict=V?V.dataset.state:null;R.chips=qa('#imWin [data-chip]').map(c=>c.dataset.chip+':'+c.dataset.state);
R.prog=!!q('#imWin [data-im="progress"]');R.windows=!!q('#imWin [data-win="before"]')&&!!q('#imWin [data-win="after"]');
const rows=qa('#imGpu .im-row[data-key]'),keys=rows.map(r=>r.dataset.key).filter(k=>k!=='gpu_h_day_wd');
const proven=(A.days||0)>=MIN&&keys.every(k=>enough(M(k),val(M(k),A.id)));R.proven=proven;
R.ruleOk=V?(proven?V.dataset.state!=='early':V.dataset.state==='early'):false;
// I-2 rows
R.rows=keys.length;R.groups=qa('#imGpu [data-grp]').map(g=>g.dataset.grp).join(',');R.headMissing=MS.filter(m=>m.headline&&!keys.includes(m.key)).map(m=>m.key);
// I-3 trust: n < min_n -> no change, no %, no good / bad colour, hollow dot
R.badTrust=[];
rows.forEach(r=>{const m=M(r.dataset.key);if(!m)return;const e=enough(m,val(m,A.id)),c=r.querySelector('.im-chg');
  if(String(+e)!==r.dataset.enough)R.badTrust.push('flag:'+m.key);
  if(!e){if(c.querySelector('.im-pill.good,.im-pill.bad,.im-up,.im-down')||/%|[+−]\d/.test(c.textContent))R.badTrust.push('row:'+m.key);
    const d=r.querySelector('.im-dot.a');if(d&&!d.classList.contains('hollow'))R.badTrust.push('dot:'+m.key);}});
qa('#imRel tr[data-key]').forEach(tr=>{const m=M(tr.dataset.key);if(m&&!enough(m,val(m,A.id))&&tr.querySelector('[data-c]').textContent.trim()!=='–')R.badTrust.push('table:'+m.key);});
qa('#imGha [data-watch]').forEach(li=>{const m=M(li.dataset.watch);if(!m||!enough(m,val(m,A.id)))R.badTrust.push('watch:'+li.dataset.watch);});
qa('#imWin [data-chip]').forEach(c=>{if(c.dataset.state==='better'||c.dataset.state==='worse'){const ks={cost:['gpu_h_day','gpu_h_per_push'],speed:['gpu_queue_p50','l12_done_p50'],safety:['repeat_rate','weekly_pass','weekly_mp_fail']}[c.dataset.chip]||[];
  if(!ks.some(k=>M(k)&&enough(M(k),val(M(k),A.id))))R.badTrust.push('chip:'+c.dataset.chip);}});
// I-4 GPU parts, written sum, explanation
R.parts=qa('#imMp [data-im="gpu-go"] [data-part]').length;const br=q('#imMp [data-im="bridge"]');R.sumOk=!!br&&Math.abs(parseFloat(br.dataset.sum)-parseFloat(br.dataset.after))<0.05;
const why=q('#imMp [data-im="why"]');R.why=why?why.textContent.length:0;
const t=M('gpu_h_day'),du=M('draft_gpu_unit');R.contra=!!(t&&du&&val(t,A.id).value>val(t,VS[0].id).value&&val(du,A.id).value<val(du,VS[0].id).value);
R.whyOk=!R.contra||(why&&/%/.test(why.textContent)&&why.textContent.length>120);
// shared helpers for the fix checks: numbers as the page writes them in the current language
const LG=(window.I18N&&I18N.lang)||'en',DEC=LG==='vi'?',':'.';
const num=x=>parseFloat(LG==='vi'?x.replace(/\u202f/g,'').replace(/\./g,'').replace(',','.'):x.replace(/,/g,''));
const nums=s=>(String(s).match(/\d[\d\u202f.,]*\d|\d/g)||[]).map(num);
const IMS='section[data-tab="impact"]',texts=()=>{const out=[];const tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
  while(n=tw.nextNode()){const p=n.parentElement;if(!p||!p.closest(IMS)||p.closest('code,pre,script,style,.obsraw'))continue;const v=n.nodeValue.trim();if(v)out.push(v);}
  qa(IMS+' [data-tip]').forEach(e=>out.push(e.getAttribute('data-tip')));qa(IMS+' [aria-label]').forEach(e=>out.push(e.getAttribute('aria-label')));return out;};
// I-10 a part with n = 0 (post-merge builds) is 'no data', hatched, NOT in the sum; the chart says its share of before; the sum still closes
const devm=M('dev_tested'),tt=M('gpu_h_day'),tp_=M('gpu_h_day_pr');R.post0=!!devm&&!hasN(val(devm,A.id));
if(R.post0){const pr=q('#imMp [data-part="post"]'),txt=pr?pr.textContent:'',bpost=val(tt,VS[0].id).value-val(tp_,VS[0].id).value;
  const terms=br?qa('#imMp [data-im="bridge"] [data-term]').filter(e=>e.dataset.term!=='gap').map(e=>{const t=e.textContent.trim();return (t[0]==='−'?-1:1)*nums(t)[0];}):[];
  // the sum must close on the numbers AS SHOWN: before − gap = comparable, comparable + terms = after
  const sv=k=>{const e=br&&br.querySelector(`[data-v="${k}"]`);return e?nums(e.textContent)[0]:NaN;},gs=br&&br.querySelector('[data-term="gap"]')?nums(br.querySelector('[data-term="gap"]').textContent)[0]:NaN;
  const close=!!br&&Math.abs(sv('before')-gs-sv('comparable'))<0.001&&Math.abs(sv('comparable')+terms.reduce((a,b)=>a+b,0)-sv('after'))<0.001;
  R.n0={row:!!pr&&pr.dataset.nodata==='1',nodata:/no data|chưa có dữ liệu/.test(txt),hatch:!!(pr&&pr.querySelector('.im-hatch')),noZeroBar:!!pr&&!pr.querySelector('.im-bar.a,.v.a'),
    notInSum:!!br&&(br.dataset.gap||'').split(',').includes('post')&&!br.querySelector('[data-term="post"]')&&Math.abs(parseFloat(br.dataset.gapv)-bpost)<0.06,
    share:nums(txt).some(x=>Math.abs(x-bpost)<0.06)&&/cannot be compared yet|chưa so sánh được/.test(txt),why:!!why&&nums(why.textContent).some(x=>Math.abs(x-bpost)<0.06),
    totalSeg:!!q('#imMp [data-part="total"] [data-im="gap-seg"]'),close};
  R.n0bad=Object.keys(R.n0).filter(k=>!R.n0[k]);}
// I-11 VI number format: every tooltip / aria-label in the tab, and the live tooltip on focus
R.numBad=[];const tipsAll=qa(IMS+' [data-tip]').map(e=>e.getAttribute('data-tip')).concat(qa(IMS+' [aria-label]').map(e=>e.getAttribute('aria-label')));
tipsAll.forEach(t=>{if(LG==='vi'?/\d\.\d/.test(t)||/\d,\d{3}(?!\d)/.test(t):/\d,\d{1,2}(?!\d)/.test(t)||/\u202f/.test(t))R.numBad.push(t.slice(0,60));});
{const d=q('#imGpu .im-row[data-key="gpu_h_per_push"] .im-dot.a')||q('#imGpu .im-dot.a');if(d){d.focus();await Wt(60);const tx=(document.getElementById('imTip')||{}).textContent||'';
  R.tipNum=LG==='vi'?/\d,\d/.test(tx)&&!/\d\.\d/.test(tx):/\d\.\d/.test(tx)&&!/\d,\d{1,2}(?!\d)/.test(tx);d.blur();}else R.tipNum=false;}
R.numBad=R.numBad.slice(0,4);
// I-12 percent rule everywhere: whole % when |x| >= 10, one decimal below (0 may stay 0)
R.pctBad=[];texts().forEach(t=>{for(const m of String(t).matchAll(/(\d[\d\u202f.,]*)\s?%/g)){const raw=m[1],x=Math.abs(num(raw)),dp=raw.includes(DEC)?raw.split(DEC).pop().length:0;
  if(x>=10?dp!==0:(x!==0&&dp!==1))R.pctBad.push(raw+'%');}});R.pctBad=[...new Set(R.pctBad)].slice(0,8);
// I-13 plain words + one VI term set
R.termBad=[];texts().forEach(t=>{const hit=LG==='vi'?t.match(/GPU-giờ|GPU-phút|\bretry\b|\bruns?\b|phút runner|Retry vẫn lỗi|Sớm nhất:/i):t.match(/GPU-min\b|Runner-min|k3-multiprocess-\*|convert-to-draft|GPU-hours/);if(hit)R.termBad.push(hit[0]+' @ '+t.slice(0,50));});
R.termBad=[...new Set(R.termBad)].slice(0,6);
R.retryRow=/^(≈ )?(GPU on retries that failed again|GPU cho lần chạy lại vẫn lỗi)/.test(((q('#imMp [data-part="retry"] .im-lab')||{}).textContent||'').trim());
// I-14 first screen: windows on one line (one element, no boxes), weekday warning = one sentence
const wn=q('#imWin [data-im="windows"]');R.winLine=!!wn&&wn.tagName==='P'&&!q('#imWin .im-win');
const wdn=q('#imWin [data-im="weekday"]');R.wdSent=wdn?(wdn.textContent.match(/[.!?](\s|$)/g)||[]).length:0;R.wdOk=!wdn||R.wdSent===1;
// I-15 details table: Cost / Speed / Safety column (sortable), unit in its own column, number cells without units
const ths=qa('#imRel table[data-im="table"] th').map(t=>t.dataset.col);R.tCols=ths.join(',');
const gb=q('#imRel [data-sort="g"]');if(gb){gb.click();await Wt(80);const gs=qa('#imRel tr[data-key]').map(tr=>({cost:0,speed:1,safety:2})[tr.dataset.g]);R.gSorted=gs.every((x,i)=>!i||gs[i-1]<=x)&&gs.includes(0)&&gs.includes(2);}
const bi=ths.indexOf('b'),ai=ths.indexOf('a');R.unitCells=qa('#imRel tr[data-key]').map(tr=>[tr.children[bi],tr.children[ai]]).flat().filter(td=>td&&/[A-Za-zÀ-ỹ%]/.test(td.textContent)).length;
R.watchSoFar=qa('#imGha .im-sofar').length;
// I-5 table + sort + tooltip
R.trs=qa('#imRel table[data-im="table"] tr[data-key]').length;
const sb=q('#imRel [data-sort="n"]');if(sb){sb.click();await Wt(80);const ns=qa('#imRel tr[data-key]').map(tr=>M(tr.dataset.key)).map(m=>(val(m,A.id).n||0));R.sorted=ns.every((x,i)=>!i||ns[i-1]<=x)&&q('#imRel th[data-col="n"]').getAttribute('aria-sort')==='ascending';}
const dot=q('#imGpu .im-dot');if(dot){dot.focus();await Wt(60);const tp=document.getElementById('imTip');R.tip=!!(tp&&!tp.hidden&&tp.textContent.length>5);dot.blur();}else R.tip=false;
// I-6 overflow
const VW=document.documentElement.clientWidth;R.vw=VW;R.sw=document.documentElement.scrollWidth;
R.over=[];document.querySelectorAll('section[data-tab="impact"] *').forEach(e=>{const b=e.getBoundingClientRect();if(!b.width)return;
  if(b.right>VW+1||b.left<-1){const sc=e.closest('.dk-scroll');if(sc&&sc!==e&&sc.getBoundingClientRect().right<=VW+1)return;R.over.push((e.tagName+'.'+String(e.className).split(' ')[0]).toLowerCase()+' +'+Math.round(Math.max(b.right-VW,-b.left)));}});
R.over=R.over.slice(0,6);
// I-8 VI text + live EN / VI switch
const L0=window.I18N&&I18N.lang;
if(L0==='vi'){const left=[];const tw=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
  while(n=tw.nextNode()){const s=n.nodeValue.trim(),p=n.parentElement;if(!s||!p||!p.closest('section[data-tab="impact"]')||p.closest('code,pre,script,style,.obsraw'))continue;
    const hits=(s.match(/(?<![\p{L}\-_])(the|is|are|and|of|to|on|when|only|with|for|runs|files|passed|show|see|per|not|in|a|too|early|better|worse|before|after)(?![\p{L}\-_])/giu)||[]).length;if(hits>=2)left.push(s.slice(0,80));}
  R.untranslated=left;R.viVerdict=/[ăâđêôơư]/i.test(((V||{}).textContent)||'');}
if(window.I18N){const h0=q('#imWinH').textContent;I18N.setLang(L0==='vi'?'en':'vi');await Wt(200);const h1=q('#imWinH').textContent;R.switch=h0!==h1&&!!q('#imWin [data-im="verdict"]');I18N.setLang(L0);await Wt(200);R.switchBack=q('#imWinH').textContent===h0;}
// I-16 weekday rule (synthetic data, then restored): plain vs same-weekday comparisons in opposite directions -> Cost chip neutral 'unclear'
{const W=D.gpu_by_weekday||{},bw=W[VS[0].id]||{},aw=W[A.id]||{},ks=Object.keys(aw).filter(k=>aw[k][1]>0&&bw[k]&&bw[k][1]>0);
  const t=M('gpu_h_day'),av=val(t,A.id),bv=val(t,VS[0].id).value,wd=ks.length?ks.reduce((s,k)=>s+(bw[k][0]/bw[k][1])*aw[k][1],0)/ks.reduce((s,k)=>s+aw[k][1],0):null;
  const chipOf=()=>q('#imWin [data-chip="cost"]'),neutral=c=>!!c&&c.dataset.state==='unclear'&&!c.classList.contains('good')&&!c.classList.contains('bad')&&/unclear \(weekday effect\)|chưa rõ \(lệch ngày trong tuần\)/.test(c.textContent);
  if((A.days||0)<7&&wd!=null&&enough(t,av)){const real=(av.value-bv)*(av.value-wd)<0;R.wdReal=real?neutral(chipOf()):chipOf().dataset.state!=='unclear';
    const keep=av.value;av.value=Math.round(((bv+wd)/2)*10)/10;IMPACT.render();await Wt(60);const c=chipOf(),row=q('#imGpu .im-row[data-key="gpu_h_day"]');
    R.wdSplit=neutral(c)&&!!row&&!row.querySelector('.im-pill.good,.im-pill.bad,.im-up,.im-down')&&row.querySelector('.im-chg').dataset.j==='unclear'&&!q('#imGha [data-watch="gpu_h_day"]');
    av.value=Math.round(Math.min(bv,wd)*0.5*10)/10;IMPACT.render();await Wt(60);R.wdAgree=chipOf().dataset.state!=='unclear';
    av.value=keep;IMPACT.render();await Wt(60);R.wdRestored=val(t,A.id).value===keep;}
  else R.wdSkip=true;}
// I-9 routes
R.routes=[];for(const h of ['#impact','#ci-impact','#before-after','#obs/impact']){vizNav.show('obs','today');await Wt(80);location.hash=h;await Wt(250);R.routes.push(h+'>'+location.hash+' '+vizNav.state.v+'/'+vizNav.state.t);}
vizNav.show('obs','impact');await Wt(100);scrollTo(0,0);
}catch(e){R.err=String(e&&e.stack||e)}R.jsErr=__e;parent.postMessage('RR:'+JSON.stringify(R),'*');},3500);</script>"""


def run(width, lang, theme, shot=None):
    head = ("<head><script>window.__e=[];addEventListener('error',e=>__e.push(String(e.message)));"
            "try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','%s')}catch(e){}"
            "document.documentElement.dataset.theme='%s';</script>" % (lang, theme))
    src = PAGE.read_text(encoding="utf-8").replace("<head>", head, 1)
    i = src.rindex("</body>")
    d = Path(tempfile.mkdtemp(prefix="ux_impact_"))
    (d / "p.html").write_text(src[:i] + PROBE + src[i:], encoding="utf-8")
    h = (7600 if width < 600 else 4600) if shot else 1400
    lst = ("<script>addEventListener('message',e=>{if(String(e.data).startsWith('RR:')){const x=document.createElement('pre');"
           "x.id='RR';x.style.display='none';x.textContent=String(e.data).slice(3);document.body.appendChild(x);}})</script>")
    (d / "w.html").write_text(f'<!doctype html><html><body style="margin:0;background:#888">{lst}<iframe src="p.html#obs/impact" width="{width}" '
                              f'height="{h}" style="border:0;display:block"></iframe></body></html>', encoding="utf-8")
    win = f"--window-size={max(width, 520)},{h}"
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", win, "--virtual-time-budget=25000",
                          "--dump-dom", (d / "w.html").as_uri()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    if shot:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", win, "--virtual-time-budget=25000",
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
                shot = str(Path(shots) / f"impact_{width}_{lang}_{theme}.png") if shots else None
                r = run(width, lang, theme, shot)
                routes = r.get("routes") or []
                ck = {
                    "I-1 verdict": r.get("tab") == "impact" and r.get("verdict") in ("early", "better", "worse") and r.get("ruleOk") is True
                    and [c.split(":")[0] for c in r.get("chips") or []] == ["cost", "speed", "safety"] and r.get("prog") and r.get("windows"),
                    "I-2 rows": r.get("rows", 0) >= 6 and r.get("groups") == "cost,speed,safety" and not r.get("headMissing"),
                    "I-3 trust": not r.get("badTrust"),
                    "I-4 gpu": r.get("parts", 0) >= 5 and r.get("sumOk") is True and r.get("why", 0) > 40 and r.get("whyOk") is True,
                    "I-5 table / tooltip": r.get("trs") == r.get("nm") and r.get("nm", 0) > 0 and r.get("sorted") is True and r.get("tip") is True,
                    "I-6 overflow": r.get("sw", 9999) <= r.get("vw", 0) and not r.get("over"),
                    "I-7 js": not r.get("jsErr") and not r.get("err"),
                    "I-8 en / vi": not r.get("untranslated") and (lang != "vi" or r.get("viVerdict") is True) and r.get("switch") is True and r.get("switchBack") is True,
                    "I-9 routes": len(routes) == 4 and all(x.endswith("#obs/impact obs/impact") for x in routes),
                    "I-10 n=0 part": not r.get("post0") or not r.get("n0bad"),
                    "I-11 number format": not r.get("numBad") and r.get("tipNum") is True,
                    "I-12 % rule": not r.get("pctBad"),
                    "I-13 plain words": not r.get("termBad") and r.get("retryRow") is True,
                    "I-14 first screen": r.get("winLine") is True and r.get("wdOk") is True,
                    "I-15 table": "g" in (r.get("tCols") or "") and "u" in (r.get("tCols") or "") and r.get("gSorted") is True and r.get("unitCells") == 0 and r.get("watchSoFar") == 0,
                    "I-16 weekday rule": bool(r.get("wdSkip")) or (r.get("wdReal") is True and r.get("wdSplit") is True and r.get("wdAgree") is True and r.get("wdRestored") is True),
                }
                bad = [k for k, v in ck.items() if not v]
                fails += bool(bad)
                print(f"{width:4} {lang} {theme:5} {'PASS' if not bad else 'FAIL ' + ', '.join(bad)} · verdict {r.get('verdict')} {r.get('chips')} · rows {r.get('rows')} · "
                      f"parts {r.get('parts')} · table {r.get('trs')}/{r.get('nm')} · width {r.get('sw')}/{r.get('vw')} {r.get('over') or ''}"
                      f"{' · trust ' + str(r.get('badTrust')) if r.get('badTrust') else ''}{' · routes ' + str(routes) if 'I-9 routes' in bad else ''}"
                      f"{' · ' + str(r.get('untranslated')) if r.get('untranslated') else ''}"
                      f"{' · n0 ' + str(r.get('n0bad')) if r.get('n0bad') else ''}{' · num ' + str(r.get('numBad')) if r.get('numBad') else ''}"
                      f"{' · pct ' + str(r.get('pctBad')) if r.get('pctBad') else ''}{' · terms ' + str(r.get('termBad')) if r.get('termBad') else ''}"
                      f"{' · wd ' + str([r.get(k) for k in ('wdReal', 'wdSplit', 'wdAgree', 'wdRestored', 'wdSkip')]) if 'I-16 weekday rule' in bad else ''}"
                      f"{' · tbl ' + str([r.get(k) for k in ('tCols', 'gSorted', 'unitCells', 'watchSoFar')]) if 'I-15 table' in bad else ''}"
                      f"{' · first ' + str([r.get(k) for k in ('winLine', 'wdSent')]) if 'I-14 first screen' in bad else ''}"
                      f"{' · tip ' + str(r.get('tipNum')) if 'I-11 number format' in bad else ''}{' · retryRow ' + str(r.get('retryRow')) if 'I-13 plain words' in bad else ''}"
                      f"{' · ERR ' + str(r.get('err') or r.get('jsErr')) if (r.get('err') or r.get('jsErr')) else ''}")
    if shots:
        print("screenshots ->", shots)
    print("RESULT:", "PASS" if not fails else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
