import os
import subprocess
import tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PAGE = os.path.abspath("LM-762-ci-resource/plan-2026-11/06_PR_TO_CI_VISUAL.html")
src = open(PAGE, encoding="utf-8").read()

outdir = os.path.abspath("LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/shots_baseline")
os.makedirs(outdir, exist_ok=True)

tmp = tempfile.mkdtemp(prefix="shots_obs_")
tabs = ["trend", "now", "prs", "release", "ci"]

for lang in ("en", "vi"):
    f = os.path.join(tmp, f"page_{lang}.html")
    with open(f, "w", encoding="utf-8") as fp:
        fp.write(src.replace("<head>", f'<head><script>try{{localStorage.setItem("ciMapLang","{lang}");localStorage.setItem("obsOnOpen","false")}}catch(e){{}}</script>', 1))
    for t in tabs:
        png = os.path.join(outdir, f"{lang}_obs_{t}.png")
        file_url = "file:///" + f.replace("\\", "/") + f"#obs/{t}"
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=5000", "--window-size=1280,1400", f"--screenshot={png}", file_url]
        subprocess.run(cmd, timeout=30)
        sz = os.path.getsize(png) if os.path.exists(png) else 0
        print(f"{lang}_obs_{t}.png: {sz} bytes")

png_mobile = os.path.join(outdir, "mobile_390_en_obs_now.png")
f_en = os.path.join(tmp, "page_en.html")
cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=5000", "--window-size=390,1400", f"--screenshot={png_mobile}", "file:///" + f_en.replace("\\", "/") + "#obs/now"]
subprocess.run(cmd, timeout=30)
sz = os.path.getsize(png_mobile) if os.path.exists(png_mobile) else 0
print(f"mobile_390_en_obs_now.png: {sz} bytes")

