"""Living knowledge base: FRS per code area (feature) and RFC per PR, generated from the PR Inspector data,
versioned in ops.db (tables kb_doc, kb_version, kb_link, kb_proposal, kb_analysis; see docs/ERD.md).

Rules
  - The generator never overwrites a version. New facts (CI pipeline steps, gates, tests, open PRs, bugs) for an
    existing document create a PROPOSAL: the changed facts + a unified diff of the document. A person accepts or
    rejects it. Text a person wrote (sections marked "(edit)" and "Notes") is carried into every proposal.
  - Local data only: pr_inspector.json (built by build_pr_inspector.py). No network.

Commands (run in ops-app/backend):
  python -X utf8 kb.py build [--pi PATH] [--simulate FILE] [--db PATH]   create v1 docs / propose updates
  python -X utf8 kb.py list [--db PATH]                                   documents, versions, open proposals
  python -X utf8 kb.py show DOC [--version N]                             print a version
  python -X utf8 kb.py diff PROPOSAL                                      print a proposal's diff
  python -X utf8 kb.py accept PROPOSAL [--reason TEXT] | reject PROPOSAL   decide a proposal
  python -X utf8 kb.py edit DOC --file F.md [--reason TEXT]               a human edit = a new version (author 'human')
  python -X utf8 kb.py export [--out PATH]                                JSON for the page (embedded by build_pr_inspector.py)

--simulate FILE (test a CI / feature change without touching real inputs), JSON like:
  {"ci": {"k3-multiprocess-test": {"add": [["vllm / new_workload / zmq", "build.env(\\"X\\") == \\"1\\""]], "drop": ["deadlock"]}},
   "gates": {"drop_required": ["k3-unit-tests"]}, "areas": {"smcore": {"nt": 99}}}
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from config import DB_PATH
from db import connect, now_iso

HERE = Path(__file__).resolve().parent
PI = HERE.parents[1] / "plan-2026-11" / "outputs" / "cpu_tests" / "pr_inspector.json"
EDITABLE = ("Summary (edit)", "Motivation (edit)", "Rollout and rollback (edit)", "Open questions (edit)", "Notes (edit)")
MAX_RFC = 120     # RFCs are generated for open PRs (newest first) and for PRs named with --pr


def h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- facts (same model as the Inspector JS)
def pr_model(D, n):
    p = D["prs"].get(str(n)) or {}
    files = p.get("f") or []
    is_doc = lambda f: f[0].startswith("docs/") or re.search(r"\.(md|rst|txt)$", f[0], re.I)
    code = [f for f in files if not f[0].startswith("tests/") and not is_doc(f)]
    areas = []
    for a in [x[0] for x in p.get("ar") or []] + [f[6] for f in code if f[6]]:
        if a in D["areas"] and a not in areas:
            areas.append(a)
    cls = set()
    if files:
        if not code:
            cls.add("tests_only" if any(f[0].startswith("tests/") for f in files) else "docs")
        else:
            cls.update(D["areas"][f[6]]["cls"] if f[6] in D["areas"] else "core" for f in code)
    else:
        cls.update(D["areas"][a]["cls"] for a in areas)
    return p, files, code, areas, sorted(cls)


def gates_of_class(D, classes, drop_required=()):
    tiers = {}
    for c in classes:
        for t, lvl in ((D["classes"].get(c) or {}).get("tiers") or {}).items():
            tiers[t] = min(tiers.get(t, 9), lvl)
    out = {}
    for t, lvl in tiers.items():
        ti = D["tiers"].get(t) or {}
        j = ti.get("job") or t
        g = out.setdefault(j, dict(name=j, tiers=[], workloads=[], lvl=9, req=bool(ti.get("req")) and j not in drop_required))
        g["tiers"].append(t); g["workloads"] += ti.get("wl") or []; g["lvl"] = min(g["lvl"], lvl)
    for g in out.values():
        g["level"] = "required" if g["req"] and g["lvl"] == 1 else "conditional" if g["lvl"] == 2 else "advisory"
        g["tiers"].sort(); g["workloads"] = sorted(set(g["workloads"]))
        del g["lvl"], g["req"]
    return sorted(out.values(), key=lambda g: g["name"])


def frs_facts(D, a, sim):
    A = D["areas"][a]
    gates = gates_of_class(D, [A["cls"]], (sim.get("gates") or {}).get("drop_required") or ())
    ci = {}
    for g in gates:
        c = (D.get("ci") or {}).get(g["name"])
        if c:
            ci[g["name"]] = dict(file=c["file"], n=c["n"], n_cond=c["n_cond"], steps=[s[0] for s in c["steps"]],
                                 cond={s[0]: s[1] for s in c["steps"] if s[1]})
    over = (sim.get("areas") or {}).get(a) or {}
    return dict(area=a, title=A["t"], cls=A["cls"],
                F=[dict(id=f, name=(D["F"].get(f) or {}).get("name"), risk=(D["F"].get(f) or {}).get("risk"),
                        gate=(D["F"].get(f) or {}).get("gate"), cpu=(D["F"].get(f) or {}).get("cpu"), gpu=(D["F"].get(f) or {}).get("gpu"))
                   for f in A.get("F") or []],
                gates=gates, ci=ci, tests=over.get("nt", A.get("nt")), concurrency_tests=sorted(A.get("ct") or []),
                flaky=[w["name"] for w in D.get("flaky") or []] if any(g["name"] == "k3-multiprocess-test" for g in gates) else [],
                bugs=A.get("bugs") or [], open_prs=sorted(A.get("open") or []))


def rfc_facts(D, n):
    p, files, code, areas, cls = pr_model(D, n)
    scan = D.get("scan") or {}
    conc, nondet = set(), set()
    for f in files:
        s = scan.get(f[0]) or {}
        for hcat, kind, _line, fn in s.get("h") or []:
            if fn in f[4] or fn in f[5]:
                (conc if hcat == "c" else nondet).add(kind)
    failed = [b for b in p.get("b") or [] if (D["builds"].get(b) or {}).get("st") == "failed"]
    return dict(pr=str(n), title=p.get("t"), state=p.get("st"), author=p.get("au"), sha=p.get("sha"), released=p.get("rel") or [],
                files=[[f[0], f[6] or "", f[4][:6]] for f in files], areas=areas, F=sorted({F for a in areas for F in D["areas"][a].get("F") or []}),
                classes=cls, gates=gates_of_class(D, cls), tests_edited=[t[5:] for t in p.get("te") or []],
                concurrency=sorted(conc), nondeterminism=sorted(nondet), retries=len(p.get("rt") or []),
                merged_overlap=sorted({c["m"] for c in p.get("c24") or []}, key=str), open_overlap=sorted({c["m"] for c in p.get("oc") or []}, key=str),
                failed_builds=failed, sigs=sorted({s for b in failed for s in (D["builds"][b].get("sig") or [])}),
                new_ci=[dict(file=e["file"], edited=[s["label"] for s in e["steps"] if s.get("chg")][:10]) for e in (D.get("seq") or {}).get(str(n), [])])


def apply_sim(D, sim):
    """--simulate: change the CI pipeline facts in memory (a pipeline edit) before facts are computed."""
    for job, ch in (sim.get("ci") or {}).items():
        c = (D.get("ci") or {}).get(job)
        if not c:
            continue
        drop = set(ch.get("drop") or [])
        c["steps"] = [s for s in c["steps"] if not any(d in s[0] for d in drop)] + [[lab, cond, 0] for lab, cond in ch.get("add") or []]
        c["n"] = len(c["steps"]); c["n_cond"] = sum(1 for s in c["steps"] if s[1])
    return D


# ---------------------------------------------------------------- documents (markdown templates)
def md_table(rows, head):
    if not rows:
        return "_none_\n"
    out = "| " + " | ".join(head) + " |\n|" + "---|" * len(head) + "\n"
    return out + "".join("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in r) + " |\n" for r in rows)


def frs_body(F, made):
    s = [f"# FRS · {F['title']} (`{F['area']}`)\n",
         f"> Generated from local data ({made}). A fact change creates a proposal, never a silent overwrite. "
         "Write in the sections marked (edit); they are kept in every proposal.\n",
         "## Scope\n", f"Code area `{F['area']}`, change class `{F['cls']}`. Features (draft F map): "
         + (", ".join(f"{f['id']} {f['name'] or ''}" for f in F["F"]) or "none mapped") + ".\n",
         "## Functional requirements\n"]
    s += [f"- **FR-{i + 1} · {f['id']} {f['name'] or ''}**: CPU check: {f['cpu'] or 'unknown'}. GPU check: {f['gpu'] or 'unknown'}. "
          f"Risk: {f['risk'] or 'unknown'}. Gate named in the matrix: {f['gate'] or 'unknown'}.\n" for i, f in enumerate(F["F"])] or ["- unknown: no feature mapped to this area\n"]
    s += ["\n## CI gates\n", md_table([[g["name"], g["level"], ", ".join(g["tiers"]), ", ".join(g["workloads"]) or "-"] for g in F["gates"]],
                                      ["Gate", "Level", "Tiers", "Workloads"])]
    s += ["\n## CI pipeline facts\n"]
    for job, c in sorted(F["ci"].items()):
        s.append(f"- `{job}`: {c['n']} steps ({c['n_cond']} conditional) in `{c['file']}`.\n")
        by = {}
        for st in c["steps"]:
            by.setdefault(c["cond"].get(st, ""), []).append(st)
        s += [f"  - {'if `' + cond + '`' if cond else 'always'}: " + ", ".join(f"`{x}`" for x in sts) + "\n" for cond, sts in by.items()]
    if not F["ci"]:
        s.append("- unknown: no pipeline file for these gates in the local clone\n")
    s += ["\n## Tests\n", f"- {F['tests']} test files cover the area.\n",
          f"- Concurrency tests: {', '.join(f'`{t}`' for t in F['concurrency_tests']) or 'none'}.\n",
          "\n## Known risks\n", f"- Flaky workloads in the gate suite: {', '.join(F['flaky']) or 'none'}.\n",
          f"- Failure signatures on tests of this area: {', '.join(F['bugs']) or 'none'}.\n",
          "\n## Open work\n", f"- Open PRs on this area: {', '.join('#' + str(x) for x in F['open_prs']) or 'none'}.\n",
          "\n## Notes (edit)\n", "_Write design decisions, invariants and links here._\n"]
    return "".join(s)


def rfc_body(R, made):
    s = [f"# RFC · #{R['pr']} {R['title'] or ''}\n",
         f"> Template generated from the PR Inspector ({made}); state `{R['state']}`, author `{R['author']}`, commit `{R['sha']}`. "
         "Facts below are generated; write in the sections marked (edit).\n",
         "## Summary (edit)\n", "_One paragraph: what changes for a user or an operator._\n",
         "## Motivation (edit)\n", "_Why now; the issue or failure it answers._\n",
         "## Change\n", md_table([[f"`{f[0]}`", f[1] or "-", ", ".join(f"`{x}`" for x in f[2]) or "-"] for f in R["files"][:40]], ["File", "Area", "Functions"]),
         "\n## Impact: features and gates\n",
         f"- Code areas: {', '.join(R['areas']) or 'unknown'}. Features (draft F map): {', '.join(R['F']) or 'unknown'}. Change class: {', '.join(R['classes']) or 'unknown'}.\n"]
    s += [f"- `{g['name']}`: {g['level']} (tiers {', '.join(g['tiers'])})\n" for g in R["gates"]]
    s += ["\n## Risks (from the 5 Inspector views)\n",
          f"- Race & concurrency: edited code uses {', '.join(R['concurrency']) or 'no lock / thread / asyncio / process / CUDA stream'}.\n",
          f"- Flaky & non-determinism: edited code uses {', '.join(R['nondeterminism']) or 'no sleep / clock / random / fixed port'}; CI retries in the baselines: {R['retries']}.\n",
          f"- Semantic conflict: overlaps with merges of the last 24 h: {', '.join('#' + str(m) for m in R['merged_overlap']) or 'none'}; with open PRs: {', '.join('#' + str(m) for m in R['open_overlap'][:10]) or 'none'}.\n"]
    for e in R["new_ci"]:
        s.append(f"- new.CI: `{e['file']}`, edited steps: {', '.join(e['edited']) or 'none found'}.\n")
    s += ["\n## Test plan\n", f"- Tests edited: {', '.join(f'`{t}`' for t in R['tests_edited'][:20]) or 'none (ask for a test that fails without this change)'}.\n",
          f"- Required gates: {', '.join(g['name'] for g in R['gates'] if g['level'] == 'required') or 'none'}.\n",
          "\n## Rollout and rollback (edit)\n", "_Flag, config default, how to revert._\n",
          "\n## Bug / error analysis\n",
          f"- Failed builds of this PR: {', '.join(R['failed_builds']) or 'none in the index'}; signatures: {', '.join(R['sigs']) or 'none'}.\n",
          "\n## Open questions (edit)\n", "_Reviewer questions from the Inspector checklist that are still open._\n",
          "\n## Notes (edit)\n", "_Free notes._\n"]
    return "".join(s)


def sections(md):
    parts, cur = {}, None
    for ln in md.splitlines(keepends=True):
        m = re.match(r"^## (.+?)\s*$", ln)
        if m:
            cur = m.group(1)
            parts[cur] = ""
        elif cur:
            parts[cur] += ln
    return parts


def carry_human(new_md, old_md, gen_md=None):
    """Keep what a person wrote in the (edit) sections of the current version, and any section a person added."""
    old = sections(old_md)
    new_heads = set(sections(new_md))
    extra = [k for k in old if k not in new_heads and k not in EDITABLE and k != "_"]
    out, cur = [], None
    for ln in new_md.splitlines(keepends=True):
        m = re.match(r"^## (.+?)\s*$", ln)
        if m:
            cur = m.group(1)
            out.append(ln)
            if cur in EDITABLE and cur in old:
                out.append(old[cur])
            continue
        if cur in EDITABLE and cur in old:
            continue
        out.append(ln)
    for k in extra:   # a person's own section ("## Invariants") survives regeneration, at the end
        out.append(("\n" if out and not out[-1].endswith("\n\n") else "") + f"## {k}\n" + old[k])
    return "".join(out)


def fact_changes(a, b, prefix=""):
    out = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if x == y:
            continue
        if isinstance(x, dict) and isinstance(y, dict):
            out += fact_changes(x, y, prefix + k + ".")
        else:
            out.append(dict(fact=prefix + k, before=x, after=y))
    return out


TRIGGER_RULES = (("ci_change", r"^(ci|new_ci)\b"), ("gate_change", r"gates"), ("test_change", r"tests"),
                 ("pr_overlap", r"(merged|open)_overlap"), ("pr_change", r"open_prs|files|state|released|sha|failed_builds|sigs|retries"))


def triggers_of(changes):
    """Every trigger a change set matches (feature_change when no rule matches)."""
    out = []
    for c in changes:
        t = next((t for t, rx in TRIGGER_RULES if re.search(rx, c["fact"])), "feature_change")
        if t not in out:
            out.append(t)
    return out or ["feature_change"]


def trigger_of(changes):
    return ",".join(triggers_of(changes))


def norm_facts(f):
    """Old versions stored some list facts unsorted: sort them before comparing, so order alone is never a change."""
    f = dict(f)
    for k in ("merged_overlap", "open_overlap"):
        if isinstance(f.get(k), list):
            f[k] = sorted(set(f[k]), key=str)
    return f


# ---------------------------------------------------------------- store
MIGRATIONS = (
    ("kb_proposal", "source", "TEXT NOT NULL DEFAULT 'build'"),      # build | simulate
    ("kb_proposal", "input_made", "TEXT"),                           # when the facts it came from were made
    ("kb_proposal", "decided_by", "TEXT"),
    ("kb_proposal", "decision_reason", "TEXT"),
    ("kb_proposal", "superseded_by", "INTEGER"),
    ("kb_version", "proposal_id", "INTEGER"),                        # the accepted proposal, if any
    ("kb_version", "decided_by", "TEXT"),
    ("kb_version", "facts_made", "TEXT"),
    ("kb_doc", "last_seen", "TEXT"),                                 # last build whose input still had this subject
)
GUARDS = """
CREATE INDEX IF NOT EXISTS ix_kb_proposal_doc_status ON kb_proposal(doc_id, status);
CREATE TRIGGER IF NOT EXISTS kb_version_no_update BEFORE UPDATE ON kb_version
  BEGIN SELECT RAISE(ABORT, 'kb_version is append-only'); END;
CREATE TRIGGER IF NOT EXISTS kb_version_no_delete BEFORE DELETE ON kb_version
  BEGIN SELECT RAISE(ABORT, 'kb_version is append-only'); END;
CREATE TRIGGER IF NOT EXISTS kb_version_valid BEFORE INSERT ON kb_version
  WHEN NEW.author NOT IN ('generator','human') OR length(trim(NEW.body_md)) = 0
  BEGIN SELECT RAISE(ABORT, 'kb_version: author must be generator|human and body not empty'); END;
CREATE TRIGGER IF NOT EXISTS kb_proposal_valid_ins BEFORE INSERT ON kb_proposal
  WHEN NEW.status NOT IN ('open','accepted','rejected','superseded') OR NEW.source NOT IN ('build','simulate')
  BEGIN SELECT RAISE(ABORT, 'kb_proposal: bad status or source'); END;
CREATE TRIGGER IF NOT EXISTS kb_proposal_valid_upd BEFORE UPDATE OF status ON kb_proposal
  WHEN NEW.status NOT IN ('open','accepted','rejected','superseded') OR OLD.status <> 'open'
  BEGIN SELECT RAISE(ABORT, 'kb_proposal: only an open proposal can be decided, to a known status'); END;
CREATE TRIGGER IF NOT EXISTS kb_doc_version_exists BEFORE UPDATE OF current_version ON kb_doc
  WHEN NOT EXISTS (SELECT 1 FROM kb_version v WHERE v.doc_id = NEW.doc_id AND v.version = NEW.current_version)
  BEGIN SELECT RAISE(ABORT, 'kb_doc.current_version must point at an existing version'); END;
"""


def migrate(con):
    for t, c, decl in MIGRATIONS:
        if c not in [r[1] for r in con.execute(f"PRAGMA table_info({t})")]:
            con.execute(f"ALTER TABLE {t} ADD COLUMN {c} {decl}")
    con.executescript(GUARDS)
    con.commit()


def kb_connect(db):
    con = connect(Path(db))
    migrate(con)
    return con


def supersede_outdated(con, doc_id, cv, now, by=None):
    """Open proposals made for an older version can never be accepted: close them (they are rebuilt from the new base)."""
    con.execute("UPDATE kb_proposal SET status='superseded', decided_at=?, superseded_by=?, decision_reason=? "
                "WHERE doc_id=? AND status='open' AND base_version<>?", (now, by, f"document moved on to v{cv}", doc_id, cv))


def upsert_doc(con, doc_id, kind, subject, title, facts, body, links, now, source="build", made=None):
    fh = h(facts)
    row = con.execute("SELECT current_version FROM kb_doc WHERE doc_id=?", (doc_id,)).fetchone()
    if not row:
        con.execute("INSERT INTO kb_doc(doc_id,kind,subject,title,status,current_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (doc_id, kind, subject, title, "draft", 1, now, now))
        con.execute("INSERT INTO kb_version(doc_id,version,body_md,facts_json,facts_hash,author,reason,created_at,facts_made) VALUES (?,?,?,?,?,?,?,?,?)",
                    (doc_id, 1, body, json.dumps(facts, ensure_ascii=False, sort_keys=True), fh, "generator", "first version", now, made))
        res = "created"
    else:
        cv = row["current_version"]
        cur = con.execute("SELECT body_md,facts_json,facts_hash FROM kb_version WHERE doc_id=? AND version=?", (doc_id, cv)).fetchone()
        supersede_outdated(con, doc_id, cv, now)
        if cur["facts_hash"] == fh or h(norm_facts(json.loads(cur["facts_json"]))) == fh:
            res = "same"
            # the facts are back to the current version (or only their order differed): open proposals are moot
            con.execute("UPDATE kb_proposal SET status='superseded', decided_at=?, decision_reason='facts equal the current version again' "
                        "WHERE doc_id=? AND status='open' AND source=?", (now, doc_id, source))
        elif con.execute("SELECT 1 FROM kb_proposal WHERE doc_id=? AND status='open' AND new_facts_hash=? AND base_version=? AND source=?",
                         (doc_id, fh, cv, source)).fetchone():
            res = "proposed (already open)"
        else:
            nid = (con.execute("SELECT COALESCE(MAX(proposal_id),0)+1 FROM kb_proposal").fetchone()[0])
            con.execute("UPDATE kb_proposal SET status='superseded', decided_at=?, superseded_by=?, decision_reason='newer facts' "
                        "WHERE doc_id=? AND status='open' AND source=?", (now, nid, doc_id, source))
            new_md = carry_human(body, cur["body_md"])
            changes = fact_changes(json.loads(cur["facts_json"]), facts)
            diff = "".join(difflib.unified_diff(cur["body_md"].splitlines(keepends=True), new_md.splitlines(keepends=True),
                                                f"{doc_id} v{cv}", f"{doc_id} proposed", n=1))
            con.execute("INSERT INTO kb_proposal(proposal_id,doc_id,base_version,trigger,changes_json,diff,new_body_md,new_facts_json,new_facts_hash,status,created_at,source,input_made) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (nid, doc_id, cv, trigger_of(changes), json.dumps(changes, ensure_ascii=False, default=str),
                                                          diff, new_md, json.dumps(facts, ensure_ascii=False, sort_keys=True), fh, "open", now, source, made))
            res = "proposed"
    if source == "build":
        con.execute("UPDATE kb_doc SET last_seen=? WHERE doc_id=?", (made or now, doc_id))
    con.execute("DELETE FROM kb_link WHERE doc_id=?", (doc_id,))
    con.executemany("INSERT OR IGNORE INTO kb_link(doc_id,ref,rel) VALUES (?,?,?)", [(doc_id, r, rel) for r, rel in links])
    return res


def cmd_build(a):
    D = json.loads(Path(a.pi).read_text(encoding="utf-8"))
    sim = json.loads(Path(a.simulate).read_text(encoding="utf-8")) if a.simulate else {}
    if sim:
        if Path(a.db).resolve() == Path(DB_PATH).resolve() and not a.allow_real_db:
            print("kb build --simulate writes proposals: use --db <a copy of ops.db> (or --allow-real-db; they are marked source=simulate)")
            return 2
        apply_sim(D, sim)
    con = kb_connect(a.db)
    now, made = now_iso(), D.get("made")
    src = "simulate" if sim else "build"
    stats = {}
    for area in sorted(D["areas"]):
        F = frs_facts(D, area, sim)
        links = [(f"feature:{area}", "spec_of")] + [(f["id"], "covers") for f in F["F"]] + \
                [(f"gate:{g['name']}", "gated_by") for g in F["gates"]] + [(f"bug:{b}", "risk") for b in F["bugs"]] + \
                [(f"pr:{n}", "changes") for n in F["open_prs"]]
        r = upsert_doc(con, f"frs:{area}", "frs", f"feature:{area}", f"FRS · {F['title']}", F, frs_body(F, made), links, now, src, made)
        stats[r] = stats.get(r, 0) + 1
    open_prs = sorted((n for n, x in D["prs"].items() if x.get("st") == "open" and x.get("f")), key=int, reverse=True)[:MAX_RFC]
    # and the PRs of the newest final release (release knowledge for later bug / error analysis)
    finals = {t for x in D["prs"].values() for t in x.get("rel") or [] if re.fullmatch(r"v\d+\.\d+\.\d+(\.post\d+)?", t)}
    newest = max(finals, key=lambda t: tuple(int(x) for x in re.findall(r"\d+", t)), default=None)
    rel_prs = [n for n, x in D["prs"].items() if newest and newest in (x.get("rel") or []) and x.get("f")]
    for n in sorted(set(open_prs) | set(rel_prs) | set(a.pr or []), key=int):
        if n not in D["prs"]:
            continue
        R = rfc_facts(D, n)
        links = [(f"pr:{n}", "about")] + [(f"feature:{x}", "changes") for x in R["areas"]] + [(f, "covers") for f in R["F"]] + \
                [(f"gate:{g['name']}", "gated_by") for g in R["gates"]] + [(f"bug:{s}", "analyses") for s in R["sigs"]]
        r = upsert_doc(con, f"rfc:{n}", "rfc", f"pr:{n}", f"RFC · #{n} {R['title'] or ''}", R, rfc_body(R, made), links, now, src, made)
        stats[r] = stats.get(r, 0) + 1
    # bug / error analysis rows (backward direction): failure signature -> suspect PRs
    for sig, b in D["bugs"].items():
        sus = []
        for bk in b.get("b") or []:
            B = D["builds"].get(bk) or {}
            for n in B.get("pr") or []:
                _, _, code, areas, _ = pr_model(D, n)
                sus.append(dict(pr=n, commit=B.get("sha"), features=areas, functions=sorted({x for f in code for x in f[4]})[:6], why=bk))
        con.execute("INSERT INTO kb_analysis(ref,summary,suspects_json,updated_at) VALUES (?,?,?,?) ON CONFLICT(ref) DO UPDATE SET "
                    "summary=excluded.summary, suspects_json=excluded.suspects_json, updated_at=excluded.updated_at",
                    (f"bug:{sig}", f"{b.get('t')} · {b.get('n') or 0} jobs in 30 days · {b.get('line') or ''}", json.dumps(sus[:30], ensure_ascii=False), now))
    con.commit()
    print("kb build:", ", ".join(f"{k} {v}" for k, v in sorted(stats.items())),
          "· open proposals", con.execute("SELECT COUNT(*) FROM kb_proposal WHERE status='open'").fetchone()[0],
          "· analyses", con.execute("SELECT COUNT(*) FROM kb_analysis").fetchone()[0], "· db", Path(a.db).name)
    return 0


def decide(a, accept):
    con = kb_connect(a.db)
    con.isolation_level = None
    con.execute("BEGIN IMMEDIATE")          # one decision at a time: no accept + reject race
    try:
        p = con.execute("SELECT * FROM kb_proposal WHERE proposal_id=?", (a.id,)).fetchone()
        if not p or p["status"] != "open":
            con.execute("ROLLBACK"); print("no open proposal", a.id); return 1
        if accept and p["source"] == "simulate" and not getattr(a, "allow_simulated", False):
            con.execute("ROLLBACK"); print(f"proposal {a.id} comes from --simulate: not accepted (use --allow-simulated on a copy)"); return 1
        now, by = now_iso(), getattr(a, "by", None) or "unspecified"
        if accept:
            cv = con.execute("SELECT current_version FROM kb_doc WHERE doc_id=?", (p["doc_id"],)).fetchone()[0]
            if cv != p["base_version"]:
                supersede_outdated(con, p["doc_id"], cv, now)
                con.execute("COMMIT")
                print(f"the document moved on (v{cv}, proposal is for v{p['base_version']}): proposal closed as superseded; run build to get a new one"); return 1
            con.execute("INSERT INTO kb_version(doc_id,version,body_md,facts_json,facts_hash,author,reason,created_at,proposal_id,decided_by,facts_made) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (p["doc_id"], cv + 1, p["new_body_md"], p["new_facts_json"], p["new_facts_hash"], "generator",
                         f"accepted proposal {a.id} ({p['trigger']})" + (f": {a.reason}" if a.reason else ""), now, a.id, by, p["input_made"]))
            con.execute("UPDATE kb_doc SET current_version=?, updated_at=? WHERE doc_id=?", (cv + 1, now, p["doc_id"]))
        cur = con.execute("UPDATE kb_proposal SET status=?, decided_at=?, decided_by=?, decision_reason=? WHERE proposal_id=? AND status='open'",
                          ("accepted" if accept else "rejected", now, by, a.reason, a.id))
        if cur.rowcount != 1:
            con.execute("ROLLBACK"); print("proposal", a.id, "was decided by someone else meanwhile"); return 1
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    print(("accepted" if accept else "rejected"), "proposal", a.id, "for", p["doc_id"], f"(by {by})")
    return 0


def cmd_edit(a):
    con = kb_connect(a.db)
    d = con.execute("SELECT current_version FROM kb_doc WHERE doc_id=?", (a.doc,)).fetchone()
    if not d:
        print("no document", a.doc); return 1
    cv = d[0]
    cur = con.execute("SELECT body_md,facts_json,facts_hash,facts_made FROM kb_version WHERE doc_id=? AND version=?", (a.doc, cv)).fetchone()
    body = Path(a.file).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if not body.strip() or not re.search(r"^# \S", body, re.M):
        print("edit refused: the file is empty or has no '# title' line"); return 1
    old, new = sections(cur["body_md"]), sections(body)
    changed = [k for k in old if k not in EDITABLE and k != "_" and new.get(k, None) != old[k]]
    if changed and not a.force:
        print("edit refused: these generated sections changed and would be lost at the next accepted proposal: "
              + "; ".join(changed) + ". Put your text in an '(edit)' section or a new '## …' section (kept), or use --force.")
        return 1
    now = now_iso()
    supersede_outdated(con, a.doc, cv + 1, now)
    con.execute("INSERT INTO kb_version(doc_id,version,body_md,facts_json,facts_hash,author,reason,created_at,decided_by,facts_made) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (a.doc, cv + 1, body, cur["facts_json"], cur["facts_hash"], "human", a.reason or "edited", now, a.by, cur["facts_made"]))
    con.execute("UPDATE kb_doc SET current_version=?, updated_at=?, status='reviewed' WHERE doc_id=?", (cv + 1, now, a.doc))
    con.commit()
    print(f"{a.doc}: v{cv + 1} saved (human, by {a.by})")
    return 0


def export(db):
    con = kb_connect(db)
    docs = {}
    for d in con.execute("SELECT * FROM kb_doc ORDER BY doc_id"):
        v = con.execute("SELECT body_md,author,created_at,facts_made FROM kb_version WHERE doc_id=? AND version=?", (d["doc_id"], d["current_version"])).fetchone()
        docs[d["doc_id"]] = dict(kind=d["kind"], subject=d["subject"], title=d["title"], status=d["status"], v=d["current_version"], body=v["body_md"],
                                 facts_made=v["facts_made"], last_seen=d["last_seen"],
                                 versions=[[r["version"], r["created_at"], r["author"], r["reason"]] for r in con.execute(
                                     "SELECT version,created_at,author,reason FROM kb_version WHERE doc_id=? ORDER BY version DESC", (d["doc_id"],))],
                                 proposals=[dict(id=r["proposal_id"], base=r["base_version"], trigger=r["trigger"], at=r["created_at"], source=r["source"],
                                                 changes=json.loads(r["changes_json"])[:30], diff=r["diff"][:12000]) for r in con.execute(
                                     "SELECT * FROM kb_proposal WHERE doc_id=? AND status='open' ORDER BY proposal_id", (d["doc_id"],))],
                                 links=[[r["ref"], r["rel"]] for r in con.execute("SELECT ref,rel FROM kb_link WHERE doc_id=?", (d["doc_id"],))])
    analyses = {r["ref"]: dict(summary=r["summary"], n=len(json.loads(r["suspects_json"]))) for r in con.execute("SELECT * FROM kb_analysis")}
    last = con.execute("SELECT MAX(last_seen) FROM kb_doc").fetchone()[0]
    return dict(made=now_iso(), facts_made=last, docs=docs, analyses=analyses)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(DB_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--pi", default=str(PI)); b.add_argument("--simulate"); b.add_argument("--pr", nargs="*")
    b.add_argument("--allow-real-db", action="store_true", help="allow --simulate on the real ops.db (proposals are marked source=simulate)")
    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("doc"); s.add_argument("--version", type=int)
    d = sub.add_parser("diff"); d.add_argument("id", type=int)
    for name in ("accept", "reject"):
        x = sub.add_parser(name); x.add_argument("id", type=int); x.add_argument("--reason")
        x.add_argument("--by", default=os.environ.get("OPS_KB_REVIEWER") or "unspecified", help="who decides (e.g. a GitHub handle); default $OPS_KB_REVIEWER")
        x.add_argument("--allow-simulated", action="store_true")
    e = sub.add_parser("edit"); e.add_argument("doc"); e.add_argument("--file", required=True); e.add_argument("--reason")
    e.add_argument("--by", default=os.environ.get("OPS_KB_REVIEWER") or "unspecified"); e.add_argument("--force", action="store_true")
    o = sub.add_parser("export"); o.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd in ("accept", "reject"):
        return decide(a, a.cmd == "accept")
    if a.cmd == "edit":
        return cmd_edit(a)
    con = kb_connect(a.db)
    if a.cmd == "list":
        for r in con.execute("SELECT d.doc_id,d.kind,d.current_version,d.status,(SELECT COUNT(*) FROM kb_proposal p WHERE p.doc_id=d.doc_id AND p.status='open') o FROM kb_doc d ORDER BY d.kind,d.doc_id"):
            print(f"{r['doc_id']:24} {r['kind']}  v{r['current_version']}  {r['status']:8} open proposals {r['o']}")
        for r in con.execute("SELECT * FROM v_kb_open_proposals"):
            print(f"proposal {r['proposal_id']}: {r['doc_id']} from v{r['base_version']} ({r['trigger']}, {r['created_at']})")
    elif a.cmd == "show":
        d = con.execute("SELECT current_version FROM kb_doc WHERE doc_id=?", (a.doc,)).fetchone()
        r = d and con.execute("SELECT body_md FROM kb_version WHERE doc_id=? AND version=?", (a.doc, a.version or d[0])).fetchone()
        if not r:
            print("no document / version", a.doc, a.version or ""); return 1
        print(r[0])
    elif a.cmd == "diff":
        p = con.execute("SELECT * FROM kb_proposal WHERE proposal_id=?", (a.id,)).fetchone()
        if not p:
            print("no proposal", a.id); return 1
        print(json.dumps(json.loads(p["changes_json"]), ensure_ascii=False, indent=1)); print(p["diff"])
    elif a.cmd == "export":
        out = json.dumps(export(a.db), ensure_ascii=False, separators=(",", ":"))
        if a.out:
            Path(a.out).write_text(out, encoding="utf-8")
        else:
            sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
