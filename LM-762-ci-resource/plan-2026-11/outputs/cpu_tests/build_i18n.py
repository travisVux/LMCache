"""Add an EN / VI language switch to 06_PR_TO_CI_VISUAL.html (idempotent).

Text fragments are translated in place from i18n_vi.VI (exact match) and i18n_vi.RULES
(regex for strings with numbers). File paths, code, test names and test docstrings stay
in English. A MutationObserver translates content that JS renders later (tooltips,
explorer, matrix details). The mindmap translates labels before truncating them.
"""
import json
import re

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # sibling modules also under python -I
from i18n_vi import RULES, VI

from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")

CSS = r"""
/* I18N:CSS:START */
.lang{display:inline-flex;background:var(--surface-2);border-radius:9px;padding:3px;gap:2px}
.lang button{all:unset;cursor:pointer;font-size:12px;font-weight:650;padding:4px 10px;border-radius:7px;color:var(--text-secondary)}
.lang button:hover{color:var(--text-primary)}
.lang button:focus-visible{outline:2px solid var(--series-1)}
.lang button[aria-pressed="true"]{background:var(--surface-1);color:var(--text-primary);box-shadow:0 0 0 1px var(--border)}
/* I18N:CSS:END */
"""

JS = r"""
<!-- I18N:JS:START -->
<script id="i18nData" type="application/json">__DATA__</script>
<script>
(function(){
  const D=JSON.parse(document.getElementById('i18nData').textContent);
  const VI=D.vi, RULES=D.rules.map(([p,r])=>[new RegExp(p),r]);
  const SKIP='code,pre,script,style,#mm,.p,.det-files,#slow .l,.tf-body .doc,.tt td,#nr td.p,.lang,.obsraw,.obs-set input';
  let lang='en';
  try{ lang=localStorage.getItem('ciMapLang') || ((navigator.language||'').toLowerCase().startsWith('vi')?'vi':'en'); }catch(e){}
  function tr(k){
    let v=VI[k]; if(v!==undefined) return v;
    for(const [re,rep] of RULES){ const m=k.match(re); if(m){ return rep.replace(/§T\(\$(\d)\)/g,(_,i)=>{const x=tr(m[i]);return x===undefined?m[i]:x;}).replace(/\$(\d)/g,(_,i)=>m[i]); } }
    return undefined;
  }
  // whitespace inside a text node is collapsed before the lookup: a formatter that wraps the HTML must not break the translation
  function t(s){ if(lang!=='vi'||typeof s!=='string') return s; const k=s.trim(); if(!k) return s; let v=tr(k); if(v===undefined&&/\s{2,}|\n/.test(k)) v=tr(k.replace(/\s+/g,' ')); if(v===undefined) return s; return s.match(/^\s*/)[0]+v+s.match(/\s*$/)[0]; }
  const orig=new WeakMap();
  function applyNode(n){
    const p=n.parentElement; if(!p||p.closest(SKIP)) return;
    let o=orig.get(n); if(o===undefined){ o=n.nodeValue; orig.set(n,o); }
    const nv=t(o); if(n.nodeValue!==nv) n.nodeValue=nv;
  }
  function apply(root){
    if(root.nodeType===3){ applyNode(root); return; }
    if(root.nodeType!==1) return;
    const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT); let n; while(n=w.nextNode()) applyNode(n);
    root.querySelectorAll&&root.querySelectorAll('[placeholder]').forEach(e=>{ if(!e.dataset.phEn) e.dataset.phEn=e.getAttribute('placeholder'); e.setAttribute('placeholder',t(e.dataset.phEn)); });
  }
  new MutationObserver(ms=>{ if(lang!=='vi') return; ms.forEach(m=>m.addedNodes.forEach(apply)); }).observe(document.body,{childList:true,subtree:true});

  // switch UI
  const box=document.createElement('div'); box.className='lang'; box.setAttribute('role','group'); box.setAttribute('aria-label','Language / Ngôn ngữ');
  [['en','EN','English'],['vi','VI','Tiếng Việt']].forEach(([id,txt,title])=>{const b=document.createElement('button'); b.type='button'; b.dataset.l=id; b.textContent=txt; b.title=title; b.addEventListener('click',()=>setLang(id)); box.appendChild(b);});
  const row=document.querySelector('.vnav .row'), all=row&&row.querySelector('label.all');
  if(row) row.insertBefore(box, all||null);

  function setLang(l){
    lang=l; try{localStorage.setItem('ciMapLang',l);}catch(e){}
    document.documentElement.lang=l;
    box.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.l===l)));
    apply(document.body);
    dispatchEvent(new Event('langchange'));
  }
  // origOf / adopt: let the entity linkifier (build_entity_ui.py) split a text node and later restore its English source
  window.I18N={t,setLang,get lang(){return lang;},origOf:n=>orig.get(n),adopt:(n,o)=>{orig.set(n,o);}};
  document.addEventListener('keydown',e=>{ if(e.key.toLowerCase()!=='l'||e.ctrlKey||e.metaKey||e.altKey) return; const tg=e.target&&e.target.closest?e.target:document.body; if(tg.closest('input,select,textarea')) return; setLang(lang==='vi'?'en':'vi'); });
  setLang(lang);
})();
</script>
<!-- I18N:JS:END -->
"""


def put(page, start, end, block, anchor):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:]


def main():
    page = open(PAGE, encoding="utf-8").read()
    data = json.dumps({"vi": VI, "rules": RULES}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = put(page, "/* I18N:CSS:START */", "/* I18N:CSS:END */", CSS, "@media (max-width:980px)")
    page = put(page, "<!-- I18N:JS:START -->", "<!-- I18N:JS:END -->", JS.replace("__DATA__", data), "</body>")
    # mindmap: translate the label before it is truncated; redraw on language change
    page = page.replace("const label=n=>n.n;", "const label=n=>(window.I18N?I18N.t(n.n):n.n);")
    hook = "  addEventListener('langchange',()=>{GN.replaceChildren();draw();});\n"
    if hook not in page:
        page = page.replace("  rebuild();\n})();", hook + "  rebuild();\n})();", 1)
    # keyboard hint
    page = page.replace("<kbd>C</kbd> / <kbd>G</kbd> switch · <kbd>←</kbd><kbd>→</kbd> tabs",
                        "<kbd>C</kbd> / <kbd>G</kbd> switch · <kbd>←</kbd><kbd>→</kbd> tabs · <kbd>L</kbd> EN/VI")
    open(PAGE, "w", encoding="utf-8").write(page)
    print("i18n: %d strings, %d rules; mindmap hook=%s" % (len(VI), len(RULES), hook in page))


if __name__ == "__main__":
    main()
