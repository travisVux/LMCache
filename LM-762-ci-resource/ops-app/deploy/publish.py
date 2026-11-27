"""Put a new build live, safely. Python stdlib only. Used by refresh.ps1 (mode C) and sync.ps1 / sync.sh (mode A).

  python -X utf8 publish.py publish  [--dist DIR] [--db FILE] [--releases DIR] [--keep 5] [--note TEXT]
  python -X utf8 publish.py rollback [--to NAME] [--releases DIR]
  python -X utf8 publish.py list     [--releases DIR]
  python -X utf8 publish.py scan     DIR                 # privacy scan only (exit 1 on any hit)

publish:
  0. take releases/.publish.lock (one publish / rollback at a time; a lock older than 3 h is stale)
  1. privacy scan of DIR and of ops.db (local paths, user names, e-mails, tokens; files > 15 MB) -> stop on any hit
     (hits are printed as file, rule and a short hash, never the matched text); check free disk space
  2. copy DIR -> releases/.staging-<ts>/site, ops.db -> releases/.staging-<ts>/ops.db (sqlite backup API, consistent)
  3. write release.json, rename .staging-<ts> -> <ts>                                  (never served before this)
  4. write CURRENT.tmp, os.replace -> CURRENT                                          (atomic switch)
  5. keep the newest --keep releases (never the live one or the one before it)
The server (--root releases) reads CURRENT per request, so it serves the old or the new build, never a half copy.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import hashlib
import secrets
import contextlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
MAX_BYTES = 15 * 2**20
TEXT_EXT = {".html", ".js", ".css", ".json", ".jsonl", ".md", ".csv", ".txt", ".svg", ".log", ".py", ".yaml", ".yml", ".xml"}


# ───────────── privacy scan ─────────────
def privacy_rules():
    home = str(Path.home())
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    rules = [
        ("windows user path", r"[A-Za-z]:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+(?!Public\b)[A-Za-z0-9._-]+"),
        ("mac user path", r"/Users/(?!Shared\b)[A-Za-z0-9._-]+/"),
        ("linux home path", r"/home/(?!runner/|user/|ubuntu/|<)[A-Za-z0-9._-]+/"),
        ("old PC name", r"HoiPC"),
        ("e-mail", r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)(?!example\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
        ("GitHub token", r"\b(?:gh[opsur]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
        ("Buildkite token", r"\bbkua_[A-Za-z0-9]{20,}"),
        ("Anthropic key", r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
        ("this home folder", re.escape(home)), ("this home folder", re.escape(home.replace("\\", "/"))),
    ]
    if len(user) >= 4 and user.lower() not in ("admin", "user", "runner", "root"):   # too generic to grep for
        rules.append(("this user name", r"\b" + re.escape(user) + r"\b"))
    for w in filter(None, os.environ.get("OPS_PRIVACY_WORDS", "").split(",")):     # extra words, comma separated
        rules.append(("listed word", re.escape(w.strip())))
    return [(n, re.compile(p, re.I if n != "e-mail" else 0)) for n, p in rules]


ALLOW_EMAIL = re.compile(r"^(git@github\.com|noreply@[\w.-]+|[\w.+-]+@users\.noreply\.github\.com|.*@(example|anthropic)\.com|noreply@anthropic\.com)$", re.I)


def scan_db(db):
    """Privacy scan of every text cell of ops.db (the API serves it). -> list of (table.column, rule, hash)."""
    hits, rules = [], privacy_rules()
    con = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)
    try:
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
            for c in cols:
                for (v,) in con.execute(f'SELECT DISTINCT "{c}" FROM "{t}" WHERE typeof("{c}")=\'text\''):
                    for name, rx in rules:
                        m = rx.search(v)
                        if m and not (name == "e-mail" and ALLOW_EMAIL.match(m.group(0))):
                            hits.append((f"ops.db:{t}.{c}", name, "sha256:" + hashlib.sha256(m.group(0).encode()).hexdigest()[:12]))
                            break
    finally:
        con.close()
    return hits


def scan(root):
    """-> list of (file, rule, sample). Empty = clean."""
    root, hits, rules = Path(root), [], privacy_rules()
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        if f.stat().st_size > MAX_BYTES:
            hits.append((rel, "file > 15 MB", f"{f.stat().st_size // 2**20} MB"))
            continue
        if f.suffix.lower() not in TEXT_EXT:
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        for name, rx in rules:
            for m in rx.finditer(txt):
                s = m.group(0)
                if name == "e-mail" and ALLOW_EMAIL.match(s):
                    continue
                hits.append((rel, name, "sha256:" + hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:12]))
                break
    return hits


# ───────────── releases ─────────────
def releases(rdir):
    return sorted(p.name for p in rdir.iterdir() if p.is_dir() and not p.name.startswith(".") and (p / "site").is_dir())


def current(rdir):
    p = rdir / "CURRENT"
    return p.read_text(encoding="utf-8").strip() if p.is_file() else None


def retry(fn, what, tries=12):
    """Windows refuses a rename while another process (server, antivirus, indexer) has the file open: retry with backoff."""
    for i in range(tries):
        try:
            return fn()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))
            print(f"  retry {what} ({i + 1})", file=sys.stderr)


def switch(rdir, name):
    if not (rdir / name / "site" / "index.html").is_file() or not (rdir / name / "ops.db").is_file():
        sys.exit(f"switch: {name} is not a complete release (site/index.html and ops.db needed)")
    tmp = rdir / f"CURRENT.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(name + "\n")
        f.flush()
        os.fsync(f.fileno())
    retry(lambda: os.replace(tmp, rdir / "CURRENT"), "CURRENT switch")   # atomic on NTFS and POSIX


@contextlib.contextmanager
def publish_lock(rdir):
    """One publish / rollback at a time, whoever starts it (refresh.ps1, sync.ps1, sync.sh, by hand)."""
    lock = rdir / ".publish.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - lock.stat().st_mtime
        if age < 3 * 3600:
            sys.exit(f"publish: another publish holds {lock} ({int(age)} s old); nothing done")
        print(f"publish: removing a stale lock ({int(age)} s old)")
        lock.unlink()
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, f"{os.getpid()} {dt.datetime.now(dt.timezone.utc).isoformat()}\n".encode())
    os.close(fd)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


def rmtree_logged(p):
    errs = []
    shutil.rmtree(p, onerror=lambda f, path, e: errs.append(path))
    if errs:
        print(f"  WARNING: could not remove {len(errs)} path(s) under {p.name} (in use?); will retry next run")


def copy_db(src, dst):
    """Consistent copy even while a collector writes; the copy is a single file (no WAL) so it opens read-only."""
    s = sqlite3.connect(f"{Path(src).resolve().as_uri()}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    with d:
        s.backup(d)
    d.execute("PRAGMA journal_mode=DELETE")
    d.close()
    s.close()


def git_rev():
    try:
        return subprocess.run(["git", "-C", str(APP), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def do_publish(a):
    dist, db, rdir = Path(a.dist).resolve(), Path(a.db).resolve(), Path(a.releases).resolve()
    if a.keep < 2:
        sys.exit("publish: --keep must be 2 or more (the live release and the one before it)")
    rdir.mkdir(parents=True, exist_ok=True)
    with publish_lock(rdir):
        _publish(a, dist, db, rdir)


def _publish(a, dist, db, rdir):
    for need in (dist / "index.html", dist / "shell.html", db):
        if not need.is_file():
            sys.exit(f"publish: missing {need}")
    hits = scan(dist)
    if hits:
        for h in hits[:40]:
            print("  PRIVACY", *h)
        sys.exit(f"publish: privacy scan found {len(hits)} hit(s) in {dist}: nothing published")
    dbhits = scan_db(db)
    if dbhits:
        for h in dbhits[:40]:
            print("  PRIVACY", *h)
        sys.exit(f"publish: privacy scan found {len(dbhits)} hit(s) in {db}: nothing published")
    print(f"privacy scan: 0 hits in {dist} and ops.db")
    need = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file()) + db.stat().st_size
    free = shutil.disk_usage(rdir).free
    if free < 2 * need:
        sys.exit(f"publish: only {free // 2**20} MB free, need about {2 * need // 2**20} MB: nothing published")
    now = dt.datetime.now(dt.timezone.utc)
    name = now.strftime("%Y%m%dT%H%M%SZ")
    while (rdir / name).exists():          # two publishes in the same second
        name = now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)
    stage = rdir / f".staging-{name}"
    shutil.copytree(dist, stage / "site", ignore=shutil.ignore_patterns("check-harness.html", "__check_harness.html"))
    copy_db(db, stage / "ops.db")
    files = [f for f in (stage / "site").rglob("*") if f.is_file()]
    meta = dict(name=name, published_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                page_built=dt.datetime.fromtimestamp((dist / "index.html").stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                from_host=socket.gethostname() if a.show_host else None, git=git_rev(), files=len(files),
                bytes=sum(f.stat().st_size for f in files), note=a.note, previous=current(rdir))
    (stage / "release.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    retry(lambda: os.replace(stage, rdir / name), "release rename")
    switch(rdir, name)
    print(f"live: {name}  ({meta['files']} files, {meta['bytes'] // 2**20} MB; previous {meta['previous']})")
    keep = set(releases(rdir)[-a.keep:]) | {name, meta["previous"]}
    for old in releases(rdir):
        if old not in keep:
            rmtree_logged(rdir / old)
            print("removed old release", old)
    for st in rdir.glob(".staging-*"):   # left over from a crashed run (only old ones: we hold the lock, but be safe)
        if time.time() - st.stat().st_mtime > 3600:
            rmtree_logged(st)


def do_rollback(a):
    rdir = Path(a.releases).resolve()
    with publish_lock(rdir):
        _rollback(a, rdir)


def _rollback(a, rdir):
    rs, cur = releases(rdir), current(rdir)
    if a.to:
        if a.to not in rs:
            sys.exit(f"rollback: no release {a.to}; have {rs}")
        target = a.to
    else:
        older = [r for r in rs if cur is None or r < cur]
        if not older:
            sys.exit(f"rollback: nothing older than {cur}")
        target = older[-1]
    switch(rdir, target)
    print(f"live: {target}  (was {cur})")


def do_list(a):
    rdir = Path(a.releases).resolve()
    cur = current(rdir)
    for r in releases(rdir):
        m = rdir / r / "release.json"
        meta = json.loads(m.read_text(encoding="utf-8")) if m.is_file() else {}
        print(("* " if r == cur else "  ") + r, meta.get("page_built", ""), meta.get("files", ""), meta.get("note") or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--dist", default=str(APP / "dist"))
    p.add_argument("--db", default=str(APP / "data" / "ops.db"))
    p.add_argument("--keep", type=int, default=5)
    p.add_argument("--note")
    p.add_argument("--show-host", action="store_true", help="write this machine's name into release.json (off by default)")
    for name in ("publish", "rollback", "list"):
        q = p if name == "publish" else sub.add_parser(name)
        q.add_argument("--releases", default=str(APP / "releases"))
        if name == "rollback":
            q.add_argument("--to")
    s = sub.add_parser("scan")
    s.add_argument("dir")
    s.add_argument("--db", help="also scan this sqlite file")
    a = ap.parse_args()
    if a.cmd == "scan":
        hits = scan(a.dir) + (scan_db(a.db) if a.db else [])
        for h in hits:
            print("  PRIVACY", *h)
        print(f"privacy scan: {len(hits)} hit(s) in {a.dir}")
        return 1 if hits else 0
    {"publish": do_publish, "rollback": do_rollback, "list": do_list}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
