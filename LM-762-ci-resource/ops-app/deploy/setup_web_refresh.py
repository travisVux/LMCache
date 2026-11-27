"""One-time setup of the web "Refresh data" button (round 3). Run once, by the owner:

  python -X utf8 setup_web_refresh.py          # create KV namespace release-desk-ctl, bind it to the Pages project as RD_CTL,
                                               # write OPS_KV_NS to ops-app.env, register task ops-app-webrefresh (every 2 min)
  python -X utf8 setup_web_refresh.py --remove # unregister the task (the KV namespace stays; delete it in the dashboard)

The binding takes effect on the next deploy (pages.py deploy).
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = "ops-app-webrefresh"


def env():
    e = {}
    for line in (HERE / "ops-app.env").read_text(encoding="utf-8-sig").splitlines():
        t = line.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            e[k.strip()] = v.strip().strip('"')
    return e


def call(tok, method, path, body=None):
    r = urllib.request.Request("https://api.cloudflare.com/client/v4" + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    if "--remove" in sys.argv:
        subprocess.run(["schtasks.exe", "/Delete", "/TN", TASK, "/F"])
        return 0
    E = env()
    tok, acc, prj = E["CLOUDFLARE_API_TOKEN"], E["CLOUDFLARE_ACCOUNT_ID"], E["OPS_PAGES_PROJECT"]
    s, j = call(tok, "GET", f"/accounts/{acc}/storage/kv/namespaces?per_page=100")
    ns = next((n for n in j.get("result") or [] if n["title"] == "release-desk-ctl"), None)
    if not ns:
        s, j = call(tok, "POST", f"/accounts/{acc}/storage/kv/namespaces", {"title": "release-desk-ctl"})
        if s not in (200, 201):
            sys.exit(f"could not create the KV namespace ({s}): add 'Workers KV Storage: Edit' to the API token")
        ns = j["result"]
    print("KV namespace:", ns["id"])
    s, j = call(tok, "PATCH", f"/accounts/{acc}/pages/projects/{prj}",
                {"deployment_configs": {"production": {"kv_namespaces": {"RD_CTL": {"namespace_id": ns["id"]}}}}})
    if s != 200:
        sys.exit(f"could not bind KV to the Pages project ({s}): {j.get('errors')}")
    print("bound to", prj, "as RD_CTL (active from the next deploy)")
    f = HERE / "ops-app.env"
    t = f.read_text(encoding="utf-8")
    if "OPS_KV_NS=" not in t:
        f.write_text(t.rstrip("\r\n") + f"\r\nOPS_KV_NS={ns['id']}\r\n", encoding="utf-8")
    py = sys.executable.replace("python.exe", "pythonw.exe") if Path(sys.executable.replace("python.exe", "pythonw.exe")).is_file() else sys.executable   # no console window every 2 min
    cmd = f'"{py}" -X utf8 "{HERE / "web_refresh.py"}" once'
    r = subprocess.run(["schtasks.exe", "/Create", "/TN", TASK, "/SC", "MINUTE", "/MO", "2", "/TR", cmd, "/F"], capture_output=True, text=True)
    print("task", TASK, "registered" if r.returncode == 0 else f"NOT registered: {r.stderr.strip()}")
    print("next: python -X utf8 pages.py deploy   (so the web copy gets the binding and the button)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
