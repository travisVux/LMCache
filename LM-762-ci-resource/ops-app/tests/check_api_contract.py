"""Contract test: the release PC API (backend/dbapi.py via server.py) and the Cloudflare functions
(deploy/pages-functions) give the same answers on the same snapshot. Python stdlib only.

  python -X utf8 check_api_contract.py --pc http://127.0.0.1:8797 --cf http://127.0.0.1:8796 [--cf-auth user:password]

Set up both on ONE snapshot: server.py --root <releases dir> (release R), and `wrangler pages dev` on a copy of
(push with OPS_D1_DAYS=0: the PC serves all history, the public D1 only its window, so a windowed copy differs by design)
deploy/pages-functions whose local D1 holds R (d1_sync.py push --target sqlite:<file>, then load its dump with
`wrangler d1 execute --local --file`). Compared: status codes, error codes, key sets, row order and values, total,
next_offset, filters applied. Known differences by design (not compared): `source`, `pinned` on views, the `d1` / `run`
/ `queue` / `last_attempt` details of /api/sync-status.
"""
import argparse
import base64
import json
import sys
import urllib.error
import urllib.request

QUERIES = [
    "/api/db/pr?limit=3",
    "/api/db/pr?limit=2&offset=1000",
    "/api/db/artifact?tag=v0.5.8",
    "/api/db/bk_build?env=k3-unit-tests&range=7d&limit=5",
    "/api/db/kpi_daily?range=1d",
    "/api/db/kpi_daily?range=3d&limit=7&offset=7",
    "/api/db/v_release_cycle",
    "/api/db/v_failing_jobs?limit=5",
    "/api/db/pr?tag=zzz",                 # filter that cannot apply -> 400 filter_not_applicable
    "/api/db/v_failing_jobs?branch=x",    # same on a view
    "/api/db/pr?limit=0",                 # clamped to 1 on both
    "/api/db/pr?limit=10abc",             # bad_param on both
    "/api/db/pr?range=soon",              # bad_param on both
    "/api/db/sqlite_master",              # unknown_table
    "/api/nope",                          # not_found (JSON, never HTML)
]
SKIP_KEYS = {"source", "pinned", "d1", "run", "queue", "last_attempt", "page_made", "tables"}


def get(base, path, auth=None):
    req = urllib.request.Request(base + path)
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8", "replace")


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in SKIP_KEYS}
    if isinstance(o, list):
        return [strip(x) for x in o]
    if isinstance(o, float) and o.is_integer():
        return int(o)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pc", required=True)
    ap.add_argument("--cf", required=True)
    ap.add_argument("--cf-auth")
    a = ap.parse_args()
    bad = 0
    for q in QUERIES:
        s1, t1, b1 = get(a.pc, q)
        s2, t2, b2 = get(a.cf, q, a.cf_auth)
        why = []
        if s1 != s2:
            why.append(f"status {s1} vs {s2}")
        if "json" not in t1 or "json" not in t2:
            why.append(f"content-type {t1!r} vs {t2!r}")
        try:
            j1, j2 = json.loads(b1), json.loads(b2)
        except ValueError:
            why.append("not JSON")
            j1 = j2 = None
        if j1 is not None:
            e1, e2 = (j1.get("error") or {}).get("code"), (j2.get("error") or {}).get("code")
            if e1 != e2:
                why.append(f"error {e1} vs {e2}")
            if set(strip(j1)) != set(strip(j2)):
                why.append(f"keys {sorted(set(strip(j1)) ^ set(strip(j2)))}")
            for k in ("n", "total", "limit", "offset", "next_offset", "filters", "rows"):
                if k in j1 and strip(j1.get(k)) != strip(j2.get(k)):
                    why.append(f"{k} differs" + (f" ({j1.get(k)} vs {j2.get(k)})" if k != "rows" else ""))
        bad += bool(why)
        print(f"{'PASS' if not why else 'FAIL'}  {s1} {q}" + (f"  ({'; '.join(why)})" if why else ""))
    s1, _, b1 = get(a.pc, "/api/sync-status")
    s2, _, b2 = get(a.cf, "/api/sync-status", a.cf_auth)
    k1, k2 = set(json.loads(b1)), set(json.loads(b2))
    ok = s1 == s2 == 200 and k1 == k2
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL'}  /api/sync-status same keys" + ("" if ok else f" ({sorted(k1 ^ k2)})"))
    print("RESULT:", "PASS" if not bad else f"FAIL ({bad})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
