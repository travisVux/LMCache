"""HTTP with retry for the three APIs (Buildkite REST, GitHub REST, GitHub GraphQL).

Tokens are read at runtime, kept in memory only, never printed or written to disk.
Retry policy:
  - 401 / 404 / 410 / 422            -> Fatal (no retry: the request itself is wrong)
  - 403 / 429 with rate limit spent   -> sleep until the reset time, then retry (does not use a try)
  - 5xx, timeouts, network errors     -> exponential backoff (2, 4, 8 ... max 120 s), up to `tries`
  - remaining quota below `min_remaining` after a call -> sleep until reset before the next call
    (no_wait: stop instead - every later call of this client fails at once without a request, so a scheduled step
     ends in time and leaves the rest of the quota alone; the failed partitions are fetched on the next run)
"""
import json
import os
import random
import subprocess
import threading
import time
import urllib.error
import urllib.request


class Fatal(Exception):
    """The request can not succeed by retrying."""


def _gh_token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    p = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        raise Fatal("no GitHub token: run `gh auth login`")
    return p.stdout.strip()


def _bk_token():
    t = os.environ.get("BUILDKITE_API_TOKEN")
    if t:
        return t
    p = os.path.expanduser(r"~\.claude.json.bak-buildkite")
    d = json.load(open(p, encoding="utf-8"))
    h = d["mcpServers"]["buildkite"]["headers"]["Authorization"]
    return h.split(" ", 1)[1] if h.lower().startswith("bearer ") else h


class Client:
    def __init__(self, base, token_fn, reset_is_epoch, rem_header, reset_header, min_remaining=60, no_wait=False):
        self.base, self._token_fn, self._tok = base, token_fn, None
        self.reset_is_epoch, self.rem_h, self.reset_h, self.min_remaining = reset_is_epoch, rem_header, reset_header, min_remaining
        self._lock = threading.Lock()
        self.calls = 0
        self.no_wait, self.stopped = no_wait, None

    def token(self):
        with self._lock:
            if self._tok is None:
                self._tok = self._token_fn()
            return self._tok

    def _reset_wait(self, h):
        r = h.get(self.reset_h)
        if r is None:
            return int(h.get("Retry-After", "30"))
        r = int(float(r))
        return max(1, r - int(time.time())) + 2 if self.reset_is_epoch else r + 2

    def _after(self, h):
        rem = h.get(self.rem_h)
        if rem is not None and int(rem) < self.min_remaining:
            if self.no_wait:
                self.stopped = f"quota floor: {rem} left < {self.min_remaining}"
                print(f"  [rate] {self.base} remaining {rem} < {self.min_remaining}: no more calls in this run", flush=True)
                return
            w = self._reset_wait(h)
            print(f"  [rate] {self.base} remaining {rem}, sleeping {w // 60} min {w % 60} s", flush=True)
            time.sleep(w)

    def request(self, url, body=None, accept="application/json", tries=8):
        if not url.startswith("http"):
            url = self.base + url.lstrip("/")
        short = url.split("?")[0]
        if self.stopped:
            raise RuntimeError(self.stopped)
        last, a = None, 0
        while a < tries:
            hdr = {"Authorization": "Bearer " + self.token(), "Accept": accept, "User-Agent": "CacheAgent-ETL"}
            data = None
            if body is not None:
                data, hdr["Content-Type"] = json.dumps(body).encode(), "application/json"
            req = urllib.request.Request(url, data=data, headers=hdr, method="POST" if body is not None else "GET")
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    payload = json.loads(r.read())
                    self.calls += 1
                    self._after(r.headers)
                    return payload, r.headers
            except urllib.error.HTTPError as e:
                h, last = e.headers, f"HTTP {e.code}"
                spent = h.get(self.rem_h) == "0" or "Retry-After" in h or e.code == 429
                if e.code in (403, 429) and spent:
                    w = self._reset_wait(h)
                    print(f"  [rate] {last} on {short}, sleeping {w} s", flush=True)
                    time.sleep(w)
                    continue
                if e.code in (401, 403, 404, 410, 422):
                    raise Fatal(f"{last} {short}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as e:
                last = type(e).__name__
            a += 1
            time.sleep(min(120, 2 ** a + random.random()))
        raise RuntimeError(f"failed after {tries} tries: {last} {short}")


BK = Client("https://api.buildkite.com/v2/", _bk_token, reset_is_epoch=False, rem_header="RateLimit-Remaining", reset_header="RateLimit-Reset")
GH = Client("https://api.github.com/", _gh_token, reset_is_epoch=True, rem_header="X-RateLimit-Remaining", reset_header="X-RateLimit-Reset",
            min_remaining=int(os.environ.get("ETL_GH_MIN_REMAINING") or 60),   # below it: sleep until the reset
            no_wait=os.environ.get("ETL_GH_NO_WAIT") == "1")                  # ... or stop calling GitHub in this run


def next_link(h):
    for part in (h.get("Link") or "").split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1:part.find(">")]
    return None


def graphql(query):
    d, _ = GH.request("graphql", body={"query": query})
    if d.get("errors") or not d.get("data"):
        raise RuntimeError("graphql: " + str(d.get("errors"))[:300])
    return d["data"]
