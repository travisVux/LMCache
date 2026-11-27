"""Minimal Buildkite REST client. Token is read at runtime and never printed."""
import json, time, urllib.request, urllib.error, os

ORG = "lmcache"
_TOKEN = None

def _token():
    global _TOKEN
    if _TOKEN is None and os.environ.get("BUILDKITE_API_TOKEN"):   # the refresh loads it from ops-app.env (common.ps1)
        _TOKEN = os.environ["BUILDKITE_API_TOKEN"]
    if _TOKEN is None:
        p = os.path.expanduser(r"~\.claude.json.bak-buildkite")
        d = json.load(open(p, encoding="utf-8"))
        h = d["mcpServers"]["buildkite"]["headers"]["Authorization"]
        _TOKEN = h.split(" ", 1)[1] if h.lower().startswith("bearer ") else h
    return _TOKEN

def get(url, accept="application/json", retries=8, raw=False):
    if not url.startswith("http"):
        url = "https://api.buildkite.com/v2/" + url.lstrip("/")
    last = None
    for a in range(retries):
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _token(), "Accept": accept, "User-Agent": "CacheAgent-P1"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read()
                link = r.headers.get("Link", "")
                return (body if raw else json.loads(body)), link
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                raise RuntimeError(f"HTTP {e.code} for {url.split('?')[0]}") from None
            last = f"HTTP {e.code}"
            if e.code == 429:
                time.sleep(int(e.headers.get("RateLimit-Reset", "10")) + 1); continue
        except Exception as e:
            last = type(e).__name__
        time.sleep(min(60, 2 * (a + 1) ** 1.5))
    raise RuntimeError(f"failed after retries: {last} {url.split('?')[0]}")

def next_link(link):
    for part in link.split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1:part.find(">")]
    return None
