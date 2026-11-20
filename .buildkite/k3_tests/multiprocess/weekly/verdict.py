#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verdict for the weekly multiprocess full suite.

The list of required jobs is computed from pipeline.yml itself: every
command step whose `if` is true for a weekly build, with each matrix
expanded. Nobody has to keep a second list of tests in sync.

A required job counts as passed only when its own run recorded "passed"
(weekly/record-result.sh). Everything else fails the weekly run:

  failed   the job ran and exited non-zero (also on its last retry)
  missing  no record: never scheduled, timed out, agent lost, canceled
  skipped  preflight skip (unsupported engine/workload) that is not listed
           in weekly/allowed-skips.txt

A job that passed only after a retry still passes, but is listed as flaky.

Outputs: weekly_verdict.json, weekly_verdict.md, a build annotation, and the
build meta-data key `weekly-verdict` (compact JSON) for the dashboard.

Local check, without Buildkite:
  python3 verdict.py --list               # print the required job labels
  python3 verdict.py --results r.json     # evaluate saved results
"""

# Future
from __future__ import annotations

# Standard
from pathlib import Path
from typing import cast
import argparse
import io
import itertools
import json
import os
import re
import subprocess
import sys

# Third Party
import yaml

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent / "pipeline.yml"
ALLOWED_SKIPS = HERE / "allowed-skips.txt"
RESULT_PREFIX = "weekly-result-"

# Env the weekly schedule sets. VERIFY_AND_PIN_* are refused by
# upload-pipeline.sh, so they are always unset here.
WEEKLY_ENV = {"WEEKLY_FULL": "true"}

EMOJI_PREFIX = re.compile(r"^(:[a-z0-9_+-]+:\s*)+")
CLAUSE = re.compile(
    r'^build\.env\("(?P<var>[A-Z0-9_]+)"\)\s*'
    r'(?:(?P<rop>=~|!~)\s*/(?P<re>.*)/|(?P<sop>==|!=)\s*"(?P<str>[^"]*)")$'
)


def normalize_label(label: str) -> str:
    return EMOJI_PREFIX.sub("", label or "").strip()


def eval_if(expr: str | None, env: dict[str, str]) -> bool:
    """Evaluate the small subset of Buildkite conditionals this file uses.

    Supports clauses `build.env("X") =~ /re/`, `!~ /re/`, `== "s"`,
    `!= "s"`, joined by `&&` and `||` (no parentheses). Anything else raises,
    so a new kind of condition breaks the verdict loudly instead of silently
    dropping jobs from the required list.
    """
    if not expr:
        return True
    any_true = False
    for alternative in expr.split("||"):
        all_true = True
        for raw in alternative.split("&&"):
            clause = raw.strip()
            m = CLAUSE.match(clause)
            if not m:
                raise ValueError(f"unsupported `if` clause: {clause!r}")
            value = env.get(m["var"], "")
            if m["rop"]:
                hit = re.search(m["re"], value) is not None
                ok = hit if m["rop"] == "=~" else not hit
            else:
                ok = (value == m["str"]) if m["sop"] == "==" else (value != m["str"])
            all_true = all_true and ok
        any_true = any_true or all_true
    return any_true


def matrix_combinations(matrix) -> list[dict[str, str]]:
    if matrix is None:
        return [{}]
    if isinstance(matrix, list):
        return [{"": str(v)} for v in matrix]
    setup = matrix.get("setup", {})
    if isinstance(setup, list):
        combos = [{"": str(v)} for v in setup]
    else:
        keys = list(setup)
        combos = [
            dict(zip(keys, map(str, values), strict=True))
            for values in itertools.product(*(setup[k] for k in keys))
        ]
    for adj in matrix.get("adjustments", []) or []:
        target = {k: str(v) for k, v in (adj.get("with") or {}).items()}
        if adj.get("skip"):
            combos = [c for c in combos if c != target]
        elif target not in combos:
            combos.append(target)
    return combos


def render_label(label: str, combo: dict[str, str]) -> str:
    out = label
    for key, value in combo.items():
        token = "{{matrix}}" if key == "" else "{{matrix.%s}}" % key
        out = out.replace(token, value)
    return normalize_label(out)


def required_jobs(pipeline_path: Path, env: dict[str, str]) -> list[str]:
    doc = yaml.safe_load(pipeline_path.read_text())
    labels: list[str] = []

    def visit(steps, parent_ok: bool):
        for step in steps or []:
            if not isinstance(step, dict):
                continue  # "wait" shorthand
            ok = parent_ok and eval_if(step.get("if"), env)
            if "group" in step:
                visit(step.get("steps"), ok)
                continue
            if not ok or step.get("skip") or "command" not in step:
                continue  # wait/block/trigger steps or excluded steps
            if step.get("key") == "weekly-verdict":
                continue
            label = step.get("label") or step.get("name") or step["command"]
            if int(step.get("parallelism") or 1) > 1:
                # Shards share one label, so one passing shard would hide a
                # missing or failed one. Refuse until results are keyed per
                # shard (BUILDKITE_PARALLEL_JOB).
                raise ValueError(
                    f"parallelism > 1 is not supported by the weekly verdict: {label!r}"
                )
            for combo in matrix_combinations(step.get("matrix")):
                labels.append(render_label(label, combo))

    visit(doc.get("steps"), True)
    duplicates = sorted({x for x in labels if labels.count(x) > 1})
    if duplicates:
        # Same reason: two jobs with one label cannot be told apart.
        raise ValueError(f"duplicate job labels in a weekly build: {duplicates}")
    return labels


def load_allowed_skips(path: Path) -> set[str]:
    allowed = set()
    if path.exists():
        for line in path.read_text().splitlines():
            entry = line.split("#", 1)[0].strip()
            if entry:
                allowed.add(normalize_label(entry))
    return allowed


def agent(*args: str) -> str:
    return subprocess.run(
        ["buildkite-agent", *args], check=True, capture_output=True, text=True
    ).stdout


def fetch_results() -> list[dict]:
    results = []
    for key in agent("meta-data", "keys").split():
        if key.startswith(RESULT_PREFIX):
            try:
                value = json.loads(agent("meta-data", "get", key))
            except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
                print(f"warning: cannot read {key}: {exc}", file=sys.stderr)
                continue
            value["job_id"] = key[len(RESULT_PREFIX) :]
            results.append(value)
    return results


def evaluate(required: list[str], results: list[dict], allowed: set[str]) -> dict:
    by_label: dict[str, list[dict]] = {}
    for r in results:
        by_label.setdefault(normalize_label(r.get("label", "")), []).append(r)

    rows = []
    seen = set()
    for label in sorted(set(required)):
        seen.add(label)
        attempts = sorted(by_label.get(label, []), key=lambda r: r.get("retry", 0))
        statuses = [a.get("status") for a in attempts]
        if "passed" in statuses:
            retry = min(
                a.get("retry", 0) for a in attempts if a.get("status") == "passed"
            )
            status = "flaky" if retry > 0 or "failed" in statuses else "passed"
        elif "failed" in statuses:
            status = "failed"
        elif "skipped" in statuses:
            status = "allowed_skip" if label in allowed else "skipped"
        else:
            status = "missing"
        reason = (
            next(
                (
                    a.get("reason")
                    for a in reversed(attempts)
                    if a.get("status") == statuses[-1]
                ),
                "",
            )
            if attempts
            else "no result recorded (not run, timed out, lost or canceled)"
        )
        rows.append(
            {
                "label": label,
                "status": status,
                "attempts": len(attempts),
                "reason": reason,
            }
        )

    blocking = [r for r in rows if r["status"] in ("failed", "missing", "skipped")]
    stale_allowed = sorted(
        a
        for a in allowed
        if a in seen
        and any(r["label"] == a and r["status"] in ("passed", "flaky") for r in rows)
    )
    unknown_allowed = sorted(a for a in allowed if a not in seen)
    unexpected = sorted(set(by_label) - seen)
    counts = {
        s: sum(1 for r in rows if r["status"] == s)
        for s in ("passed", "flaky", "failed", "missing", "skipped", "allowed_skip")
    }
    return {
        "verdict": "fail" if blocking else "pass",
        "required": len(rows),
        "counts": counts,
        "jobs": rows,
        "allowed_skips_now_passing": stale_allowed,
        "allowed_skips_not_in_pipeline": unknown_allowed,
        "unexpected_results": unexpected,
        "build": {
            "number": os.environ.get("BUILDKITE_BUILD_NUMBER"),
            "url": os.environ.get("BUILDKITE_BUILD_URL"),
            "commit": os.environ.get("BUILDKITE_COMMIT"),
            "branch": os.environ.get("BUILDKITE_BRANCH"),
            "source": os.environ.get("BUILDKITE_SOURCE"),
        },
    }


ICON = {
    "passed": "✅",
    "flaky": "🟡",
    "failed": "❌",
    "missing": "⛔",
    "skipped": "⏭️",
    "allowed_skip": "⚪",
}


def to_markdown(v: dict) -> str:
    c = v["counts"]
    head = (
        "✅ Weekly full suite PASSED"
        if v["verdict"] == "pass"
        else "❌ Weekly full suite FAILED"
    )
    lines = [
        f"### {head}",
        "",
        f"Required jobs: **{v['required']}** · passed {c['passed']} · "
        f"flaky {c['flaky']} · failed {c['failed']} · "
        f"missing {c['missing']} · skipped {c['skipped']} · "
        f"allowed skips {c['allowed_skip']}",
        "",
    ]
    order = ["failed", "missing", "skipped", "flaky", "allowed_skip"]
    problems = [r for s in order for r in v["jobs"] if r["status"] == s]
    if problems:
        lines += ["| | Job | Status | Attempts | Reason |", "|---|---|---|---|---|"]
        for r in problems:
            lines.append(
                f"| {ICON[r['status']]} | `{r['label']}` | {r['status']} | "
                f"{r['attempts']} | {r['reason']} |"
            )
        lines.append("")
    if v["allowed_skips_now_passing"]:
        lines.append(
            "Remove from allowed-skips.txt (they pass now): "
            + ", ".join(f"`{x}`" for x in v["allowed_skips_now_passing"])
        )
    if v["allowed_skips_not_in_pipeline"]:
        lines.append(
            "allowed-skips.txt entries with no matching job: "
            + ", ".join(f"`{x}`" for x in v["allowed_skips_not_in_pipeline"])
        )
    if v["unexpected_results"]:
        lines.append(
            "Results from jobs that are not in the required list: "
            + ", ".join(f"`{x}`" for x in v["unexpected_results"])
        )
    lines.append("")
    lines.append(
        "Rules: `.buildkite/k3_tests/multiprocess/weekly/README.md`. "
        "Full table: artifact `weekly_verdict.json`."
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--pipeline", type=Path, default=PIPELINE)
    ap.add_argument(
        "--list", action="store_true", help="print required job labels and exit"
    )
    ap.add_argument(
        "--results", type=Path, help="evaluate saved results (JSON list) offline"
    )
    args = ap.parse_args()

    required = required_jobs(args.pipeline, WEEKLY_ENV)
    allowed = load_allowed_skips(ALLOWED_SKIPS)
    if args.list:
        print("\n".join(sorted(required)))
        print(
            f"# {len(required)} required jobs, {len(allowed)} allowed skips",
            file=sys.stderr,
        )
        return 0

    if os.environ.get("WEEKLY_FULL") != "true" and not args.results:
        print("WEEKLY_FULL is not true; nothing to judge", file=sys.stderr)
        return 1

    results = json.loads(args.results.read_text()) if args.results else fetch_results()
    verdict = evaluate(required, results, allowed)
    markdown = to_markdown(verdict)
    Path("weekly_verdict.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8"
    )
    Path("weekly_verdict.md").write_text(markdown, encoding="utf-8")
    cast(io.TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")
    print(markdown)

    if not args.results:
        summary = {
            "verdict": verdict["verdict"],
            "required": verdict["required"],
            **verdict["counts"],
        }
        agent(
            "meta-data",
            "set",
            "weekly-verdict",
            json.dumps(summary, separators=(",", ":")),
        )
        style = "success" if verdict["verdict"] == "pass" else "error"
        subprocess.run(
            [
                "buildkite-agent",
                "annotate",
                "--style",
                style,
                "--context",
                "weekly-verdict",
            ],
            input=markdown,
            text=True,
            check=False,
        )
    return 0 if verdict["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
