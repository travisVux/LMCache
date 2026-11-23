"""Write a static copy (frontend + API answers as JSON files) to ops-app/dist/.

The same frontend runs without the server: it reads api/*.json when window.OPS_STATIC is set.
Use it to look at the page offline, or later to publish to GitHub Pages.
Run:  python -X utf8 export_static.py
"""
import json
import shutil

import legacy
import model
from config import DIST, FRONTEND
from db import connect


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(FRONTEND, DIST)
    shell = DIST / "shell.html"   # optional single-bar shell; index.html = the page with its 3 views
    (DIST / "index.html").rename(shell)
    shell.write_text(shell.read_text(encoding="utf-8").replace("<head>", "<head><script>window.OPS_STATIC=true</script>", 1),
                     encoding="utf-8")
    shutil.copy2(legacy.PAGE, DIST / "index.html")
    (DIST / "legacy.html").write_text(legacy.html(), encoding="utf-8")
    big, n = [], 0
    for f in legacy.linked_outputs():   # the page's relative evidence links must work in the copy too
        if f.stat().st_size > 15 * 2**20:
            big.append(f.name)
            continue
        dst = DIST / f.relative_to(legacy.PLAN)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        n += 1
    print(f"page files copied: {n}" + (f"; skipped > 15 MB: {', '.join(big)}" if big else ""))
    con = connect()
    ov = model.overview(con)
    dump(DIST / "api" / "overview.json", ov)
    dump(DIST / "api" / "history.json", model.history(con))
    for r in ov["releases"]:
        dump(DIST / "api" / "release" / f"{r['tag']}.json", model.release_detail(con, r["tag"]))
    print(f"static copy in {DIST}  ({sum(1 for _ in DIST.rglob('*.json'))} json files)")


if __name__ == "__main__":
    main()
