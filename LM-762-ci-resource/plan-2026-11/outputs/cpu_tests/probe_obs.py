import json
import os
import re
import subprocess
import tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PAGE = os.path.abspath("LM-762-ci-resource/plan-2026-11/06_PR_TO_CI_VISUAL.html")
src = open(PAGE, encoding="utf-8").read()

PROBE_SCRIPT = r"""
<script>
window.__results = { errors: window.__err || [], tests: {} };

function runTests() {
  try {
    // 1. Check tab visibility
    const obsTabs = ['trend', 'now', 'prs', 'release', 'ci'];
    obsTabs.forEach(t => {
      vizNav.show('obs', t, false);
      const vis = [...document.querySelectorAll('section[data-view="obs"]')].filter(x => !x.classList.contains('vhide'));
      __results.tests['tab_' + t] = vis.length > 0 ? 'PASS' : 'FAIL';
    });

    // 2. Tracer in trend tab
    vizNav.show('obs', 'trend', false);
    const tr = document.getElementById('obsTracer');
    __results.tests['tracer_rendered'] = (tr && tr.children.length > 0) ? 'PASS' : 'FAIL';

    // 3. Test clicking each stage node
    const stages = [1, 2, 3, 4, 5];
    const stageClicks = {};
    stages.forEach(s => {
      const n = document.querySelector(`#obsTracer .tr-fnode[data-stage="${s}"]`);
      if (n) {
        n.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        const insp = document.querySelector('#obsTracer .tr-ip');
        stageClicks['stage_' + s] = insp ? 'PASS' : 'FAIL';
      } else {
        stageClicks['stage_' + s] = 'NODE_NOT_FOUND';
      }
    });
    __results.tests['stage_clicks'] = stageClicks;

    // 4. Test PR filter input in tracer
    const qInput = document.getElementById('trPrQ');
    if (qInput) {
      qInput.value = 'trace';
      qInput.dispatchEvent(new Event('input', { bubbles: true }));
      const chipsAfter = document.querySelectorAll('#obsTracer .tr-chip');
      __results.tests['tracer_filter'] = chipsAfter.length > 0 ? 'PASS' : 'FAIL';
    } else {
      __results.tests['tracer_filter'] = 'INPUT_NOT_FOUND';
    }

    // 5. Check Copy Daily Report
    const copyBtn = document.querySelector('#obsTracer .tr-btn.pri');
    __results.tests['tracer_copy_btn'] = copyBtn ? 'PASS' : 'FAIL';

    // 6. Check Explore buttons in tracer
    const expBtns = document.querySelectorAll('#obsTracer button');
    let hasExplore = false;
    expBtns.forEach(b => { if (b.textContent.includes('Explore') || b.textContent.includes('Khám phá')) hasExplore = true; });
    __results.tests['tracer_explore_btn'] = hasExplore ? 'PASS' : 'FAIL';

    // 7. Check Alerts in obs/now
    vizNav.show('obs', 'now', false);
    const alerts = document.querySelectorAll('#obsAlerts .obs-al');
    __results.tests['alerts_count'] = alerts.length;

    // 8. Check PRs in obs/prs
    vizNav.show('obs', 'prs', false);
    const prRows = document.querySelectorAll('#obsPrs tbody tr');
    __results.tests['prs_table_rows'] = prRows.length;

    // 9. Check post-merge health in obs/ci
    vizNav.show('obs', 'ci', false);
    const healthDots = document.querySelectorAll('#obsHealth .dot');
    __results.tests['health_dots'] = healthDots.length;

  } catch (e) {
    __results.errors.push('Probe exception: ' + e.message);
  }

  const pre = document.createElement('pre');
  pre.id = 'probeResults';
  pre.textContent = JSON.stringify(__results);
  document.body.appendChild(pre);
}

setTimeout(runTests, 600);
</script>
"""

tmp = tempfile.mkdtemp(prefix="probe_obs_")
probe_page = os.path.join(tmp, "probe.html")

patched = src.replace("<head>", '<head><script>try{localStorage.setItem("obsOnOpen","false")}catch(e){}window.__err=[];addEventListener("error",e=>__err.push(e.message));</script>', 1)
patched = patched.replace("</body>", PROBE_SCRIPT + "</body>")

with open(probe_page, "w", encoding="utf-8") as f:
    f.write(patched)

cmd = [CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=5000", "--dump-dom", f"file:///{probe_page.replace(chr(92), '/')}#obs/trend"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

m = re.search(r'<pre id="probeResults">(.*?)</pre>', res.stdout, re.S)
if m:
    data = json.loads(m.group(1))
    print(json.dumps(data, indent=2))
else:
    print("Probe output not found! Full output:")
    print(res.stdout[:1000])

