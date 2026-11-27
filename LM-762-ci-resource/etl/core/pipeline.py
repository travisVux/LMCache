"""Source contract + the runner that does incremental fetch, backfill and retry.

A Source splits its data into partitions. For a date range it `plan`s the partitions that should exist:
    Part(key, day, watermark)   watermark = the time the data last changed, if the source can see it (else None)
The runner fetches a partition when
    - it is not in the lake, or
    - its last fetch failed (status failed; 'dead' only with --retry-dead), or
    - it is not final yet (recent data that may still change: running builds, open PRs), or
    - its watermark moved past the last fetch (the PR / run changed after we read it), or
    - --refresh was given.
--max-age D: a not-final partition fetched less than D days ago, whose watermark did not move, is kept when its
source says the stored copy is settled enough (Source.recent_ok; only gh_prs: an open PR whose check suites all concluded).
After a fetch the source says whether the payload is final (settled): final partitions are not fetched again.
Failures never stop the run: they are written to the state table with the error and retried on the next run.
"""
import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

Part = namedtuple("Part", "key day watermark")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def days(since, until):
    d, end = ts(since).date(), ts(until).date()
    while d < end:
        yield d.isoformat()
        d += timedelta(days=1)


class Source:
    name = ""
    workers = 1
    max_attempts = 5

    def plan(self, ctx, since, until):   # -> [Part]
        raise NotImplementedError

    def fetch(self, ctx, part):           # -> (payload, rows, watermark, final)
        raise NotImplementedError

    def recent_ok(self, lake, key):       # --max-age: may a recent, not-final copy be kept? default no
        return False


def need(lake, src, p, refresh, retry_dead, max_age=None):
    st = lake.get(src.name, p.key)
    if refresh or st is None or not lake.has_payload(src.name, p.key) and st["status"] == "ok":
        return True
    if st["status"] == "dead":
        return retry_dead
    if st["status"] == "failed":
        return True
    if not st["final"]:
        moved = bool(p.watermark and st["fetched_at"] and p.watermark > st["fetched_at"])
        fresh = bool(max_age and st["fetched_at"] and ts(st["fetched_at"]) >= datetime.now(timezone.utc) - max_age)
        return not (fresh and not moved and src.recent_ok(lake, p.key))
    return bool(p.watermark and st["fetched_at"] and p.watermark > st["fetched_at"])


def run(src, ctx, since, until, refresh=False, retry_dead=False, only_failed=False, limit=None, command="", dry_run=False, max_age=None):
    lake, t0, started = ctx.lake, time.time(), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = src.plan(ctx, since, until)
    todo = [p for p in parts if need(lake, src, p, refresh, retry_dead, max_age)]
    kept = sum(1 for p in parts if (lake.get(src.name, p.key) or {}).get("final") is False and p not in todo) if max_age else 0
    if only_failed:
        todo = [p for p in todo if (lake.get(src.name, p.key) or {}).get("status") in ("failed", "dead")]
    if limit:
        todo = todo[:limit]
    print(f"[{src.name}] planned {len(parts)} · to fetch {len(todo)} · up to date {len(parts) - len(todo)}"
          + (f" (of which not final but fetched < max-age ago: {kept})" if kept else ""), flush=True)
    if dry_run:
        why = {}
        for p in todo:
            st = lake.get(src.name, p.key)
            r = "new" if st is None else st["status"] if st["status"] != "ok" else "not final" if not st["final"] else "changed"
            why[r] = why.get(r, 0) + 1
        print(f"  [{src.name}] dry run, reasons: {why}", flush=True)
        return dict(planned=len(parts), to_fetch=len(todo), reasons=why)
    done = failed = 0

    def one(p):
        payload, rows, wm, final = src.fetch(ctx, p)
        lake.write(src.name, p.key, payload)
        lake.ok(src.name, p.key, p.day, rows, wm or p.watermark, final)
        return final

    with ThreadPoolExecutor(max(1, src.workers)) as ex:
        futs = {ex.submit(one, p): p for p in todo}
        for i, f in enumerate(as_completed(futs), 1):
            p = futs[f]
            try:
                f.result(); done += 1
            except Exception as e:  # noqa: BLE001  recorded, retried next run
                failed += 1
                st = lake.fail(src.name, p.key, p.day, f"{type(e).__name__}: {e}", src.max_attempts)
                print(f"  [{src.name}] {p.key}: {st}: {e}", flush=True)
            if i % 200 == 0 or i == len(todo):
                print(f"  [{src.name}] {i}/{len(todo)} · failed {failed} · {time.time() - t0:.0f}s", flush=True)
    lake.log(started=started, command=command, source=src.name, planned=len(parts), fetched=done, skipped=len(parts) - len(todo), failed=failed)
    return dict(planned=len(parts), fetched=done, failed=failed)
