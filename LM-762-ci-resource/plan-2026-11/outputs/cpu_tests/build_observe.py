"""Add the "PR / Release watch" view (#obs/...) to 06_PR_TO_CI_VISUAL.html (idempotent).

Visible tabs owned here (2026-11-10 refactor):
  1 Releases (tags, publish.yml, nightlies)  -> tab "release"
  2 Release trace (release -> PR -> fix)     -> tab "trace"
The old tabs now / prs / ci / trend were removed on 2026-11-13 (v2 clean-up, P5); their hashes land on
visible tabs through the nav aliases. New tabs come from build_ops_tabs.py, build_today.py.

Data: observe_snapshot.json (from observe_collect.py) is embedded, so the page works offline.
The "Refresh" button re-runs the same requests from the browser (GitHub + Buildkite both allow
CORS). Tokens are optional and stay in the viewer's browser. CONFIG below is the single source
for repo, workflows, gate check-name patterns, thresholds and the PR GraphQL query; the
collector imports it too. Run after build_gates.py, before build_i18n.py (build_page calls it).
"""
import json
import os
import re

import sys  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir
from gates import JOBS

from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
SNAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "observe_snapshot.json")

# 50 PRs per page: mergeStateStatus is costly, so a 2nd query asks it only for approved PRs (MSTATE_QUERY).
PR_QUERY = (
    'query($after:String){repository(owner:"LMCache",name:"LMCache"){pullRequests(states:OPEN,first:50,after:$after,'
    'orderBy:{field:UPDATED_AT,direction:DESC}){totalCount pageInfo{endCursor hasNextPage} nodes{number title url isDraft createdAt updatedAt '
    'reviewDecision mergeable baseRefName author{login} assignees(first:3){nodes{login}} labels(first:8){nodes{name color}} '
    'milestone{title} autoMergeRequest{enabledAt} commits(last:1){nodes{commit{oid statusCheckRollup{state '
    'contexts(first:80){nodes{__typename ... on CheckRun{name status conclusion detailsUrl} '
    '... on StatusContext{context state targetUrl}}}}}}}}}}}'
)
MSTATE_QUERY = 'query{repository(owner:"LMCache",name:"LMCache"){__PRS__}}'  # __PRS__ -> p123:pullRequest(number:123){number mergeStateStatus}
# "Fixed on dev" tab: files, closed issues and merge commit of waiting + recently merged PRs (40 aliases per query)
COVER_FIELDS = 'number mergeCommit{oid} files(first:100){nodes{path}} closingIssuesReferences(first:5){nodes{number}}'
COVER_DAYS = 7  # fetch window; the tab shows 1 / 3 / 7 days


GATE_KIND = {j["id"]: j["gate"][0] for j in JOBS}
CONFIG = dict(
    repo="LMCache/LMCache",
    bk_org="lmcache",
    workflows=dict(publish=157910139, nightly=164357863),  # publish.yml, nightly_build.yml
    main_tag_re=r"^v\d+\.\d+\.\d+(rc\d+|\.post\d+)?$",               # no platform suffix (-xpu, -rocm, ...)
    stable_tag_re=r"^v\d+\.\d+\.\d+$",
    tag_runs=4,                                             # publish.yml runs fetched for the newest N main tags
    # repo-wide counts (GitHub search; works without a token, 10 searches / min)
    counts=dict(open="is:pr is:open", draft="is:pr is:open draft:true",
                approved="is:pr is:open draft:false review:approved",
                changes="is:pr is:open draft:false review:changes_requested"),
    # PR gate chips: check / status name pattern -> gate id in gates.py (kind = merge / release / advisory)
    gates=[
        dict(id="dco", label="DCO", re=r"^DCO$"),
        dict(id="cq", label="Lint", re=r"^Check code quality$"),
        dict(id="k3u", label="k3 unit", re=r"^buildkite/k3-unit-tests$"),
        dict(id="k3mp", label="k3 MP", re=r"^buildkite/k3-multiprocess-test$"),
        dict(id="ght", label="GHA Test", re=r"^test: 3\."),
        dict(id="cpud", label="CPU dev", re=r"^CPU device \((?!\$)"),
    ],
    gate_kind=GATE_KIND,
    # Buildkite pipelines in display order; key=True -> required check, used for the dev-health tile
    pipelines=[["k3-unit-tests", True], ["k3-multiprocess-test", True], ["k3-integration-test", False],
               ["k3-correctness-test", False], ["k3-sglang-test", False], ["k3-blend-test", False],
               ["k3-comprehensive-test", False], ["amd-mp-test", False], ["unit-tests-amd", False],
               ["xpu-mp-test", False], ["unit-tests-xpu", False], ["musa-mp-test", False],
               ["unit-tests-musa", False], ["rbln-mp-test", False], ["metax-maca-mp-test", False],
               ["lmcache-operator-integration-test", False]],
    queue_pipelines=["k3-unit-tests", "k3-multiprocess-test"],  # queue-wait stats from recent builds
    queue_builds=20,
    th=dict(nightly_stale_h=36, snap_stale_min=60, open_refresh_min=10, wait_warn_min=30, waiting_jobs_warn=10, gha_queued_warn=40),
    pr_query=PR_QUERY,
    mstate_query=MSTATE_QUERY,
    pr_pages=2,
    local_only=True,  # data comes only from local runs: no Refresh, auto refresh, tokens or live API calls in the page
    collect_cmd="python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/observe_collect.py",
    cover_fields=COVER_FIELDS,
    cover_days=COVER_DAYS,
)

HTML = r"""
<!-- OBS:HTML:START -->
<div class="obs-bar" id="obsBar" aria-live="polite"></div>
<section class="card" data-view="obs" data-tab="release">
  <div class="head"><h2>1A · Releases</h2>
  <p class="sub">Tags, publish.yml jobs, nightly builds.</p></div>
  <div id="obsTrain"></div>
  <div id="obsPub" style="margin-top:14px"></div>
  <div id="obsNightly" style="margin-top:14px"></div>
</section>
<section class="card" data-view="obs" data-tab="trace">
  <div class="head"><h2>2A · Release trace</h2>
  <p class="sub">Release → PR → failed check → fix (v0.5.7+).</p></div>
  <div id="obsTracer"></div>
</section>
<!-- OBS:HTML:END -->
"""

CSS = r"""
/* OBS:CSS:START */
.obs-bar{display:none;flex-wrap:wrap;gap:10px;align-items:center;margin:14px 0 2px;padding:10px 14px;border:1px solid var(--border);border-radius:12px;background:var(--surface-1);font-size:12.5px}
body[data-v="obs"] .obs-bar,body[data-all="1"] .obs-bar{display:flex}
.obs-bar .st{display:flex;align-items:center;gap:8px;font-weight:650}
.obs-bar .st small{font-weight:400;color:var(--text-muted)}
.obs-bar .lamp{width:10px;height:10px;border-radius:50%;background:var(--text-muted)}
.obs-bar .lamp.live{background:var(--good);box-shadow:0 0 0 3px color-mix(in oklab,var(--good) 25%,transparent)}
.obs-bar .lamp.old{background:var(--warning)}
.obs-bar .lamp.busy{background:var(--series-1);animation:obsPulse 1s infinite}
.obs-bar .src{display:flex;gap:6px;flex-wrap:wrap}
.obs-bar .src span{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--border);color:var(--text-secondary);white-space:nowrap}
.obs-bar .src span.ok{border-color:color-mix(in oklab,var(--good) 60%,var(--border))}
.obs-bar .src span.off{opacity:.7;border-style:dashed}
.obs-bar .src span.stale{border-color:var(--warning);border-style:dashed}
.obs-bar .src span.err{border-color:var(--critical);color:var(--critical)}
.obs-bar .sp{flex:1}
.obs-bar button,.obs-bar select,.obs-set input{background:var(--surface-1);color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:5px 10px;font:inherit;font-size:12.5px}
.obs-bar button{cursor:pointer}
.obs-bar button.pri{background:var(--series-1);border-color:var(--series-1);color:#fff;font-weight:650}
.obs-bar button:disabled{opacity:.6;cursor:wait}
.obs-bar label{color:var(--text-secondary);display:flex;gap:6px;align-items:center}
.obs-set{flex-basis:100%;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;padding-top:10px;border-top:1px solid var(--grid)}
.obs-set label{display:grid;gap:4px;font-size:12px}
.obs-set input{width:100%;box-sizing:border-box;font-family:ui-monospace,Consolas,monospace}
.obs-set .hint{grid-column:1/-1;color:var(--text-muted);font-size:11.5px}
.obs-errs{flex-basis:100%;color:var(--critical);font-size:11.5px}







.obs-h3{margin:0 0 8px;font-size:12px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em}

.obs-al.s-warn{border-left-color:var(--warning)}.obs-al.s-ok{border-left-color:var(--good)}
.obs-verdict.unk{border-left-color:var(--warning)}
.obs-verdict.bad .vh b{color:var(--crit-text)}.obs-verdict .vn{font-size:11.5px;color:var(--text-secondary);margin-top:6px}.obs-fails{margin:0 0 14px}
@media(max-width:640px){.obs-fails td:nth-child(4){min-width:180px}}
.obs-jobs.only-bad a[data-st="ok"],.obs-jobs.only-bad a[data-st="skip"]{display:none}
.obs-al a,.obs-t a,.obs-feed a,.obs-link{color:var(--series-1);text-decoration:none;cursor:pointer}.obs-t a:hover,.obs-link:hover{text-decoration:underline}



.obs-feed .ev.s-warn .m::before{content:"● ";color:var(--warning)}.obs-feed .ev.s-info .m::before{content:"● ";color:var(--series-1)}
.obs-note{font-size:12px;color:var(--text-secondary);margin-bottom:8px}






.obs-scroll{overflow-x:auto}
.obs-t{width:100%;border-collapse:collapse;font-size:12.5px}
.obs-t th{text-align:left;color:var(--text-secondary);font-weight:600;font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.obs-t td{padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
.obs-t td.r,.obs-t th.r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.obs-t td.nw{white-space:nowrap}

.obs-t .ttl{font-weight:600;line-height:1.35}
.obs-t .meta{color:var(--text-muted);font-size:11.5px;margin-top:2px}
.obs-lab{display:inline-block;font-size:10.5px;padding:0 6px;border-radius:999px;margin:2px 4px 0 0;border:1px solid var(--border);color:var(--text-secondary)}
/* --good-text / --crit-text / --muted-text: aliases in the round-3 token block (ux_ui.TOKENS) */
button.theme{white-space:nowrap}
.gch{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:650;padding:1px 6px;border-radius:5px;margin:1px 3px 1px 0;border:1px solid var(--border);white-space:nowrap;color:var(--text-secondary)}
.gch::before{content:"";width:7px;height:7px;border-radius:2px;background:var(--border)}
.gch.adv{opacity:.75;font-weight:500}
.gch.s-ok::before,.dot.s-ok{background:var(--good)}
.gch.s-fail{color:var(--crit-text);border-color:var(--critical)}.gch.s-fail::before,.dot.s-fail{background:var(--critical)}
.gch.s-run::before,.dot.s-run{background:var(--warning);animation:obsPulse 1.4s infinite}

.gch.s-none{border-style:dashed;opacity:.55}.gch.s-none::before{background:transparent;border:1px dashed var(--text-muted)}
.dot{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:3px;vertical-align:middle;background:var(--border)}

a.dot{cursor:pointer}a.dot:hover{outline:2px solid var(--text-muted);outline-offset:1px}
.bkt{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;padding:1px 7px;border-radius:999px;color:#fff;white-space:nowrap}
.obs-train{display:grid;gap:10px}
.obs-train .row{display:grid;grid-template-columns:90px 1fr;gap:10px;align-items:start;border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1)}
.obs-train .ver{font:700 15px ui-monospace,Consolas,monospace}
.obs-train .ver small{display:block;font:11px system-ui,sans-serif;color:var(--text-muted);margin-top:2px}
.obs-train .chain{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.obs-train .tg{display:flex;flex-direction:column;border:1px solid var(--border);border-radius:8px;padding:4px 9px;font-size:11.5px;min-width:74px;text-decoration:none;color:var(--text-primary);cursor:pointer}
.obs-train .tg b{font:650 12px ui-monospace,Consolas,monospace}
.obs-train .tg span{color:var(--text-muted)}
.obs-train .tg.stable{border-color:var(--series-2);background:color-mix(in oklab,var(--series-2) 8%,transparent)}
.obs-train .tg.s-fail{border-color:var(--critical)}
.obs-train .arr{color:var(--text-muted)}
.obs-train .plat{font-size:11.5px;color:var(--text-muted);margin-top:6px}
.obs-jobs{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:6px;margin:8px 0 16px}
.obs-jobs a{display:flex;gap:6px;align-items:center;font-size:12px;padding:4px 8px;border:1px solid var(--border);border-radius:7px;color:var(--text-primary);text-decoration:none}
.obs-jobs a:hover{border-color:var(--text-muted)}
.obs-jobs a .n{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.obs-jobs a .t{color:var(--text-muted);font-variant-numeric:tabular-nums;font-size:11px}
.obs-runhd{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12.5px}
.obs-runhd b{font-family:ui-monospace,Consolas,monospace}








.obs-empty{color:var(--text-muted);font-size:12.5px;padding:6px 0}
































.rp-svg .rp-stk.part{opacity:.3}





.rp-foldable{border:1px solid var(--border);border-radius:12px;background:var(--surface-1);margin-top:20px;padding:12px 16px}
.rp-foldable summary{cursor:pointer;font-weight:650;font-size:13.5px;color:var(--text-primary);padding:4px 0}
.rp-foldable[open] summary{margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid var(--border)}

/* Unified 5-Stage Interactive Flowchart: Release -> PR -> Critical Stage -> Test Case -> Error Log (+ Component Inspector) */
.tr-wrap{border:1px solid var(--border);border-radius:14px;padding:14px 16px;background:var(--surface-1);display:flex;flex-direction:column;gap:12px}
.tr-hd{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;padding-bottom:10px;border-bottom:1px solid var(--grid)}
.tr-hd h3{margin:0;font-size:14px;display:flex;align-items:center;gap:8px}
.tr-hd p{margin:2px 0 0;font-size:12px;color:var(--text-secondary)}
.tr-ctrl{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.tr-btn{all:unset;cursor:pointer;font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-primary);display:inline-flex;align-items:center;gap:5px}
.tr-btn:hover{border-color:var(--series-1)}
.tr-btn.pri{background:var(--series-1);border-color:var(--series-1);color:#fff}
.tr-btn.sm{padding:1px 7px;font-size:10.5px}
.tr-flow-box{border:1px solid var(--border);border-radius:12px;background:var(--surface-0);padding:8px 10px;overflow-x:auto}
.tr-flow-svg{width:100%;min-width:980px;height:auto;display:block}
.tr-flow-svg .tr-col{cursor:pointer}
.tr-flow-svg .tr-col rect{fill:none;stroke:var(--grid);stroke-dasharray:4 4;transition:stroke .2s,fill .2s}
.tr-flow-svg .tr-col:hover rect{stroke:var(--text-muted)}
.tr-flow-svg .tr-col.focus rect{stroke:var(--series-1);stroke-dasharray:none;stroke-width:1.6;fill:color-mix(in oklab,var(--series-1) 5%,transparent)}
.tr-flow-svg .tr-col-lbl{font:700 10.5px ui-monospace,Consolas,monospace;fill:var(--text-secondary);letter-spacing:.04em}
.tr-flow-svg .tr-col.focus .tr-col-lbl{fill:var(--series-1)}
.tr-flow-svg .tr-pipe-bg{fill:none;stroke:var(--border);stroke-width:2;opacity:.45}
.tr-flow-svg .tr-stream{fill:none;stroke:var(--series-1);stroke-width:3;stroke-linecap:round;stroke-dasharray:10 7;animation:trFlowDash .65s linear infinite}
.tr-flow-svg .tr-stream.crit{stroke:var(--critical);stroke-width:3.4;animation-duration:.5s}
.tr-flow-svg .tr-stream.dim{stroke:var(--text-muted);stroke-width:1.8;stroke-dasharray:5 6;opacity:.45;animation-duration:1.3s}
.tr-flow-svg .tr-particle{fill:var(--series-1);filter:drop-shadow(0 0 4px var(--series-1))}
.tr-flow-svg .tr-particle.crit{fill:var(--critical);filter:drop-shadow(0 0 5px var(--critical))}
.tr-flow-svg .tr-fnode{cursor:pointer;outline:none}
.tr-flow-svg .tr-fnode rect.bx{fill:var(--surface-1);stroke:var(--border);stroke-width:1.5;transition:stroke .2s,fill .2s}
.tr-flow-svg .tr-fnode:hover rect.bx,.tr-flow-svg .tr-fnode:focus-visible rect.bx{stroke:var(--text-muted)}
.tr-flow-svg .tr-fnode.sel rect.bx{stroke:var(--series-1);stroke-width:2.4;fill:color-mix(in oklab,var(--series-1) 12%,var(--surface-1))}
.tr-flow-svg .tr-fnode.crit rect.bx{stroke:var(--critical);stroke-width:2.4;fill:color-mix(in oklab,var(--critical) 13%,var(--surface-1))}
.tr-flow-svg .tr-fnode rect.ring{fill:none;stroke:none}
.tr-flow-svg .tr-fnode.focus rect.ring{stroke:var(--series-1);stroke-width:1.6;stroke-dasharray:3 3}
.tr-flow-svg .tr-fnode text.t1{font:700 11px ui-monospace,Consolas,monospace;fill:var(--text-primary)}
.tr-flow-svg .tr-fnode text.t2{font:10px system-ui,sans-serif;fill:var(--text-secondary)}
.tr-flow-box.animating .tr-fnode.on rect.bx{animation:trNodePulse .9s ease both}
.tr-flow-box.animating .tr-fnode.on[data-stage="2"] rect.bx{animation-delay:.15s}
.tr-flow-box.animating .tr-fnode.on[data-stage="3"] rect.bx{animation-delay:.3s}
.tr-flow-box.animating .tr-fnode.on[data-stage="4"] rect.bx{animation-delay:.45s}
.tr-flow-box.animating .tr-fnode.on[data-stage="5"] rect.bx{animation-delay:.6s}
@keyframes trNodePulse{0%{filter:drop-shadow(0 0 0 transparent)}40%{filter:drop-shadow(0 0 12px var(--series-1));stroke-width:3.4}100%{filter:drop-shadow(0 0 0 transparent)}}
@keyframes trFlowDash{to{stroke-dashoffset:-34}}
.tr-flow-box.replay .tr-col rect{animation:trColSweep 1.5s ease both}
.tr-flow-box.replay .tr-col[data-col="2"] rect{animation-delay:.35s}
.tr-flow-box.replay .tr-col[data-col="3"] rect{animation-delay:.7s}
.tr-flow-box.replay .tr-col[data-col="4"] rect{animation-delay:1.05s}
.tr-flow-box.replay .tr-col[data-col="5"] rect{animation-delay:1.4s}
@keyframes trColSweep{0%{stroke:var(--grid)}30%{stroke:var(--series-1);stroke-width:2;fill:color-mix(in oklab,var(--series-1) 9%,transparent)}100%{}}
.tr-flow-box.replay .tr-stream:not(.dim){animation:trSurge .55s ease-out both,trFlowDash .65s linear infinite}
.tr-flow-box.replay .tr-stream[data-col="3"]:not(.dim){animation-delay:.35s,0s}
.tr-flow-box.replay .tr-stream[data-col="4"]:not(.dim){animation-delay:.7s,0s}
.tr-flow-box.replay .tr-stream[data-col="5"]:not(.dim){animation-delay:1.05s,0s}
@keyframes trSurge{0%{opacity:0;stroke-width:1}60%{opacity:1;stroke-width:7}100%{opacity:1}}
.tr-flow-box.replay .tr-fnode.on rect.bx{animation:trNodePulse 1s ease both}
.tr-flow-box.replay .tr-fnode.on[data-stage="2"] rect.bx{animation-delay:.35s}
.tr-flow-box.replay .tr-fnode.on[data-stage="3"] rect.bx{animation-delay:.7s}
.tr-flow-box.replay .tr-fnode.on[data-stage="4"] rect.bx{animation-delay:1.05s}
.tr-flow-box.replay .tr-fnode.on[data-stage="5"] rect.bx{animation-delay:1.4s}
.tr-hint{font-size:11px;color:var(--text-muted);margin:4px 2px 0}
.tr-pills{display:flex;flex-wrap:wrap;gap:6px}
.tr-pill{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:6px;font-size:11.5px;padding:4px 10px 4px 5px;border-radius:999px;border:1px solid var(--border);background:var(--surface-0);color:var(--text-secondary)}
.tr-pill:hover{border-color:var(--text-muted)}
.tr-pill:focus-visible{outline:2px solid var(--series-1);outline-offset:1px}
.tr-pill .n{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;background:var(--surface-2);color:var(--text-primary);font-size:10.5px;font-weight:800}
.tr-pill .v{font:600 11px ui-monospace,Consolas,monospace;color:var(--text-primary)}
.tr-pill[aria-pressed="true"]{border-color:var(--series-1);background:color-mix(in oklab,var(--series-1) 10%,var(--surface-0));color:var(--text-primary);font-weight:650}
.tr-pill[aria-pressed="true"] .n{background:var(--series-1);color:#fff}
.tr-pill.bad .v{color:var(--critical)}
.tr-insp{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:12px;border:1px solid color-mix(in oklab,var(--series-1) 45%,var(--border));border-radius:12px;padding:12px;background:var(--surface-0);animation:trFade .35s ease}
.tr-insp.full{grid-template-columns:minmax(0,1fr)}
@keyframes trFade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.tr-ip{display:flex;flex-direction:column;gap:8px;min-width:0}
.tr-ip-hd{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.04em;color:var(--text-secondary);border-bottom:1px solid var(--grid);padding-bottom:6px}
.tr-ip-hd .step-num{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;background:var(--series-1);color:#fff;font-size:10.5px;font-weight:800;margin-right:4px}
.tr-ip-ttl{font-size:14px;font-weight:700;color:var(--text-primary);display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.tr-ip-ttl .mono{font:700 13px ui-monospace,Consolas,monospace}
.tr-kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 12px;font-size:12px}
.tr-kv dt{color:var(--text-muted);font-weight:600}
.tr-kv dd{margin:0;color:var(--text-primary);min-width:0;overflow-wrap:anywhere}
.tr-links{display:flex;flex-wrap:wrap;gap:6px}
.tr-chips{display:flex;flex-wrap:wrap;gap:5px;max-height:132px;overflow-y:auto}
@media (max-width:640px){.tr-pill,.tr-chip{white-space:normal;max-width:100%;box-sizing:border-box;overflow-wrap:anywhere}.tr-pills,.tr-chips{min-width:0;max-width:100%}section[data-tab="trace"] .mono{overflow-wrap:anywhere}section[data-tab="trace"] svg{max-width:100%}}
.tr-chip{all:unset;cursor:pointer;font:600 11px ui-monospace,Consolas,monospace;padding:2px 8px;border-radius:6px;border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary)}
.tr-chip:hover{border-color:var(--text-muted)}
.tr-chip.sel{border-color:var(--series-1);box-shadow:inset 0 -2px 0 var(--series-1)}
.tr-chip.crit{color:var(--critical)}
.tr-q{width:100%;box-sizing:border-box;padding:4px 8px;border:1px solid var(--border);border-radius:6px;background:var(--surface-1);color:var(--text-primary);font-size:11.5px}
.tr-steps{display:flex;flex-direction:column;gap:4px}
.tr-step{border:1px solid var(--border);border-radius:8px;padding:6px 8px;background:var(--surface-1);font-size:11.5px;display:flex;align-items:center;justify-content:space-between;gap:6px}
.tr-step.crit{border-color:var(--critical);background:color-mix(in oklab,var(--critical) 12%,var(--surface-1));font-weight:700;color:var(--text-primary)}
.tr-step.active{border-color:var(--series-1);box-shadow:inset 3px 0 0 var(--series-1)}
.tr-step.pick{outline:2px dashed var(--series-1);outline-offset:1px}
.tr-step-arr{text-align:center;font-size:10px;color:var(--text-muted);line-height:1;margin:-2px 0}
.tr-files{border-top:1px dashed var(--border);padding-top:6px;font-size:11px;display:flex;flex-direction:column;gap:3px}
.tr-file{font:10.5px ui-monospace,Consolas,monospace;color:var(--text-secondary);background:var(--surface-2);padding:2px 6px;border-radius:4px;word-break:break-all}
.tr-file.lnk{cursor:pointer}.tr-file.lnk:hover{color:var(--text-primary)}
.tr-term{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:9px;padding:9px 10px;font:11px/1.45 ui-monospace,Consolas,monospace;display:flex;flex-direction:column;gap:6px;overflow-x:auto}
.tr-term-hd{display:flex;justify-content:space-between;align-items:center;gap:6px;padding-bottom:5px;border-bottom:1px solid #21262d;color:#8b949e;font-size:10.5px}
.tr-term-dots{display:inline-flex;gap:4px}
.tr-term-dots i{width:8px;height:8px;border-radius:50%;display:inline-block}
.tr-log-lines{display:flex;flex-direction:column;gap:2px;max-height:190px;overflow-y:auto}
.tr-insp.full .tr-log-lines{max-height:300px}
.tr-log-ln{white-space:pre-wrap;word-break:break-word;padding:1px 4px;border-radius:3px}
.tr-log-ln.err{color:#ff7b72;background:rgba(248,81,73,0.14);font-weight:650}
.tr-log-ln.warn{color:#d29922;background:rgba(210,153,34,0.12)}
.tr-diag{border:1px solid var(--border);border-radius:8px;padding:7px 9px;background:var(--surface-1);font-size:11.5px;display:flex;flex-direction:column;gap:5px}
.tr-diag b{color:var(--text-primary)}
.tr-repro{font:10.5px ui-monospace,Consolas,monospace;background:var(--surface-2);padding:3px 6px;border-radius:5px;color:var(--text-primary);display:flex;justify-content:space-between;align-items:center;gap:6px}
@media (max-width:1100px){.tr-insp{grid-template-columns:minmax(0,1fr)}}
.tr-sub{font-size:11px;color:var(--text-secondary);line-height:1.3}
.tr-agent{border:1px solid color-mix(in oklab,var(--series-1) 45%,var(--border));border-radius:8px;padding:8px 10px;background:color-mix(in oklab,var(--series-1) 6%,var(--surface-1));font-size:11.5px;display:flex;flex-direction:column;gap:6px}
.tr-agent.pending{border-style:dashed;border-color:color-mix(in oklab,var(--warning) 60%,var(--border));background:var(--surface-1)}
.tr-agent.err{border-color:color-mix(in oklab,var(--critical) 55%,var(--border))}
.tr-agent.ok{border-color:color-mix(in oklab,var(--good) 55%,var(--border));background:var(--surface-1)}
.tr-agent-hd{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.tr-agent-hd .m{color:var(--text-muted);font-size:10.5px}
.tr-agent .fx{color:var(--good)}
.tr-agent ul{margin:0;padding-left:18px;color:var(--text-secondary)}
.tr-agent details summary{cursor:pointer;color:var(--text-secondary);font-weight:600}
.tr-agent details pre{max-height:340px;overflow:auto;white-space:pre-wrap;word-break:break-word;font:10.5px/1.45 ui-monospace,Consolas,monospace;background:var(--surface-2);color:var(--text-primary);padding:8px;border-radius:6px;margin:6px 0 0}
.tr-agent-sum{font-size:11px;color:var(--text-secondary);display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border:1px solid var(--border);border-radius:999px;background:var(--surface-0)}
.tr-pr{border:1px solid var(--border);border-radius:9px;padding:9px 11px;background:var(--surface-1);box-shadow:inset 3px 0 0 var(--series-1)}
@media (prefers-reduced-motion:reduce){#obsTracer .tr-particle{display:none}#obsTracer .tr-stream,#obsTracer .tr-flow-box,#obsTracer .tr-flow-box *{animation:none!important;transition:none!important}}
.tr-pr.suspect{border-color:color-mix(in oklab,var(--critical) 55%,var(--border));box-shadow:inset 3px 0 0 var(--critical)}
@media (max-width:980px){.obs-2col{grid-template-columns:1fr}.obs-train .row{grid-template-columns:1fr}}
@keyframes obsPulse{50%{opacity:.35}}
@media (prefers-reduced-motion:reduce){.gch.s-run::before,.dot.s-run,.obs-bar .lamp.busy,.tr-flow-svg .tr-stream,.tr-flow-box.animating .tr-fnode.on rect.bx,.tr-flow-box.replay .tr-col rect,.tr-insp{animation:none}.tr-flow-svg .tr-particle{display:none}}
/* OBS:CSS:END */
"""

JS = r"""
<!-- OBS:JS:START -->
<script id="obsCfg" type="application/json">__CFG__</script>
<script id="obsSnap" type="application/json">__SNAP__</script>
<script id="obsHist" type="application/json">__HIST__</script>
<script>
(function(){
  const CFG=JSON.parse(document.getElementById('obsCfg').textContent);
  let SNAP=null;try{SNAP=JSON.parse(document.getElementById('obsSnap').textContent);}catch(e){}
  let HIST={points:[],mp:null,measured:{}};try{HIST=JSON.parse(document.getElementById('obsHist').textContent)||HIST;}catch(e){}
  const RP=HIST.report;   // release_trace / trace_agent / required_checks (release tracer, 1A train)
  const NS='http://www.w3.org/2000/svg',sv=(t,a)=>{const e=document.createElementNS(NS,t);for(const[k,v]of Object.entries(a))e.setAttribute(k,v);return e;};   // SVG helper (release tracer)
  const $=s=>document.querySelector(s);
  const el=(t,a={},...kids)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(v==null)continue;if(k==='class')e.className=v;else if(k==='style')e.style.cssText=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v);}
    kids.flat().forEach(c=>{if(c==null||c===false)return;e.append(c.nodeType?c:document.createTextNode(String(c)));});return e;};
  const V=()=>(window.I18N&&I18N.lang==='vi')?1:0, T=(en,vi)=>V()?vi:en;
  const fmt=n=>n==null?'—':Number(n).toLocaleString('en-US');
  const ms=s=>s?Date.parse(s):NaN;
  const sleep=t=>new Promise(r=>setTimeout(r,t));
  function ago(t){if(!t)return '—';const d=(Date.now()-(typeof t==='number'?t:Date.parse(t)))/1000;if(!isFinite(d))return '—';
    if(d<60)return T(Math.max(0,Math.round(d))+' s ago',Math.max(0,Math.round(d))+' giây trước');if(d<3600)return T(Math.round(d/60)+' min ago',Math.round(d/60)+' phút trước');
    if(d<172800)return T(Math.round(d/3600)+' h ago',Math.round(d/3600)+' giờ trước');return T(Math.round(d/86400)+' d ago',Math.round(d/86400)+' ngày trước');}
  function dur(s){if(s==null||!isFinite(s))return '—';s=Math.max(0,s);if(s<90)return Math.round(s)+' s';if(s<5400)return Math.round(s/60)+T(' min',' phút');return (s/3600).toFixed(1)+T(' h',' giờ');}
  const day=t=>t?new Date(t).toLocaleDateString(V()?'vi-VN':'en-CA',{month:'2-digit',day:'2-digit'}):'—';
  const clock=t=>new Date(t).toLocaleTimeString(V()?'vi-VN':'en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const pct=(a,p)=>{if(!a.length)return null;const s=[...a].sort((x,y)=>x-y);return s[Math.min(s.length-1,Math.floor(p*(s.length-1)+.5))];};
  const store=(k,d)=>{try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v);}catch(e){return d;}};
  const save=(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}};

  // ---------- tokens (stay in this browser) ----------
  let tok={gh:'',bk:''};
  try{tok=JSON.parse(localStorage.getItem('obsTok')||sessionStorage.getItem('obsTok')||'{"gh":"","bk":""}');}catch(e){}
  let remember=store('obsTokRemember',false);
  function saveTok(){const s=JSON.stringify(tok);try{if(remember){localStorage.setItem('obsTok',s);sessionStorage.removeItem('obsTok');}else{sessionStorage.setItem('obsTok',s);localStorage.removeItem('obsTok');}}catch(e){}save('obsTokRemember',remember);}

  // ---------- transport ----------
  const net={calls:0,rate:null,bkRate:null};
  async function req(url,opt,tries=3){let last;for(let i=0;i<tries;i++){try{const r=await fetch(url,opt);if(r.status>=500){last=new Error('HTTP '+r.status);await sleep(700*(i+1));continue;}return r;}catch(e){last=e;await sleep(700*(i+1));}}throw last;}
  async function gh(path){const h={'Accept':'application/vnd.github+json'};if(tok.gh)h.Authorization='Bearer '+tok.gh;
    const r=await req('https://api.github.com/'+path,{headers:h});net.calls++;const rm=r.headers.get('x-ratelimit-remaining');if(rm!=null&&!path.startsWith('search'))net.rate=+rm;
    if(!r.ok)throw new Error('GitHub '+r.status+' '+path.split('?')[0]+(r.status===403||r.status===429?T(' (rate limit: add a token)',' (hết lượt: thêm token)'):''));return r.json();}
  async function gql(query,variables){const r=await req('https://api.github.com/graphql',{method:'POST',headers:{Authorization:'Bearer '+tok.gh,'Content-Type':'application/json'},body:JSON.stringify({query,variables:variables||{}})});net.calls++;
    const j=await r.json();if(!r.ok||j.errors)throw new Error('GraphQL '+(j.message||(j.errors&&j.errors[0].message)||r.status));return j.data;}
  async function bk(path){const r=await req('https://api.buildkite.com/v2/'+path,{headers:{Authorization:'Bearer '+tok.bk}});net.calls++;const rm=r.headers.get('ratelimit-remaining');if(rm!=null)net.bkRate=+rm;
    if(!r.ok)throw new Error('Buildkite '+r.status+' '+path.split('?')[0]);return r.json();}

  async function fetchAll(){
    const errors=[],R=CFG.repo,W=CFG.workflows,O=CFG.bk_org,q=encodeURIComponent;net.calls=0;
    const safe=async(l,f,d=null)=>{try{return await f();}catch(e){errors.push(l+': '+e.message);return d;}};
    const P={
      releases:()=>gh(`repos/${R}/releases?per_page=100`),
      runs_dev:()=>gh(`repos/${R}/actions/runs?branch=dev&per_page=100`).then(x=>x.workflow_runs),
      nightly_runs:()=>gh(`repos/${R}/actions/workflows/${W.nightly}/runs?per_page=10`).then(x=>x.workflow_runs),
      publish_dev:()=>gh(`repos/${R}/actions/workflows/${W.publish}/runs?branch=dev&per_page=5`).then(x=>x.workflow_runs),
      gha_queued:()=>gh(`repos/${R}/actions/runs?status=queued&per_page=1`).then(x=>x.total_count),
      gha_running:()=>gh(`repos/${R}/actions/runs?status=in_progress&per_page=1`).then(x=>x.total_count),
    };
    if(tok.gh)P.prs_gql=async()=>{let after=null,out=null;for(let i=0;i<CFG.pr_pages;i++){const p=(await gql(CFG.pr_query,{after})).repository.pullRequests;
        if(!out)out={totalCount:p.totalCount,nodes:[]};out.nodes.push(...p.nodes);if(!p.pageInfo.hasNextPage)break;after=p.pageInfo.endCursor;}
      const ap=out.nodes.filter(n=>n.reviewDecision==='APPROVED'&&!n.isDraft).map(n=>n.number);
      if(ap.length){const d=await gql(CFG.mstate_query.replace('__PRS__',ap.map(n=>`p${n}:pullRequest(number:${n}){number mergeStateStatus}`).join(' ')));
        const ms={};Object.values(d.repository).forEach(x=>{if(x)ms[x.number]=x.mergeStateStatus;});out.nodes.forEach(n=>{if(ms[n.number])n.mergeStateStatus=ms[n.number];});}
      return out;};
    else P.prs_rest=()=>gh(`repos/${R}/pulls?state=open&sort=updated&direction=desc&per_page=100`);
    Object.entries(CFG.counts).forEach(([k,s])=>P['count_'+k]=()=>gh(`search/issues?q=${q('repo:'+R+' '+s)}&per_page=1`).then(x=>x.total_count));
    if(tok.bk){
      P.bk_pipelines=()=>bk(`organizations/${O}/pipelines?per_page=100`);
      P.bk_dev_builds=()=>bk(`organizations/${O}/builds?branch=dev&per_page=100&exclude_jobs=true`);
      P.bk_active=()=>bk(`organizations/${O}/builds?state[]=running&state[]=scheduled&state[]=failing&per_page=100&exclude_jobs=true`);
      CFG.queue_pipelines.forEach(s=>P['bk_recent_'+s]=()=>bk(`organizations/${O}/pipelines/${s}/builds?per_page=${CFG.queue_builds}&state[]=passed&state[]=failed`));
    }
    const keys=Object.keys(P),vals=await Promise.all(keys.map(k=>safe(k,P[k])));
    const G={counts:{}},B=tok.bk?{recent:{}}:null;
    keys.forEach((k,i)=>{const v=vals[i];if(k.startsWith('count_'))G.counts[k.slice(6)]=v;else if(k.startsWith('bk_recent_'))B.recent[k.slice(10)]=v;else if(k.startsWith('bk_'))B[k.slice(3)]=v;else G[k]=v;});
    const rel=(G.releases||[]).filter(r=>!r.draft&&new RegExp(CFG.main_tag_re).test(r.tag_name)).sort((a,b)=>ms(b.published_at)-ms(a.published_at));
    const stable=rel.find(r=>new RegExp(CFG.stable_tag_re).test(r.tag_name));
    G.publish_tags={};const step2=rel.slice(0,CFG.tag_runs).map(r=>safe('publish '+r.tag_name,()=>gh(`repos/${R}/actions/workflows/${W.publish}/runs?branch=${q(r.tag_name)}&per_page=3`).then(x=>{G.publish_tags[r.tag_name]=x.workflow_runs;})));
    if(stable){G.merged_since=stable.tag_name;step2.push(safe('merged',()=>gh(`search/issues?q=${q(`repo:${R} is:pr is:merged base:dev merged:>=${stable.published_at}`)}&per_page=100&sort=updated`).then(x=>{G.merged=x.items;})));}
    await Promise.all(step2);
    { // Fixed on dev: PRs merged into dev in the last CFG.cover_days, then files / issues / merge commit (GraphQL, needs a token)
      const since=new Date(Date.now()-CFG.cover_days*864e5).toISOString().slice(0,19)+'Z';
      await safe('merged_recent',()=>gh(`search/issues?q=${q(`repo:${R} is:pr is:merged base:dev merged:>=${since}`)}&per_page=100&sort=updated`).then(x=>{G.merged_recent=x.items;}));
      if(tok.gh&&G.prs_gql){const nums=[...new Set([...G.prs_gql.nodes.filter(n=>!n.isDraft&&n.baseRefName==='dev').map(n=>n.number),...(G.merged_recent||[]).map(i=>i.number)])];G.pr_files={};
        for(let i=0;i<nums.length;i+=40){const ch=nums.slice(i,i+40);await safe('pr_files',()=>gql(CFG.mstate_query.replace('__PRS__',ch.map(n=>`p${n}:pullRequest(number:${n}){${CFG.cover_fields}}`).join(' '))).then(d=>{
          Object.values(d.repository).forEach(p=>{if(p)G.pr_files[p.number]={merge:(p.mergeCommit||{}).oid||null,files:((p.files||{}).nodes||[]).map(f=>f.path),issues:((p.closingIssuesReferences||{}).nodes||[]).map(x=>x.number)};});}));}}
    }
    G.publish_jobs={};const tagRuns=Object.values(G.publish_tags).flat().filter(Boolean).sort((a,b)=>ms(b.created_at)-ms(a.created_at));
    const runs=[tagRuns[0],(G.publish_dev||[])[0]].filter(Boolean);
    await Promise.all(runs.map(r=>safe('jobs',()=>gh(`repos/${R}/actions/runs/${r.id}/jobs?per_page=100`).then(x=>{G.publish_jobs[r.id]=x.jobs;}))));
    G.rate=net.rate;
    return {at:new Date().toISOString(),via:'live',gh:G,bk:B,errors,mode:{gql:!!G.prs_gql,bk:!!B},calls:net.calls,bkRate:net.bkRate};
  }

  // ---------- normalize ----------
  const GATES=CFG.gates.map(g=>({...g,rx:new RegExp(g.re),kind:CFG.gate_kind[g.id]||'advisory'}));
  const RUNST=r=>r.status&&r.status!=='completed'?'run':({success:'ok',failure:'fail',timed_out:'fail',startup_failure:'fail',action_required:'fail',cancelled:'cancel',skipped:'skip',neutral:'skip',stale:'cancel'})[r.conclusion]||'skip';
  const BKST=s=>({passed:'ok',failed:'fail',failing:'fail',running:'run',scheduled:'run',creating:'run',canceled:'cancel',canceling:'cancel'})[s]||'skip';
  const ctxSt=c=>c.__typename==='StatusContext'||c.context?({SUCCESS:'ok',PENDING:'run',EXPECTED:'run',FAILURE:'fail',ERROR:'fail'})[c.state]||'skip'
     :c.status&&c.status!=='COMPLETED'?'run':({SUCCESS:'ok',NEUTRAL:'ok',SKIPPED:'ok',CANCELLED:'cancel',STALE:'cancel'})[c.conclusion]||'fail';
  const BUCKETS=[['ready','Ready to merge','Sẵn sàng merge','var(--good)'],['ci_fail','Required check failing','Check bắt buộc fail','var(--critical)'],['ci_run','CI running','CI đang chạy','var(--warning)'],
    ['changes','Changes requested','Yêu cầu sửa','var(--series-2)'],['review','Needs review','Chờ review','var(--series-1)'],['conflict','Merge conflict','Xung đột merge','#8a5cd0'],
    ['blocked','Blocked (other)','Bị chặn (khác)','var(--text-muted)'],['draft','Draft','Bản nháp','var(--text-muted)'],['unknown','No check data','Chưa có dữ liệu check','var(--text-muted)']];
  const BK=Object.fromEntries(BUCKETS.map(b=>[b[0],b]));
  function gateStates(ctx){const o={};GATES.forEach(g=>{const m=ctx.filter(c=>g.rx.test(c.name));let s='none';
      if(m.length)s=m.some(c=>c.st==='run')?'run':m.some(c=>c.st==='fail')?'fail':m.some(c=>c.st==='ok')?'ok':'cancel';o[g.id]=s;});return o;}
  function prGql(n){const c=(n.commits.nodes[0]||{}).commit||{},ru=c.statusCheckRollup;const ctx=ru?ru.contexts.nodes.map(x=>({name:x.name||x.context,st:ctxSt(x),url:x.targetUrl})):[];
    const g=gateStates(ctx),mg=GATES.filter(x=>x.kind==='merge');let b;
    if(n.isDraft)b='draft';else if(n.mergeable==='CONFLICTING'||n.mergeStateStatus==='DIRTY')b='conflict';else if(['CLEAN','HAS_HOOKS','UNSTABLE'].includes(n.mergeStateStatus))b='ready';
    else if(mg.some(x=>g[x.id]==='fail'))b='ci_fail';else if(mg.some(x=>g[x.id]==='run')||(ru&&ru.state==='PENDING'))b='ci_run';
    else if(n.reviewDecision==='CHANGES_REQUESTED')b='changes';else if(n.reviewDecision!=='APPROVED')b='review';else b='blocked';
    const advFail=ctx.filter(x=>x.st==='fail').length;
    return {num:n.number,title:n.title,url:n.url,author:(n.author||{}).login||'?',draft:n.isDraft,created:n.createdAt,updated:n.updatedAt,review:n.reviewDecision,mstate:n.mergeStateStatus,
      base:n.baseRefName,failCtx:ctx.filter(x=>x.st==='fail').map(x=>x.name),labels:(n.labels?n.labels.nodes:[]),milestone:(n.milestone||{}).title,auto:!!n.autoMergeRequest,gates:g,bucket:b,fails:advFail,rollup:ru?ru.state:null,bkUrl:(ctx.find(x=>/^buildkite\/k3-unit/.test(x.name))||{}).url};}
  function prRest(p){return {num:p.number,title:p.title,url:p.html_url,author:(p.user||{}).login||'?',draft:p.draft,created:p.created_at,updated:p.updated_at,review:null,base:(p.base||{}).ref,
      labels:p.labels||[],milestone:(p.milestone||{}).title,gates:null,bucket:p.draft?'draft':'unknown',fails:0};}
  const slugOf=b=>(b.pipeline&&b.pipeline.slug)||((b.web_url||'').match(/buildkite\.com\/[^/]+\/([^/]+)\/builds/)||[])[1];

  function model(S){
    const G=S.gh||{},B=S.bk,now=Date.now(),M={S,at:ms(S.at)};
    const verRe=/^v(\d+)\.(\d+)\.(\d+)(rc\d+)?(?:\.(post\d+))?(?:-(.+))?$/;
    const tags=(G.releases||[]).filter(r=>!r.draft).map(r=>{const m=r.tag_name.match(verRe);return m?{tag:r.tag_name,ver:m[1]+'.'+m[2]+'.'+m[3],key:(+m[1])*1e6+(+m[2])*1e3+(+m[3]),rc:m[4]||'',post:m[5]||'',plat:m[6]||'',at:r.published_at,url:r.html_url,assets:(r.assets||[]).length}:null;}).filter(Boolean);
    const main=tags.filter(t=>!t.plat).sort((a,b)=>ms(b.at)-ms(a.at));
    M.stable=main.find(t=>!t.rc);M.rc=main.find(t=>t.rc);M.latest=main[0];
    const pub={},pubAll={};Object.entries(G.publish_tags||{}).forEach(([t,rs])=>{if(rs&&rs.length){pubAll[t]=[...rs].sort((a,b)=>ms(b.created_at)-ms(a.created_at));pub[t]=pubAll[t][0];}});M.pub=pub;M.pubAll=pubAll;
    const vers={};tags.forEach(t=>{const v=vers[t.ver]=vers[t.ver]||{ver:t.ver,key:t.key,main:[],plat:[]};v[t.plat?'plat':'main'].push(t);});
    M.versions=Object.values(vers).sort((a,b)=>b.key-a.key).slice(0,4);M.versions.forEach(v=>v.main.sort((a,b)=>ms(a.at)-ms(b.at)));
    M.nightly=(G.releases||[]).filter(r=>/^nightly/.test(r.tag_name)&&!/\d{4}-\d{2}-\d{2}/.test(r.tag_name)).map(r=>({tag:r.tag_name,at:r.published_at,url:r.html_url,assets:(r.assets||[]).length,age:(now-ms(r.published_at))/36e5})).sort((a,b)=>a.tag.localeCompare(b.tag));
    M.nightlyRuns=[...(G.nightly_runs||[])].sort((a,b)=>ms(a.created_at)-ms(b.created_at));
    M.publishJobs=Object.entries(G.publish_jobs||{}).map(([id,jobs])=>{const run=[...Object.values(G.publish_tags||{}).flat(),...(G.publish_dev||[])].find(r=>r&&String(r.id)===String(id));return {run,jobs:jobs||[]};}).filter(x=>x.run);
    M.prs=G.prs_gql?G.prs_gql.nodes.map(prGql):(G.prs_rest||[]).map(prRest);M.prMode=G.prs_gql?'gql':G.prs_rest?'rest':'none';M.prTotal=G.prs_gql?G.prs_gql.totalCount:null;
    M.counts=G.counts||{};M.merged=[...(G.merged||[])].map(i=>({num:i.number,title:i.title,url:i.html_url,author:(i.user||{}).login,at:(i.pull_request||{}).merged_at,labels:i.labels||[]})).sort((a,b)=>ms(b.at)-ms(a.at));M.mergedSince=G.merged_since;
    M.gha={queued:G.gha_queued,running:G.gha_running,rate:G.rate};
    const wf={};(G.runs_dev||[]).filter(r=>['push','schedule','workflow_dispatch'].includes(r.event)).forEach(r=>(wf[r.name]=wf[r.name]||[]).push(r));
    M.wf=Object.entries(wf).map(([n,rs])=>({name:n,runs:rs.sort((a,b)=>ms(b.created_at)-ms(a.created_at)).slice(0,10).reverse()})).sort((a,b)=>a.name.localeCompare(b.name));
    M.bk=null;
    if(B){const pipes=Object.fromEntries((B.pipelines||[]).map(p=>[p.slug,p]));const dev={};(B.dev_builds||[]).forEach(b=>{const s=slugOf(b);(dev[s]=dev[s]||[]).push(b);});
      const order=CFG.pipelines.map(p=>p[0]);Object.keys(dev).forEach(s=>{if(!order.includes(s))order.push(s);});
      const key=Object.fromEntries(CFG.pipelines);
      const rows=order.filter(s=>dev[s]||pipes[s]).map(s=>{const bs=(dev[s]||[]).sort((a,b)=>b.number-a.number);const fin=bs.find(b=>['passed','failed','canceled'].includes(b.state));
        return {slug:s,key:!!key[s],builds:bs.slice(0,10).reverse(),last:fin,pipe:pipes[s]};});
      const active=(B.active||[]).map(b=>({slug:slugOf(b),num:b.number,state:b.state,branch:b.branch,pr:(b.pull_request||{}).id,url:b.web_url,created:b.created_at,started:b.started_at,msg:b.message,author:(b.author||{}).name})).sort((a,b)=>ms(a.created)-ms(b.created));
      const qs=Object.entries(B.recent||{}).map(([s,bs])=>{const L=(bs||[]).map(b=>{const js=(b.jobs||[]).filter(j=>j.type==='script'&&j.runnable_at&&j.started_at);
          const w=js.length?Math.max(...js.map(j=>(ms(j.started_at)-ms(j.runnable_at))/1000)):null;return {num:b.number,state:b.state,wait:w,run:b.finished_at&&b.created_at?(ms(b.finished_at)-ms(b.created_at))/1000:null,pr:(b.pull_request||{}).id,url:b.web_url};}).reverse();
        const W=L.map(x=>x.wait).filter(x=>x!=null),D=L.map(x=>x.run).filter(x=>x!=null);return {slug:s,builds:L,w50:pct(W,.5),w90:pct(W,.9),d50:pct(D,.5),pass:L.filter(x=>x.state==='passed').length,n:L.length};});
      const sum=k=>(B.pipelines||[]).reduce((a,p)=>a+(p[k]||0),0);
      M.bk={rows,active,qs,running:sum('running_builds_count'),scheduled:sum('scheduled_builds_count'),waiting:sum('waiting_jobs_count'),runningJobs:sum('running_jobs_count'),pipes};}
    // alerts
    const A=[],th=CFG.th,add=(sev,en,vi,go)=>A.push({sev,en,vi,go});
    const age=(now-M.at)/60000;if(S.via!=='live'&&age>th.snap_stale_min)add('warn',`Data is ${dur(age*60)} old. Run observe_collect.py locally.`,`Dữ liệu đã cũ ${dur(age*60)}. Chạy observe_collect.py ở máy local.`);
    if(M.bk)M.bk.rows.filter(r=>r.last&&r.last.state==='failed').forEach(r=>add(r.key?'crit':'warn',`dev is red on ${r.slug} (#${r.last.number}, ${ago(r.last.finished_at)})`,`dev đang đỏ ở ${r.slug} (#${r.last.number}, ${ago(r.last.finished_at)})`,r.last.web_url));
    const nr=[...M.nightlyRuns].reverse();let k=0;while(k<nr.length&&RUNST(nr[k])==='fail')k++;
    if(k)add(k>1?'crit':'warn',`Nightly container build failed ${k} time(s) in a row (last ${ago(nr[0].created_at)})`,`Build container nightly fail ${k} lần liên tiếp (lần cuối ${ago(nr[0].created_at)})`,nr[0].html_url);
    const stale=M.nightly.filter(n=>n.age>th.nightly_stale_h);if(stale.length)add('warn',`${stale.length} nightly release(s) older than ${th.nightly_stale_h} h: ${stale.map(n=>n.tag).join(', ')}`,`${stale.length} bản nightly cũ hơn ${th.nightly_stale_h} giờ: ${stale.map(n=>n.tag).join(', ')}`,'#obs/release');
    if(M.latest){const r=pub[M.latest.tag];if(r){const s=RUNST(r);if(s==='fail')add('crit',`publish.yml failed for ${M.latest.tag}`,`publish.yml fail cho ${M.latest.tag}`,r.html_url);else if(s==='run')add('info',`publish.yml is running for ${M.latest.tag}`,`publish.yml đang chạy cho ${M.latest.tag}`,r.html_url);}}
    const apf=M.prs.filter(p=>p.review==='APPROVED'&&p.bucket==='ci_fail');if(apf.length)add('warn',`${apf.length} approved PR(s) blocked by a failing required check`,`${apf.length} PR đã approve nhưng bị check bắt buộc fail chặn`,'#pr:ci_fail');
    const rd=M.prs.filter(p=>p.bucket==='ready');if(rd.length)add('ok',`${rd.length} PR(s) ready to merge now`,`${rd.length} PR sẵn sàng merge ngay`,'#pr:ready');
    if(M.bk){if(M.bk.waiting>th.waiting_jobs_warn)add('warn',`${M.bk.waiting} Buildkite jobs waiting for an agent`,`${M.bk.waiting} job Buildkite đang chờ agent`,'#obs/ci');
      M.bk.active.filter(b=>!b.started&&(now-ms(b.created))/60000>th.wait_warn_min).slice(0,3).forEach(b=>add('warn',`${b.slug} #${b.num} waiting ${dur((now-ms(b.created))/1000)} to start`,`${b.slug} #${b.num} chờ ${dur((now-ms(b.created))/1000)} chưa chạy`,b.url));}
    if(M.gha.queued>th.gha_queued_warn)add('warn',`${M.gha.queued} GitHub Actions runs queued`,`${M.gha.queued} run GitHub Actions đang xếp hàng`);
    if(!S.mode||!S.mode.gql)add('info','No PR gate data in this snapshot: run observe_collect.py (needs gh login).','Snapshot không có dữ liệu cổng PR: chạy observe_collect.py (cần gh login).');
    if(!S.mode||!S.mode.bk)add('info','No Buildkite data in this snapshot: run observe_collect.py (needs a Buildkite token).','Snapshot không có dữ liệu Buildkite: chạy observe_collect.py (cần Buildkite token).');
    const order={crit:0,warn:1,info:2,ok:3};M.alerts=A.sort((a,b)=>order[a.sev]-order[b.sev]);
    return M;
  }

  // ---------- state ----------
  let M=null,busy=false,lastFetch=0,lastErr=[],showSet=false;
  let auto=store('obsAuto',0),onOpen=store('obsOnOpen',true);
  const F=Object.assign({b:'all',q:'',sort:'updated',base:'dev'},store('obsFilter',{}));
  function use(S){M=model(S);render();}
  async function refresh(){if(CFG.local_only||busy)return;busy=true;renderBar();
    try{const S=await fetchAll();lastErr=S.errors;lastFetch=Date.now();use(S);}catch(e){lastErr=[String(e.message||e)];}finally{busy=false;renderBar();}}

  // ---------- render ----------
  const dot=(st,title,url)=>el(url?'a':'span',{class:'dot s-'+st,title,href:url,target:url?'_blank':null,rel:url?'noopener':null});
  const bkt=b=>el('span',{class:'bkt',style:'background:'+BK[b][3]},BK[b][1+V()]);
  const goto=(href,text)=>el('a',{class:'obs-link',onclick:ev=>{ev.preventDefault();nav(href);}},text);
  function nav(h){if(!h)return;if(h==='#set'){showSet=true;renderBar();const b=$('#obsBar');b&&b.scrollIntoView({behavior:'smooth',block:'center'});return;}
    if(h.startsWith('#pr:')){window.vizNav&&vizNav.show('obs','overlap');return;}
    if(h.startsWith('#obs/')){window.vizNav&&vizNav.show('obs',h.split('/')[1]);return;}
    window.open(h,'_blank','noopener');}

  function renderBar(){const b=$('#obsBar');if(!b)return;b.replaceChildren();if(!M){b.append(el('span',{class:'obs-empty'},T('No data: run observe_collect.py locally.','Chưa có dữ liệu: chạy observe_collect.py ở máy local.')));}
    const S=M&&M.S,live=S&&S.via==='live',age=M?(Date.now()-M.at)/60000:0;
    const lamp=el('span',{class:'lamp '+(busy?'busy':live&&age<15?'live':age>CFG.th.snap_stale_min?'old':'')});
    const st=el('span',{class:'st'},lamp,busy?T('Refreshing…','Đang làm mới…'):S?(live?T('Live','Trực tiếp'):T('Snapshot','Dữ liệu chụp lúc')):'—');
    if(S&&!busy)st.append(el('small',{},`${(d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`)(new Date(M.at))} · ${ago(M.at)}`));
    b.append(st);
    if(S){const src=el('span',{class:'src'});const errs=lastErr.length?lastErr:(S.errors||[]);
      const hasErr=p=>errs.some(e=>e.toLowerCase().includes(p));
      const oldH=(Date.now()-M.at)/36e5,old=!live&&oldH>48,ok=old?'stale':'ok',mk=old?T(` · ${Math.round(oldH/24)} d old`,` · cũ ${Math.round(oldH/24)} ngày`):' ✓';   // round 2 C3 / D5
      src.append(el('span',{class:hasErr('github')||hasErr('search')?'err':ok,title:'GitHub REST'},'GitHub'+(old?mk:'')+(M.gha.rate!=null?T(` · ${fmt(M.gha.rate)} calls left`,` · còn ${fmt(M.gha.rate)} lượt`):'')),
        el('span',{class:S.mode&&S.mode.gql?ok:'off',title:T('PR reviews + checks (GraphQL, needs a token)','Review + check của PR (GraphQL, cần token)')},'PR checks'+(S.mode&&S.mode.gql?mk:T(' · no token',' · chưa có token'))),
        (()=>{const bh=S.bk_at?(Date.now()-Date.parse(S.bk_at))/36e5:oldH,bo=!live&&bh>48;   // Buildkite kept from an older run (no token)
          return el('span',{class:S.mode&&S.mode.bk?(bo?'stale':hasErr('buildkite')?'err':'ok'):'off',title:S.bk_at&&S.bk_at!==S.at?T(`Buildkite data of ${String(S.bk_at).slice(0,16).replace('T',' ')} UTC (no token on this host)`,`Dữ liệu Buildkite lúc ${String(S.bk_at).slice(0,16).replace('T',' ')} UTC (máy này chưa có token)`):''},'Buildkite'+(S.mode&&S.mode.bk?(bo?T(` · ${Math.round(bh/24)} d old`,` · cũ ${Math.round(bh/24)} ngày`):' ✓'):T(' · no token',' · chưa có token')));})());
      if(live&&S.calls)src.append(el('span',{},T(`${S.calls} requests`,`${S.calls} request`)));b.append(src);}
    b.append(el('span',{class:'sp'}));
    if(CFG.local_only){const cp=el('button',{title:T('Copy the command','Chép lệnh'),onclick:()=>{try{navigator.clipboard.writeText(CFG.collect_cmd);cp.textContent='✓';setTimeout(()=>cp.textContent=T('Copy','Chép'),1200);}catch(e){}}},T('Copy','Chép'));
      const web=!/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname)&&location.protocol!=='file:';   // round 2 B3: readers of the web copy cannot run scripts
      b.append(web?el('span',{class:'obs-note',style:'margin:0'},T('Refreshed daily at 07:00 (UTC+7) on the release PC; if it looks old, tell the release owner.','Làm mới 07:00 (UTC+7) hằng ngày trên máy release; nếu thấy cũ, báo release owner.')):el('span',{class:'obs-note',style:'margin:0'},T('Refresh: local run','Làm mới: chạy local'),' ',el('code',{class:'obsraw',style:'font-size:11px'},'observe_collect.py')));if(!web)b.append(cp);}
    else{const sel=el('select',{'aria-label':T('Auto refresh','Tự làm mới'),onchange:e=>{auto=+e.target.value;save('obsAuto',auto);}});
    [[0,T('Auto: off','Tự động: tắt')],[1,T('every 1 min','mỗi 1 phút')],[2,T('every 2 min','mỗi 2 phút')],[5,T('every 5 min','mỗi 5 phút')],[15,T('every 15 min','mỗi 15 phút')]].forEach(([v,t])=>{const o=el('option',{value:v},t);if(v===auto)o.selected=true;sel.append(o);});
    const btn=el('button',{class:'pri',onclick:refresh},T('⟳ Refresh','⟳ Làm mới'));
    b.append(sel,btn,el('button',{onclick:()=>{showSet=!showSet;renderBar();},'aria-expanded':String(showSet)},T('Settings','Cài đặt')));}
    const errs=lastErr.length?lastErr:(S&&S.errors)||[];if(errs.length)b.append(el('div',{class:'obs-errs'},'⚠ '+errs.slice(0,4).map(e=>/^buildkite: no token/i.test(e)?T('Buildkite: no token. Set BUILDKITE_API_TOKEN','Buildkite: thiếu token. Đặt BUILDKITE_API_TOKEN'):e).join(' · ')+(errs.length>4?` (+${errs.length-4})`:'')));
    if(showSet&&!CFG.local_only){const box=el('div',{class:'obs-set'});
      const inp=(k,label,ph)=>{const i=el('input',{type:'password',value:tok[k]||'',placeholder:ph,autocomplete:'off',spellcheck:'false',onchange:e=>{tok[k]=e.target.value.trim();saveTok();}});return el('label',{},label,i);};
      const rem=el('input',{type:'checkbox',onchange:e=>{remember=e.target.checked;saveTok();}});rem.checked=remember;
      const oo=el('input',{type:'checkbox',onchange:e=>{onOpen=e.target.checked;save('obsOnOpen',onOpen);}});oo.checked=onOpen;
      box.append(inp('gh',T('GitHub token (read-only, public repo access is enough)','GitHub token (chỉ đọc, quyền repo public là đủ)'),'github_pat_… / gho_…'),
        inp('bk',T('Buildkite API token (read_builds, read_pipelines)','Buildkite API token (read_builds, read_pipelines)'),'bkua_…'),
        el('label',{style:'display:flex;gap:6px;align-items:center'},rem,T('Remember tokens in this browser','Nhớ token trong trình duyệt này')),
        el('label',{style:'display:flex;gap:6px;align-items:center'},oo,T(`Refresh when this view opens and data is older than ${CFG.th.open_refresh_min} min`,`Tự làm mới khi mở view này và dữ liệu cũ hơn ${CFG.th.open_refresh_min} phút`)),
        el('div',{class:'hint'},T('Tokens never leave this browser: they are sent only to api.github.com and api.buildkite.com. Without "remember" they are dropped when the tab closes. Without a GitHub token: 60 requests/hour (≈3 refreshes) and no PR check data. Team snapshot: run observe_collect.py.',
          'Token không rời khỏi trình duyệt này: chỉ gửi tới api.github.com và api.buildkite.com. Không chọn "nhớ" thì token mất khi đóng tab. Không có GitHub token: 60 request/giờ (≈3 lần làm mới) và không có dữ liệu check của PR. Snapshot cho team: chạy observe_collect.py.')));
      b.append(box);}
  }

  function rTrain(){const w=$('#obsTrain');if(!w||!M)return;w.replaceChildren();const box=el('div',{class:'obs-train'});
    M.versions.forEach(v=>{const ch=el('div',{class:'chain'});const st=v.main.find(t=>!t.rc),first=v.main[0];
      v.main.forEach((t,i)=>{if(i)ch.append(el('span',{class:'arr'},'→'));const r=M.pub[t.tag],s=r?RUNST(r):null;
        const hasTrace=(RP&&RP.release_trace||[]).some(x=>x.tag===t.tag);
        const a=el('a',{class:'tg'+(t.rc?'':' stable')+(s==='fail'?' s-fail':''),href:r?r.html_url:t.url,target:'_blank',rel:'noopener',
          onclick:hasTrace?ev=>{if(!ev.ctrlKey&&!ev.metaKey){ev.preventDefault();openTrace(t.tag);}}:null,
          title:r?(M.pubAll[t.tag]||[r]).map(x=>`publish.yml (${x.event}, attempt ${x.run_attempt||1}): ${x.conclusion||x.status}`).join(' · ')+(hasTrace?' · Click to trace PRs & Error Logs':''):t.tag});
        a.append(el('b',{},t.rc||t.post||'stable'),el('span',{},day(t.at)+(s?' '+({ok:'✓',fail:'✗',run:'…',cancel:'⊘',skip:'–'})[s]:'')));ch.append(a);});
      const sub=st&&first&&first!==st?T(`rc1 → stable: ${Math.round((ms(st.at)-ms(first.at))/864e5)} d`,`rc1 → stable: ${Math.round((ms(st.at)-ms(first.at))/864e5)} ngày`):st?T('stable','stable'):(lr=>lr?T(`Testing ${lr}`,`Đang test ${lr}`):T('Testing','Đang test'))(String((v.main.filter(t=>t.rc).pop()||{}).tag||'').replace(/^.*?(rc\d+)$/,'$1'));
      const row=el('div',{class:'row'},el('div',{class:'ver'},'v'+v.ver,el('small',{},sub)),el('div',{},ch));
      if(v.plat.length){const pl=[...new Set(v.plat.map(t=>t.plat))].sort();row.lastChild.append(el('div',{class:'plat'},T(`+${v.plat.length} platform tags: `,`+${v.plat.length} tag nền tảng: `)+pl.join(', ')));}box.append(row);});
    if(!M.versions.length)box.append(el('div',{class:'obs-empty'},T('No release data.','Không có dữ liệu release.')));w.append(box);
    w.append(el('div',{class:'obs-note',style:'margin-top:8px'},T(`✓ / ✗ = publish.yml result, fetched for the newest ${CFG.tag_runs} main tags. Click any v0.5.7 tag above to trace its PRs, Critical Stage, Test Cases & Error Logs in the Release trace tab.`,`✓ / ✗ = kết quả publish.yml, lấy cho ${CFG.tag_runs} tag chính mới nhất. Bấm vào bất kỳ tag v0.5.7 nào ở trên để truy vết sang PR, Critical Stage, Test Case và Error Log trong tab Truy vết release.`)));}

  function rPub(){const w=$('#obsPub');if(!w||!M)return;w.replaceChildren();
    if(!M.publishJobs.length)w.append(el('div',{class:'obs-empty'},T('No publish run data.','Không có dữ liệu publish run.')));
    M.publishJobs.forEach(({run,jobs})=>{const s=RUNST(run),cnt={};jobs.forEach(j=>{const k=RUNST(j);cnt[k]=(cnt[k]||0)+1;});
      const det=el('details',{class:'rp-foldable',style:'margin:6px 0 8px;padding:8px 12px',open:s==='fail'?'':null});
      const hd=el('summary',{class:'obs-runhd',style:'padding:2px 0'},el('h3',{class:'obs-h3',style:'margin:0'},'publish.yml'),el('b',{},run.head_branch),el('span',{class:'gch s-'+s},run.conclusion||run.status),
        el('span',{style:'font-weight:400'},`${T('started','bắt đầu')} ${ago(run.run_started_at||run.created_at)} · ${T('attempt','lần')} ${run.run_attempt||1} · `+Object.entries(cnt).map(([k,n])=>`${n} ${k}`).join(' · ')),
        el('a',{class:'obs-link',href:run.html_url,target:'_blank',rel:'noopener',onclick:e=>e.stopPropagation()},T('open run ↗','mở run ↗')));
      const g=el('div',{class:'obs-jobs only-bad',style:'margin:8px 0 2px'});[...jobs].sort((a,b)=>({fail:0,run:1,cancel:2,ok:3,skip:4})[RUNST(a)]-({fail:0,run:1,cancel:2,ok:3,skip:4})[RUNST(b)]).forEach(j=>{const d=j.completed_at&&j.started_at?(ms(j.completed_at)-ms(j.started_at))/1000:null;
        g.append(el('a',{href:j.html_url,'data-st':RUNST(j),target:'_blank',rel:'noopener',title:`${j.name}: ${j.conclusion||j.status}`},dot(RUNST(j)),el('span',{class:'n'},j.name),el('span',{class:'t'},d!=null?dur(d):(j.status!=='completed'?j.status:''))));});
      const nBad=jobs.filter(j=>!['ok','skip'].includes(RUNST(j))).length,lab=()=>g.classList.contains('only-bad')?T(`Show all ${jobs.length} jobs`,`Hiện cả ${jobs.length} job`):T('Show failed only','Chỉ hiện job lỗi');
      const tg=el('button',{class:'tr-btn sm',onclick:()=>{g.classList.toggle('only-bad');tg.textContent=lab();}},lab());
      det.append(hd);if(!nBad)det.append(el('div',{class:'obs-note'},T('No failed job.','Không có job lỗi.')));det.append(g,tg);w.append(det);});}
  function rNightly(){const w=$('#obsNightly');if(!w||!M)return;w.replaceChildren(el('h3',{class:'obs-h3'},T('Nightly builds','Build nightly')));
    const runs=el('div',{class:'obs-note'},'nightly_build.yml: ');M.nightlyRuns.forEach(r=>runs.append(dot(RUNST(r),`${day(r.created_at)} · ${r.conclusion||r.status}`,r.html_url)));w.append(runs);
    const t=el('table',{class:'obs-t'}),tb=el('tbody');t.append(el('thead',{},el('tr',{},el('th',{},T('Release tag','Tag release')),el('th',{class:'r'},T('Published','Publish')),el('th',{class:'r'},T('Assets','Asset')),el('th',{},T('Fresh?','Còn mới?')))),tb);
    M.nightly.forEach(n=>{const ok=n.age<=CFG.th.nightly_stale_h;tb.append(el('tr',{},el('td',{},el('a',{href:n.url,target:'_blank',rel:'noopener'},n.tag)),el('td',{class:'r'},ago(n.at)),el('td',{class:'r'},n.assets),
      el('td',{},el('span',{class:'gch '+(ok?'s-ok':'s-fail')},ok?T('fresh','mới'):T(`stale > ${CFG.th.nightly_stale_h} h`,`cũ > ${CFG.th.nightly_stale_h} giờ`)))));});w.append(el('div',{class:'obs-scroll'},t));}

  // ---------- Unified 5-Stage Interactive Flowchart: Release -> PR -> Critical Stage -> Test Case -> Error Log ----------
  // One SVG flowchart (Bezier streams + particles). Every node is clickable: it re-routes the active branch
  // AND focuses the Component Inspector below on that stage (TR_FOCUS 1..5).
  let TR_TAG=store('obsTrTag','v0.5.7rc4'),TR_PR=store('obsTrPr',6208),TR_GATE=store('obsTrGate','g_rc4_amd'),TR_Q='';
  let TR_FOCUS=store('obsTrFocus',4),TR_STEP=-1;
  const TR_ERR=/error|failed|exception|assert|unsatisfiable|inconsistent|denied/i,TR_WARN=/warn|note|computed version/i;
  // Trace Agent (trace_agent_daily.py) works release -> PR and writes outputs/trace_agent/proposals.js after every PR.
  // The page polls that file and redraws the tracer, so agent results land in the UI without a rebuild.
  // RP.trace_agent is the snapshot embedded at build time (fallback, e.g. on gh-pages).
  let TR_LIVE=null,TR_POLL_FAIL=0;const TA_SRC='outputs/trace_agent/proposals.js';
  function trAgent(){const b=Object.assign({updated_at:'',min_version:[0,5,7],releases:{},prs:{}},(RP&&RP.trace_agent)||{});return TR_LIVE&&TR_LIVE.updated_at>b.updated_at?TR_LIVE:b;}
  function trInScope(tag){const m=/^v?(\d+)\.(\d+)\.(\d+)/.exec(tag||'');if(!m)return false;const mv=trAgent().min_version||[0,5,7];for(let i=0;i<3;i++){const d=+m[i+1]-mv[i];if(d)return d>0;}return true;}
  window.onTraceAgent=d=>{if(!d||!d.updated_at||(TR_LIVE&&TR_LIVE.updated_at===d.updated_at))return;const before=trAgent().updated_at;TR_LIVE=d;
    if(d.updated_at>before){const a=document.activeElement;if(!(a&&a.id==='trPrQ'))rTracer();}};
  function trPoll(){if(TR_POLL_FAIL>=3)return;const s=document.createElement('script');s.src=TA_SRC+'?t='+Date.now();
    s.onload=()=>{TR_POLL_FAIL=0;s.remove();};s.onerror=()=>{TR_POLL_FAIL++;s.remove();};document.head.append(s);}
  setTimeout(trPoll,1200);
  setInterval(()=>{const w=document.getElementById('obsTracer');if(!document.hidden&&w&&w.offsetParent)trPoll();},30000);
  function trSet(o){
    if('tag' in o){TR_TAG=o.tag;save('obsTrTag',TR_TAG);}
    if('pr' in o){TR_PR=o.pr;save('obsTrPr',TR_PR);}
    if('gate' in o){TR_GATE=o.gate;save('obsTrGate',TR_GATE);}
    if('focus' in o){TR_FOCUS=o.focus;save('obsTrFocus',TR_FOCUS);}
    if('step' in o)TR_STEP=o.step;
    rTracer();if(o.anim!==false)triggerFlowAnim();
  }
  function triggerFlowAnim(){
    const b=$('#obsTracer .tr-flow-box');if(!b)return;
    clearTimeout(b._rp);b.classList.remove('animating','replay');void b.offsetWidth;b.classList.add('animating','replay');
    b._rp=setTimeout(()=>b.classList.remove('replay'),2600);
    TR_T0=performance.now();
  }
  function openTrace(tag,prNum,gateId){
    const list=(RP&&RP.release_trace)||[];
    const rel=list.find(x=>x.tag===tag)||list[0];if(!rel)return;
    const pr=(prNum&&rel.prs.find(p=>p.num===prNum))||rel.prs[0];
    const gt=(gateId&&rel.gates.find(g=>g.id===gateId))||(pr&&rel.gates.find(g=>g.log_id===pr.log_id))||rel.gates[0];
    if(window.vizNav)vizNav.show('obs','trace',false);
    trSet({tag:rel.tag,pr:pr?pr.num:0,gate:gt?gt.id:'',focus:gateId?4:prNum?2:1,step:-1});
    setTimeout(()=>{const w=$('#obsTracer');if(w)w.scrollIntoView({behavior:'smooth',block:'start'});},80);
  }
  // CPU Test Explorer (#cpu/explore) only knows the files in its CPU-run snapshot (cpuData.files).
  let TR_EXF=null;
  function trExFiles(){if(!TR_EXF){try{TR_EXF=new Set(JSON.parse(document.getElementById('cpuData').textContent).files.map(f=>f[0]));}catch(e){TR_EXF=new Set();}}return TR_EXF;}
  function trExTarget(tf){
    if(!tf||!tf.startsWith('tests/'))return null;const S=trExFiles();
    if(S.has(tf))return {kind:'file',q:tf};
    const dir=tf.replace(/[^/]+$/,'');
    return dir&&dir!=='tests/'&&[...S].some(p=>p.startsWith(dir))?{kind:'dir',q:dir}:null;
  }
  function jumpExplorer(testFile){
    const t=trExTarget(testFile);if(!t||!window.vizNav)return;
    if(t.kind==='file'&&window.cpuOpenFile){window.cpuOpenFile(t.q);return;}
    vizNav.show('cpu','explore',true);
    setTimeout(()=>{const q=document.getElementById('exQ');if(q){q.value=t.q;q.dispatchEvent(new Event('input'));q.scrollIntoView({behavior:'smooth',block:'center'});}},60);
  }

  // particles on the tracer streams: one rAF loop, idle while the tab is hidden; restart = reset TR_T0
  let TR_T0=performance.now();const TR_RM=window.matchMedia?matchMedia('(prefers-reduced-motion: reduce)'):{matches:false};
  function trParticles(now){requestAnimationFrame(trParticles);const w=document.getElementById('obsTracer');if(document.hidden||!w||!w.offsetParent||TR_RM.matches)return;
    w.querySelectorAll('.tr-particle').forEach(c=>{if(!c._path)return;const t=(now-TR_T0)/1000-c._begin;if(t<0){c.setAttribute('visibility','hidden');return;}
      const L=c._len||(c._len=c._path.getTotalLength());if(!L)return;const pt=c._path.getPointAtLength(L*((t/c._dur)%1));
      c.setAttribute('cx',pt.x.toFixed(1));c.setAttribute('cy',pt.y.toFixed(1));c.setAttribute('visibility','visible');});}
  requestAnimationFrame(trParticles);
  function rTracer(){
    const w=$('#obsTracer');if(!w)return;TR_T0=performance.now();
    const hadQ=document.activeElement&&document.activeElement.id==='trPrQ';
    w.replaceChildren();
    const list=(RP&&RP.release_trace)||[];
    if(!list.length){w.append(el('div',{class:'obs-empty'},T('No release trace data.','Chưa có dữ liệu truy vết release.')));return;}
    const rel=list.find(x=>x.tag===TR_TAG)||list[0];TR_TAG=rel.tag;
    {const ua=trAgent().updated_at,h=(Date.now()-Date.parse(ua))/36e5;w.append(el('div',{class:'obs-note',style:'margin:0 0 8px;font-weight:600'+(h>24?';color:var(--warning)':'')},(h>24?'⚠ ':'')+T(`Trace Agent: updated ${ua?dur((Date.now()-Date.parse(ua))/1000)+' ago':'never'}.`,`Trace Agent: cập nhật ${ua?dur((Date.now()-Date.parse(ua))/1000)+' trước':'chưa bao giờ'}.`)));}
    const qq=TR_Q.trim().toLowerCase();
    const filtPrs=rel.prs.filter(p=>!qq||(`#${p.num} ${p.title} ${p.area} ${(p.files||[]).join(' ')}`).toLowerCase().includes(qq));
    const selPr=rel.prs.find(p=>p.num===TR_PR)||filtPrs[0]||rel.prs[0];
    TR_PR=selPr?selPr.num:0;
    const selGate=rel.gates.find(g=>g.id===TR_GATE)||(selPr&&rel.gates.find(g=>g.log_id===selPr.log_id))||rel.gates[0];
    TR_GATE=selGate?selGate.id:'';
    const logId=(selGate&&selGate.log_id)||(selPr&&selPr.log_id)||Object.keys(rel.logs)[0];
    const logObj=rel.logs[logId]||Object.values(rel.logs)[0]||{title:'—',job:'',lines:[],why:['—','—'],fix:['—','—'],repro:''};
    const FOC=[1,2,3,4,5].includes(TR_FOCUS)?TR_FOCUS:4;
    // Fix proposals for releases >= 0.5.7 come ONLY from the daily Trace Agent (trace_agent_daily.py).
    const AG=trAgent(),inScope=trInScope(rel.tag),relAg=AG.releases[rel.tag];
    const agOf=p=>p?AG.prs[`${rel.tag}::${p.num}`]:null,nFail=a=>a&&a.checks?a.checks.failed:null;
    // Merge-required checks (branch protection of dev). A failed check outside this list does not block a merge.
    const RQ=(RP&&RP.required_checks)||{names:[]},REQ=new Set(RQ.names||[]);
    const nReq=a=>a&&a.checks?a.checks.fail.filter(f=>REQ.has(f.name)).length:null;
    // Real source beats hand-entered data: the Trace Agent verdict (or green CI) overrides the hand-entered `suspect` flag.
    const susSrc=p=>{const a=agOf(p),pr=a&&a.proposal;return pr&&pr.ok?'agent':(a&&a.checks&&!a.checks.failed)?'ci':'hand';};
    const susOf=p=>{if(!p)return false;const a=agOf(p),pr=a&&a.proposal,s=susSrc(p);return s==='agent'?(pr.impact==='blocks-release'||pr.impact==='shipped-bug'):s==='ci'?false:!!p.suspect;};
    const prBadge=p=>{const a=agOf(p),nf=nFail(a);if(nf>0){const r=nReq(a);return [((a.proposal||{}).status==='ok'?'🤖 ':'CI ')+'✗'+nf+(r===0?' opt':''),r===0?'var(--warning)':'var(--critical)'];}
      return nf===0?['CI ✓','var(--good)']:(susOf(p)?['CRITICAL','var(--critical)']:[p.sha,'var(--series-1)']);};
    const selAg=agOf(selPr),prop=selAg&&selAg.proposal,gateOk=!!(selGate&&selGate.status==='ok');
    const propOk=!!(prop&&prop.ok),selGreen=nFail(selAg)===0;
    const whyTxt=propOk&&prop.root_cause[V()]?prop.root_cause[V()]:logObj.why[V()];
    const fixTxt=inScope?(propOk?prop.fix[V()]:''):logObj.fix[V()];
    const reproTxt=(propOk&&prop.repro)||logObj.repro;
    const AGENT_CMD=`python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_daily.py --tag ${rel.tag}${selPr?` --pr ${selPr.num}`:''}`;
    const prStep=selPr&&selPr.flow_idx!=null?selPr.flow_idx:rel.crit_idx;
    const stBadge=s=>el('span',{class:'gch s-'+(s==='fail'?'fail':s==='warn'?'run':'ok')},s==='fail'?'FAIL':s==='warn'?'WARN':'PASS');
    const stCol=s=>s==='fail'?'var(--critical)':s==='warn'?'var(--warning)':'var(--good)';
    const ghPr=n=>`https://github.com/${CFG.repo}/pull/${n}`;
    const pickPr=p=>{const mg=rel.gates.find(g=>g.log_id===p.log_id)||rel.gates[0];trSet({pr:p.num,gate:mg?mg.id:TR_GATE,focus:2});};
    const pickRel=r=>trSet({tag:r.tag,pr:r.prs[0]?r.prs[0].num:0,gate:r.gates[0]?r.gates[0].id:'',focus:1,step:-1});

    // ----- header: Replay + Copy Daily Report -----
    const copyBtn=el('button',{class:'tr-btn pri',onclick:()=>{
      const md=`### Daily Release & CI Triage — ${rel.tag} (${rel.title[V()]})\n`+
        `- **Release Status**: \`${rel.status.toUpperCase()}\` (${rel.badge})\n`+
        `- **${susOf(selPr)?'Suspect':'Traced'} PR**: \`#${selPr.num}\` — ${selPr.title} (\`${selPr.sha}\`, area: \`${selPr.area}\`)\n`+
        `- **Critical Stage**: \`${rel.flow[rel.crit_idx][V()]}\` · Files: \`${(selPr.files||[]).join(', ')}\`\n`+
        `- **Failing Gate / Test Case**: \`${selGate?selGate.name:'—'}\` (\`${selGate?selGate.test_file:''}\`)\n`+
        `- **Error Log (${logObj.job})**:\n\`\`\`text\n${logObj.lines.join('\n')}\n\`\`\`\n`+
        (inScope&&selAg&&selAg.checks?`- **PR #${selPr.num} CI checks**: ${selAg.checks.passed} passed, ${selAg.checks.failed} failed${selAg.checks.fail.length?' ('+selAg.checks.fail.map(f=>f.name).join('; ')+')':''}\n`:'')+
        `- **Root Cause**${propOk?` (Trace Agent, PR #${selPr.num})`:inScope?' (manual triage, not agent-verified)':''}: ${whyTxt}\n`+
        `- **Actionable Fix**: ${inScope?(propOk?`${fixTxt} _(Trace Agent on PR #${selPr.num}, ${prop.run_at}, option ${prop.option}, confidence ${prop.confidence}${prop.fix_pr?`, fix PR #${prop.fix_pr}`:''}${prop.stale?', STALE':''})_`:(selGreen?`— (PR #${selPr.num}: CI green, nothing to fix)`:'PENDING — awaiting Trace Agent')):fixTxt}\n`+
        `- **Local Repro**: \`${reproTxt}\`\n`;
      navigator.clipboard&&navigator.clipboard.writeText(md);
      copyBtn.textContent=T('✓ Copied Daily Report!','✓ Đã copy Báo cáo Ngày!');
      setTimeout(()=>{copyBtn.textContent=T('📋 Copy Daily Report','📋 Copy Báo cáo Ngày');},1800);
    }},T('📋 Copy Daily Report','📋 Copy Báo cáo Ngày'));
    const replayBtn=el('button',{class:'tr-btn',onclick:triggerFlowAnim},T('▶ Replay Flow Animation','▶ Chạy lại Animation Luồng'));
    const hd=el('div',{class:'tr-hd'},
      el('div',{},
        el('h3',{},'⚡ ',T('Release → PR → Critical Stage → Test Case → Error Log Tracer','Truy vết Luồng Động: Release → PR → Critical Stage → Test Case → Error Log')),
        el('p',{},T('Click a node to see its details.','Bấm một node để xem chi tiết.'))
      ),
      el('div',{class:'tr-ctrl'},agentSum(),replayBtn,copyBtn)
    );
    function agentSum(){
      if(!inScope)return null;
      const a=relAg;
      return el('span',{class:'tr-agent-sum',title:T('Trace Agent: release → PR CI checks → trace of failed PRs (PR_FAILURE_TRACE_AGENT_PROMPT.md)','Trace Agent: release → kiểm tra CI từng PR → truy vết PR bị lỗi (PR_FAILURE_TRACE_AGENT_PROMPT.md)')},'🤖 ',
        a?T(`Trace Agent ${rel.tag}: ${a.checked}/${a.prs} PRs checked · ${a.failing} failing · ${a.proposed} proposed`,`Trace Agent ${rel.tag}: ${a.checked}/${a.prs} PR đã kiểm · ${a.failing} lỗi · ${a.proposed} đã đề xuất`):T('Trace Agent: not run yet','Trace Agent: chưa chạy'),
        a&&a.last_run?el('span',{class:'obsraw',style:'color:var(--text-muted)'},` · ${a.last_run.slice(0,16).replace('T',' ')}`):null,
        (()=>{const rs=Object.entries(AG.releases||{}).filter(([k])=>trInScope(k)).map(([,v])=>v);if(rs.length<2)return null;
          const f=rs.reduce((s,v)=>s+(v.failing||0),0),pp=rs.reduce((s,v)=>s+(v.proposed||0),0);
          return el('span',{style:'margin-left:4px;padding-left:7px;border-left:1px solid var(--border)'},T(`all ≥ v0.5.7: ${pp}/${f} failing PRs proposed`,`mọi release ≥ v0.5.7: ${pp}/${f} PR lỗi đã đề xuất`));})(),
        TR_LIVE?el('span',{style:'color:var(--good)',title:TA_SRC},' ● live'):null);
    }

    // ----- the single SVG flowchart -----
    const W=1140,H=355;
    const svg=sv('svg',{viewBox:`0 0 ${W} ${H}`,class:'tr-flow-svg',role:'group','aria-label':T('Release to Error Log flowchart','Flowchart từ Release tới Error Log')});
    const colLayer=sv('g',{}),pipeLayer=sv('g',{}),nodeLayer=sv('g',{});
    svg.append(colLayer,pipeLayer,nodeLayer);
    const shownPrs=(filtPrs.length?filtPrs:rel.prs).slice(0,4);
    if(selPr&&shownPrs.length&&!shownPrs.some(p=>p.num===selPr.num))shownPrs[shownPrs.length-1]=selPr;
    [[14,174,T('1 · RELEASE / RC TAG','1 · BẢN RELEASE / RC')],
     [232,196,T(`2 · PRs (#) · ${filtPrs.length}/${rel.total_prs}`,`2 · PR (#) · ${filtPrs.length}/${rel.total_prs}`)],
     [472,198,T('3 · CRITICAL STAGE','3 · CRITICAL STAGE')],
     [714,198,T('4 · CPU & GPU TEST CASES','4 · CPU & GPU TEST CASE')],
     [956,170,T('5 · ERROR LOG & FIX','5 · ERROR LOG & HƯỚNG FIX')]
    ].forEach(([x,cw,lbl],i)=>{
      const g=sv('g',{class:'tr-col'+(FOC===i+1?' focus':''),'data-col':String(i+1)});
      g.append(sv('rect',{x,y:6,width:cw,height:H-12,rx:10}));
      const tx=sv('text',{x:x+10,y:24,class:'tr-col-lbl'});tx.textContent=lbl;g.append(tx);
      g.addEventListener('click',()=>trSet({focus:i+1,anim:false}));
      colLayer.append(g);
    });
    let pIdx=0;
    function addStream(x1,y1,x2,y2,mode,dur,begin){
      const cx1=Math.round(x1+(x2-x1)*0.48),cx2=Math.round(x1+(x2-x1)*0.52);
      const d=`M${x1},${y1} C${cx1},${y1} ${cx2},${y2} ${x2},${y2}`;
      pipeLayer.append(sv('path',{d,class:'tr-pipe-bg'}));
      const col=x2<300?2:x2<600?3:x2<850?4:5;
      const st=sv('path',{d,class:'tr-stream'+(mode==='crit'?' crit':mode==='dim'?' dim':''),'data-col':String(col)});pipeLayer.append(st);
      if(mode!=='dim'){
        // moved by trParticles() (JS), not SMIL: SMIL <set>/<animateMotion> with a late `begin` never fired after a redraw or seek
        const c=sv('circle',{r:mode==='crit'?'4.5':'3.8',class:'tr-particle'+(mode==='crit'?' crit':''),visibility:'hidden'});
        c._path=st;c._dur=parseFloat(dur||'1.4')||1.4;c._begin=parseFloat(begin||'0')||0;
        pipeLayer.append(c);pIdx++;
      }
    }
    // stage: 1..5 · on: part of active branch · cls: sel|crit · focus: this exact node is what the inspector shows
    function addNode(stage,x,y,nw,nh,o,onClick){
      const g=sv('g',{class:'tr-fnode obsraw'+(o.on?' on':'')+(o.cls?' '+o.cls:'')+(o.focus?' focus':''),'data-stage':String(stage),tabindex:'0',role:'button','aria-label':`${stage}: ${o.l1}`});
      g.append(sv('rect',{x:x-3,y:y-3,width:nw+6,height:nh+6,rx:10,class:'ring'}));
      g.append(sv('rect',{x,y,width:nw,height:nh,rx:8,class:'bx'}));
      const bw0=o.badge?Math.max(30,o.badge.length*6.2+10)+6:0,maxC=Math.max(6,Math.floor((nw-15-bw0)/6.7));
      const t1=sv('text',{x:x+9,y:y+18,class:'t1'});t1.textContent=o.l1.length>maxC?o.l1.slice(0,maxC-1)+'…':o.l1;g.append(t1);
      if(o.l2){const t2=sv('text',{x:x+9,y:y+34,class:'t2'});t2.textContent=o.l2.length>28?o.l2.slice(0,27)+'…':o.l2;g.append(t2);}
      (o.extra||[]).forEach(([ty,txt,st])=>{const t=sv('text',{x:x+9,y:y+ty,style:st});t.textContent=txt;g.append(t);});
      if(o.badge){
        const bw=Math.max(30,o.badge.length*6.2+10),bx=x+nw-bw-6,by=y+6;
        g.append(sv('rect',{x:bx,y:by,width:bw,height:15,rx:4,style:`fill:${o.badgeCol};stroke:none`}));
        const bt=sv('text',{x:bx+bw/2,y:by+11,'text-anchor':'middle',style:'font:700 9px ui-monospace,Consolas,monospace;fill:#fff'});
        bt.textContent=o.badge;g.append(bt);
      }
      const tt=sv('title',{});tt.textContent=o.tip||o.l1;g.append(tt);
      g.addEventListener('click',onClick);
      g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onClick();}});
      nodeLayer.append(g);
    }
    // col 1: releases
    const rIdx=Math.max(0,list.findIndex(r=>r.tag===rel.tag)),rY=i=>40+i*60;
    list.forEach((r,i)=>{
      const on=i===rIdx;
      addNode(1,22,rY(i),158,48,{on,cls:on?(r.status==='fail'?'crit':'sel'):'',focus:on&&FOC===1,l1:r.tag,l2:r.title[V()],badge:r.status.toUpperCase(),badgeCol:stCol(r.status),
        tip:`${r.tag} · ${r.badge}`},()=>r.tag===rel.tag?trSet({focus:1,anim:false}):pickRel(r));
    });
    const selRY=rY(rIdx)+24;
    // col 2: PRs
    const pY=i=>42+i*74;let selPY=pY(0)+26;
    shownPrs.forEach((p,i)=>{
      const y=pY(i),on=selPr&&p.num===selPr.num;if(on)selPY=y+26;
      addStream(180,selRY,240,y+26,on?(susOf(p)?'crit':'act'):'dim',on?'1.2s':'2s','0s');
      addNode(2,240,y,180,52,{on,cls:on?(susOf(p)?'crit':'sel'):'',focus:on&&FOC===2,l1:`#${p.num} · ${p.area}`,l2:p.title,badge:prBadge(p)[0],badgeCol:prBadge(p)[1],
        tip:`#${p.num} ${p.title}`},()=>on?trSet({focus:2,anim:false}):pickPr(p));
    });
    if(!shownPrs.length)selPY=selRY;
    // col 3: 4-step critical stage
    const fY=i=>42+i*74;
    rel.flow.forEach((step,i)=>{
      const y=fY(i),isCrit=i===rel.crit_idx,isAct=i===prStep;
      addStream(420,selPY,480,y+24,isCrit?'crit':isAct?'act':'dim','1.3s','.35s');
      if(i>0)pipeLayer.append(sv('path',{d:`M571,${fY(i-1)+48} L571,${y}`,class:'tr-stream'+(isCrit?' crit':''),'data-col':'3'}));
      const picked=FOC===3&&(TR_STEP===i||(TR_STEP<0&&isCrit));
      addNode(3,480,y,182,48,{on:isCrit||isAct,cls:isCrit?'crit':isAct?'sel':'',focus:picked,l1:step[V()],
        l2:isCrit?T('Bottleneck stage','Khâu điểm nghẽn'):(isAct&&selPr&&selPr.files&&selPr.files[0])||'',badge:isCrit?'BOTTLENECK':isAct&&selPr?`#${selPr.num}`:'',badgeCol:isCrit?'var(--critical)':'var(--series-1)'},
        ()=>trSet({focus:3,step:i,anim:false}));
    });
    const critY=fY(rel.crit_idx)+24;
    // col 4: CPU & GPU test cases / gates
    const gates=rel.gates.slice(0,4);
    if(selGate&&gates.length&&!gates.some(g=>g.id===selGate.id))gates[gates.length-1]=selGate;
    const gY=i=>46+i*(gates.length<=3?92:72);let selGY=gY(0)+26;
    gates.forEach((g,i)=>{
      const y=gY(i),on=selGate&&g.id===selGate.id;if(on)selGY=y+26;
      addStream(662,critY,722,y+26,on?(g.status==='fail'?'crit':'act'):'dim','1.25s','.7s');
      addNode(4,722,y,182,52,{on,cls:on?(g.status==='fail'?'crit':'sel'):'',focus:on&&FOC===4,l1:g.name,l2:(g.test_missing?'⚠ ':'')+(g.test_file||g.kind),badge:g.status.toUpperCase(),badgeCol:stCol(g.status),
        tip:`${g.kind} · ${g.name}`},()=>on?trSet({focus:4,anim:false}):trSet({gate:g.id,focus:4}));
    });
    // col 5: error log node
    const termY=118,firstErr=(logObj.lines||[]).find(l=>TR_ERR.test(l))||(logObj.lines||[])[0]||'';
    const lst=selGate?selGate.status:rel.status;
    addStream(904,selGY,964,termY+52,lst==='ok'?'act':'crit','1s','1.05s');
    addNode(5,964,termY,154,104,{on:true,cls:lst==='ok'?'sel':'crit',focus:FOC===5,l1:'ERROR LOG',l2:logObj.title,badge:lst.toUpperCase(),badgeCol:stCol(lst),
      extra:[[56,firstErr.slice(0,24)+'…','font:600 9.5px ui-monospace,Consolas,monospace;fill:var(--critical)'],[76,fixTxt?(inScope?'🤖 ':'🛠️ ')+fixTxt.slice(0,22)+'…':selGreen?(lst==='ok'?'✓ '+T('PR CI green','CI của PR xanh'):'⚠ '+T('gate ✗ · this PR CI ✓','gate ✗ · CI PR này ✓')):'⏳ '+T('awaiting Trace Agent','chờ Trace Agent'),'font:9.5px system-ui,sans-serif;fill:'+(fixTxt||(selGreen&&lst==='ok')?'var(--good)':'var(--warning)')]],
      tip:logObj.title},()=>trSet({focus:5,anim:false}));
    const flow=el('div',{class:'tr-flow-box animating'},svg);

    // ----- stage pills (same 5 components, shows the active branch) -----
    const pillVal=[rel.tag,selPr?`#${selPr.num}`:'—',rel.flow[TR_STEP>=0&&TR_STEP<rel.flow.length?TR_STEP:rel.crit_idx][V()],selGate?selGate.name:'—',lst.toUpperCase()];
    const pillLbl=[T('Release','Release'),T('PR','PR'),T('Stage','Stage'),T('Test case','Test case'),T('Error log','Error log')];
    const pills=el('div',{class:'tr-pills',role:'toolbar','aria-label':T('Inspector stage','Chọn stage để xem chi tiết')});
    pillLbl.forEach((lb,i)=>pills.append(el('button',{class:'tr-pill'+((i===4&&lst!=='ok')||(i===0&&rel.status==='fail')?' bad':''),'aria-pressed':String(FOC===i+1),'data-stage':String(i+1),
      onclick:()=>trSet({focus:i+1,anim:false})},el('span',{class:'n'},String(i+1)),lb,el('span',{class:'v obsraw'},pillVal[i]))));

    // ----- Component Inspector -----
    const kv=rows=>{const d=el('dl',{class:'tr-kv'});rows.filter(Boolean).forEach(([k,v])=>d.append(el('dt',{},k),el('dd',{},v)));return d;};
    const ipHd=(n,lbl,right)=>el('div',{class:'tr-ip-hd'},el('span',{},el('span',{class:'step-num'},String(n)),lbl),right||null);
    const linkBtn=(href,txt)=>el('a',{class:'tr-btn sm',href,target:'_blank',rel:'noopener'},txt);
    const exploreBtn=tf=>{
      const t=trExTarget(tf);
      if(t)return el('button',{class:'tr-btn sm',onclick:()=>jumpExplorer(tf),title:t.q},t.kind==='file'?T('🔍 Explore in CPU Test Explorer →','🔍 Mở trong Khám phá Test CPU →'):T('🔍 Explore this folder in CPU Test Explorer →','🔍 Mở thư mục này trong Khám phá Test CPU →'));
      return tf&&tf.startsWith('tests/')?el('span',{class:'tr-sub',style:'color:var(--warning)'},'⚠ ',el('span',{class:'obsraw'},tf),' ',T('is not in the CPU Test Explorer snapshot (GPU-only test, or path not in the repo).','không có trong snapshot Khám phá Test CPU (test chỉ chạy GPU, hoặc đường dẫn không có trong repo).')):null;};
    const fileList=(title,files,click)=>{const b=el('div',{class:'tr-files'},el('b',{style:'font-size:11px;color:var(--text-primary)'},title));
      const miss=new Set((selPr&&selPr.missing)||[]);
      (files||[]).forEach(f=>{const m=miss.has(f),c=!m&&click&&(click!==jumpExplorer||trExTarget(f));b.append(el('div',{class:'tr-file obsraw'+(c?' lnk':'')+(m?' miss':''),onclick:c?()=>click(f):null,title:m?`not in the repo at ${rel.ref}`:c?'':(click===jumpExplorer?'not in CPU Test Explorer':''),style:m?'color:var(--warning)':null},(m?'⚠ ':c?'🔍 ':'')+f,m?el('span',{class:'tr-sub'},' · ',T(`not in repo at ${rel.ref} (hand-entered)`,`không có trong repo ở ${rel.ref} (nhập tay)`)):null));});
      if(!(files||[]).length)b.append(el('div',{class:'tr-sub',style:'color:var(--text-muted)'},T('none','không có')));return b;};
    function termBox(){
      const box=el('div',{class:'tr-log-lines'});
      (logObj.lines||[]).forEach(ln=>box.append(el('div',{class:'tr-log-ln obsraw'+(TR_ERR.test(ln)?' err':TR_WARN.test(ln)?' warn':'')},ln)));
      return el('div',{class:'tr-term'},
        inScope?el('div',{class:'tr-term-note',style:'color:#e3b341;font-size:11.5px;font-weight:600'},el('span',{class:'gch s-run',style:'margin-right:6px'},T('MANUAL','NHẬP TAY')),'⚠ ',T('Hand-entered log excerpt, not fetched from the job.','Đoạn log nhập tay, không lấy từ job.'),
          ...((selAg&&selAg.checks&&selAg.checks.fail.length)?[' ',T('Real failed job: ','Job lỗi thật: '),el('a',{href:selAg.checks.fail[0].link,target:'_blank',rel:'noopener',class:'obsraw',style:'color:#58a6ff'},selAg.checks.fail[0].name+' ↗')]:[])):null,
        el('div',{class:'tr-term-hd'},
          el('span',{class:'tr-term-dots'},el('i',{style:'background:#ff5f56'}),el('i',{style:'background:#ffbd2e'}),el('i',{style:'background:#27c93f'})),
          el('span',{class:'obsraw',style:'font-weight:650;color:#c9d1d9'},logObj.title),
          el('span',{class:'obsraw'},logObj.job)),
        box);
    }
    const OPT={R:['Rerun','Chạy lại'],A:['Revert culprit','Revert commit gây lỗi'],B:['Fix the test','Sửa test'],C:['Fix production code','Sửa code'],D:['Change CI env','Đổi môi trường CI'],Q:['Quarantine','Cách ly test']};
    const ago=iso=>{const h=(Date.now()-Date.parse(iso))/36e5;if(!isFinite(h))return '';return (h<1?'<1h':h<48?Math.round(h)+'h':Math.round(h/24)+'d')+T(' ago',' trước');};
    const whyLbl=()=>propOk?T('Root cause (Trace Agent): ','Nguyên nhân gốc (Trace Agent): '):inScope?T('Root cause (manual triage, not agent-verified): ','Nguyên nhân gốc (triage thủ công, chưa qua agent): '):T('Root cause: ','Nguyên nhân gốc: ');
    const checksBox=a=>{
      if(!a||!a.checks)return null;const c=a.checks;
      const b=el('div',{class:'tr-files'},el('b',{style:'font-size:11px;color:var(--text-primary)'},T('CI checks on the PR head','CI checks trên commit cuối của PR'),' ',
        el('span',{class:'obsraw',style:'font-weight:400;color:var(--text-muted)'},`✓ ${c.passed} · ✗ ${c.failed} · … ${c.pending} / ${c.total}`)));
      c.fail.forEach(f=>{const rq=REQ.has(f.name);b.append(el('a',{class:'tr-file obsraw lnk',href:f.link,target:'_blank',rel:'noopener',style:'color:'+(rq?'var(--critical)':'var(--warning)')},`✗ ${f.name} ↗`,' ',el('span',{class:'gch '+(rq?'s-fail':'s-run')},rq?T('required for merge','bắt buộc để merge'):T('not required for merge','không bắt buộc để merge'))));});
      if(c.fail.length)b.append(el('div',{class:'tr-sub',style:'color:var(--text-muted)'},T('Required for merge on dev: ','Bắt buộc để merge vào dev: '),el('span',{class:'obsraw'},(RQ.names||[]).join(' · ')+` (${RQ.source||''}, ${RQ.as_of||''})`),' ',T('A failed optional check can still matter for a release gate.','Check không bắt buộc bị lỗi vẫn có thể quan trọng với cổng release.')));
      return b;};
    const othersList=()=>{
      const xs=rel.prs.filter(p=>p!==selPr&&nFail(agOf(p))>0);if(!xs.length)return null;
      const ch=el('div',{class:'tr-chips'});
      xs.forEach(p=>{const a=agOf(p),ok=(a.proposal||{}).status==='ok';ch.append(el('button',{class:'tr-chip obsraw crit',title:p.title,onclick:()=>pickPr(p)},`#${p.num} ✗${a.checks.failed}${ok?' 🤖':''}`));});
      return el('div',{},el('b',{},T('Other PRs in this release with failed checks:','PR khác trong release có check lỗi:')),ch);};
    function agentBlock(full){
      if(!inScope||!selPr)return null;
      const pn=`#${selPr.num}`;
      const cmdRow=()=>{const cp=el('button',{class:'tr-btn sm',onclick:()=>{navigator.clipboard&&navigator.clipboard.writeText(AGENT_CMD);cp.textContent='✓';setTimeout(()=>{cp.textContent=T('Copy','Copy');},1200);}},T('Copy','Copy'));
        return el('details',{class:'td-ops'},el('summary',{},T('For operators: run the agent','Cho người vận hành: chạy agent')),el('div',{class:'tr-repro'},el('span',{class:'obsraw'},'$ '+AGENT_CMD),cp));};
      if(!selAg||!selAg.checks)return el('div',{class:'tr-agent pending'},
        el('div',{class:'tr-agent-hd'},'⏳ ',el('b',{},T(`PR ${pn} not checked by Trace Agent yet`,`PR ${pn} chưa được Trace Agent kiểm`))),
        el('div',{},T('Trace Agent goes release → PR: it reads each PR’s CI checks, then traces PRs with failed checks using PR_FAILURE_TRACE_AGENT_PROMPT.md. From v0.5.7 on, fixes are shown only from it.','Trace Agent đi theo release → PR: đọc CI check của từng PR, rồi truy vết PR có check lỗi bằng PR_FAILURE_TRACE_AGENT_PROMPT.md. Từ v0.5.7 trở đi, hướng fix chỉ lấy từ đây.')),
        full?cmdRow():null,full?othersList():null);
      if(!selAg.checks.failed&&!prop)return el('div',{class:'tr-agent ok'},
        el('div',{class:'tr-agent-hd'},'✓ ',el('b',{},T(`PR ${pn}: all ${selAg.checks.passed} CI checks passed — nothing to fix on this PR.`,`PR ${pn}: cả ${selAg.checks.passed} CI check đều xanh — không có gì cần fix ở PR này.`))),
        full?othersList():null);
      if(!prop)return el('div',{class:'tr-agent pending'},
        el('div',{class:'tr-agent-hd'},'⏳ ',el('b',{},T(`PR ${pn}: ${selAg.checks.failed} failed check(s) — awaiting trace`,`PR ${pn}: ${selAg.checks.failed} check lỗi — đang chờ truy vết`))),
        full?checksBox(selAg):null,full?cmdRow():null);
      const when=el('span',{class:'m obsraw'},`${prop.run_at.slice(0,16).replace('T',' ')} · ${ago(prop.run_at)}`);
      if(!propOk)return el('div',{class:'tr-agent err'},
        el('div',{class:'tr-agent-hd'},'⚠️ ',el('b',{},T(`Trace Agent run on ${pn} failed — no proposal yet`,`Lần chạy Trace Agent trên ${pn} bị lỗi — chưa có đề xuất`)),when),
        full&&prop.error?el('div',{class:'obsraw',style:'font:10.5px ui-monospace,Consolas,monospace;color:var(--text-secondary)'},prop.error.slice(-240)):null,
        full?cmdRow():null);
      const o=OPT[prop.option];
      const IMP={'blocks-release':['blocks release','chặn release'],'shipped-bug':['bug shipped','bug đã vào release'],none:['no release impact','không ảnh hưởng release']}[prop.impact];
      const hd=el('div',{class:'tr-agent-hd'},'🤖 ',el('b',{},T(`Trace Agent · PR ${pn}`,`Trace Agent · PR ${pn}`)),
        prop.cls?el('span',{class:'obs-lab obsraw'},prop.cls):null,
        IMP?el('span',{class:'gch '+(prop.impact==='none'?'s-ok':'s-fail')},IMP[V()]):null,
        o?el('span',{class:'gch s-ok'},`${prop.option} · ${o[V()]}`):null,
        prop.confidence?el('span',{class:'obs-lab'},T('confidence ','độ tin cậy '),el('span',{class:'obsraw'},prop.confidence)):null,
        prop.stale?el('span',{class:'gch s-run'},T('stale: checks changed','cũ: check đã đổi')):null,
        when);
      const fixPr=prop.fix_pr?el('a',{class:'obs-link obsraw',href:ghPr(prop.fix_pr),target:'_blank',rel:'noopener'},`#${prop.fix_pr} ↗`):null;
      if(!full)return el('div',{class:'tr-agent'},hd,el('div',{class:'fx'},'🛠️ ',prop.fix[V()],fixPr?' · ':null,fixPr));
      return el('div',{class:'tr-agent'},hd,
        el('div',{class:'fx'},'🛠️ ',el('b',{style:'color:var(--good)'},T('Actionable fix: ','Hướng xử lý: ')),prop.fix[V()]),
        prop.fix_pr||prop.fix_status?el('div',{},el('b',{},T('Existing fix: ','Fix hiện có: ')),fixPr||'',' ',el('span',{class:'obsraw'},prop.fix_status||'')):null,
        (prop.failing_tests||[]).length?el('div',{},el('b',{},T('Failing tests: ','Test lỗi: ')),el('span',{class:'obsraw'},prop.failing_tests.join(' · '))):null,
        prop.guard&&prop.guard[V()]?el('div',{},'🛡️ ',el('b',{},T('Prevention (G): ','Phòng lặp lại (G): ')),prop.guard[V()]):null,
        (prop.unverified||[]).length?el('div',{},el('b',{},T('Not verified:','Chưa xác minh:')),el('ul',{},...prop.unverified.map(x=>el('li',{class:'obsraw'},x)))):null,
        checksBox(selAg),
        prop.report_text?el('details',{},el('summary',{},T('Full trace report','Báo cáo truy vết đầy đủ'),el('span',{class:'obsraw',style:'font-weight:400'},prop.report?` · ${prop.report}`:'')),el('pre',{class:'obsraw'},prop.report_text)):null);
    }
    let main;
    if(FOC===1){
      const issues=rel.gates.filter(g=>g.status!=='ok').length;
      main=el('div',{class:'tr-ip'},ipHd(1,T('Release / RC Tag','Bản Release / RC'),stBadge(rel.status)),
        el('div',{class:'tr-ip-ttl'},el('span',{class:'mono obsraw'},rel.tag),el('span',{},rel.title[V()])),
        kv([[T('Status','Trạng thái'),el('span',{},stBadge(rel.status),' ',el('span',{class:'obsraw'},rel.badge))],
            [T('Theme','Chủ đề'),rel.theme[V()]],[T('Focus','Trọng tâm'),rel.focus[V()]],
            [T('Key risk','Rủi ro chính'),el('span',{style:'color:var(--critical);font-weight:600'},rel.risk[V()])],
            [T('PRs in release','Số PR trong release'),el('span',{class:'obsraw'},`${rel.total_prs} (${rel.prs.length} ${T('traced','được truy vết')}) · ${rel.rng||''}`)],
            [T('CI gates','Cổng CI'),`${rel.gates.length} · ${issues} ${T('with issues','có lỗi')}`],
            inScope?[T('Trace Agent','Trace Agent'),relAg?T(`${relAg.checked}/${relAg.prs} PRs checked · ${relAg.failing} with failed checks · ${relAg.proposed} fix proposals`,`${relAg.checked}/${relAg.prs} PR đã kiểm · ${relAg.failing} PR có check lỗi · ${relAg.proposed} đề xuất fix`):T('not run yet','chưa chạy')]:null]),
        inScope?othersList():null,
        el('div',{class:'tr-links'},linkBtn(`https://github.com/${CFG.repo}/releases/tag/${rel.tag}`,T('GitHub tag ↗','Tag GitHub ↗')),
          linkBtn(`https://github.com/${CFG.repo}/actions/workflows/publish.yml`,'publish.yml ↗'),
          el('button',{class:'tr-btn sm',onclick:()=>trSet({focus:2,anim:false})},T('Next: PRs →','Tiếp: PR →'))));
    }else if(FOC===2){
      const q=el('input',{id:'trPrQ',class:'tr-q',type:'search',value:TR_Q,placeholder:T('Filter #PR, title, area, file…','Lọc #PR, tiêu đề, vùng code, file…'),
        oninput:e=>{TR_Q=e.target.value;rTracer();}});
      const chips=el('div',{class:'tr-chips'});
      filtPrs.forEach(p=>chips.append(el('button',{class:'tr-chip obsraw'+(selPr&&p.num===selPr.num?' sel':'')+(susOf(p)?' crit':''),title:p.title,onclick:()=>pickPr(p)},`#${p.num}${susOf(p)?' ★':''}${(nf=>nf>0?' ✗'+nf+(nReq(agOf(p))===0?' opt':''):nf===0?' ✓':'')(nFail(agOf(p)))}${((agOf(p)||{}).proposal||{}).status==='ok'?' 🤖':''}`)));
      if(!filtPrs.length)chips.append(el('span',{class:'tr-sub',style:'color:var(--text-muted)'},T('No PR matches the filter.','Không có PR khớp bộ lọc.')));
      main=el('div',{class:'tr-ip'},ipHd(2,T('PR in release','PR trong release'),el('span',{class:'obsraw'},`${filtPrs.length}/${rel.total_prs}`)),q,chips,
        selPr?el('div',{class:'tr-pr'+(susOf(selPr)?' suspect':''),style:'display:flex;flex-direction:column;gap:8px'},
          el('div',{class:'tr-ip-ttl'},el('a',{class:'mono obs-link obsraw',href:ghPr(selPr.num),target:'_blank',rel:'noopener'},`#${selPr.num} ↗`),
            susOf(selPr)?el('span',{class:'gch s-fail'},susSrc(selPr)==='agent'?T('★ Blocks release (Trace Agent)','★ Chặn release (Trace Agent)'):T('★ Suspect (hand-entered, not verified)','★ Nghi vấn (nhập tay, chưa xác minh)')):null,
            selPr.suspect&&!susOf(selPr)?el('span',{class:'gch s-ok'},susSrc(selPr)==='agent'?T('hand-entered suspect overruled by Trace Agent','nghi vấn nhập tay bị Trace Agent bác'):T('hand-entered suspect overruled: CI green','nghi vấn nhập tay bị bác: CI xanh')):null),
          selPr.range_ok===false?el('div',{class:'tr-sub',style:'color:var(--warning)'},'⚠ ',T(`This PR is not in ${rel.rng} (git log). It was merged in another release.`,`PR này không nằm trong ${rel.rng} (git log). Nó được merge ở release khác.`)):null,
          el('div',{class:'obsraw',style:'font-weight:600;font-size:12.5px'},selPr.title),
          kv([[T('Commit','Commit'),el('a',{class:'obs-link obsraw',href:`https://github.com/${CFG.repo}/commit/${selPr.sha}`,target:'_blank',rel:'noopener'},selPr.sha)],
              [T('Area','Phân khu'),el('span',{class:'obs-lab obsraw'},selPr.area)],
              selPr.author?[T('Author','Tác giả'),el('span',{class:'obsraw'},selPr.author)]:null,
              [T('Stage touched','Stage bị tác động'),rel.flow[prStep]?rel.flow[prStep][V()]:'—']]),
          fileList(T(`Changed files (${(selPr.files||[]).length})`,`File thay đổi (${(selPr.files||[]).length})`),selPr.files),
          (selAg&&selAg.checks&&!selAg.checks.failed)?checksBox(selAg):null):null,
        agentBlock(true));
    }else if(FOC===3){
      const steps=el('div',{class:'tr-steps'});
      rel.flow.forEach((s,i)=>{
        if(i>0)steps.append(el('div',{class:'tr-step-arr'},'↓'));
        const isCrit=i===rel.crit_idx,isPr=i===prStep,pick=TR_STEP===i;
        steps.append(el('div',{class:'tr-step'+(isCrit?' crit':'')+(isPr?' active':'')+(pick?' pick':''),style:'cursor:pointer',onclick:()=>trSet({focus:3,step:i,anim:false})},
          el('span',{},`${i+1}. `,s[V()]),
          el('span',{style:'display:inline-flex;gap:4px'},isCrit?el('span',{class:'gch s-fail'},T('Bottleneck','Điểm nghẽn')):null,isPr&&selPr?el('span',{class:'gch s-ok obsraw'},`#${selPr.num}`):null)));
      });
      main=el('div',{class:'tr-ip'},ipHd(3,T('Critical Stage','Critical Stage'),el('span',{class:'obsraw'},selPr?`#${selPr.num}`:'')),
        kv([[T('Theme','Chủ đề'),rel.theme[V()]],[T('Bottleneck','Điểm nghẽn'),el('b',{style:'color:var(--critical)'},rel.flow[rel.crit_idx][V()])],
            [T('PR acts on','PR tác động'),rel.flow[prStep]?rel.flow[prStep][V()]:'—']]),
        steps,
        fileList(T(`Changed files in #${selPr?selPr.num:''}`,`File thay đổi ở #${selPr?selPr.num:''}`),selPr&&selPr.files));
    }else if(FOC===4){
      const chips=el('div',{class:'tr-chips'});
      rel.gates.forEach(g=>chips.append(el('button',{class:'tr-chip obsraw'+(selGate&&g.id===selGate.id?' sel':'')+(g.status==='fail'?' crit':''),title:g.kind,onclick:()=>trSet({gate:g.id,focus:4})},`${g.status==='fail'?'✗':g.status==='warn'?'!':'✓'} ${g.name}`)));
      main=el('div',{class:'tr-ip'},ipHd(4,T('CPU & GPU Test Case','CPU & GPU Test Case'),el('span',{class:'obsraw'},`${rel.gates.length} ${T('gates','cổng')}`)),chips,
        selGate?el('div',{style:'display:flex;flex-direction:column;gap:8px'},
          el('div',{class:'tr-ip-ttl'},el('span',{class:'mono obsraw'},selGate.name),stBadge(selGate.status)),
          kv([[T('Kind','Loại'),el('span',{class:'obs-lab obsraw'},selGate.kind)],[T('Status','Trạng thái'),stBadge(selGate.status)],
              [T('Test file','File test'),el('span',{},el('span',{class:'obsraw',style:'font-family:ui-monospace,Consolas,monospace'},selGate.test_file||'—'),selGate.test_missing?el('span',{class:'tr-sub tr-gmiss',style:'color:var(--warning)'},' ⚠ ',T(`not in repo at ${rel.ref} (hand-entered)`,`không có trong repo ở ${rel.ref} (nhập tay)`)):null)]]),
          inScope?el('div',{class:'tr-sub',style:'color:var(--warning);font-weight:600'},el('span',{class:'gch s-run',style:'margin-right:6px'},T('MANUAL','NHẬP TAY')),T('These gates are hand-entered for this release. For the selected PR, the failing jobs below come from CI (Trace Agent).','Các cổng này được nhập tay cho release. Với PR đang chọn, job lỗi bên dưới lấy từ CI (Trace Agent).')):null,
          inScope&&propOk&&(prop.failing_tests||[]).length?el('div',{},el('b',{},T('Failing tests (Trace Agent): ','Test lỗi (Trace Agent): ')),el('span',{class:'obsraw'},prop.failing_tests.join(' · '))):null,
          inScope?checksBox(selAg):null,
          el('div',{class:'tr-links'},exploreBtn(selGate.test_file),el('button',{class:'tr-btn sm',onclick:()=>trSet({focus:5,anim:false})},T('Open error log →','Mở error log →')))):null,
        selPr?fileList(T(`PR #${selPr.num} unit tests`,`Unit test của PR #${selPr.num}`),selPr.tests,jumpExplorer):null);
    }else{
      const reproBtn=el('button',{class:'tr-btn sm',onclick:()=>{navigator.clipboard&&navigator.clipboard.writeText(reproTxt);reproBtn.textContent='✓';setTimeout(()=>{reproBtn.textContent=T('Copy','Copy');},1200);}},T('Copy','Copy'));
      main=el('div',{class:'tr-ip'},ipHd(5,T('Error Log & Fix','Error Log & Hướng Fix'),stBadge(lst)),termBox(),
        el('div',{class:'tr-diag'},
          el('div',{},'🔎 ',el('b',{},whyLbl()),whyTxt),
          !inScope&&fixTxt?el('div',{style:'color:var(--good)'},'🛠️ ',el('b',{style:'color:var(--good)'},T('Actionable fix: ','Hướng xử lý: ')),fixTxt):null,
          reproTxt?el('div',{class:'tr-repro'},el('span',{class:'obsraw'},'$ '+reproTxt),reproBtn):null),
        agentBlock(true),
        el('div',{class:'tr-links'},exploreBtn(selGate&&selGate.test_file)));
    }
    const side=FOC===5?null:el('div',{class:'tr-ip'},
      ipHd(5,T('Error log of this branch','Error log của nhánh này'),stBadge(lst)),termBox(),
      el('div',{class:'tr-diag'},el('div',{},'🔎 ',el('b',{},whyLbl()),whyTxt),
        !inScope&&fixTxt?el('div',{style:'color:var(--good)'},'🛠️ ',fixTxt):null,
        el('button',{class:'tr-btn sm',style:'align-self:flex-start',onclick:()=>trSet({focus:5,anim:false})},T('Full log, fix & repro →','Xem log đầy đủ, fix & repro →'))),
      FOC===2?null:agentBlock(false));
    const insp=el('div',{class:'tr-insp'+(side?'':' full'),'data-stage':String(FOC),'aria-live':'polite'},main,side);

    w.append(el('div',{class:'tr-wrap'},hd,
      el('div',{},flow,el('div',{class:'tr-hint'},T('Tip: click a column title or any node · the dashed ring marks what the inspector shows.','Mẹo: bấm vào tiêu đề cột hoặc bất kỳ node nào · viền nét đứt đánh dấu component đang xem ở khung chi tiết.'))),
      pills,insp));
    if(hadQ){const q=$('#trPrQ');if(q){q.focus();q.setSelectionRange(q.value.length,q.value.length);}}
  }

  function render(){renderBar();rTrain();rTracer();rPub();rNightly();}

  // ---------- wiring ----------
  const inObs=()=>document.body.dataset.v==='obs'||document.body.dataset.all==='1';
  function maybeOpenRefresh(){if(!CFG.local_only&&onOpen&&inObs()&&!busy&&M&&(Date.now()-M.at)/60000>CFG.th.open_refresh_min&&(!lastFetch||(Date.now()-lastFetch)/60000>CFG.th.open_refresh_min))refresh();}
  addEventListener('viewchange',maybeOpenRefresh);
  addEventListener('langchange',()=>{if(M)render();else rTracer();});
  document.addEventListener('keydown',e=>{if(e.key.toLowerCase()!=='r'||e.ctrlKey||e.metaKey||e.altKey||!inObs())return;const tg=e.target&&e.target.closest?e.target:document.body;if(tg.closest('input,select,textarea'))return;e.preventDefault();refresh();});
  let tick=0;setInterval(()=>{if(document.hidden)return;tick++;
    if(auto&&!busy&&Date.now()-Math.max(lastFetch,M?M.at:0)>=auto*60000)refresh();
    else if(tick%10===0&&!busy&&!showSet)renderBar();},1000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)maybeOpenRefresh();});
  if(SNAP&&SNAP.at)use(SNAP);else{renderBar();rTracer();}
  maybeOpenRefresh();
})();
</script>
<!-- OBS:JS:END -->
"""


def put(page, start, end, block, anchor):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:]


def main():
    page = open(PAGE, encoding="utf-8").read()
    if os.path.exists(SNAP):
        sd = json.load(open(SNAP, encoding="utf-8"))
        for pr in (sd.get("gh", {}).get("prs_gql") or {}).get("nodes", []):
            for cm in (pr.get("commits") or {}).get("nodes", []):
                for cx in (((cm.get("commit") or {}).get("statusCheckRollup") or {}).get("contexts") or {}).get("nodes", []):
                    if not str(cx.get("name") or "").startswith("buildkite/k3-unit"):
                        cx.pop("targetUrl", None)
        snap = json.dumps(sd, ensure_ascii=False, separators=(",", ":"))
    else:
        snap = "null"
    cfg = json.dumps(CONFIG, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    import observe_history
    rep_ = (observe_history.load_all() or {}).get("report") or {}
    keep = {k: rep_.get(k) for k in ("release_trace", "trace_agent", "required_checks")}   # the trend report was removed (P5)
    hist = json.dumps(dict(report=keep), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    js = JS.replace("__CFG__", cfg).replace("__SNAP__", snap.replace("</", "<\\/")).replace("__HIST__", hist)
    for a, b in (("/* TRD:CSS:START */", "/* TRD:CSS:END */"), ("<!-- TRD:HTML:START -->", "<!-- TRD:HTML:END -->"), ("<!-- TRD:JS:START -->", "<!-- TRD:JS:END -->")):
        page = re.sub(re.escape(a) + r".*?" + re.escape(b) + r"\n?", "", page, flags=re.S)   # retired flaky / gpuload / bug tabs
    page = put(page, "/* OBS:CSS:START */", "/* OBS:CSS:END */", CSS, "@media (max-width:980px)")
    page = put(page, "<!-- OBS:HTML:START -->", "<!-- OBS:HTML:END -->", HTML, "<!-- GATES:HTML:START -->")
    page = put(page, "<!-- OBS:JS:START -->", "<!-- OBS:JS:END -->", js, "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    print(f"observe: snapshot {len(snap) / 1024:.0f} KB, page {len(page.encode('utf-8')) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
