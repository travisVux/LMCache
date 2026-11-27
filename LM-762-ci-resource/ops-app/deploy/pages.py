"""Put the live Release Desk build on Cloudflare Pages, behind a sign-in. Python stdlib + wrangler (Node).

Sign-in (either one; check/deploy accept both):
  * shared password (free, no card): deploy/pages-functions/functions/_middleware.js runs before every file and asks
    for user "release" + the password; only its SHA-256 is stored at Cloudflare (secret RD_PASS_SHA256).
      python -X utf8 pages.py set-password      # new random password -> Cloudflare secret + cloudflare-credentials.txt
      python -X utf8 pages.py set-password --user admin --password <pw>   # chosen user + password (RD_USER secret too)
  * Cloudflare Access (Zero Trust; needs a payment card on file even for the free plan): cf_access.py apply

  python -X utf8 pages.py stage                 # releases/CURRENT/site -> pages-out/ (+ _headers, robots.txt), privacy scan
  python -X utf8 pages.py check                 # is https://<project>.pages.dev behind Access? (no upload)
  python -X utf8 pages.py init                  # once: create the project with a placeholder page (no data)
  python -X utf8 pages.py deploy [--dry-run]    # stage + scan + Access check + upload + check the new deployment URL

Settings (deploy/ops-app.env or the environment):
  OPS_PAGES_PROJECT       Pages project name -> https://<name>.pages.dev
  CLOUDFLARE_API_TOKEN    API token with "Cloudflare Pages: Edit" (wrangler reads it; never printed)
  CLOUDFLARE_ACCOUNT_ID   the account id (dashboard, right column)

Fail closed: deploy uploads nothing unless https://<project>.pages.dev/ asks for a sign-in (Access redirect, or 401
from the password gate) and a random preview name https://<random>.<project>.pages.dev/ asks for one or serves nothing
(404), to a request without cookie or password. The middleware answers 503 when no password is configured. Only the published, checked build (releases/CURRENT) is uploaded - never ops.db.
Steps for the dashboard: CLOUDFLARE.md (section "Cloudflare Pages").
"""
import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
OUT = APP / "pages-out"
RELEASES = APP / "releases"
WRANGLER = "wrangler@4"
MAX_FILE = 25 * 2**20          # Cloudflare Pages: 25 MiB per file
MAX_FILES = 20000              # Cloudflare Pages (free): files per deployment
sys.path.insert(0, str(HERE))
import publish  # noqa: E402  (privacy scan)

HEADERS = """/*
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.github.com https://api.buildkite.com; frame-ancestors 'self'; base-uri 'self'; form-action 'none'; object-src 'none'
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Referrer-Policy: same-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
  X-Robots-Tag: noindex, nofollow
"""
PLACEHOLDER = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Release Desk</title>
<p style="font:16px system-ui;margin:40px">Release Desk: not published yet.</p>
"""


def load_env():
    f = HERE / "ops-app.env"
    if f.is_file():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            t = line.strip()
            if t and not t.startswith("#") and "=" in t:
                k, v = t.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def project():
    p = os.environ.get("OPS_PAGES_PROJECT", "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,56}", p):
        sys.exit("OPS_PAGES_PROJECT is empty or not a valid Pages project name (a-z, 0-9, -)")
    return p


# ───────────── Access check ─────────────
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def protected(url):
    """-> (True/False, short reason). True only for an Access sign-in answer."""
    op = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "release-desk-access-check"})
    try:
        with op.open(req, timeout=20) as r:
            return False, f"{r.status} (page served without sign-in)"
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "")
        host = urllib.parse.urlparse(loc).hostname or ""
        if e.code in (301, 302, 303, 307, 308) and host.endswith(".cloudflareaccess.com"):
            return True, f"{e.code} -> Access sign-in"
        if e.code == 401 and 'realm="Release Desk"' in (e.headers.get("WWW-Authenticate") or ""):
            return True, "401 -> password sign-in"
        body = e.read(4096).decode("utf-8", "replace") if e.code in (401, 403) else ""
        if e.code in (401, 403) and (any(k.lower().startswith("cf-access") for k in e.headers) or "Cloudflare Access" in body):
            return True, f"{e.code} (Access refused without sign-in)"
        return False, f"{e.code} {('-> ' + host) if host else ''}".strip()
    except (urllib.error.URLError, OSError) as e:
        return False, f"unreachable ({type(e).__name__})"


def check(p, quiet=False):
    urls = [f"https://{p}.pages.dev/", f"https://zz{secrets.token_hex(3)}.{p}.pages.dev/"]
    ok = True
    for n, u in enumerate(urls):
        good, why = protected(u)
        if n and not good and why.startswith("404"):
            good, why = True, "404 (no such deployment: nothing served)"
        ok &= good
        if not quiet:
            print(f"  {'OK  ' if good else 'FAIL'} {u}  {why}")
    return ok


# ───────────── stage ─────────────
def stage():
    cur = (RELEASES / "CURRENT").read_text(encoding="utf-8").strip() if (RELEASES / "CURRENT").is_file() else None
    if not cur or not (RELEASES / cur / "site" / "index.html").is_file():
        sys.exit("no live release: run publish.py publish (or refresh.ps1) first")
    src = RELEASES / cur / "site"
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(src, OUT, ignore=shutil.ignore_patterns("__*", ".*", "*.db", "*.db-*"))
    (OUT / "_headers").write_text(HEADERS, encoding="utf-8", newline="\n")
    (OUT / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8", newline="\n")
    files = [f for f in OUT.rglob("*") if f.is_file()]
    big = [f.relative_to(OUT).as_posix() for f in files if f.stat().st_size > MAX_FILE]
    if big or len(files) > MAX_FILES:
        sys.exit(f"over Cloudflare Pages limits: {len(files)} files, too big: {big}")
    hits = publish.scan(OUT)
    for h in hits:
        print("  PRIVACY", *h)
    if hits:
        sys.exit(f"privacy scan: {len(hits)} hit(s) in pages-out - nothing uploaded")
    size = sum(f.stat().st_size for f in files)
    print(f"staged release {cur}: {len(files)} files, {size / 2**20:.1f} MB in {OUT}  (privacy scan clean)")
    return cur


# ───────────── wrangler ─────────────
def npx():
    for n in ("npx.cmd", "npx"):
        w = shutil.which(n)
        if w:
            return w
    for d in (os.environ.get("OPS_NODE_DIR", ""), os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs")):
        if d and os.path.isfile(os.path.join(d, "npx.cmd")):   # just installed: PATH of this session is not refreshed yet
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            return os.path.join(d, "npx.cmd")
    sys.exit("Node.js not found (wrangler needs it): winget install OpenJS.NodeJS.LTS  -- or upload pages-out/ by hand "
             "(dashboard: Workers & Pages > your project > Create deployment > upload the folder)")


def wrangler(*args, stdin=None, cwd=None):
    for k in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not os.environ.get(k):
            sys.exit(f"{k} is empty (deploy/ops-app.env)")
    cmd = [npx(), "--yes", WRANGLER, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", input=stdin, cwd=cwd,
                       env=dict(os.environ, WRANGLER_SEND_METRICS="false"))
    out = (r.stdout or "") + (r.stderr or "")
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    print(out.replace(tok, "***") if tok else out)
    return r.returncode, out


def deploy_dir(p, folder, branch="main"):
    # run from pages-functions/ so wrangler bundles functions/_middleware.js (the password gate) with every deployment
    rc, out = wrangler("pages", "deploy", str(Path(folder).resolve()), "--project-name", p, "--branch", branch,
                       "--commit-dirty=true", cwd=str(HERE / "pages-functions"))
    if rc:
        sys.exit(f"wrangler failed ({rc})")
    m = re.findall(r"https://[a-z0-9-]+\." + re.escape(p) + r"\.pages\.dev", out)
    return m[-1] if m else None


CRED = HERE / "cloudflare-credentials.txt"


def set_password(p, user=None, pw=None):
    """Shared login: SHA-256 of the password goes to Cloudflare (secret RD_PASS_SHA256), the user name to secret RD_USER,
    both in clear to cloudflare-credentials.txt. Without --password a random one is made."""
    import hashlib
    pw = pw or "-".join(secrets.token_urlsafe(6).replace("_", "x").replace("-", "y") for _ in range(4))
    user = user or "release"
    if ":" in user or not user.strip():
        sys.exit("the user name must be non-empty and must not contain ':'")
    rc, _ = wrangler("pages", "secret", "put", "RD_USER", "--project-name", p, stdin=user + "\n")
    if rc:
        sys.exit("could not store the user name at Cloudflare; the old login still works")
    rc, _ = wrangler("pages", "secret", "put", "RD_PASS_SHA256", "--project-name", p, stdin=hashlib.sha256(pw.encode()).hexdigest() + "\n")
    if rc:
        sys.exit("could not store the password hash at Cloudflare; the old password (if any) still works")
    lines = [l for l in (CRED.read_text(encoding="utf-8").splitlines() if CRED.is_file() else []) if not l.startswith("Site login")]
    lines += [f"Site login : https://{p}.pages.dev/   user: {user}   password: {pw}"]
    CRED.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")
    print(f"new password stored: hash at Cloudflare (secret RD_PASS_SHA256), password in {CRED.name}")
    print("it applies to deployments made from now on: run  pages.py init  or  pages.py deploy")


def main():
    load_env()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["stage", "check", "init", "deploy", "set-password"])
    ap.add_argument("--dry-run", action="store_true", help="deploy: everything except the upload")
    ap.add_argument("--user", help="set-password: login user name (default release)")
    ap.add_argument("--password", help="set-password: use this password instead of a random one")
    a = ap.parse_args()
    if a.cmd == "stage":
        stage()
        return 0
    p = project()
    if a.cmd == "set-password":
        set_password(p, a.user, a.password)
        return 0
    if a.cmd == "check":
        ok = check(p)
        print("Access: protected" if ok else "Access: NOT protected (see CLOUDFLARE.md, Cloudflare Pages step 3)")
        return 0 if ok else 1
    if a.cmd == "init":
        rc, out = wrangler("pages", "project", "list")
        if p not in out:
            rc, _ = wrangler("pages", "project", "create", p, "--production-branch", "main")
            if rc:
                sys.exit("could not create the project")
        tmp = APP / "pages-placeholder"
        tmp.mkdir(exist_ok=True)
        (tmp / "index.html").write_text(PLACEHOLDER, encoding="utf-8")
        (tmp / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
        deploy_dir(p, tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"project {p} has a placeholder page (no data). Now add the Access application, then: pages.py check")
        return 0
    # deploy
    cur = stage()
    print(f"Access check for {p}.pages.dev (no cookie):")
    if not check(p):
        sys.exit("NOT uploaded: the site would be readable without sign-in. Add / fix the Access application "
                 "(CLOUDFLARE.md, Cloudflare Pages step 3), then run  pages.py check")
    if a.dry_run:
        print("dry run: staged, scanned and Access checked; nothing uploaded")
        return 0
    url = deploy_dir(p, OUT)
    ok = True
    if url:
        import time
        for _ in range(24):                      # a new deployment name takes a few seconds to resolve (404 meanwhile)
            ok, why = protected(url + "/")
            if not why.startswith("404"):
                break
            time.sleep(5)
        print(f"  new deployment {url.split('//')[1].split('.')[0]}...: {why}")
    status = dict(release=cur, project=p, deployment=url, protected=ok)
    log = APP / "logs" / "pages-last.json"
    log.parent.mkdir(exist_ok=True)
    log.write_text(json.dumps(status, indent=1), encoding="utf-8")
    if not ok:
        print("WARNING: the new deployment URL answered without sign-in. Check the Access application covers "
              f"*.{p}.pages.dev, or delete the deployment in the dashboard.", file=sys.stderr)
        return 2
    print(f"live: https://{p}.pages.dev/  (release {cur}, behind Access)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
