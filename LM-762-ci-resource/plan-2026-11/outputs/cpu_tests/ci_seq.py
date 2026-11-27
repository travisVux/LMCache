"""CI pipeline -> ordered steps for the PR Inspector sequence diagram (phase B). Stdlib only (no PyYAML).

parse(path, text) -> list of steps: {g: group label, label, key, cond, deps, cmd, line, end, kind}
  Buildkite (.buildkite/**.yml): top-level `- group:` / `- label:` / `- wait` / `- block:` / `- trigger:` items and the
     steps inside a group; `if:` of the group and of the step are both kept (group first).
  GitHub Actions (.github/workflows/*.yml): one step per job (`jobs: <id>:`), `if:`, `needs:`, the first `run:` line;
     the workflow `on:` triggers and path filters become the first step (the trigger).
The parser reads indentation, not full YAML: it is for drawing and linking (file:line), not for running anything.
"""
import re

ITEM = re.compile(r"^(\s*)- (group|label|wait|block|trigger|command|input)\b:?\s*(.*)$")
KEY = re.compile(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$")


def _clean(v):
    v = (v or "").strip()
    if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def _block(val, lines, i):
    """`key: |` / `key: >-`: the value is the next non-empty line(s); keep the first two, joined."""
    if val not in ("|", "|-", ">", ">-", ">+", "|+"):
        return val
    out = []
    for nxt in lines[i:i + 6]:
        if nxt.strip():
            out.append(nxt.strip())
        if len(out) == 2:
            break
    return " ".join(out)


def parse_buildkite(text):
    lines = text.splitlines()
    steps, group, gind, gcond = [], None, -1, ""
    cur = None
    for i, ln in enumerate(lines, 1):
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        ind = len(ln) - len(ln.lstrip())
        m = ITEM.match(ln)
        if m:
            kind, val = m.group(2), _clean(m.group(3))
            if group is not None and ind <= gind:
                group, gind, gcond = None, -1, ""
            if cur:
                cur["end"] = i - 1
            if kind == "group":
                group, gind, gcond = val, ind, ""
                cur = dict(g=val, label=val, kind="group", cond="", deps="", key="", cmd="", line=i, end=i, ind=ind)
                steps.append(cur)
                continue
            cur = dict(g=group or "", label=val if kind not in ("wait",) else "wait", kind=kind, cond=gcond if group else "",
                       deps="", key="", cmd="", line=i, end=i, ind=ind)
            steps.append(cur)
            continue
        k = KEY.match(ln)
        if k and cur and ind > cur["ind"] and ind <= cur["ind"] + 4:
            key, val = k.group(2), _block(_clean(k.group(3)), lines, i)
            if key == "if":
                if cur["kind"] == "group":
                    gcond = val
                cur["cond"] = (gcond + " && " + val) if (gcond and cur["kind"] != "group" and val != gcond) else val
            elif key in ("depends_on", "needs"):
                cur["deps"] = val
            elif key == "key":
                cur["key"] = val
            elif key in ("command", "commands") and not cur["cmd"]:
                cur["cmd"] = val or (lines[i].strip().lstrip("- ").strip() if i < len(lines) else "")
            elif key == "soft_fail" and val:
                cur["cond"] = (cur["cond"] + " · " if cur["cond"] else "") + "soft_fail: " + val
            elif key == "label" and cur["kind"] == "command":
                cur["label"] = val
    if cur:
        cur["end"] = len(lines)
    for s in steps:
        s.pop("ind", None)
    return [s for s in steps if s["label"]]


def parse_gha(text):
    lines = text.splitlines()
    steps, in_jobs, job, on_lines = [], False, None, []
    on_start = None
    JI = KI = None     # indentation of job names and of job keys: detected, not assumed 2 / 4 (review M3)
    for i, ln in enumerate(lines, 1):
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        ind = len(ln) - len(ln.lstrip())
        if ind == 0:
            in_jobs = ln.startswith("jobs:")
            if re.match(r"^(on|\"on\"|'on'|true):", ln):
                on_start = i
            elif on_start and not on_lines:
                on_lines = lines[on_start - 1:i - 1]
            if job:
                job["end"] = i - 1
            continue
        if in_jobs and JI is None:
            JI = ind
        if job and KI is None and ind > JI:
            KI = ind
        if in_jobs and ind == JI and ln.rstrip().endswith(":"):
            if job:
                job["end"] = i - 1
            job = dict(g="jobs", label=ln.strip()[:-1], kind="job", cond="", deps="", key=ln.strip()[:-1], cmd="", line=i, end=i)
            steps.append(job)
            continue
        if job and ind == KI:
            k = KEY.match(ln)
            if k:
                key, val = k.group(2), _block(_clean(k.group(3)), lines, i)
                if key == "if":
                    job["cond"] = val
                elif key == "needs":
                    job["deps"] = val
                elif key == "name":
                    job["label"] = val or job["label"]
        if job and not job["cmd"]:
            r = re.match(r"^\s*(?:- )?run:\s*(.*)$", ln)
            if r:
                job["cmd"] = _block(_clean(r.group(1)), lines, i) or (lines[i].strip() if i < len(lines) else "")
    if job:
        job["end"] = len(lines)
    trig = " ".join(x.strip() for x in on_lines if x.strip())[:240]
    if on_start:
        steps.insert(0, dict(g="on", label="trigger", kind="trigger", cond=trig, deps="", key="on", cmd="", line=on_start, end=on_start + len(on_lines)))
    return steps


def parse(path, text):
    if path.startswith(".github/workflows/"):
        return parse_gha(text)
    if path.startswith(".buildkite/"):
        return parse_buildkite(text)
    return []
