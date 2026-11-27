"""Pick up "Refresh data" requests made on the web copy (round 3). Python stdlib only. Runs on the release PC.

  python -X utf8 web_refresh.py once     # check Cloudflare KV once; if a request is queued, run the pipeline + deploy
  python -X utf8 web_refresh.py status   # print the request / status keys

Scheduled task ops-app-webrefresh runs `once` every 2 minutes (outbound HTTPS to api.cloudflare.com only).
Flow: KV "request" present -> delete it, write status running -> refresh.ps1 (07:00 pipeline, publishes locally) ->
pages.py deploy (web copy) -> status done / failed. Never runs while another refresh holds logs/refresh.lock.
Needs in ops-app.env: CLOUDFLARE_API_TOKEN (Pages Edit + Workers KV Storage Edit), CLOUDFLARE_ACCOUNT_ID, OPS_KV_NS.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
sys.path.insert(0, str(APP / "backend"))
import refresh_progress  # noqa: E402  (per-source progress rows, shared with the local button)
PS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), r"System32\WindowsPowerShell\v1.0\powershell.exe")


def load_env():
    f = HERE / "ops-app.env"
    if f.is_file():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            t = line.strip()
            if t and not t.startswith("#") and "=" in t:
                k, v = t.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def kv(method, key, value=None, ttl=None):
    acc, ns, tok = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["OPS_KV_NS"], os.environ["CLOUDFLARE_API_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/storage/kv/namespaces/{ns}/values/{key}"
    if ttl:
        url += f"?expiration_ttl={int(ttl)}"
    req = urllib.request.Request(url, method=method, data=value.encode() if value is not None else None,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def put_status(**k):
    # review R3: "running" expires after 2 h, so a PC that dies mid-run cannot lock the web button / chip forever
    kv("PUT", "status", json.dumps(dict(at=now(), **k)), ttl=7200 if k.get("state") == "running" else None)


def busy():
    lock = APP / "logs" / "refresh.lock"
    if not lock.exists():
        return False
    try:
        with open(lock, "r+b"):
            return False
    except PermissionError:
        return True


def once():
    req = kv("GET", "request")
    if not req:
        return 0
    if busy():
        print("a refresh is running here; the web request stays queued")
        return 0
    kv("DELETE", "request")
    requested = json.loads(req).get("at")
    put_status(state="running", requested=requested)
    before = {p.name for p in (APP / "logs").glob("refresh-*.log")}
    p = subprocess.Popen([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "refresh.ps1")], cwd=str(HERE), creationflags=NOWIN)
    sent = None
    while p.poll() is None:   # push the per-source progress while it runs (only when a row changes: ~20 KV writes a run)
        time.sleep(10)
        pr = live_progress(before, True)
        key = pr and json.dumps([(x["id"], x["state"], x["note"]) for x in pr["steps"]])
        if pr and key != sent:
            try:
                put_status(state="running", requested=requested, progress=pr)
                sent = key
            except (OSError, urllib.error.URLError) as e:
                print("progress push failed:", e)
    r = p
    try:
        last = json.loads((APP / "logs" / "last-refresh.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        last = {}
    pr = live_progress(before, True)
    if r.returncode != 0 or last.get("status") == "failed":
        put_status(state="failed", text=last.get("text") or f"refresh exit {r.returncode}", progress=pr)
        return 1
    up = pr and next((x for x in pr["steps"] if x["id"] == "pages_deploy"), None)
    if up:
        up["state"] = "running"
        put_status(state="running", requested=requested, progress=pr)
    t0 = time.time()
    d = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), "-X", "utf8", str(HERE / "pages.py"), "deploy"], cwd=str(HERE), creationflags=NOWIN,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    rel = (APP / "releases" / "CURRENT").read_text(encoding="utf-8").strip() if (APP / "releases" / "CURRENT").is_file() else None
    if up:
        up.update(state="done" if d.returncode == 0 else "failed", secs=int(time.time() - t0),
                  note=refresh_progress._note("pages_deploy", (d.stdout or "").splitlines()) if d.returncode == 0 else "upload failed (the release PC copy is live)")
        pr["done"] = sum(x["state"] in ("done", "skipped", "failed") for x in pr["steps"])
    put_status(state="done" if d.returncode == 0 else "failed", release=rel, result=last.get("status"),
               text=last.get("text") if d.returncode == 0 else "web upload failed", progress=pr)
    return d.returncode


def live_progress(before, web):
    """Progress of the log this run created (None until refresh.ps1 has written it)."""
    new = sorted(p for p in (APP / "logs").glob("refresh-*.log") if p.name not in before)
    if not new:
        return None
    try:
        return refresh_progress.progress(new[-1], web=web)
    except Exception as e:  # noqa: BLE001  (progress is a nicety: never stop the run)
        print("progress:", e)
        return None


def main():
    load_env()
    for k in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "OPS_KV_NS"):
        if not os.environ.get(k):
            print(f"{k} is empty (deploy/ops-app.env): web refresh is off")
            return 0
    if (sys.argv[1:] or ["once"])[0] == "status":
        print("request:", kv("GET", "request"))
        print("status:", kv("GET", "status"))
        return 0
    return once()


if __name__ == "__main__":
    sys.exit(main())
