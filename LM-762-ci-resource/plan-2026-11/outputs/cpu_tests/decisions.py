"""Every decision verb on the Release & CI page comes from this file (v2, phase P3).

One pure function per decision kind. The first line of each docstring is the rule in one sentence;
build_today.py checks that it equals RULE[verb][0] and shows RULE[verb] in the chip tooltip.
No I/O here: callers pass plain dicts from the local collectors.

Who decides: these are RULE decisions (solid chip). A Trace Agent finding is passed through with by="agent"
(dashed chip) and is never merged into a rule verb.

Inputs used below:
  gates  = {"dco", "quality", "unit", "mp"} -> ok / run / fail / cancel / missing / label   (4 required checks)
  level  = worst clash with a merge of the last 24 h: p0 breaks on rebase · p1 same function · p2 nearby lines
           · p3 same file · p4 no shared code
  review = GitHub reviewDecision (APPROVED / CHANGES_REQUESTED / REVIEW_REQUIRED / None)
"""
import re

# verb -> (EN label, VI label, tone). tone: act = do it now · do = needs a person · ok = can go · info = watch, no action today
VERBS = {
    "cancel": ("CANCEL CI", "HUỶ CI", "act"),
    "block": ("BLOCK", "CHẶN", "act"),
    "triage": ("TRIAGE", "TRIAGE", "act"),
    "fix": ("FIX", "SỬA", "act"),
    "rebase": ("REBASE FIRST", "REBASE TRƯỚC", "do"),
    "merge": ("MERGE", "MERGE", "ok"),
    "full": ("ADD 'full'", "GẮN 'full'", "do"),
    "quarantine": ("QUARANTINE?", "CÁCH LY?", "do"),
    "keep": ("KEEP CI", "GIỮ CI", "info"),
    "review": ("REVIEW", "REVIEW", "info"),
    "red": ("WAIT FIX", "CHỜ SỬA", "info"),
    "dco": ("FIX DCO", "SỬA DCO", "info"),
    "author": ("WAIT AUTHOR", "CHỜ TÁC GIẢ", "info"),
    "watch": ("WATCH", "THEO DÕI", "info"),
    "in": ("IN", "VÀO", "ok"),
    "out": ("OUT", "RA", "act"),
    "needs_test": ("NEEDS TEST", "CẦN TEST", "do"),
    "shipped": ("SHIPPED", "ĐÃ SHIP", "ok"),
    "shipped_fail": ("SHIPPED WITH FAILURES", "SHIP KÈM LỖI", "do"),
    "blocked": ("BLOCKED", "BỊ CHẶN", "act"),
    "no_data": ("NO PUBLISH DATA", "CHƯA CÓ DỮ LIỆU PUBLISH", "info"),
    "publishing": ("PUBLISHING", "ĐANG PUBLISH", "info"),
}
# the Today inbox, most urgent first: running GPU waste, release blockers, new red on dev, then PR decisions
TODAY = ["cancel", "block", "triage", "fix", "rebase", "merge", "full", "quarantine"]
LVN = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "p4": 4}

RULE = {
    "cancel": ["CI is running while DCO already failed or a merge of the last 24 h changed the same code (P0/P1).",
               "CI đang chạy trong khi DCO đã fail hoặc một merge trong 24 giờ qua đã đổi cùng đoạn code (P0/P1)."],
    "keep": ["CI is running and no merge of the last 24 h clashed with it above nearby lines (P2–P4).",
             "CI đang chạy và không merge nào trong 24 giờ qua đụng nặng hơn mức gần dòng (P2–P4)."],
    "dco": ["DCO failed on a PR without running CI: the author must sign off before review.",
            "DCO fail ở PR không có CI đang chạy: tác giả phải sign-off trước khi review."],
    "rebase": ["A merge of the last 24 h changed the same code (P0 breaks on rebase, P1 same function).",
               "Một merge trong 24 giờ qua đã đổi cùng đoạn code (P0 hỏng khi rebase, P1 cùng hàm)."],
    "red": ["Check code quality or k3-unit-tests is red: wait for the author's fix push.",
            "Check code quality hoặc k3-unit-tests đang đỏ: chờ tác giả push sửa."],
    "merge": ["All 4 required checks are green, the PR is approved and no P0/P1 clash.",
              "Đủ 4 check bắt buộc xanh, PR đã duyệt và không đụng P0/P1."],
    "full": ["The PR is approved and the MP suite has not run because the 'full' label is missing.",
             "PR đã duyệt và bộ MP chưa chạy vì thiếu nhãn 'full'."],
    "author": ["A reviewer requested changes: the author acts next.",
               "Reviewer đã yêu cầu sửa: tác giả làm tiếp."],
    "review": ["No rule above applies: the PR waits for a review.",
               "Không luật nào ở trên khớp: PR chờ review."],
    "triage": ["The newest finished dev build of a pipeline failed and the build before it (another commit) passed.",
               "Build dev xong gần nhất của một pipeline fail trong khi build trước đó (commit khác) pass."],
    "watch": ["The pipeline was already red before its newest dev build: known red, no new cause.",
              "Pipeline đã đỏ từ trước build dev mới nhất: đỏ đã biết, không có nguyên nhân mới."],
    "quarantine": ["In the last 24 h one commit failed and then passed the same pipeline or job, and it is not a known flaky workload.",
                   "Trong 24 giờ qua một commit fail rồi pass cùng pipeline hoặc job, và không phải workload flaky đã biết."],
    "block": ["The Trace Agent marked a PR 'blocks-release' for the current or next version and its fix is not merged.",
              "Trace Agent đánh dấu một PR 'blocks-release' cho version hiện tại hoặc tới và bản sửa chưa merge."],
    "out": ["A PR of the item is not merged into dev, so it cannot ship in this release.",
            "Một PR của mục chưa merge vào dev, nên không thể ship trong release này."],
    "needs_test": ["A PR of the item needs the MP suite but has no green k3-multiprocess-test build on the PR in local data.",
                   "Một PR của mục cần bộ MP nhưng chưa có build k3-multiprocess-test xanh trên PR trong dữ liệu local."],
    "in": ["Every PR of the item is merged into dev and each one that needs the MP suite has a green MP build.",
           "Mọi PR của mục đã merge vào dev và PR nào cần bộ MP đều có build MP xanh."],
    "blocked": ["A 'blocks-release' finding of the Trace Agent for this tag has no merged fix.",
                "Một kết quả 'blocks-release' của Trace Agent cho tag này chưa có bản sửa đã merge."],
    "shipped_fail": ["The tag is published, but its newest publish.yml run did not end green or a blocker needed a later fix.",
                     "Tag đã publish, nhưng run publish.yml mới nhất không xanh hoặc có blocker phải sửa sau."],
    "shipped": ["The tag is published, its newest publish.yml run is green and it has no blocks-release finding.",
                "Tag đã publish, run publish.yml mới nhất xanh và không có kết quả 'blocks-release'."],
    "publishing": ["A publish.yml run of this tag exists in the snapshot but has not finished.",
                   "Snapshot có run publish.yml của tag này nhưng run chưa xong."],
    "no_data": ["No finished publish.yml run of this tag is in the local snapshot.",
                "Snapshot local không có run publish.yml đã xong nào của tag này."],
    "fix": ["A carry-over blocker in RELEASE_PREP is not done, or the newest publish.yml run of the latest or stable tag failed or was cancelled.",
            "Một blocker mang sang trong RELEASE_PREP chưa xong, hoặc run publish.yml mới nhất của tag mới nhất / stable bị fail hoặc bị huỷ."],
}


def _d(verb, why, short, **kw):
    """One decision: verb key, long reason [en, vi] (Rebase risk tab), short reason [en, vi] (≤ 8 words, Today + card)."""
    return dict(verb=verb, why=why, short=short, rule=verb, **kw)


def _clash_m(clash):
    return f"#{clash[0]['m']}" if clash else "a merge"


# ---------------------------------------------------------------- PR with CI running
def cancel_ci(gates, level):
    """CI is running while DCO already failed or a merge of the last 24 h changed the same code (P0/P1)."""
    return gates.get("dco") == "fail" or level in ("p0", "p1")


def keep_ci(gates, level):
    """CI is running and no merge of the last 24 h clashed with it above nearby lines (P2–P4)."""
    return not cancel_ci(gates, level)


def pr_running(gates, level, clash=()):
    """Decision for an open PR whose CI is running: cancel_ci, else keep_ci."""
    if gates.get("dco") == "fail":
        return _d("cancel", ["DCO failed: the PR must be pushed again anyway.", "DCO fail: đằng nào PR cũng phải push lại."],
                  ["DCO failed; PR must be pushed again", "DCO fail; PR phải push lại"])
    if cancel_ci(gates, level):
        m, L = _clash_m(clash), level.upper()
        return _d("cancel", ["Tests code that the merge changed. Rebase, then one run.", "Đang test code đã bị merge thay đổi. Rebase rồi chạy một lần."],
                  [f"{L} clash with {m}: tests stale code", f"Đụng {L} với {m}: đang test code cũ"])
    return _d("keep", ["No clash with the merges, or only nearby lines: let it finish.", "Không đụng các merge, hoặc chỉ gần dòng: để chạy xong."],
              ["No real clash; let it finish", "Không đụng thật; để chạy xong"])


# ---------------------------------------------------------------- PR without running CI (precedence = order of the checks below)
def dco_fail(gates):
    """DCO failed on a PR without running CI: the author must sign off before review."""
    return gates.get("dco") == "fail"


def rebase_first(level):
    """A merge of the last 24 h changed the same code (P0 breaks on rebase, P1 same function)."""
    return level in ("p0", "p1")


def wait_fix(gates):
    """Check code quality or k3-unit-tests is red: wait for the author's fix push."""
    return gates.get("quality") == "fail" or gates.get("unit") == "fail"


def merge(gates, level, review):
    """All 4 required checks are green, the PR is approved and no P0/P1 clash."""
    return review == "APPROVED" and all(v == "ok" for v in gates.values()) and level not in ("p0", "p1")


def add_full(gates, review):
    """The PR is approved and the MP suite has not run because the 'full' label is missing."""
    return review == "APPROVED" and gates.get("mp") == "label"


def wait_author(review):
    """A reviewer requested changes: the author acts next."""
    return review == "CHANGES_REQUESTED"


def pr_waiting(gates, level, review, clash=()):
    """Decision for an open PR without running CI, first match wins:
    dco_fail → rebase_first → wait_fix → merge → add_full → wait_author → review."""
    near = level in ("p2", "p3")
    if dco_fail(gates):
        return _d("dco", ["Sign-off missing. Ask the author to fix DCO before review.", "Thiếu sign-off. Nhờ tác giả sửa DCO trước khi review."],
                  ["Sign-off missing; author fixes DCO", "Thiếu sign-off; tác giả sửa DCO"])
    if rebase_first(level):
        m, L = _clash_m(clash), level.upper()
        return _d("rebase", ["A merge changed the same code. Rebase before review / 'full'.", "Một merge đã đổi cùng đoạn code. Rebase trước khi review / gắn 'full'."],
                  [f"{L} clash with {m}; rebase before review", f"Đụng {L} với {m}; rebase trước review"])
    if wait_fix(gates):
        return _d("red", ["A required check is red. Wait for a fix push.", "Một check bắt buộc đang đỏ. Chờ push sửa."],
                  ["Required check red; wait for fix", "Check bắt buộc đỏ; chờ bản sửa"])
    if merge(gates, level, review):
        return _d("merge", ["All 4 checks green and approved. Rebase once first (nearby edits)." if near else "All 4 checks green and approved.",
                            "Đủ 4 check xanh và đã duyệt. Rebase một lần trước (sửa gần nhau)." if near else "Đủ 4 check xanh và đã duyệt."],
                  ["4 checks green, approved; rebase once" if near else "4 checks green, approved, no clash",
                   "4 check xanh, đã duyệt; rebase một lần" if near else "4 check xanh, đã duyệt, không đụng"])
    if add_full(gates, review):
        return _d("full", ["Approved; MP suite has not run. Add 'full' to start it.", "Đã duyệt; bộ MP chưa chạy. Gắn 'full' để chạy."],
                  ["Approved; MP suite not run yet", "Đã duyệt; bộ MP chưa chạy"])
    if wait_author(review):
        return _d("author", ["Changes requested: waiting for the author.", "Đã yêu cầu sửa: chờ tác giả."],
                  ["Changes requested; waiting for author", "Đã yêu cầu sửa; chờ tác giả"])
    cpu_ok = gates.get("dco") == "ok" and gates.get("quality") == "ok"
    why = ["CPU checks green. Review now; add 'full' when it looks good." if cpu_ok else "Waiting for checks to finish, then review.",
           "Check CPU xanh. Review ngay; gắn 'full' khi ổn." if cpu_ok else "Chờ check chạy xong rồi review."]
    if near:
        why = [why[0] + " Rebase once before merge.", why[1] + " Rebase một lần trước merge."]
    return _d("review", why, ["CPU checks green; review now" if cpu_ok else "Checks still running; review after",
                              "Check CPU xanh; review ngay" if cpu_ok else "Check còn chạy; review sau"])


# ---------------------------------------------------------------- Rebase risk section A: action per (clash level × PR state)
CLASH_TEXT = {
    "fix": ["Fix calls to the removed symbol, then rebase.", "Sửa chỗ gọi symbol đã xoá, rồi rebase."],
    "stale": ["Tests stale code. Rebase, re-run once.", "Đang test code cũ. Rebase, chạy lại 1 lần."],
    "predates": ["Green CI predates the merge. Rebase, re-run.", "CI xanh có trước merge. Rebase, chạy lại."],
    "nextpush": ["Rebase in the next fix push.", "Rebase trong lần push sửa tới."],
    "nofull": ["No 'full', no merge. Rebase first.", "Chưa gắn 'full', chưa merge. Rebase trước."],
    "finish": ["Let it finish. Rebase before merge.", "Để chạy xong. Rebase trước merge."],
    "diffs": ["Rebase before 'full'. Read both diffs.", "Rebase trước khi gắn 'full'. Đọc cả hai diff."],
    "once": ["Rebase once before merge.", "Rebase một lần trước merge."],
    "none": ["No action.", "Không cần làm gì."],
    "resume": ["Rebase when work resumes.", "Rebase khi làm tiếp."]}


def clash_action(level, sub, inactive=False):
    """Action for one open PR from its worst clash level and its state (Rebase risk matrix).
    Returns (verb, [en, vi]); verbs: stop / block / hold / rebase / keep / later / go / idle."""
    if inactive:
        return ("idle", CLASH_TEXT["resume"]) if level != "p4" else ("go", CLASH_TEXT["none"])
    run, ready, red = sub == "ci_run", sub == "ready", sub == "ci_fail"
    T = CLASH_TEXT
    if level == "p0":
        return ("stop" if run else "block" if ready else "rebase"), T["fix"]
    if level == "p1":
        return ("stop", T["stale"]) if run else ("block", T["predates"]) if ready else ("rebase", T["nextpush"]) if red else ("hold", T["nofull"])
    if level == "p2":
        return ("keep", T["finish"]) if run else ("rebase", T["nextpush"]) if red else ("later", T["diffs"])
    if level == "p3":
        return ("keep", T["finish"]) if run else ("later", T["once"])
    return "go", T["none"]


# ---------------------------------------------------------------- dev health
def new_red(newest, previous):
    """The newest finished dev build of a pipeline failed and the build before it (another commit) passed."""
    return bool(newest) and newest.get("state") == "failed" and bool(previous) and previous.get("state") == "passed"


def known_red(newest, previous):
    """The pipeline was already red before its newest dev build: known red, no new cause."""
    return bool(newest) and newest.get("state") == "failed" and not new_red(newest, previous)


def dev_pipeline(builds):
    """Decision for one pipeline from its dev builds (any order): triage on new_red, watch on known_red, else None.
    Returns the decision plus the newest failed build and the PR named in its commit message."""
    fin = sorted((b for b in builds if b.get("state") in ("passed", "failed")), key=lambda b: b.get("created_at") or "", reverse=True)
    if not fin or fin[0].get("state") != "failed":
        return None
    newest = fin[0]
    prev = next((b for b in fin[1:] if b.get("commit") != newest.get("commit")), None)
    m = re.search(r"\(#(\d+)\)\s*$", (newest.get("message") or "").splitlines()[0] if newest.get("message") else "")
    pr = int(m.group(1)) if m else None
    after = f" after #{pr}" if pr else ""
    if new_red(newest, prev):
        return _d("triage", ["New red on dev: the build before passed.", "Đỏ mới trên dev: build trước đó pass."],
                  [f"New red{after}; build before passed", f"Đỏ mới{(' sau #' + str(pr)) if pr else ''}; build trước pass"],
                  build=newest, pr=pr)
    return _d("watch", ["Red before this build too: known red.", "Đã đỏ từ trước build này: đỏ đã biết."],
              ["Red before too; known red", "Đã đỏ từ trước; đỏ đã biết"], build=newest, pr=pr)


# ---------------------------------------------------------------- flaky
def quarantine(states, known):
    """In the last 24 h one commit failed and then passed the same pipeline or job, and it is not a known flaky workload."""
    return "failed" in states and "passed" in states and not known


# ---------------------------------------------------------------- release
def _ver(tag):
    m = re.search(r"(\d+\.\d+\.\d+)", tag or "")
    return m.group(1) if m else None


def block_release(item, current, nxt):
    """The Trace Agent marked a PR 'blocks-release' for the current or next version and its fix is not merged."""
    return item.get("impact") == "blocks-release" and item.get("fix_status") not in ("merged", "fixed") \
        and _ver(item.get("tag")) in {_ver(current), _ver(nxt)} - {None}


def fix_carry_over(row):
    """A carry-over blocker in RELEASE_PREP is not done, or the newest publish.yml run of the latest or stable tag failed or was cancelled."""
    return row.get("id", "").startswith("C") and not re.match(r"^(merged|done|fixed|xong|đã)", (row.get("cols") or ["", "", ""])[2] or "", re.I)


def fix_publish(run):
    """A carry-over blocker in RELEASE_PREP is not done, or the newest publish.yml run of the latest or stable tag failed or was cancelled."""
    return bool(run) and run.get("status") == "completed" and run.get("conclusion") in ("failure", "cancelled")


# ---------------------------------------------------------------- next release: one scope item of the ROADMAP
MP_TIERS = ("L2", "CE", "AO", "FULL")   # tiers that only the k3-multiprocess-test suite runs (same list as mpReq in next_release.js)


def mp_required(pr):
    """The PR's change class needs a tier that only the MP suite runs."""
    return any(t in MP_TIERS for t in (pr.get("cpu_tiers") or []) + (pr.get("gpu_tiers") or []))


def item_out(missing):
    """A PR of the item is not merged into dev, so it cannot ship in this release."""
    return bool(missing)


def item_needs_test(prs):
    """A PR of the item needs the MP suite but has no green k3-multiprocess-test build on the PR in local data."""
    return any(mp_required(p) and (p.get("mp_ev") or {}).get("state") != "passed" for p in prs)


def item_in(prs, missing):
    """Every PR of the item is merged into dev and each one that needs the MP suite has a green MP build."""
    return not item_out(missing) and not item_needs_test(prs)


def scope_item(prs, missing):
    """Decision for one ROADMAP scope item, first match wins: item_out → item_needs_test → item_in.
    prs = merged PR dicts of the item (with mp_ev = newest MP build of the PR); missing = item PR numbers not merged."""
    if item_out(missing):
        n = ", ".join(f"#{x}" for x in missing[:2])
        return _d("out", ["Not merged into dev.", "Chưa merge vào dev."], [f"{n} not merged into dev", f"{n} chưa merge vào dev"])
    bad = [p for p in prs if mp_required(p) and (p.get("mp_ev") or {}).get("state") != "passed"]
    if bad:
        n = ", ".join(f"#{p['num']}" for p in bad[:2])
        red = any((p.get("mp_ev") or {}).get("state") == "failed" for p in bad)
        return _d("needs_test", ["MP suite needed; no green MP build on the PR.", "Cần bộ MP; PR chưa có build MP xanh."],
                  [f"{n}: newest MP build red" if red else f"{n}: no green MP build in local data",
                   f"{n}: build MP mới nhất đỏ" if red else f"{n}: dữ liệu local không có build MP xanh"])
    if any(mp_required(p) for p in prs):
        return _d("in", ["Merged; MP green on the PR.", "Đã merge; MP xanh trên PR."], ["Merged; MP green on the PR", "Đã merge; MP xanh trên PR"])
    return _d("in", ["Merged; the change class does not need the MP suite.", "Đã merge; nhóm thay đổi không cần bộ MP."],
              ["Merged; MP suite not needed by rule", "Đã merge; luật không yêu cầu MP"])


# ---------------------------------------------------------------- one release tag
def release_blocked(blockers):
    """A 'blocks-release' finding of the Trace Agent for this tag has no merged fix."""
    return any(b.get("fix_status") not in ("merged", "fixed") for b in blockers)


def release_no_data(run):
    """No finished publish.yml run of this tag is in the local snapshot."""
    return not run


def release_shipped(run, blockers):
    """The tag is published, its newest publish.yml run is green and it has no blocks-release finding."""
    return bool(run) and run.get("conclusion") == "success" and not blockers


def release_with_failures(run, blockers):
    """The tag is published, but its newest publish.yml run did not end green or a blocker needed a later fix."""
    return bool(run) and not release_blocked(blockers) and not release_shipped(run, blockers)


def release_publishing(run, pending):
    """A publish.yml run of this tag exists in the snapshot but has not finished."""
    return not run and bool(pending)


def release_verdict(run, blockers, pending=None):
    """Verdict for one release tag, first match wins: release_blocked → release_no_data → release_shipped → release_with_failures.
    run = newest finished publish.yml run of the tag; blockers = Trace Agent findings with impact 'blocks-release'."""
    if release_blocked(blockers):
        n = ", ".join(f"#{b['num']}" for b in blockers if b.get("fix_status") not in ("merged", "fixed"))
        return _d("blocked", ["Open blocker found by the Trace Agent.", "Blocker còn mở do Trace Agent tìm ra."], [f"{n} blocks it; no fix merged", f"{n} chặn; chưa có bản sửa"], by="agent")
    if release_publishing(run, pending):
        st = pending[0].get("status") or "pending"
        return _d("publishing", ["Publish run not finished.", "Run publish chưa xong."], [f"Publish run {st} since {(pending[0].get('created_at') or '')[11:16]} UTC",
                  f"Run publish {st} từ {(pending[0].get('created_at') or '')[11:16]} UTC"])
    if release_no_data(run):
        return _d("no_data", ["No publish run in local data.", "Dữ liệu local không có run publish."], ["No publish run in local data", "Dữ liệu local không có run publish"])
    if release_shipped(run, blockers):
        return _d("shipped", ["Published; publish run green.", "Đã publish; run publish xanh."], ["Publish run green; no blocker", "Run publish xanh; không có blocker"])
    c = run.get("conclusion") or "?"
    fixed = [f"#{b['num']}" for b in blockers]
    return _d("shipped_fail", ["Published with a failure.", "Đã publish nhưng có lỗi."],
              [f"Publish run {c}" + (f"; {fixed[0]} fixed later" if fixed else ""), f"Run publish {c}" + (f"; {fixed[0]} sửa sau" if fixed else "")])


def check():
    """Keep the tooltip text and the code in step: every rule function's first docstring line is a RULE text."""
    fns = {"cancel": cancel_ci, "keep": keep_ci, "dco": dco_fail, "rebase": rebase_first, "red": wait_fix, "merge": merge,
           "full": add_full, "author": wait_author, "triage": new_red, "watch": known_red, "quarantine": quarantine,
           "block": block_release, "fix": fix_carry_over, "out": item_out, "needs_test": item_needs_test, "in": item_in,
           "blocked": release_blocked, "no_data": release_no_data, "shipped": release_shipped, "shipped_fail": release_with_failures,
           "publishing": release_publishing}
    bad = [v for v, f in fns.items() if f.__doc__.strip().splitlines()[0] != RULE[v][0]]
    bad += [v for v in RULE if v not in VERBS]
    return bad
