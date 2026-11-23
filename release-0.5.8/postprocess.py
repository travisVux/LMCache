"""Dashmotion flow-mode post-process: color ISSUE/SOLUTION boxes, add legend, add ?motion=on."""
import re, sys
p = sys.argv[1]; s = open(p, encoding='utf-8').read()
STY = {'ISSUE': 'fill="rgba(244,63,94,0.08)" stroke="#f43f5e" stroke-width="1.5"/>',
       'SOLUTION': 'fill="rgba(34,211,238,0.06)" stroke="#22d3ee" stroke-width="1.5" stroke-dasharray="6 3"/>'}
plain = 'fill="rgba(16,185,129,0.04)" stroke="#10b981"/>'
for kind, new in STY.items():
    for m in reversed(list(re.finditer(r'<tspan[^>]*>' + kind, s))):
        j = s.rfind(plain, 0, m.start()); assert j > 0 and m.start() - j < 200, kind
        s = s[:j] + new + s[j + len(plain):]
W, H = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', s).groups())
font = "ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace"
items = [('<rect width="14" height="10" rx="2" fill="none" stroke="#10b981"/>', 'works today'),
         ('<rect width="14" height="10" rx="2" fill="rgba(244,63,94,0.08)" stroke="#f43f5e"/>', 'issue (today)'),
         ('<rect width="14" height="10" rx="2" fill="none" stroke="#22d3ee" stroke-dasharray="3 2"/>', 'solution (proposed)'),
         ('<circle cx="7" cy="5" r="3.5" fill="#34d399"/>', 'build in flight')]
per_row = 4 if W >= 640 else 2
rows = (len(items) + per_row - 1) // per_row
y0 = H - 50 + 30  # engine: H = lowest bottom + 50
newH = y0 + 16 * (rows - 1) + 20
s = re.sub(r'viewBox="0 0 ([\d.]+) [\d.]+"', lambda m: f'viewBox="0 0 {m.group(1)} {newH:g}"', s, count=1)
parts = []
for i, (sw, txt) in enumerate(items):
    x = 34 + (i % per_row) * 150; y = y0 + (i // per_row) * 16
    parts.append(f'<g transform="translate({x} {y - 9})">{sw}<text x="20" y="9">{txt}</text></g>')
leg = f'<g font-size="11" fill="#94a3b8" font-family="{font}">' + ''.join(parts) + '</g></svg>'
k = s.index('</svg>'); s = s[:k] + leg + s[k + 6:]
css_anchor = '.pulse-dot { animation: pulse 2s ease-in-out infinite; }\n  }'
s = s.replace(css_anchor, css_anchor + '''
  /* ?motion=on forces animation even when the OS asks for reduced motion */
  html.force-motion .flow { animation: dashmove 0.75s linear infinite; }
  html.force-motion .flow-async { animation: dashasync 0.9s linear infinite; }
  html.force-motion .flow-auth { animation: dashauth 1.2s linear infinite; }
  html.force-motion .pulse-dot { animation: pulse 2s ease-in-out infinite; }''', 1)
js_anchor = "  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {"
assert js_anchor in s
s = s.replace(js_anchor, "  var force = /[?&]motion=on\b/.test(location.search);\n  if (force) document.documentElement.classList.add('force-motion');\n  if (!force && matchMedia('(prefers-reduced-motion: reduce)').matches) {", 1)
open(p, 'w', encoding='utf-8').write(s); print('post-processed', p)
