"""Local JSON API + static frontend. Python stdlib only.

Run:  python -X utf8 server.py [--port 8765]   then open http://127.0.0.1:8765/  (the page with its 3 views)
Endpoints:
  GET /api/overview            release-manager view (now, decisions, blockers, artifacts, releases, dev gates)
  GET /api/history             trends for analysis (cycle, nightly, publish weekly, dev gates daily, failing jobs, kpis)
  GET /api/release/<tag>       one release: verdict, artifact matrix, publish runs, PRs, verdict history
  GET /api/sql?view=<v_name>   raw rows of one analysis view (read-only, whitelisted)
  GET /legacy.html             the existing 06_PR_TO_CI_VISUAL.html in embed mode (every old tab)
"""
import argparse
import json
import mimetypes
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import legacy
import model
from config import FRONTEND
from db import connect

VIEWS = {"v_release_cycle", "v_artifact_matrix", "v_publish_weekly", "v_dev_pipeline_daily", "v_failing_jobs"}


def api(path, query):
    con = connect()
    try:
        if path == "overview":
            return model.overview(con)
        if path == "history":
            return model.history(con)
        if path.startswith("release/"):
            return model.release_detail(con, urllib.parse.unquote(path[8:]))
        if path == "sql":
            v = (query.get("view") or [""])[0]
            if v in VIEWS:
                return model.rows(con, f"SELECT * FROM {v} LIMIT 2000")
        return None
    finally:
        con.close()


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/api/"):
            data = api(u.path[5:].strip("/"), urllib.parse.parse_qs(u.query))
            if data is None:
                return self._send(404, b'{"error":"not found"}', "application/json")
            return self._send(200, json.dumps(data, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8")
        if u.path in ("/", "/index.html"):   # main UI: the page with its 3 views (Release Management · Exploration · Report 1130)
            return self._send(200, legacy.PAGE.read_bytes(), "text/html; charset=utf-8")
        if u.path == "/shell.html":   # optional single-bar shell (native #now/#history + embedded page)
            return self._send(200, (FRONTEND / "index.html").read_bytes(), "text/html; charset=utf-8")
        if u.path == "/legacy.html":   # the existing page, embed mode (all its tabs)
            return self._send(200, legacy.html().encode("utf-8"), "text/html; charset=utf-8")
        if u.path.startswith("/outputs/"):   # relative links of the embedded page
            f = legacy.outputs_file(urllib.parse.unquote(u.path.lstrip("/")))
            if not f:
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(f.name)[0] or ("text/markdown" if f.suffix == ".md" else "text/plain")
            return self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
        rel = u.path.lstrip("/") or "index.html"
        f = (FRONTEND / rel).resolve()
        if FRONTEND.resolve() not in f.parents and f != FRONTEND.resolve() or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def log_message(self, fmt, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    print(f"ops-app on http://127.0.0.1:{a.port}/")
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
