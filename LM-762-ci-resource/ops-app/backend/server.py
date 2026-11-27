"""Release Desk web server: the page + read-only JSON API. Python stdlib only.

Run:
  python -X utf8 server.py                                   # live sources, http://127.0.0.1:8765/
  python -X utf8 server.py --root ../dist                    # a static build (export_static.py output)
  python -X utf8 server.py --root ../releases --host 127.0.0.1 --port 8765 --log ../logs/access.log
                                                             # production: serves releases/<CURRENT>/site + its ops.db

--root:
  live              (default) the page from plan-2026-11/, frontend/, outputs/ and data/ops.db, as on the old PC
  <dir with CURRENT> release mode: CURRENT holds the name of the live release folder (<dir>/<name>/site, <dir>/<name>/ops.db);
                    publish.py writes it with an atomic rename, so a request sees the old or the new build, never half
  <any other dir>   a static site folder (dist/); the API reads --db (default data/ops.db)

Endpoints (all GET/HEAD, nothing writes):
  /  /index.html               the page with its 3 views (Release Management · Exploration · Report 1130)
  /shell.html  /legacy.html    single-bar shell / page in embed mode
  /outputs/...                 relative links of the page (path traversal refused)
  /api/overview  /api/history  /api/release/<tag>  /api/sql?view=v_...   from SQLite opened read-only
  /healthz                     ok / stale / data age per source; build details only to loopback clients.
                               "ok" is false when a source is stale (HTTP 200); /healthz?strict=1 answers 503 then,
                               for an uptime monitor. A broken DB is always 503.

Hardening: idle connections time out after 15 s; only GET/HEAD; Host must be a loopback name or OPS_DOMAIN /
OPS_ALLOWED_HOSTS / OPS_TUNNEL_HOSTNAME (comma separated) - stops DNS rebinding; X-Forwarded-For and
Cf-Connecting-Ip are only trusted from 127.0.0.1 / ::1;
Cloudflare Tunnel (deploy/CLOUDFLARE.md): a request that came through the tunnel (Cf-Ray / Cf-Connecting-Ip from loopback)
or names OPS_TUNNEL_HOSTNAME must carry Cloudflare Access's Cf-Access-Jwt-Assertion, else 403 - fail closed when the
Access application is missing or was switched off; such requests also get the CSP / HSTS headers Caddy would add;
dotfiles and NTFS stream names (':') are refused; CR/LF never reach the access log.
"""
import argparse
import subprocess
import email.utils
import hashlib
import json
import logging
import logging.handlers
import mimetypes
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import legacy
import dbapi
import model
import refresh_progress
from config import APP, DB_PATH, FRONTEND
from db import connect_ro

VIEWS = {"v_release_cycle", "v_artifact_matrix", "v_publish_weekly", "v_dev_pipeline_daily", "v_failing_jobs"}
STARTED = time.time()
mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("text/csv", ".csv")
mimetypes.add_type("application/x-ndjson", ".jsonl")
TEXTY = ("text/", "application/json", "application/x-ndjson", "image/svg+xml")
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def allowed_hosts():
    hs = {"localhost", "127.0.0.1", "[::1]", "::1"}
    for v in (os.environ.get("OPS_DOMAIN", ""), os.environ.get("OPS_ALLOWED_HOSTS", ""), os.environ.get("OPS_TUNNEL_HOSTNAME", "")):
        hs |= {h.strip().lower() for h in v.split(",") if h.strip()}
    return hs


ALLOWED_HOSTS = allowed_hosts()
TUNNEL_HOSTS = {h.strip().lower() for h in os.environ.get("OPS_TUNNEL_HOSTNAME", "").split(",") if h.strip()}
# the same headers deploy/Caddyfile adds; sent on tunnel requests, where Caddy is not in front
EDGE_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data: https:; connect-src 'self' https://api.github.com https://api.buildkite.com; "
                               "frame-ancestors 'self'; base-uri 'self'; form-action 'none'; object-src 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}


def host_ok(host):
    if not host:
        return False
    h = host.strip().lower()
    if h.startswith("["):                       # [::1]:8765
        h = h.split("]")[0] + "]"
    elif h.count(":") == 1:
        h = h.split(":")[0]
    return h in ALLOWED_HOSTS


# ───────────── where files and data come from ─────────────
class Source:
    """Resolves the site folder and DB for each request. In release mode it follows the CURRENT pointer."""

    def __init__(self, root, db):
        self.mode, self._db, self._cache = "live", Path(db) if db else None, (None, None)
        self._lock = threading.Lock()
        if root and root != "live":
            self.root = Path(root).resolve()
            if not self.root.is_dir():
                sys.exit(f"--root {self.root} is not a folder")
            self.mode = "release" if (self.root / "CURRENT").is_file() else "site"

    def current(self):
        """-> (site dir or None for live, db path, release name or None)."""
        if self.mode == "live":
            return None, self._db or DB_PATH, None
        if self.mode == "site":
            return self.root, self._db or DB_PATH, None
        ptr = self.root / "CURRENT"
        mt = ptr.stat().st_mtime_ns
        with self._lock:
            if self._cache[0] != mt:
                name = ptr.read_text(encoding="utf-8").strip()
                if not name or "/" in name or "\\" in name or name.startswith("."):
                    raise RuntimeError(f"bad CURRENT pointer: {name!r}")
                self._cache = (mt, name)
            name = self._cache[1]
        rel = self.root / name
        return rel / "site", self._db or rel / "ops.db", name


def safe_child(base, rel):
    """base/rel if it stays inside base and is a file, else None (refuses ../, absolute paths, drive letters)."""
    if "\x00" in rel or "\\" in rel:
        return None
    base = base.resolve()
    f = (base / rel.lstrip("/")).resolve()
    return f if base in f.parents and f.is_file() else None


# ───────────── API (read-only) ─────────────
def api(db, path, query):
    con = connect_ro(db)
    try:
        if path == "overview":
            return model.overview(con)
        if path == "history":
            return model.history(con)
        if path == "impact":
            return model.ci_impact(con) or {}
        if path.startswith("release/"):
            return model.release_detail(con, urllib.parse.unquote(path[8:]))
        if path == "sql":
            v = (query.get("view") or [""])[0]
            if v in VIEWS:
                return model.rows(con, f"SELECT * FROM {v} LIMIT 2000")
        return None
    finally:
        con.close()


def healthz(src, full=True):
    site, db, name = src.current()
    try:   # never show local paths (user names) to the web: relative to ops-app/
        shown = "<app>/" + Path(db).resolve().relative_to(APP.resolve()).as_posix()
    except ValueError:
        shown = "<outside app>/" + Path(db).name
    out = dict(ok=True, mode=src.mode, release=name, db=shown, db_exists=Path(db).is_file(),
               uptime_s=round(time.time() - STARTED), python=sys.version.split()[0])
    meta = (site.parent / "release.json") if site else None
    if meta and meta.is_file():
        out["build"] = json.loads(meta.read_text(encoding="utf-8"))
    page = (site / "index.html") if site else legacy.PAGE
    out["page_built"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(page.stat().st_mtime)) if page.is_file() else None
    try:
        con = connect_ro(db)
        try:
            out["sources"] = model.source_ages(con)
            out["stale"] = [s["key"] for s in out["sources"] if s["stale"]]
            if out["stale"]:
                out.update(ok=False, status="stale")
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001 - health must answer even when the DB is broken
        out.update(ok=False, status="db error", error=f"{type(e).__name__}: {e}".replace(str(APP), "<app>").replace(str(Path.home()), "<home>"))
    out.setdefault("status", "ok" if out["ok"] else "error")
    lr = APP / "logs" / "last-refresh.json"     # outcome of the last scheduled refresh (refresh.ps1)
    try:
        r = json.loads(lr.read_text(encoding="utf-8-sig")) if lr.is_file() else None
        out["last_refresh"] = r and {k: r.get(k) for k in ("status", "at", "text")}
        if r and r.get("status") == "failed":
            out.update(ok=False)
    except (OSError, ValueError):
        out["last_refresh"] = None
    if not full:   # through the proxy: no versions, git sha or build host
        out.pop("python", None)
        b = out.get("build") or {}
        out["build"] = {k: b.get(k) for k in ("name", "published_at", "page_built")} if b else None
    return out


# ───────────── HTTP ─────────────
LOG = logging.getLogger("ops-app.access")


REFRESH_TASK = "ops-app-refresh"
APP_DIR = Path(__file__).resolve().parent.parent


def refresh_status():
    """Is a refresh running (refresh.ps1 holds logs/refresh.lock open), its last step, and the last outcome."""
    logs = APP_DIR / "logs"
    running = False
    lock = logs / "refresh.lock"
    if lock.exists():
        try:
            with open(lock, "r+b"):
                pass
        except PermissionError:
            running = True
        except OSError:
            pass
    step, at = None, None
    runs = sorted(logs.glob("refresh-*.log"))
    if runs:
        for ln in runs[-1].read_text(encoding="utf-8", errors="replace").splitlines():
            if " STEP " in ln:
                step, at = ln.split(" STEP ", 1)[1].strip(), ln[:19]
    try:
        last = json.loads((logs / "last-refresh.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        last = None
    return dict(running=running, step=step if running else None, step_at=at if running else None,
                last=last and {k: last.get(k) for k in ("status", "at", "text")}, progress=_progress())


def _progress():
    """Per-source rows of the running / last refresh (refresh_progress.py); None if unreadable."""
    try:
        return refresh_progress.progress()
    except Exception:  # noqa: BLE001  (progress is a nicety: never break the status call)
        LOG.exception("refresh progress")
        return None


class H(BaseHTTPRequestHandler):
    server_version = "ops-app"
    sys_version = ""
    src: Source = None
    timeout = 15   # idle keep-alive / slow clients do not hold a thread forever

    def _send(self, code, body, ctype, cache="no-cache", mtime=None, extra=None):
        etag = '"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'
        inm = self.headers.get("If-None-Match")
        if code == 200 and inm and etag in [x.strip() for x in inm.split(",")]:
            code, body = 304, b""
        self.send_response(code)
        if code != 304:
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        if code in (200, 304):
            self.send_header("ETag", etag)
            if mtime:
                self.send_header("Last-Modified", email.utils.formatdate(mtime, usegmt=True))
        for k, v in {**(EDGE_HEADERS if self._tunnel() else {}), **(extra or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _file(self, f, cache):
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith(TEXTY) or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        return self._send(200, f.read_bytes(), ctype, cache, f.stat().st_mtime)

    def _json(self, data, code=200, cache="no-cache", extra=None):
        return self._send(code, json.dumps(data, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8", cache,
                          extra=extra)

    def _404(self):
        return self._send(404, b"not found", "text/plain; charset=utf-8", "no-store")

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    # ───────────── "Refresh data" button (local only) ─────────────
    # POST /api/refresh starts the existing scheduled task ops-app-refresh (the 07:00 pipeline) and nothing else.
    # Only from this machine (no proxy, no tunnel), same-origin, and with the X-Release-Desk header (a cross-site page
    # cannot send it without a CORS preflight, which this server never answers). One run at a time (refresh.ps1 lock).
    def _origin_ok(self):
        o = self.headers.get("Origin")
        if not o:
            return True
        h = urllib.parse.urlparse(o)
        return (h.hostname or "") in ("127.0.0.1", "localhost", "::1") and host_ok(h.netloc)

    def do_POST(self):  # noqa: N802
        if not host_ok(self.headers.get("Host")):
            return self._send(421, b"unknown host", "text/plain; charset=utf-8", "no-store")
        if urllib.parse.urlparse(self.path).path not in ("/api/refresh", "/api/sync"):   # /api/sync: same as the web copy
            return self._send(405, b"method not allowed", "text/plain; charset=utf-8", "no-store", extra={"Allow": "GET, HEAD"})
        if not self._direct() or not self._origin_ok() or self.headers.get("X-Release-Desk") != "refresh":
            return self._send(403, b"forbidden: the refresh button works only on this machine", "text/plain; charset=utf-8", "no-store")
        st = refresh_status()
        if st["running"]:
            return self._json(dict(started=False, **st), 409, "no-store")
        try:
            r = subprocess.run(["schtasks.exe", "/Run", "/TN", REFRESH_TASK], capture_output=True, text=True, timeout=20)
            ok = r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        LOG.info("refresh requested from the page: %s", "started" if ok else "failed to start")
        return self._json(dict(started=ok, task=REFRESH_TASK, **refresh_status()), 202 if ok else 500, "no-store")

    def _direct(self):
        """True when the client is this machine and not a proxied request."""
        return self.client_address[0] in LOOPBACK and not self.headers.get("X-Forwarded-For") and not self._tunnel()

    def _tunnel(self):
        """True when the request came in through Cloudflare (cloudflared connects from loopback) or names the tunnel host."""
        hdr = getattr(self, "headers", None)
        if not hdr:
            return False
        host = (hdr.get("Host") or "").strip().lower().split(":")[0]
        return bool(hdr.get("Cf-Ray") or hdr.get("Cf-Connecting-Ip") or (host and host in TUNNEL_HOSTS))

    def _access_ok(self):
        """Behind the tunnel, Cloudflare Access must have let the viewer in (it adds a signed JWT header).
        Only presence is checked: the origin is reachable only through cloudflared (outbound, no open port), so the
        edge is the only way in; this catches a missing / disabled Access application (fail closed)."""
        return not self._tunnel() or bool(self.headers.get("Cf-Access-Jwt-Assertion"))

    def do_GET(self):  # noqa: N802
        if not host_ok(self.headers.get("Host")):
            return self._send(421, b"unknown host", "text/plain; charset=utf-8", "no-store")
        if not self._access_ok():
            LOG.warning("refused tunnel request without Cloudflare Access: %s", "".join(c if c.isprintable() else "?" for c in self.path[:200]))
            return self._send(403, b"forbidden: this site must be behind Cloudflare Access", "text/plain; charset=utf-8", "no-store")
        try:
            self._route()
        except BrokenPipeError:
            pass
        except Exception as e:  # noqa: BLE001
            LOG.exception("error on %s", self.path)
            if self.path.startswith("/api/"):
                self._json({"error": {"code": "server_error", "message": type(e).__name__}}, 500, "no-store")
            else:
                self._send(500, f"server error: {type(e).__name__}".encode(), "text/plain; charset=utf-8", "no-store")

    def _route(self):
        u = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(u.path)
        segs = path.replace("\\", "/").split("/")
        if any(seg in ("..", ".") or seg.startswith(".") for seg in segs) or "\x00" in path or ":" in path:
            return self._send(400, b"bad path", "text/plain; charset=utf-8", "no-store")
        site, db, release = self.src.current()
        if path == "/api/sync-status":   # same shape as the Cloudflare function (deploy/pages-functions)
            info = dbapi.sync_info(APP, site, release)
            return self._json(info, 200, "no-store", extra={"X-Sync-Id": str(info["sync_id"])} if info["sync_id"] else None)
        if path == "/api/db" or path.startswith("/api/db/"):
            info = dbapi.sync_info(APP, site, release)
            sync = {k: info[k] for k in ("sync_id", "label", "data_build", "last_synced_at", "partial_errors")}
            hdr = {"X-Sync-Id": str(info["sync_id"])} if info["sync_id"] else None
            if path.rstrip("/") == "/api/db":
                return self._json(dbapi.index(db, sync), 200, "no-store", extra=hdr)
            code, body = dbapi.rows(db, urllib.parse.unquote(path[8:]).strip("/"), urllib.parse.parse_qs(u.query), sync)
            return self._json(body, code, "no-store", extra=hdr)
        if path == "/api/refresh/status":
            if not self._direct():
                return self._send(403, b"forbidden", "text/plain; charset=utf-8", "no-store")
            return self._json(refresh_status(), 200, "no-store")
        if path == "/healthz":
            h = healthz(self.src, full=self._direct())
            strict = "strict" in urllib.parse.parse_qs(u.query)
            bad = h.get("status") == "db error" or (strict and not h["ok"])
            return self._json(h, 503 if bad else 200, "no-store")
        if path.startswith("/api/") and not path.endswith(".json"):
            data = api(db, path[5:].strip("/"), urllib.parse.parse_qs(u.query))
            if data is None:   # same error shape as /api/db and the Cloudflare functions
                return self._json({"error": {"code": "not_found", "message": f"no API at {path}"}}, 404, "no-store")
            return self._json(data)
        html = "no-cache"            # always revalidate the page (ETag makes it cheap)
        short = "public, max-age=300"  # outputs/*, css, js, static api/*.json
        if site is None:   # live sources, as on the old PC
            if path in ("/", "/index.html"):
                return self._file(legacy.PAGE, html)
            if path == "/shell.html":
                return self._file(FRONTEND / "index.html", html)
            if path == "/legacy.html":
                return self._send(200, legacy.html().encode("utf-8"), "text/html; charset=utf-8", html, legacy.PAGE.stat().st_mtime)
            if path.startswith("/outputs/"):
                f = safe_child(legacy.PLAN, path)
                return self._file(f, short) if f and legacy.outputs_file(path.lstrip("/")) else self._404()
            f = safe_child(FRONTEND, path)
            return self._file(f, short) if f else self._404()
        if path.endswith("/"):
            path += "index.html"
        f = safe_child(site, path)
        if not f or f.name.startswith("__"):
            return self._404()
        if path == "/data/manifest.json":   # the page polls it to offer "reload" when newer data is live
            return self._file(f, "no-cache")
        if path.startswith("/data/"):        # data/<build>/<id>.json: the path changes with the content
            return self._file(f, "private, max-age=31536000, immutable")
        return self._file(f, html if f.suffix == ".html" else short)

    def log_message(self, fmt, *a):
        hdr = getattr(self, "headers", None)
        who = self.client_address[0]
        if who in LOOPBACK and hdr and hdr.get("Cf-Connecting-Ip"):  # cloudflared (tunnel) says who the viewer is
            who = hdr.get("Cf-Connecting-Ip").strip()
        elif who in LOOPBACK and hdr and hdr.get("X-Forwarded-For"):   # only the local proxy may say who the client is
            who = hdr.get("X-Forwarded-For").split(",")[-1].strip()
        line = f"{who} {fmt % a}"
        LOG.info("%s", "".join(c if c.isprintable() else "?" for c in line))


def setup_log(path):
    LOG.setLevel(logging.INFO)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(path, maxBytes=10 * 2**20, backupCount=5, encoding="utf-8")
    else:
        h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    LOG.addHandler(h)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1; keep it behind the reverse proxy)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--root", default="live", help="'live', a static site folder (dist/), or a releases/ folder with CURRENT")
    ap.add_argument("--db", help="SQLite file for the API (default: the release's ops.db, else data/ops.db)")
    ap.add_argument("--log", help="access log file (rotated at 10 MB, 5 kept); default stderr")
    a = ap.parse_args()
    setup_log(a.log)
    H.src = Source(a.root, a.db)
    site, db, name = H.src.current()
    print(f"ops-app on http://{a.host}:{a.port}/  mode={H.src.mode} release={name} site={site or 'live sources'} db={db}", flush=True)
    srv = ThreadingHTTPServer((a.host, a.port), H)
    srv.daemon_threads = True
    srv.serve_forever()


if __name__ == "__main__":
    main()
