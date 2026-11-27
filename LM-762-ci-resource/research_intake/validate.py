"""Validate Research reports against research_report.schema.json (stdlib only, no jsonschema package).

  python -X utf8 validate.py inbox/*.json samples/*.json      prints OK / the errors per file, exit 1 if any file fails

Supported schema keywords (the subset the contract uses): type, const, enum, pattern, minLength, maxLength, minimum,
maximum, required, properties, additionalProperties: false, items, minItems, maxItems.
Extra checks the schema cannot express:
  - privacy: no e-mail address, no local path (C:\\..., /Users/..., /home/...), no token (ghp_, github_pat_, bkua_, sk-ant-)
  - the file name must be <id>.json
  - strict JSON: no NaN / Infinity, no duplicate keys; a UTF-8 BOM is tolerated
  - "pattern" ending in $ really means end of string (no trailing newline sneaks through)
  - created_at is a real UTC time, not more than 10 minutes in the future
  - metric names are unique; https URLs have a host; required strings are not just spaces
  - samples: a file is a sample if and only if it is in samples/, has "sample": true and an id starting rr-sample-
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "research_report.schema.json").read_text(encoding="utf-8"))
PRIVACY = [("e-mail address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
           ("local path", re.compile(r"\b[A-Za-z]:[\\/]|/Users/|/home/(?!runner\b)")),
           ("token", re.compile(r"\b(gh[opsur]_[A-Za-z0-9]{10,}|github_pat_|bkua_[A-Za-z0-9]|sk-ant-)"))]
TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}


def check(v, s, path, errs):
    t = s.get("type")
    if t:
        ok = isinstance(v, TYPES[t]) and not (t in ("integer", "number") and isinstance(v, bool))
        if not ok:
            errs.append(f"{path}: expected {t}"); return
    if "const" in s and v != s["const"]:
        errs.append(f"{path}: must be {s['const']!r}")
    if "enum" in s and v not in s["enum"]:
        errs.append(f"{path}: must be one of {s['enum']}")
    if isinstance(v, str):
        pat = s.get("pattern")
        if pat and pat.endswith("$") and not pat.endswith(chr(92) + "$"):
            pat = pat[:-1] + r"\Z"
        if pat and not re.search(pat, v):
            errs.append(f"{path}: does not match {s['pattern']}")
        if len(v.strip()) < max(1, s.get("minLength", 0)) or len(v) > s.get("maxLength", 10 ** 9):
            errs.append(f"{path}: length {len(v)} not in [{s.get('minLength', 0)}, {s.get('maxLength', '∞')}]")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in s and v < s["minimum"]:
            errs.append(f"{path}: below {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            errs.append(f"{path}: above {s['maximum']}")
    if isinstance(v, dict):
        for k in s.get("required", []):
            if k not in v:
                errs.append(f"{path}.{k}: required")
        props = s.get("properties", {})
        for k, x in v.items():
            if k in props:
                check(x, props[k], f"{path}.{k}", errs)
            elif s.get("additionalProperties") is False:
                errs.append(f"{path}.{k}: not allowed (the contract is closed)")
    if isinstance(v, list):
        if len(v) < s.get("minItems", 0) or len(v) > s.get("maxItems", 10 ** 9):
            errs.append(f"{path}: {len(v)} items not in [{s.get('minItems', 0)}, {s.get('maxItems', '∞')}]")
        for i, x in enumerate(v):
            check(x, s.get("items", {}), f"{path}[{i}]", errs)


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def _no_const(c):
    raise ValueError(f"{c} is not JSON")


def _no_dup(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate key {k!r}")
        d[k] = v
    return d


def extra_checks(doc, errs):
    if not isinstance(doc, dict):
        return
    ts = doc.get("created_at")
    if isinstance(ts, str):
        try:
            t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if t > datetime.now(timezone.utc) + timedelta(minutes=10):
                errs.append("$.created_at: in the future")
        except ValueError:
            errs.append("$.created_at: not a real date / time")
    names = [m.get("name") for m in ((doc.get("benchmark") or {}).get("metrics") or []) if isinstance(m, dict)]
    if len(names) != len(set(names)):
        errs.append("$.benchmark.metrics: metric names must be unique")

    def urls(v, path="$"):
        if isinstance(v, dict):
            for k, x in v.items():
                if k == "url" and isinstance(x, str):
                    u = urlparse(x)
                    if u.scheme != "https" or not u.netloc or "." not in u.netloc:
                        errs.append(f"{path}.url: not a full https URL")
                else:
                    urls(x, f"{path}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                urls(x, f"{path}[{i}]")
    urls(doc)


def validate(path, folder=None):
    """-> (report or None, [errors]). folder: 'samples' or 'inbox' when known (the sample flag must agree with it)."""
    p = Path(path)
    try:
        doc = json.loads(p.read_text(encoding="utf-8-sig"), parse_constant=_no_const, object_pairs_hook=_no_dup)
    except (OSError, ValueError) as e:
        return None, [f"not readable JSON: {e}"]
    errs = []
    check(doc, SCHEMA, "$", errs)
    extra_checks(doc, errs)
    folder = folder or p.parent.name
    if isinstance(doc, dict) and folder in ("samples", "inbox"):
        is_s = folder == "samples"
        if bool(doc.get("sample")) != is_s or str(doc.get("id", "")).startswith("rr-sample-") != is_s:
            errs.append("sample: a report is a sample only in samples/, with \"sample\": true and an id rr-sample-…; "
                        "a real report (inbox/) has neither")
    for s in strings(doc):
        if re.search("[\u202a-\u202e\u2066-\u2069\u200e\u200f]", s):
            errs.append(f"text: bidirectional control character in {s[:40]!r} (could hide or reorder text)")
        for what, rx in PRIVACY:
            if rx.search(s):
                errs.append(f"privacy: {what} in {s[:60]!r}")
    if isinstance(doc, dict) and doc.get("id") and p.stem != doc["id"]:
        errs.append(f"file name must be {doc['id']}.json")
    return (doc if not errs else None), errs


def main(argv):
    files = [f for a in argv for f in (sorted(Path().glob(a)) if any(c in a for c in "*?") else [Path(a)])]
    if not files:
        print(__doc__); return 2
    bad = 0
    for f in files:
        _, errs = validate(f)
        print(f"{f}: {'OK' if not errs else 'INVALID'}")
        for e in errs:
            print("   -", e)
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
