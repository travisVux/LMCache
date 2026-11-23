"""The existing page (plan-2026-11/06_PR_TO_CI_VISUAL.html) served inside the Release Desk, unchanged except for embed mode.

Embed mode only hides the page's own title header and view/tab bar: the Release Desk shell shows one navigation for
every view and drives the page through its hash (#obs/release, #gates/tiers, ...), I18N.setLang, data-theme and the
page's own #vDesc / #vAll checkboxes. Every section, card, drawer and link of the page stays as it is.
"""
from config import OLD

PAGE = OLD.parents[1] / "06_PR_TO_CI_VISUAL.html"

EMBED = """<style id="opsEmbed">
.wrap>header,.wrap>nav.vnav{display:none!important}
.viz-root{padding-top:12px!important}
@media (max-width:640px){.viz-root{padding-left:12px!important;padding-right:12px!important}}
</style><script>window.OPS_EMBED=true;try{localStorage.setItem('obsOnOpen','false')}catch(e){}</script>"""


def html():
    src = PAGE.read_text(encoding="utf-8")
    return src.replace("</head>", EMBED + "</head>", 1)


PLAN = PAGE.parent   # plan-2026-11/: the page's relative links (outputs/...) resolve here


def outputs_file(rel):
    """A file the page links relatively (outputs/trace_agent/proposals.js, evidence CSVs, reports); None if outside outputs/."""
    f = (PLAN / rel).resolve()
    root = (PLAN / "outputs").resolve()
    return f if root in f.parents and f.is_file() else None


def linked_outputs():
    """Relative outputs/... paths the page mentions, for the static copy (anchors and section marks removed)."""
    import re
    src = PAGE.read_text(encoding="utf-8")
    paths = {m.split("#")[0].split(" ")[0] for m in re.findall(r"outputs/[A-Za-z0-9_./-]+", src)}
    files = [f for f in (outputs_file(p) for p in paths) if f]
    files += [f for f in (PLAN / "outputs" / "trace_agent").rglob("*") if f.is_file()]   # proposals.js + every report it links
    return sorted(set(files))
