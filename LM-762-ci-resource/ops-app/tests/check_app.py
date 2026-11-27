"""Check every view of the Release Desk: JS console errors at 1280 px and horizontal overflow at a real 390 px width.

Serves ops-app/dist/ (run backend/export_static.py first) on a free local port, then for each hash:
  desktop: headless Chrome at 1280 px with console logging -> any error / uncaught exception (shell and embedded page)
  mobile : a same-origin harness page holds the app in a 390 px iframe (headless Chrome cannot make a window narrower
           than ~518 px) and measures scrollWidth of the shell and of the embedded page.
Run:  python -X utf8 tests/check_app.py [hash ...] [--lang vi|en] [--shot DIR]
Exit 1 when any view has a console error or overflows.
"""
import argparse
import functools
import http.server
import re
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DIST = Path(__file__).resolve().parents[1] / "dist"
HASHES = ["now", "history", "today", "weekly", "impact", "releases", "trace", "coming", "ci-cost/cpu", "ci-cost/gpu", "rebase-risk",
          "gates/guide", "gates/tiers", "tests/cpu-overview", "tests/cpu-explorer", "tests/gpu-overview", "tests/gpu-mindmap",
          "r1130/baseline", "r1130/prs", "r1130/quality"]
HARNESS = "check-harness.html"   # no leading "__": the server refuses those names
MISSING = set()
HARNESS_HTML = """<!doctype html><html><body style="margin:0"><iframe id="f" style="width:390px;height:1400px;border:0"></iframe><pre id="R"></pre>
<script>
const q=new URLSearchParams(location.search),f=document.getElementById('f');
try{localStorage.setItem('opsLang',q.get('lang'));localStorage.setItem('ciMapLang',q.get('lang'));}catch(e){}
f.src='shell.html#'+q.get('h');
const measure=d=>{const W=d.documentElement.clientWidth,o=[];d.querySelectorAll('body *').forEach(e=>{const b=e.getBoundingClientRect(),cs=d.defaultView.getComputedStyle(e);
 if(b.width&&b.right>W+1&&cs.position!=='fixed'&&cs.visibility!=='hidden'&&e.offsetParent!==null){const p=e.parentElement.getBoundingClientRect();if(p.right<=W+1)o.push(e.tagName.toLowerCase()+'.'+String(e.className).trim().split(/\\s+/)[0]+' +'+Math.round(b.right-W))}});
 return {W,S:d.documentElement.scrollWidth,o:o.slice(0,5)};};
f.onload=()=>setTimeout(()=>{const a=f.contentDocument,res={shell:measure(a)};const g=a.getElementById('legacy');
 if(g&&!a.getElementById('legacyWrap').hidden&&g.contentDocument)res.page=measure(g.contentDocument);
 document.getElementById('R').textContent=JSON.stringify(res);},7000);
</script></body></html>"""


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):   # the app server's refresh status API (server.py): idle, no run yet
            if self.path.split("?")[0] in ("/api/refresh/status", "/api/sync-status"):
                body = (b'{"running": false, "last": null, "progress": null}' if "refresh" in self.path else
                        b'{"sync_id": 1, "label": "check", "sync_status": "synced", "partial_errors": [], "in_sync": true}')
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_error(self, fmt, *a):   # a 404 of a file the page needs is a defect: report it
            MISSING.add(self.path.split("?")[0])
    handler = functools.partial(Quiet, directory=str(DIST))
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def chrome(args, timeout=120):
    base = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--virtual-time-budget=15000"]
    return subprocess.run(base + args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


# Chrome writes 'INFO:CONSOLE:1] "msg", source: url (line)' for every console call (console.error is INFO too)
CONSOLE = re.compile(r'CONSOLE[:(]\d+\)?\] "(.*?)", source: (\S+)')


# review 6.6: the page people open (index.html: data loader + every tab), not only the shell around it
INDEX_HASHES = ["obs/today", "obs/release", "obs/desk", "r1130/baseline", "gates/tiers"]


def desktop(base, h, lang, shot, page="shell.html"):
    args = ["--enable-logging=stderr", "--v=0", "--window-size=1280,1400", "--dump-dom", f"{base}/{page}?lang={lang}#{h}"]
    out = chrome(args)
    # every console message counts: the shell and the page log nothing on a healthy load
    errs = [f"{m.group(1)[:160]} @ {m.group(2).split('/')[-1].split('?')[0]}" for m in CONSOLE.finditer(out.stderr)]
    if shot:
        chrome(["--hide-scrollbars", "--window-size=1280,1400", f"--screenshot={Path(shot) / ('d_' + h.replace('/', '_') + '.png')}",
                f"{base}/shell.html#{h}"])
    return errs


def mobile(base, h, lang, shot):
    out = chrome(["--window-size=900,1500", "--dump-dom", f"{base}/{HARNESS}?h={h}&lang={lang}"])
    m = re.search(r'<pre id="R">(.*?)</pre>', out.stdout, re.S)
    if shot:
        chrome(["--hide-scrollbars", "--window-size=900,1500", f"--screenshot={Path(shot) / ('m_' + h.replace('/', '_') + '.png')}",
                f"{base}/{HARNESS}?h={h}&lang={lang}"])
    import json
    return json.loads(m.group(1).replace("&quot;", '"')) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hashes", nargs="*", default=HASHES)
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--shot")
    ap.add_argument("--base", help="check a running server instead of dist/ (e.g. http://127.0.0.1:8765); "
                                   "needs --site: the folder that server serves, for the same-origin 390 px harness")
    ap.add_argument("--site", type=Path, help="with --base: the site folder behind that URL (e.g. releases/<CURRENT>/site)")
    a = ap.parse_args()
    global DIST
    if a.base:
        if not a.site:
            print("--base needs --site")
            return 1
        DIST = a.site
    if not (DIST / "shell.html").exists():
        print("run backend/export_static.py first")
        return 1
    (DIST / HARNESS).write_text(HARNESS_HTML, encoding="utf-8")
    if a.base:
        class _NoServer:
            def shutdown(self):
                pass
        srv, base = _NoServer(), a.base.rstrip("/")
    else:
        srv, base = serve()
    bad = 0
    try:
        for h in a.hashes:
            errs = desktop(base, h, a.lang, a.shot)
            mob = mobile(base, h, a.lang, a.shot)
            over = []
            for k in ("shell", "page"):
                x = (mob or {}).get(k)
                if x and x["S"] > x["W"]:
                    over.append(f"{k} {x['S']}>{x['W']} {x['o']}")
            ok = not errs and mob is not None and not over
            bad += not ok
            print(f"{h:22s} {'OK ' if ok else 'BAD'} console={len(errs)} mobile={'no result' if mob is None else ('overflow ' + '; '.join(over) if over else 'ok')}")
            for e in errs[:4]:
                print("    ", e)
        if not a.hashes or a.hashes == HASHES:   # the full run also opens the main page directly
            for h in INDEX_HASHES:
                errs = desktop(base, h, a.lang, None, page="index.html")
                bad += bool(errs)
                print(f"{'index#' + h:22s} {'OK ' if not errs else 'BAD'} console={len(errs)}")
                for e in errs[:4]:
                    print("    ", e)
    finally:
        srv.shutdown()
        miss = sorted(m for m in MISSING if not m.endswith("favicon.ico"))
        if miss:
            print("missing files (404):", ", ".join(miss))
            bad += 1
        (DIST / HARNESS).unlink(missing_ok=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
