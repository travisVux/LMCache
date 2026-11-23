"""Combine dashmotion diagrams + explanation notes into one page.

Usage: python -I combine.py OUT.html  (sections listed in SECTIONS below)
Each diagram file must already be rendered by layout.py and post-processed by postprocess.py.
"""
import html, re, sys
from pathlib import Path

HERE = Path(__file__).parent
SECTIONS = [  # (anchor/id prefix, nav label, rendered diagram, notes fragment)
    ("sglang", "SGLang image", "sglang-torch-dashmotion.html", "sglang-notes.html"),
    ("musa", "MUSA wheel", "musa-wheel-dashmotion.html", "musa-notes.html"),
]

OVERVIEW = """
<section class="overview" lang="vi">
  <p>Release <code>v0.5.8rc1</code> (tag 11-13): PyPI, image vLLM RC, wheel XPU / ROCm / RBLN đều publish OK.
  Chỉ thiếu <b>2 thứ</b>, mỗi thứ có 2 issue và 2 solution:</p>
  <table>
    <tr><th>Thiếu gì</th><th>Issue 1 (vì sao hỏng)</th><th>Issue 2 (vì sao khó / vì sao muộn)</th><th>Solution 1 (sửa ngay)</th><th>Solution 2 (lâu dài)</th></tr>
    <tr><td><a href="#sglang">Image <code>lmcache/sglang:v0.5.8rc1</code></a></td>
        <td>Không bản SGLang nào dùng đúng torch 2.14.0 (chỉ có 2.14.1 / 2.13.0)</td>
        <td>Không nâng pin lên 2.14.1 được: vLLM 0.33.0 cần 2.14.0</td>
        <td>Chấp nhận cùng 2.14.x → SGLang v0.5.23<br><span class="muted">fork, chưa PR</span></td>
        <td>Build LMCache trên torch của SGLang<br><span class="muted">đề xuất</span></td></tr>
    <tr><td><a href="#musa">Wheel <code>v0.5.8rc1-musa</code></a></td>
        <td>#5865 cần <code>torch_musa</code> lúc build, mà image MUSA trỏ sai đường dẫn</td>
        <td>Đỏ trên dev từ 11-07, PR không có check MUSA, 6 ngày sau mới biết</td>
        <td>Thêm <code>/home/torch_musa</code> vào <code>PYTHONPATH</code> + fail-fast<br><span class="muted">fork, chưa PR</span></td>
        <td>Build MUSA trên PR sửa file MUSA<br><span class="muted">đề xuất</span></td></tr>
  </table>
</section>
"""

PAGE_CSS = """
  .container { max-width: 1240px; }
  .nav { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 1.25rem; }
  .nav a, .nav button { font: inherit; font-size: 12px; color: #94a3b8; border: 1px solid #1e293b; border-radius: 6px;
    padding: 4px 10px; text-decoration: none; background: transparent; cursor: pointer; }
  .nav a:hover, .nav button:hover { color: #e2e8f0; border-color: #334155; }
  .case { margin: 2.5rem 0 0; scroll-margin-top: 1rem; }
  .case > h2 { font-size: 1.05rem; margin-bottom: .25rem; }
  .case > .subtitle { margin-bottom: 1rem; }
  .layout { display: grid; gap: 1.25rem; grid-template-columns: minmax(0, 1fr); }
  .layout > *, .notes > * { min-width: 0; }
  h1 { overflow-wrap: anywhere; }
  .nav button { white-space: normal; text-align: left; }
  @media (min-width: 980px) { .layout { grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); align-items: start; } }
  .notes, .overview { font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #cbd5e1; }
  .notes { display: grid; gap: .9rem; }
  .note { border: 1px solid #1e293b; border-left: 3px solid #334155; border-radius: 10px; padding: .9rem 1rem; background: #030a1c; }
  .note.issue { border-left-color: #f43f5e; }
  .note.solution { border-left-color: #22d3ee; border-left-style: dashed; }
  .note h2 { font-size: 15px; color: #f1f5f9; margin-bottom: .45rem; line-height: 1.4; }
  .note p + p, .note p + ul, .note ul + p, .note p + table, .note table + p, .note p + ol, .note ol + p { margin-top: .5rem; }
  .note ul, .note ol { padding-left: 1.2rem; }
  .tag { font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: 11px; font-weight: 700; letter-spacing: .04em;
    padding: 1px 6px; border-radius: 4px; margin-right: 6px; vertical-align: 1px; }
  .issue .tag { color: #fda4af; background: rgba(244,63,94,.14); }
  .solution .tag { color: #67e8f9; background: rgba(34,211,238,.12); }
  code { font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: .88em; color: #e2e8f0;
    background: #0f172a; padding: 1px 4px; border-radius: 4px; overflow-wrap: anywhere; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #1e293b; vertical-align: top; }
  th { color: #94a3b8; font-weight: 600; }
  .overview { border: 1px solid #1e293b; border-radius: 12px; padding: 1rem; background: #030a1c; overflow-x: auto; }
  .overview table { min-width: 720px; margin-top: .6rem; }
  .overview a { color: #67e8f9; }
  .ok { color: #34d399; } .bad { color: #fb7185; }
  .muted { color: #64748b; font-size: 12.5px; }
  .warn { color: #fbbf24; font-size: 13px; }
  .timeline li { margin-bottom: .2rem; }
  .sw { display: inline-block; width: 12px; height: 8px; border: 1.5px dashed #22d3ee; border-radius: 2px; margin-right: 6px; }
  @media (max-width: 600px) { body { padding: 1rem; } }
"""

SCRIPT = """<script>
(function () {
  // Motion is ON by default on this page; ?motion=off follows the OS reduced-motion setting instead.
  var force = !/[?&]motion=off\\b/.test(location.search);
  if (!force) document.documentElement.classList.remove('force-motion');
  var svgs = document.querySelectorAll('svg.dm');
  var btn = document.getElementById('pauseAll');
  if (!force && matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.querySelectorAll('.dot').forEach(function (d) { d.remove(); });
    btn.textContent = 'animation off (?motion=off + OS reduced motion)'; btn.disabled = true; return;
  }
  var paused = false;
  btn.addEventListener('click', function () {
    paused = !paused; document.body.classList.toggle('paused', paused);
    svgs.forEach(function (s) { paused ? s.pauseAnimations() : s.unpauseAnimations(); });
    btn.textContent = paused ? '\\u25b6 play' : '\\u23f8 pause';
    btn.setAttribute('aria-pressed', String(paused));
  });
})();
</script>"""


def grab(s, pattern):
    m = re.search(pattern, s, re.S)
    return m.group(1).strip() if m else ""


def prefixed_svg(s, pfx):
    svg = s[s.index("<svg"): s.index("</svg>") + 6]
    ids = set(re.findall(r'\bid="([^"]+)"', svg))
    svg = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{pfx}_{m.group(1)}"', svg)
    svg = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{pfx}_{m.group(1)})', svg)
    svg = re.sub(r'(aria-(?:labelledby|describedby))="([^"]+)"', lambda m: f'{m.group(1)}="{pfx}_{m.group(2)}"', svg)

    def fix_begin(m):
        return 'begin="' + re.sub(r'\b([\w-]+)(?=\.(?:end|begin)\b)',
                                  lambda r: f"{pfx}_{r.group(1)}" if r.group(1) in ids else r.group(1), m.group(1)) + '"'
    svg = re.sub(r'begin="([^"]*)"', fix_begin, svg)
    return svg.replace("<svg ", '<svg class="dm" ', 1)


def main(out):
    first = (HERE / SECTIONS[0][2]).read_text(encoding="utf-8")
    style = grab(first, r"<style>(.*?)</style>")
    parts = []
    for pfx, label, diagram, notes in SECTIONS:
        s = (HERE / diagram).read_text(encoding="utf-8")
        title, sub, foot = grab(s, r"<h1>(.*?)</h1>"), grab(s, r'<p class="subtitle">(.*?)</p>'), grab(s, r'<p class="footer">(.*?)</p>')
        parts.append(f"""
  <section class="case" id="{pfx}">
    <h2>{title}</h2>
    <p class="subtitle">{sub}</p>
    <div class="layout">
      <div><div class="diagram-card">{prefixed_svg(s, pfx)}</div><p class="footer">{foot}</p></div>
      {(HERE / notes).read_text(encoding="utf-8")}
    </div>
  </section>""")
    nav = "".join(f'<a href="#{p}">{html.escape(l)}</a>' for p, l, _, _ in SECTIONS)
    page = f"""<!DOCTYPE html>
<html lang="en" class="force-motion">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>v0.5.8rc1 build issues</title>
<style>{style}{PAGE_CSS}</style>
</head>
<body>
<div class="container">
  <div class="header"><div class="pulse-dot"></div><h1>v0.5.8rc1: 2 thứ chưa publish (SGLang image, MUSA wheel)</h1></div>
  <p class="subtitle">Mỗi case: diagram bên trái (luồng build thật), giải thích bên phải. Đỏ = issue hôm nay, xanh nét đứt = solution đề xuất.</p>
  <nav class="nav">{nav}<button id="pauseAll" aria-pressed="false">⏸ pause</button></nav>
{OVERVIEW}{''.join(parts)}
</div>
{SCRIPT}
</body>
</html>
"""
    Path(out).write_text(page, encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
