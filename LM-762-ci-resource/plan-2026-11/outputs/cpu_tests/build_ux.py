"""UX layer of the Release Desk page (2026-11-24, UX review rounds): design system + decision-first helpers.

Adds, without removing any tab, hash, section or fact:
  - design tokens on .viz-root (spacing 4/8, type scale, radius, elevation, motion; status colours tuned for WCAG AA
    in light and dark) and components with the ux- prefix (status chip, metric card, decision banner, PR chip, gate chip,
    evidence link, table-to-card, empty / unknown / stale / skeleton / error states); showcase at #ux
  - Now · Release Desk: a decision banner on top (runbook phase, verdict with data age, top blocker, next action,
    dev gates that are red with "Find cause", copy link, print view #decision). Old data never shows a green verdict.
  - search / jump box (/): PR number, F-id, gate, release tag, code area, research report
  - keyboard: / search, j / k move in lists, Esc closes; deep link for every Inspector state (#e/pr/N/v3, /back, /docs)
  - History: "Since yesterday" (what changed in the 24 h before each source's own time)
  - Rebase risk: "Rebase now" list (open PRs whose overlap with the last 24 h of merges is p0-p2)
Data: red dev gates -> commits between last green and first red (local clone, approximate) -> uxData.
Runs in build_page.py after build_research.py, before build_i18n.py.
"""
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
import sys  # noqa: E402
sys.path.insert(0, HERE)  # sibling modules also under python -I
PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
CLONE = Path(__file__).resolve().parents[4] / "third_party" / "LMCache"


def git(*a):
    try:
        r = subprocess.run(["git", "-C", str(CLONE), *a], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def page_json(page, sid):
    m = re.search(r'<script id="' + sid + r'" type="application/json">(.*?)</script>', page, re.S)
    return json.loads(m.group(1).replace("<\\/", "</")) if m else {}


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:] if before else page[:i + len(anchor)] + "\n" + block.strip() + page[i + len(anchor):]


def p1_summary():
    """First 30-day window (outputs/P1): the MP-pipeline figures the GPU tab cards quote (review C2 / C5)."""
    d = Path(__file__).resolve().parent.parent / "P1"
    try:
        S = json.loads((d / "build_level_summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    w = None
    for f in (d / "window.json", d / "raw" / "window.json"):
        if f.is_file():
            try:
                w = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass
    return dict(gpu_h=round(S["gpu_min_total_pr"] / 60, 1), retry_gpu_min=round(S["retry_gpu_min_pr"]), cancel_gpu_min=round(S["canceled_gpu_min_pr"]),
                builds=S["pr_builds_total"], prs=S["distinct_prs"], since=(w or {}).get("since", "2026-10-05"), until=(w or {}).get("until", "2026-11-04"))


def pipeline_owners():
    """Owner per CI pipeline file from CODEOWNERS (review C9 / m4: owner source = CODEOWNERS)."""
    try:
        import build_pr_inspector as BPI
        R = BPI.codeowners()
    except Exception:  # noqa: BLE001
        return {}
    files = {"k3-multiprocess-test": ".buildkite/k3_tests/multiprocess/pipeline.yml", "k3-unit-tests": ".buildkite/k3_tests/unit/pipeline.yml",
             "GitHub Actions (CPU)": ".github/workflows/", "Buildkite (all)": ".buildkite/pipeline.yml"}
    return {k: BPI.owners_of([v], R) for k, v in files.items()}


def main():
    page = open(PAGE, encoding="utf-8").read()
    if "PI:JS:END" not in page or "RESEARCH:JS:END" not in page:
        raise SystemExit("build_ux: run build_pr_inspector.py and build_research.py first")
    today = page_json(page, "todayData")
    red = []
    for k in today.get("known_red") or []:
        g_at, r_at = k.get("green_at"), k.get("red_since") or k.get("at")
        commits, why = [], ""
        if g_at and r_at:
            log = git("log", "--first-parent", "--format=%h\t%s", f"--since={g_at.replace(' ', 'T')}:00Z", f"--until={r_at.replace(' ', 'T')}:59Z", "HEAD")
            commits = [ln.split("\t", 1) for ln in log.splitlines() if "\t" in ln][:30]
            if not commits:
                why = "no dev commit between the last green and the first red build in the local clone: likely flaky or infrastructure"
        else:
            why = f"no green build since {k.get('history_from') or '?'} in local data: the commit range is too large to name a PR"
        red.append(dict(pipe=k["slug"], src="known_red", why=why,
                        green=dict(num=k.get("green_num"), sha="", at=(g_at or "").replace(" ", "T") + ("Z" if g_at else ""), url=k.get("green_url"), approx=True),
                        red=dict(num=k.get("number"), sha="", at=(r_at or "").replace(" ", "T") + "Z", url=k.get("url"), approx=True),
                        commits=commits, prs=[int(m) for c in commits for m in re.findall(r"\(#(\d{3,5})\)", c[1])]))
    data = dict(made=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), red=red, p1=p1_summary(), owners=pipeline_owners())
    import ux_ui as UI  # noqa: E402  (CSS + JS, kept apart)
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = put(page, "/* UX:CSS:START */", "/* UX:CSS:END */", UI.CSS, "</style>")
    # round 3 (D_identity 3.8): ONE colour token block, last in <head>; the template's three scoped .viz-root colour blocks go
    he = page.index("</head>")
    hd = page[:he]
    hd = re.sub(r'\n[ \t]*\.viz-root \{\s*color-scheme: light;[^}]*\}', '\n', hd, count=1)
    hd = re.sub(r'\n[ \t]*@media \(prefers-color-scheme: dark\) \{\s*:root:where\(:not\(\[data-theme="light"\]\)\) \.viz-root \{\s*color-scheme: dark;[^}]*\}\s*\}', '\n', hd, count=1)
    hd = re.sub(r'\n[ \t]*:root\[data-theme="dark"\] \.viz-root \{\s*color-scheme: dark;[^}]*\}', '\n', hd, count=1)
    page = hd + page[he:]
    page = re.sub(r'<style id="rd-tokens">.*?</style>\n?', '', page, flags=re.S)
    page = page.replace("</head>", UI.TOKENS.strip() + "\n</head>", 1)
    page = put(page, "<!-- UX:JS:START -->", "<!-- UX:JS:END -->",
               f'<!-- UX:JS:START -->\n<script id="uxData" type="application/json">{blob}</script>\n' + UI.JS.strip().split("\n", 1)[1],
               "<!-- RESEARCH:JS:END -->", before=False)
    open(PAGE, "w", encoding="utf-8").write(page)
    print(f"ux: design system + decision layer · {len(red)} red dev gates "
          f"({', '.join(r['pipe'] + ': ' + (str(len(r['commits'])) + ' commits' if r['commits'] else 'unknown') for r in red)})")


if __name__ == "__main__":
    main()


def sync_p1():
    """Expert review C2: some GPU figures of the first 30-day window were written into older builders as text (3,099 GPU-h,
    9,938 GPU-min retries, p90 288 min, 87 min p50, 518 GPU-min per build). Re-write them from P1/build_level_summary.json,
    after build_i18n (so the English text and the keys / values of the VI dictionary change together)."""
    import re
    f = Path(__file__).resolve().parent.parent / "P1" / "build_level_summary.json"
    if not f.is_file():
        print("ux sync: no P1/build_level_summary.json, figures left as written"); return
    S = json.loads(f.read_text(encoding="utf-8"))
    tot = S["gpu_min_total_pr"]
    rules = [(r"3,099(?=\s?GPU)", f"{round(tot / 60):,}"),
             (r"9,938 (GPU-min|GPU-phút) \(5\.3%\)", lambda m: f"{round(S['retry_gpu_min_pr']):,} {m.group(1)} ({S['retry_gpu_min_pr'] / tot * 100:.1f}%)"),
             (r"p90 288\b", f"p90 {round(S['passed_pr_build_duration_min_p90'])}"),
             (r"\b87(?= (min|phút) p50)", f"{round(S['passed_pr_build_duration_min_p50'])}"),
             (r"\b518(?= → ~3 GPU)", f"{round(S['gpu_min_per_pr_build_p50'])}")]
    page = open(PAGE, encoding="utf-8", newline="").read()
    done = []
    for rx, to in rules:
        page, n = re.subn(rx, to, page)
        done.append(n)
    open(PAGE, "w", encoding="utf-8", newline="").write(page)
    print(f"ux sync: P1 figures re-written from build_level_summary.json {done} (GPU-h {tot / 60:,.1f})")

