"""UX review capture: contact sheets of every top-level tab, the PR Inspector and the design-system showcase,
in light + dark, at 1440 px, 768 px and 390 px (each tab in its own iframe of that real width; 390 px is an iframe,
not --window-size, because headless Chrome cannot go below 518 px). Above-the-fold view of each target (first
FOLD px), labelled. Output: outputs/ux_review/round-N/sheet_<theme>_<width>_<k>.png + targets.json.

  python -X utf8 ux_capture.py --round 1 [--only obs/today,e/pr/5673]
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HERE = Path(__file__).resolve().parent
PAGE = HERE.parents[1] / "06_PR_TO_CI_VISUAL.html"
OUT = HERE.parent / "ux_review"
TABS = ["obs/today", "obs/hist", "obs/release", "obs/coming", "obs/cost", "obs/overlap", "obs/research",
        "gates/guide", "gates/tiers", "cpu/overview", "cpu/tiers", "cpu/cost", "gpu/overview", "gpu/tiers", "gpu/explore",
        "r1130/baseline", "r1130/cpu", "r1130/green", "r1130/retry", "r1130/prs", "r1130/track", "r1130/repro", "r1130/quality"]
EXTRA = ["e/pr/5673", "e/pr/6624", "ux"]          # Inspector (open PR), Inspector with a sequence diagram, design system
LAYOUT = {1440: dict(scale=0.5, cols=2, fold=1100), 768: dict(scale=0.5, cols=3, fold=1100), 390: dict(scale=0.7, cols=5, fold=1000)}
PER_SHEET = 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True)
    ap.add_argument("--only")
    a = ap.parse_args()
    targets = a.only.split(",") if a.only else TABS + EXTRA
    out = OUT / f"round-{a.round}"
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="ux_capture_"))
    src = PAGE.read_text(encoding="utf-8")
    pages = {}
    for theme in ("light", "dark"):
        p = tmp / f"page_{theme}.html"
        p.write_text(src.replace("<head>", "<head><script>try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','en')}catch(e){}"
                                 f"document.documentElement.dataset.theme='{theme}';</script><style>.pi-drawer,.ent-drawer{{transition:none!important}}"
                                 "html{scroll-behavior:auto!important}</style>", 1), encoding="utf-8")
        pages[theme] = p
    made = []
    for theme in ("light", "dark"):
        for w, L in LAYOUT.items():
            for k in range(0, len(targets), PER_SHEET):
                chunk = targets[k:k + PER_SHEET]
                tw, th = int(w * L["scale"]), int(L["fold"] * L["scale"])
                rows = (len(chunk) + L["cols"] - 1) // L["cols"]
                sheet_w, sheet_h = L["cols"] * (tw + 12) + 12, rows * (th + 30) + 12
                tiles = "".join(
                    f'<div style="position:absolute;left:{12 + (i % L["cols"]) * (tw + 12)}px;top:{12 + (i // L["cols"]) * (th + 30)}px;width:{tw}px">'
                    f'<div style="font:600 13px system-ui;color:#000;background:#ffd;padding:2px 6px;height:18px;overflow:hidden">#{t} · {theme} · {w}px</div>'
                    f'<div style="width:{tw}px;height:{th}px;overflow:hidden;border:1px solid #999"><iframe src="{pages[theme].as_uri()}#{t}" '
                    f'style="width:{w}px;height:{L["fold"]}px;border:0;transform:scale({L["scale"]});transform-origin:0 0"></iframe></div></div>'
                    for i, t in enumerate(chunk))
                h = tmp / f"sheet_{theme}_{w}_{k}.html"
                h.write_text(f'<html><body style="margin:0;background:#bbb;width:{sheet_w}px;height:{sheet_h}px;position:relative">{tiles}</body></html>', encoding="utf-8")
                png = out / f"sheet_{theme}_{w}_{k // PER_SHEET + 1}.png"
                subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                                f"--window-size={sheet_w},{sheet_h}", "--virtual-time-budget=40000", f"--screenshot={png}", h.as_uri()],
                               capture_output=True, timeout=400)
                made.append(dict(file=png.name, theme=theme, width=w, targets=chunk))
                print(png.name, chunk)
    (out / "targets.json").write_text(json.dumps(made, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
