"""Put Cloudflare Access in front of the Pages project, through the API (no dashboard clicking). Python stdlib only.

  python -X utf8 cf_access.py status     # what exists (Zero Trust org, login methods, the application)
  python -X utf8 cf_access.py apply      # create / update: One-time PIN login + app on <project>.pages.dev and
                                         # *.<project>.pages.dev, policy "emails ending in @OPS_ACCESS_EMAIL_DOMAIN"

Needs in deploy/ops-app.env: CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, OPS_PAGES_PROJECT, OPS_ACCESS_EMAIL_DOMAIN.
The token needs, besides "Cloudflare Pages: Edit":
  Account > Access: Apps and Policies > Edit
  Account > Access: Organizations, Identity Providers, and Groups > Edit
Zero Trust must be switched on once in the dashboard (team name + Free plan); the API cannot do that step.
The token is never printed.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.cloudflare.com/client/v4"
APP_NAME = "Release Desk"


def load_env():
    f = HERE / "ops-app.env"
    if f.is_file():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            t = line.strip()
            if t and not t.startswith("#") and "=" in t:
                k, v = t.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + os.environ["CLOUDFLARE_API_TOKEN"],
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def errs(j):
    return "; ".join(f"{e.get('code')}: {e.get('message')}" for e in j.get("errors", [])) or "no detail"


def main():
    load_env()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    prj = os.environ.get("OPS_PAGES_PROJECT", "").strip()
    dom = os.environ.get("OPS_ACCESS_EMAIL_DOMAIN", "").strip().lstrip("@")
    if not (acc and prj and dom and os.environ.get("CLOUDFLARE_API_TOKEN")):
        sys.exit("need CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, OPS_PAGES_PROJECT, OPS_ACCESS_EMAIL_DOMAIN in ops-app.env")
    hosts = [f"{prj}.pages.dev", f"*.{prj}.pages.dev"]
    a = f"/accounts/{acc}/access"

    s, j = call("GET", a + "/organizations")
    if "not_enabled" in errs(j):
        sys.exit("Zero Trust / Access is not switched on for this account yet: open https://one.dash.cloudflare.com/ once, "
                 "pick a team name and the Free plan, then run this again")
    if s in (401, 403):
        sys.exit(f"token cannot read Access ({s}: {errs(j)}). Add to the token: Access: Apps and Policies > Edit, "
                 "and Access: Organizations, Identity Providers, and Groups > Edit")
    if s != 200 or not j.get("result"):
        sys.exit(f"Zero Trust is not set up on this account yet ({s}: {errs(j)}): open one.dash.cloudflare.com once, "
                 "pick a team name and the Free plan, then run this again")
    team = j["result"].get("auth_domain")
    print(f"Zero Trust org: {team}")

    s, j = call("GET", a + "/identity_providers")
    if s != 200:
        sys.exit(f"cannot list login methods ({s}: {errs(j)})")
    otp = next((p for p in j.get("result") or [] if p.get("type") == "onetimepin"), None)
    print(f"One-time PIN login: {'yes' if otp else 'no'}")

    s, j = call("GET", a + "/apps")
    if s != 200:
        sys.exit(f"cannot list Access applications ({s}: {errs(j)})")
    app = next((x for x in j.get("result") or [] if set(hosts) & set(x.get("self_hosted_domains") or [x.get("domain")])), None)
    print(f"application for {hosts[0]}: {app and app.get('name')} {app and app.get('self_hosted_domains')}")
    if cmd == "status":
        return 0

    if not otp:
        s, j = call("POST", a + "/identity_providers", {"type": "onetimepin", "name": "One-time PIN", "config": {}})
        if s not in (200, 201):
            sys.exit(f"could not add One-time PIN ({s}: {errs(j)})")
        otp = j["result"]
        print("added One-time PIN login")

    body = {
        "name": APP_NAME,
        "type": "self_hosted",
        "domain": hosts[0],
        "self_hosted_domains": hosts,
        "session_duration": "168h",
        "allowed_idps": [otp["id"]],
        "auto_redirect_to_identity": True,
        "app_launcher_visible": False,
        "policies": [{
            "name": f"emails ending in @{dom}",
            "decision": "allow",
            "include": [{"email_domain": {"domain": dom}}],
            "precedence": 1,
        }],
    }
    if app:
        s, j = call("PUT", f"{a}/apps/{app['id']}", body)
    else:
        s, j = call("POST", a + "/apps", body)
    if s not in (200, 201):
        sys.exit(f"could not {'update' if app else 'create'} the application ({s}: {errs(j)})")
    r = j["result"]
    print(f"{'updated' if app else 'created'} Access application '{r.get('name')}' on {r.get('self_hosted_domains')}, "
          f"allow emails ending in @{dom}, login One-time PIN, session 7 days")
    print("next: python -X utf8 pages.py check   (Access can take a minute to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
