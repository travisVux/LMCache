"""Split the built page into a frontend shell + data files, so data can be refreshed without rebuilding the frontend.

The builders (plan-2026-11/outputs/cpu_tests/build_*.py) still write one page with every tab's data inlined as
<script id="…" type="application/json">…</script>. This step, run by export_static.py, turns that page into:

  index.html / legacy.html     the frontend: same HTML, CSS and scripts; every data block left empty with
                               data-rd-src="data/<build>/<id>.json"; every inline script parked as type="text/x-rd-defer"
  data/<build>/<id>.json       the data, byte for byte the old block text; <build> = hash of all blocks, so the path
                               changes when any data changes (safe to cache forever) and a page never mixes two runs
  data/manifest.json           {build, made, files{id: path, bytes, sha256, made}}; the page polls it (no-cache) and
                               offers "reload" when a newer data build is live

A small loader (first script of the page) fetches the blocks, fills the empty elements, then runs the parked scripts
in their original order with document.readyState reported as "loading", and fires DOMContentLoaded afterwards. To
the page's scripts this is the same sequence as a normal load, so none of them had to change.

  python -X utf8 split_page.py <page.html> <out_dir>    # by hand: writes <out_dir>/index.html + data/
"""
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

SCHEMA = "release-desk.data/v1"
JS_TYPES = {"", "text/javascript", "application/javascript", "module"}
DEFER = "text/x-rd-defer"
MADE_KEYS = ("made", "at", "collected_at", "snap_at")

LOADER = r"""<script id="rdLoader">
/* Release Desk data loader (backend/split_page.py). Data lives in data/<build>/*.json, not in this page. */
(function(){
"use strict";
var D=document,W=window,C=W.RD_DATA=__CFG__;
function lang(){try{var h=D.documentElement.lang;if(h==='vi'||h==='en')return h;if(W.I18N&&I18N.lang)return I18N.lang;return localStorage.getItem('ciMapLang')||localStorage.getItem('opsLang')||D.documentElement.lang||'en';}catch(e){return 'en';}}
function T(en,vi){return lang()==='vi'?vi:en;}
function pill(id,html,bad){var p=D.getElementById(id);if(!p){p=D.createElement('div');p.id=id;p.setAttribute('role','status');
 p.style.cssText='position:fixed;right:16px;bottom:16px;z-index:2147483000;max-width:calc(100vw - 32px);padding:8px 12px;border-radius:8px;font:13px/1.4 system-ui,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.25)';
 (D.body||D.documentElement).appendChild(p);}
 p.style.background=bad?'#b3261e':'#1f2937';p.style.color='#fff';p.innerHTML=html;return p;}
if(location.protocol==='file:'){D.addEventListener('DOMContentLoaded',function(){pill('rdLoad',T('This page loads its data from data/*.json and needs a web server: run backend/server.py --root dist','Trang đọc dữ liệu từ data/*.json nên cần web server: chạy backend/server.py --root dist'),true);});return;}
var ids=Object.keys(C.files);
var got=ids.map(function(id){return fetch(C.files[id],{credentials:'same-origin'}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.text();})
 .then(function(t){return {ok:true,t:t};},function(e){return {ok:false,e:String(e&&e.message||e)};});});
var ready=new Promise(function(ok){if(D.readyState==='loading')D.addEventListener('DOMContentLoaded',ok,{once:true});else ok();});
ready.then(function(){pill('rdLoad',T('Loading data…','Đang tải dữ liệu…'));});
Promise.all([ready].concat(got)).then(function(res){
 /* one failed block must not blank every view (review 6.3): fill what arrived, run every script, name what is missing */
 var bad=[];ids.forEach(function(id,i){var x=res[i+1],el=D.getElementById(id);if(!el)return;if(x.ok)el.textContent=x.t;else bad.push(id+' ('+x.e+')');});
 Object.defineProperty(D,'readyState',{configurable:true,get:function(){return 'loading';}});
 try{[].slice.call(D.querySelectorAll('script[type="__DEFER__"]')).forEach(function(old){
   var s=D.createElement('script');for(var a=0;a<old.attributes.length;a++){var n=old.attributes[a].name;if(n!=='type')s.setAttribute(n,old.attributes[a].value);}
   s.text=old.text;old.parentNode.replaceChild(s,old);});}
 finally{delete D.readyState;}
 D.dispatchEvent(new Event('DOMContentLoaded',{bubbles:true}));
 var p=D.getElementById('rdLoad');
 if(bad.length){pill('rdLoad',T('Some data did not load, the views that need it are empty: ','Một phần dữ liệu không tải được, các view cần nó đang trống: ')+bad.join(', ').replace(/[<>&]/g,'')+' · <a href="" style="color:#fff;text-decoration:underline">'+T('Retry','Thử lại')+'</a>',true);if(W.console)console.warn('release-desk data missing:',bad.join(', '));}
 else if(p)p.remove();
 chip();watch();
}).catch(function(e){
 pill('rdLoad',T('Data did not load: ','Không tải được dữ liệu: ')+String(e&&e.message||e).replace(/[<>&]/g,'')+' · <a href="" style="color:#fff;text-decoration:underline">'+T('Retry','Thử lại')+'</a>',true);
 if(W.console)console.warn('release-desk data:',e);
});
function chip(){
 var DOT={synced:'#1a7f37',partial:'#9a6700',syncing:'#0969da',error:'#cf222e',unknown:'#6e7781'};
 var WORD={synced:['Synced','Đã đồng bộ'],partial:['Synced, with source errors','Đã đồng bộ, có nguồn lỗi'],syncing:['Syncing…','Đang đồng bộ…'],error:['Last sync failed','Lần đồng bộ cuối lỗi'],unknown:['Sync status unknown','Chưa rõ trạng thái']};
 var last=null;
 function show(s){last=s;var h=D.getElementById('hdrBuilt');if(!h)return;var c=D.getElementById('rdSync');
  if(!c){c=D.createElement('span');c.id='rdSync';c.setAttribute('role','status');c.style.cssText='display:inline-flex;align-items:center;gap:6px;margin-left:10px;font-size:12px;white-space:nowrap';h.appendChild(c);}
  var st=WORD[s.sync_status]?s.sync_status:'unknown',w=WORD[st],at=String(s.last_synced_at||s.page_made||'').slice(0,16).replace('T',' ');
  var pe=(s.partial_errors||[]).length,tip=['snapshot '+(s.label||'?'),'data '+(s.data_build||C.build),s.sync_id?'D1 #'+s.sync_id:'',s.in_sync===false?T('web copy and database differ','bản web và database đang lệch'):'',pe?pe+T(' source error(s)',' lỗi nguồn'):''].filter(Boolean).join(' · ');
  c.title=tip;c.innerHTML='<span style="width:8px;height:8px;border-radius:50%;background:'+DOT[st]+'"></span>'+T(w[0],w[1])+(at?' · '+at+' UTC':'')+(s.sync_id?' · #'+s.sync_id:'')+(s.in_sync===false?' · ⚠':'');}
 function get(){fetch('api/sync-status',{cache:'no-store',credentials:'same-origin'}).then(function(r){if(!r.ok)throw 0;return r.json();})
  .catch(function(){return fetch(C.manifest,{cache:'no-store',credentials:'same-origin'}).then(function(r){return r.ok?r.json():null;}).then(function(m){return m&&{sync_status:(m.partial_errors||[]).length?'partial':'synced',label:null,data_build:m.build,page_made:m.made,partial_errors:m.partial_errors};});})
  .then(function(s){if(s)show(s);}).catch(function(){});}
 get();setInterval(get,60000);
 try{new MutationObserver(function(){if(last)show(last);}).observe(D.documentElement,{attributes:true,attributeFilter:['lang']});}catch(e){}D.addEventListener('visibilitychange',function(){if(!D.hidden)get();});
}
function watch(){
 var busy=false;
 function check(){if(busy||D.hidden)return;busy=true;
  fetch(C.manifest,{cache:'no-store',credentials:'same-origin'}).then(function(r){return r.ok?r.json():null;}).then(function(m){
   if(m&&m.build&&m.build!==C.build){var p=pill('rdNew',T('New data is live','Đã có dữ liệu mới')+(m.made?' ('+String(m.made).slice(0,16).replace('T',' ')+' UTC)':'')+' · <a href="" style="color:#fff;text-decoration:underline">'+T('Reload','Tải lại')+'</a>');
    p.querySelector('a').onclick=function(ev){ev.preventDefault();location.reload();};}
  }).catch(function(){}).then(function(){busy=false;});}
 setInterval(check,C.poll_s*1000);D.addEventListener('visibilitychange',check);
}
})();
</script>"""


def _tags(html):
    """Yield (start, end_of_open_tag, content_end, close_end, attrs_text) for each <script> element, in order.
    HTML comments are skipped; a script element ends at the first </script (as browsers parse it)."""
    low, i = html.lower(), 0
    while True:
        s, c = low.find("<script", i), low.find("<!--", i)
        if s < 0:
            return
        if 0 <= c < s:
            e = low.find("-->", c + 4)
            i = len(html) if e < 0 else e + 3
            continue
        if low[s + 7:s + 8] not in (">", " ", "\t", "\n", "\r", "/"):
            i = s + 7
            continue
        o = low.index(">", s) + 1
        ce = low.index("</script", o)
        cl = low.index(">", ce) + 1
        yield s, o, ce, cl, html[s + 7:o - 1]
        i = cl


def _attr(attrs, name):
    m = re.search(r'(?:^|\s)' + name + r'\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', attrs, re.I)
    return None if not m else (m.group(2) if m.group(2) is not None else m.group(3) if m.group(3) is not None else m.group(4))


def blocks(html):
    """{id: text} of every inlined JSON data block (type application/json with an id)."""
    out = {}
    for s, o, ce, cl, attrs in _tags(html):
        bid = _attr(attrs, "id")
        if bid and (_attr(attrs, "type") or "").strip().lower() == "application/json":
            out[bid] = html[o:ce]
    return out


def build_id(data):
    h = hashlib.sha256()
    for k in sorted(data):
        h.update(k.encode() + b"\0" + data[k].encode("utf-8") + b"\0")
    return h.hexdigest()[:12]


def shell(html, files, build, poll_s=300):
    """The page without data: blocks emptied (data-rd-src), inline scripts parked, loader added first in <head>."""
    parts, last, parked = [], 0, 0
    for s, o, ce, cl, attrs in _tags(html):
        typ = (_attr(attrs, "type") or "").strip().lower()
        bid = _attr(attrs, "id")
        if bid in files and typ == "application/json":
            parts += [html[last:s], f'<script id="{bid}" type="application/json" data-rd-src="{files[bid]}"></script>']
        elif typ in JS_TYPES:
            if _attr(attrs, "src") is not None or typ == "module":
                raise SystemExit(f"split_page: external or module script ({attrs.strip()[:80]}): not supported, page left unsplit")
            new_attrs = re.sub(r'(?:^|\s)type\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', "", attrs, flags=re.I)
            parts += [html[last:s], f'<script type="{DEFER}"{new_attrs}>', html[o:cl]]
            parked += 1
        else:
            parts.append(html[last:cl])
        last = cl
    parts.append(html[last:])
    out = "".join(parts)
    cfg = json.dumps(dict(build=build, files=files, manifest="data/manifest.json", poll_s=poll_s), separators=(",", ":"))
    loader = LOADER.replace("__CFG__", cfg).replace("__DEFER__", DEFER)
    m = re.search(r"<head[^>]*>", out, re.I)
    if not m:
        raise SystemExit("split_page: no <head> in the page")
    out = out[:m.end()] + loader + out[m.end():]
    return out, parked


def partial_errors(data):
    """Collector errors the blocks carry ("errors" lists at the top level or one level down), as {source, error}."""
    out = []
    for k in sorted(data):
        try:
            d = json.loads(data[k])
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        for where, v in [(k, d.get("errors"))] + [(f"{k}.{s}", x.get("errors")) for s, x in d.items() if isinstance(x, dict)]:
            for e in v if isinstance(v, list) else []:
                out.append({"source": where, "error": (e if isinstance(e, str) else json.dumps(e, ensure_ascii=False))[:300]})
    return out[:50]


def _made(text):
    try:
        d = json.loads(text)
    except ValueError:
        return None
    return next((d[k] for k in MADE_KEYS if isinstance(d, dict) and isinstance(d.get(k), str)), None)


def split(pages, out_dir, poll_s=300):
    """pages: {output name: html}. All pages must carry the same data blocks. Writes the shells + data/ into out_dir.
    Returns the manifest."""
    out_dir = Path(out_dir)
    data = None
    for name, html in pages.items():
        b = blocks(html)
        if not b:
            raise SystemExit(f"split_page: {name} has no data blocks")
        if data is None:
            data = b
        elif b != data:
            raise SystemExit(f"split_page: {name} carries different data blocks than the first page")
    build = build_id(data)
    files = {k: f"data/{build}/{k}.json" for k in sorted(data)}
    ddir = out_dir / "data" / build
    ddir.mkdir(parents=True, exist_ok=True)
    for k, text in data.items():
        (ddir / f"{k}.json").write_text(text, encoding="utf-8", newline="")
    report = {}
    for name, html in pages.items():
        page, parked = shell(html, files, build, poll_s)
        left = blocks(page)
        if any(left[k] for k in left if k in files) or len(left) != len(data):
            raise SystemExit(f"split_page: {name}: data left inline after the split")
        (out_dir / name).write_text(page, encoding="utf-8", newline="")
        report[name] = dict(bytes=len(page.encode("utf-8")), scripts=parked)
    man = dict(schema=SCHEMA, build=build, made=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               run_id=int(os.environ["RD_RUN_ID"]) if os.environ.get("RD_RUN_ID", "").isdigit() else None,
               partial_errors=partial_errors(data), pages=report,
               files={k: dict(path=files[k], bytes=len(data[k].encode("utf-8")),
                              sha256=hashlib.sha256(data[k].encode("utf-8")).hexdigest(), made=_made(data[k]))
                      for k in sorted(data)})
    (out_dir / "data" / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return man


if __name__ == "__main__":
    import sys
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    m = split({"index.html": src.read_text(encoding="utf-8")}, out)
    print(f"build {m['build']}: {len(m['files'])} data files, {sum(f['bytes'] for f in m['files'].values()) / 2**20:.1f} MB; "
          f"shell {m['pages']['index.html']['bytes'] / 2**10:.0f} KB, {m['pages']['index.html']['scripts']} scripts parked")
