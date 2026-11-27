"""CSS + JS of the UX layer (build_ux.py). Plain JS with JSDoc types, class prefix ux-, mounted inside #root.
UI strings go through T(en, vi); raw data is wrapped in .obsraw. Nothing here calls the network.
"""

CSS = r"""
/* UX:CSS:START */
/* ---- design tokens (on .viz-root): spacing, type, motion. Colours, radii and elevation are in ONE block, the rd-tokens style
   (TOKENS below, round 3 D_identity 3.8), last in <head>; the old scoped colour definitions were removed ---- */
.viz-root{--ux-s1:4px;--ux-s2:8px;--ux-s3:12px;--ux-s4:16px;--ux-s5:24px;--ux-s6:32px;
  --ux-fs-xs:11.5px;--ux-fs-sm:12.5px;--ux-fs-md:14px;--ux-fs-lg:17px;--ux-fs-xl:24px;--ux-lh:1.45;
  --ux-t-fast:120ms;--ux-t-med:220ms;--ux-ease:cubic-bezier(.2,.7,.2,1)}
/* WCAG AA: de-emphasis by colour, not by opacity (opacity drops contrast below 4.5:1); text on fills is set by the
   contrast guard in the JS (black or white, whichever reads better on the real background, per theme) */
.gch.s-none,.nr-tier.prop,.seg button[aria-selected="false"] .tx small,.nr-phases li,.nr-phases .nr-ph{opacity:1!important}
.gch.s-none,.nr-tier.prop,.nr-pn,.nr-ps{color:var(--text-secondary)!important}
.seg button[aria-selected="false"] .ic{opacity:1!important;filter:none!important;background:var(--surface-2)!important}
.seg button[aria-selected="true"] .ic{background:var(--ux-accent)!important}.seg button[aria-selected="true"]{--ring:var(--ux-accent)!important}
.badge.fix,.rs-good,.rs-v.improves{color:var(--good)!important}.badge.rel{color:var(--critical)!important}
.gch.s-fail{color:var(--critical)!important}
/* one place per fact: the decision banner carries the verdict, phase and data ages of "Where we are" */
#uxDecision~#dkWhere #dkWhereB>div:first-child,#uxDecision~#dkWhere .dk-phase,#uxDecision~#dkWhere .dk-ages{display:none}
.pills .k{display:none}.pills .grp{font-size:11px}.pills .c{font-size:11px}
/* missing data is not a verdict: dashed, neutral, with "?" */
.tdy-v[data-verb="no_data"]{border-style:dashed!important;color:var(--text-secondary)!important;background:transparent!important}.tdy-v[data-verb="no_data"]::before{content:"?";font-weight:800}
.ux-btn.pri code{background:transparent!important;color:inherit!important;border:0!important}
#obsBar.ux-stalescope *:not(#uxBarStale):not(#uxBarStale *){color:var(--text-secondary)!important;border-color:var(--border)!important;background-color:transparent!important}
.rs-card:has(.rs-badge) .rs-good,.rs-card:has(.rs-badge) .rs-bad,.rs-card:has(.rs-badge) .rs-v{color:var(--text-secondary)!important}
.viz-root p.sub,.viz-root .sdesc{font-size:13px;line-height:1.5}
#bars .home[style*="right"]{background:var(--surface-1);color:var(--text-primary)!important;border-radius:4px;padding:0 6px!important}
.tr-term-note .gch,.tr-term .gch{color:#e6edf3!important;border-color:#8b949e!important}
.viz-root :focus-visible{outline:2px solid var(--ux-focus);outline-offset:2px}
.viz-root a:visited{color:var(--series-1)}
.ux-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.ux-skip{position:absolute;left:8px;top:-60px;z-index:100;background:var(--surface-1);color:var(--text-primary);padding:8px 12px;border:2px solid var(--ux-focus);border-radius:8px}
.ux-skip:focus{top:8px}
/* expert review U1: the pinned nav covered most of a phone screen / 200 % zoom: pin it only on large screens */
@media (max-width:767px),(max-height:500px){.vnav{position:static!important;top:auto!important}}
/* U2: reflow at 320 px - wide tables and code scroll inside their box, never the page */
@media (max-width:400px){.viz-root table{display:block;max-width:100%;overflow-x:auto}.viz-root pre,.viz-root code{white-space:pre-wrap;overflow-wrap:anywhere}
  .viz-root .obs-scroll,.viz-root .tiles,.viz-root .cards{max-width:100%;overflow-x:auto}.viz-root img,.viz-root svg{max-width:100%;height:auto}
  .viz-root section[data-view] *{min-width:0;max-width:100%}.viz-root section[data-view] .tdy-v{white-space:normal}
  .viz-root section[data-view] [class*=grid],.viz-root section[data-view] .ob-tiers{grid-template-columns:minmax(0,1fr)!important}
  .viz-root .ob-cmd-list,.viz-root .obs-jobs{grid-template-columns:minmax(0,1fr)!important}.viz-root .obs-jobs a,.viz-root .ent-t{overflow-wrap:anywhere;white-space:normal}
  .viz-root .bars,.viz-root .q{overflow-x:auto}
  .viz-root #bars{grid-template-columns:minmax(0,1fr) auto!important}.viz-root #bars>*{min-width:0}
  .viz-root{overflow-x:clip}   /* the closed (off-canvas) drawers must not widen the page */
  .viz-root section[data-view] h1,.viz-root section[data-view] h2,.viz-root section[data-view] h3,.viz-root section[data-view] h4,.viz-root section[data-view] .val,.viz-root section[data-view] .hd{overflow-wrap:anywhere}}
/* U14: targets at least 24 px */
.viz-root .dk-copy,.viz-root .ent-i,.viz-root .copy,.viz-root button.sm{min-height:24px;min-width:24px}
.viz-root input[type=checkbox],.viz-root input[type=radio]{width:18px;height:18px;margin:3px}
/* ---- components ---- */
.ux-chip{display:inline-flex;align-items:center;gap:4px;width:max-content;max-width:100%;flex-shrink:0;box-sizing:border-box;font-size:var(--ux-fs-xs);font-weight:700;line-height:18px;padding:0 8px;border-radius:var(--ux-r-pill);border:1.5px solid currentColor;white-space:nowrap;vertical-align:middle}
.ux-chip::before{font-weight:800}
.ux-chip.ok{color:var(--ux-ok)}.ux-chip.ok::before{content:"✓"}
.ux-chip.warn{color:var(--ux-warn)}.ux-chip.warn::before{content:"!"}
.ux-chip.fail{color:var(--ux-fail)}.ux-chip.fail::before{content:"✗"}
.ux-chip.stale{color:var(--ux-warn);border-style:dashed}.ux-chip.stale::before{content:"⏱"}
.ux-chip.unk{color:var(--text-secondary);border-style:dashed}.ux-chip.unk::before{content:"?"}
.ux-chip.info{color:var(--ux-accent)}.ux-chip.info::before{content:"i"}
.ux-card{border:1px solid var(--border);border-radius:var(--ux-r-md);padding:var(--ux-s3);background:var(--surface-1);min-width:0;display:flex;flex-direction:column;gap:2px}
.ux-card .lab{font-size:var(--ux-fs-xs);font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--text-secondary)}
.ux-card .val{font-size:var(--ux-fs-xl);font-weight:700;font-variant-numeric:tabular-nums;color:var(--text-primary);line-height:1.15}
.ux-card .val small{font-size:var(--ux-fs-sm);font-weight:600;color:var(--text-secondary);margin-left:4px}
.ux-card .def{font-size:var(--ux-fs-xs);color:var(--text-secondary)}
.ux-card .dl{font-size:var(--ux-fs-xs);font-weight:700}.ux-card .dl.good{color:var(--ux-ok)}.ux-card .dl.bad{color:var(--ux-fail)}.ux-card .dl.flat{color:var(--text-secondary)}
.ux-card svg{display:block;width:100%;height:28px}.ux-card svg polyline{fill:none;stroke:var(--ux-accent);stroke-width:1.6}
.ux-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:var(--ux-s2)}
.ux-banner{border:1px solid var(--border);border-left:6px solid var(--text-secondary);border-radius:var(--ux-r-md);padding:var(--ux-s3) var(--ux-s4);background:var(--surface-1);display:flex;flex-direction:column;gap:var(--ux-s2)}
.ux-banner.fail{border-left-color:var(--ux-fail)}.ux-banner.warn{border-left-color:var(--ux-warn)}.ux-banner.ok{border-left-color:var(--ux-ok)}
.ux-q{margin:0 0 12px}
.ux-pill{display:inline-flex;align-items:center;gap:6px;max-width:min(520px,100%);min-width:0;font-size:var(--ux-fs-sm);text-decoration:none;color:var(--text-primary);border:1px solid var(--border);border-left:4px solid var(--text-secondary);border-radius:var(--ux-r-sm);padding:3px 8px;background:var(--surface-1)}
.ux-pill.fail{border-left-color:var(--ux-fail)}.ux-pill.warn{border-left-color:var(--ux-warn)}.ux-pill.ok{border-left-color:var(--ux-ok)}
.ux-pill .t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.ux-pill[hidden]{display:none}
#dkWhere .dk-tile.ux-dup{display:none}#dkWhere .dk-tile.rb{border-color:var(--border)!important}
.ux-banner .hd .ux-chip{flex:none}.ux-banner .row .ux-chip{white-space:nowrap}
/* review P2-14 (phone 390 px): long check names / words in the verdict rows wrap instead of overflowing */
.ux-banner .row>*,.ux-banner .hd>*{min-width:0;overflow-wrap:anywhere}.ux-banner[data-ux="merge-verdict"] .row .ux-chip{white-space:normal;max-width:100%;overflow-wrap:anywhere}
.slow .b{background:var(--ux-accent)!important}
.ux-more>summary{cursor:pointer;font-size:var(--ux-fs-sm);color:var(--text-secondary);margin:8px 0 4px}.ux-q .ux-banner{border-left-color:var(--ux-accent)}
.ux-banner .hd{display:flex;flex-wrap:wrap;gap:var(--ux-s2);align-items:center}
.ux-banner .hd h2{margin:0;font-size:var(--ux-fs-lg);line-height:1.3}
.ux-banner .hd .ux-vt{font-size:var(--ux-fs-md);line-height:1.35;flex:1 1 240px;min-width:0}
.ux-banner .row{display:grid;grid-template-columns:120px minmax(0,1fr);gap:var(--ux-s2);align-items:baseline;font-size:var(--ux-fs-md)}
.ux-banner .row>b{font-size:var(--ux-fs-xs);text-transform:uppercase;letter-spacing:.04em;color:var(--text-secondary)}
.ux-banner .acts{display:flex;flex-wrap:wrap;gap:var(--ux-s2);margin-left:auto}
.ux-btn{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:4px;font-size:var(--ux-fs-sm);font-weight:600;padding:4px 10px;border-radius:var(--ux-r-sm);border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary)}
.ux-btn:hover{border-color:var(--ux-accent)}.ux-btn.pri{background:var(--ux-accent);border-color:var(--ux-accent);color:var(--on-accent,#fff)}
.ux-pr{display:inline-flex;gap:4px;align-items:baseline;max-width:100%;font-size:var(--ux-fs-sm);border:1px solid var(--border);border-radius:var(--ux-r-pill);padding:1px 8px;text-decoration:none;color:var(--text-primary)}
.ux-pr b{color:var(--ux-accent)}.ux-pr span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:26ch}
.ux-gate{display:inline-flex;gap:4px;align-items:center;font-size:var(--ux-fs-sm);border:1px solid var(--border);border-radius:var(--ux-r-sm);padding:1px 8px}
.ux-gate .m{font-size:var(--ux-fs-xs);color:var(--text-secondary)}
.ux-gate{flex-wrap:wrap;max-width:100%;box-sizing:border-box;margin:2px 4px 2px 0}.ux-chip.long{white-space:normal;width:auto;line-height:1.35;padding-top:1px;padding-bottom:1px}
.ux-ev{font-size:var(--ux-fs-xs);color:var(--ux-accent);text-decoration:underline;text-underline-offset:2px;white-space:nowrap}
.ux-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:var(--ux-s2)}
.ux-list>li{border:1px solid var(--border);border-radius:var(--ux-r-md);padding:var(--ux-s2) var(--ux-s3);font-size:var(--ux-fs-md);overflow-wrap:anywhere;background:var(--surface-1)}
.ux-list>li .why{font-size:var(--ux-fs-sm);color:var(--text-secondary)}
table.ux-t2c{width:100%;border-collapse:collapse;font-size:var(--ux-fs-sm)}
table.ux-t2c th{text-align:left;font-size:var(--ux-fs-xs);text-transform:uppercase;letter-spacing:.04em;color:var(--text-secondary);padding:4px 6px}
table.ux-t2c td{border-top:1px solid var(--border);padding:6px;vertical-align:top;overflow-wrap:anywhere}
.ux-empty,.ux-unk,.ux-err,.ux-stalebox{border:1px dashed var(--border);border-radius:var(--ux-r-md);padding:var(--ux-s3);font-size:var(--ux-fs-sm);color:var(--text-secondary)}
.ux-err{border:1px solid var(--ux-fail);color:var(--text-primary)}.ux-err b{color:var(--ux-fail)}
.ux-stalebox{border-color:var(--ux-warn);color:var(--text-primary)}
.ux-skel{height:14px;border-radius:var(--ux-r-sm);background:linear-gradient(90deg,var(--surface-2),var(--surface-1),var(--surface-2));background-size:200% 100%;animation:uxSh 1.4s linear infinite;margin:6px 0}
@keyframes uxSh{to{background-position:-200% 0}}
/* loading: dynamic section bodies show a skeleton until their script draws them */
#dkWhereB:empty,#dkDecideB:empty,#dkBlockB:empty,#dkGatesB:empty,#tdyBody:empty,#relBody:empty,section[data-ops]:empty,section[data-research]:empty{min-height:84px;border-radius:var(--ux-r-md);background:linear-gradient(90deg,var(--surface-2),var(--surface-1),var(--surface-2));background-size:200% 100%;animation:uxSh 1.4s linear infinite}
/* old data never shows green: a stale scope neutralises the ok colour and says why */
.ux-stalescope .s-ok,.ux-stalescope .ok,.ux-stalescope [class*="pass"],.ux-stalescope .dk-st.green{color:var(--text-secondary)!important;border-color:var(--border)!important}
.ux-stalescope .dk-dot.passed,.ux-stalescope .dk-st.green::before{background:var(--text-muted)!important}
/* search / jump */
.ux-search{position:relative;flex:0 1 320px;min-width:180px}
.ux-search input{width:100%;box-sizing:border-box;font:inherit;font-size:var(--ux-fs-sm);padding:6px 10px 6px 28px;border-radius:var(--ux-r-sm);border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary)}
.ux-search::before{content:"⌕";position:absolute;left:9px;top:5px;color:var(--text-secondary);font-size:15px}
.ux-search kbd{position:absolute;right:8px;top:6px;font:11px ui-monospace,Consolas,monospace;border:1px solid var(--border);border-radius:4px;padding:0 4px;color:var(--text-secondary)}
.ux-res{position:absolute;left:0;right:0;top:calc(100% + 4px);z-index:50;background:var(--surface-1);border:1px solid var(--border);border-radius:var(--ux-r-md);box-shadow:var(--ux-e2);max-height:min(60vh,420px);overflow:auto;padding:4px;display:none}
.ux-res.on{display:block}
.ux-res button{all:unset;cursor:pointer;display:flex;gap:8px;align-items:baseline;width:100%;box-sizing:border-box;padding:6px 8px;border-radius:var(--ux-r-sm);font-size:var(--ux-fs-sm)}
.ux-res button[aria-selected="true"],.ux-res button:hover{background:var(--surface-2)}
.ux-res .k{font-size:var(--ux-fs-xs);font-weight:700;text-transform:uppercase;color:var(--text-secondary);min-width:52px}
.ux-res .s{color:var(--text-secondary);font-size:var(--ux-fs-xs);margin-left:auto;white-space:nowrap}
.ux-kf{outline:2px solid var(--ux-focus)!important;outline-offset:2px}
/* overlays: print view and showcase */
.ux-ov{position:fixed;inset:0;z-index:70;background:var(--surface-0);overflow:auto;padding:var(--ux-s5) var(--ux-s4)}
.ux-ov .in{max-width:1100px;margin:0 auto;display:flex;flex-direction:column;gap:var(--ux-s4)}
.ux-ov .bar{display:flex;gap:var(--ux-s2);align-items:center;flex-wrap:wrap}
.ux-ov .bar h1{font-size:var(--ux-fs-xl);margin:0 auto 0 0}
.ux-toast{position:fixed;left:16px;bottom:16px;z-index:90;max-width:min(520px,calc(100vw - 32px))}
.ux-frames{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:var(--ux-s4);align-items:start}
.ux-frame{border:1px solid var(--border);border-radius:var(--ux-r-lg);padding:var(--ux-s4);background:var(--surface-0);color:var(--text-primary);display:flex;flex-direction:column;gap:var(--ux-s3);container-type:inline-size;min-width:0}
.ux-frame.m{max-width:390px}
.ux-frame h3{margin:0;font-size:var(--ux-fs-md)}
.ux-frame h4{margin:4px 0 0;font-size:var(--ux-fs-xs);text-transform:uppercase;letter-spacing:.04em;color:var(--text-secondary)}
/* .ux-th-light / .ux-th-dark (showcase frames) are defined in TOKENS with the new palette */
.pi-st.merged{color:var(--good)!important}.pi-s.ok{color:var(--good)!important}.pi-s.bad{color:var(--critical)!important}
.ux-swatch{display:flex;flex-wrap:wrap;gap:6px}.ux-swatch span{width:44px;height:28px;border-radius:var(--ux-r-sm);border:1px solid var(--border);font-size:9px;display:flex;align-items:flex-end;padding:2px;box-sizing:border-box}
.ux-scale{display:flex;gap:6px;align-items:flex-end}.ux-scale i{display:block;background:var(--ux-accent);border-radius:2px;width:10px}
/* decision first on a phone: a shorter header so the decision is near the top */
@media (max-width:600px){.seg .tx small,.pills .c,#hdrSub{display:none}.pills .grp{display:inline;padding:0 2px 0 6px}.viz-root h1{font-size:19px;line-height:1.25}
  .vnav .seg{flex-wrap:wrap;max-width:100%}.vnav .seg button{padding:6px 10px;gap:6px;min-width:0;flex:1 1 auto;min-height:32px}.vnav .seg .ic{display:none}.vnav .seg .tx b{font-size:12.5px;white-space:nowrap}
  .pills{gap:4px}.pills button{padding:6px 10px;font-size:12.5px;min-height:32px;box-sizing:border-box}.vnav label.all{font-size:11.5px}
  #obsBar>*:not(#uxBarStale):not(:first-child){display:none}#obsBar button{display:none}
  .viz-root h1{font-size:17px}.vnav label.all,.vnav .lang+label,#vAll+*{font-size:11px}.vnav .row>label{display:none}.ux-pill .ux-chip.stale{display:none}
  .ux-banner .row{grid-template-columns:minmax(0,1fr)}.ux-banner .acts{margin-left:0}.ux-search{flex:1 1 100%}
  table.ux-t2c thead{display:none}table.ux-t2c tr{display:block;border-top:1px solid var(--border);padding:4px 0}table.ux-t2c td{display:block;border:0;padding:2px 4px}
  table.ux-t2c td[data-l]::before{content:attr(data-l) ": ";font-weight:700;color:var(--text-secondary)}}
@container (max-width:600px){.ux-banner .row{grid-template-columns:minmax(0,1fr)}.ux-banner .acts{margin-left:0}
  table.ux-t2c thead{display:none}table.ux-t2c tr{display:block;border-top:1px solid var(--border);padding:4px 0}table.ux-t2c td{display:block;border:0;padding:2px 4px}
  table.ux-t2c td[data-l]::before{content:attr(data-l) ": ";font-weight:700;color:var(--text-secondary)}.ux-cards{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}
@media (prefers-reduced-motion:reduce){.ux-skel,#dkWhereB:empty,#dkDecideB:empty,#dkBlockB:empty,#dkGatesB:empty,#tdyBody:empty,#relBody:empty,section[data-ops]:empty,section[data-research]:empty{animation:none}}
@media print{.vnav,.ux-skip,#uxKeys,.ux-search,#piDrawer:not(.on),.ent-drawer:not(.on),.ux-pill,.obs-refresh{display:none!important}body{background:#fff!important;color:#000!important}.viz-root{overflow:visible!important}section{break-inside:auto}h2{break-after:avoid}
body:has(#uxPrint:not([hidden])) *{visibility:hidden!important}#uxPrint,#uxPrint *{visibility:visible!important}#uxPrint{position:absolute;inset:0;padding:0;background:#fff;color:#000}#uxPrint .bar button{display:none}}
/* ---- round 3 (expert review A_visual / B_content / C_ia): "calm desk" - 3 sizes, 2 weights, no uppercase, quiet links,
   data age in one place, help text off by default, Today banner = 3 lines + Details ---- */
.viz-root{--ux-fs-xs:13px;--ux-fs-sm:13px;--ux-fs-md:14px;--ux-fs-lg:15px;--ux-fs-xl:20px}
.viz-root *:not(code):not(kbd):not(pre){text-transform:none!important;letter-spacing:normal!important}
.viz-root :is(b,strong,th,h1,h2,h3,h4,.ux-chip,.dk-chip,.tdy-v,.seg .tx b,.pills button[aria-selected="true"],.lang button,.ux-btn,.ux-card .val,.ux-card .lab,.dk-st,.ux-chip::before){font-weight:600!important}
.viz-root :is(.dk-chip,.dk-stale,.tdy-v,.seg2,.tdy-row.hd,.sdesc .sd,.ffc .sd,.imp .sd,.ent-lab,.pills button,.lang button,.vnav label.all,.ux-keys,.ux-ev){font-size:13px!important}
.viz-root .ent-l,.viz-root .pm-pr,.viz-root .ux-ev{text-decoration:none!important}
.viz-root .ent-l:is(:hover,:focus-visible),.viz-root .pm-pr:is(:hover,:focus-visible),.viz-root .ux-ev:is(:hover,:focus-visible){text-decoration:underline dotted!important;text-underline-offset:2px}
/* header + nav: one title line, one stamp line (build · Refresh data · Data ▸), seg without captions, pills without groups / badges */
#hdrSub,header .sub{display:none!important}
header h1{font-size:20px!important;line-height:28px!important;margin:0!important}
.vnav .seg .tx small,.vnav .seg .ic,.pills .grp,.pills .c{display:none!important}
.vnav{padding-top:6px!important;padding-bottom:6px!important}
.vnav .row{gap:10px!important}
.vnav .seg{padding:3px!important;border-radius:10px!important}.vnav .seg button{padding:4px 12px!important;gap:6px!important}.vnav .seg .tx b{font-size:13px!important}
.pills{margin-top:4px!important}.pills button{padding:4px 10px!important}
.vnav .ux-search{flex:0 1 240px!important}
@media (min-width:768px){.ux-built{display:inline!important}}
.ux-built{margin:0!important;font-size:13px!important}
#hdrRefresh{font-size:13px!important;padding:0 8px!important}#hdrRefreshSt{font-size:13px!important}
.ux-age{display:inline-block;position:relative;margin-left:10px;font-size:13px;color:var(--text-secondary)}
.ux-age>summary{cursor:pointer;list-style:none;display:inline}.ux-age>summary::-webkit-details-marker{display:none}
.ux-age>summary:focus-visible{outline:2px solid var(--ux-focus);outline-offset:2px}
.ux-age.old>summary{color:var(--ux-warn)}
.ux-age .pop{position:absolute;z-index:60;left:0;top:calc(100% + 4px);width:min(640px,92vw);box-sizing:border-box;background:var(--surface-1);border:1px solid var(--border);border-radius:8px;box-shadow:var(--ux-e2);padding:12px;color:var(--text-primary)}
.ux-age table{width:100%;border-collapse:collapse}.ux-age td{padding:4px 6px;border-top:1px solid var(--border);vertical-align:top}
.ux-age td.old{color:var(--ux-warn)}.ux-age .m{color:var(--text-secondary)}.ux-age p{margin:8px 0 0}
#obsBar{display:none!important}
.ux-age #obsBar{display:flex!important;margin:8px 0 0;border:0;border-top:1px solid var(--border);border-radius:0;padding:8px 0 0;background:none}
.ux-age .obs-bar .src span{border-color:var(--border)!important;color:var(--text-secondary)!important}
.ux-age .obs-bar .src span.stale{border-color:var(--ux-warn)!important;color:var(--ux-warn)!important}
.ux-age .obs-bar .lamp.live{background:var(--text-muted)!important;box-shadow:none!important}
/* data age is never green or red: fresh = plain grey text, old = amber */
.ux-chip.na{color:var(--text-secondary);border-color:var(--border)}
/* help text (was "Descriptions"): off by default; hides subtitles, "how it is computed" notes and section descriptions */
body.nodesc section[data-view] p.sub:not([data-ux]),body.nodesc .ops-src,body.nodesc .sdesc{display:none!important}
/* Today: 0A repeats the banner; 0B / 0C / 0D start folded with a one-line summary (the weekly full build has its own tab, #obs/weekly) */
#uxDecision~#dkWhere,section.ux-gone{display:none!important}
@media screen{body:not([data-all="1"]) section.ux-folded>:not(.head),body:not([data-all="1"]) section.ux-folded>.head>:not(h2):not(.ux-fold){display:none!important}}
.ux-fold{all:unset;cursor:pointer;display:block;margin-top:2px;font-size:13px;color:var(--text-secondary)}
.ux-fold:hover{color:var(--text-primary)}.ux-fold:focus-visible{outline:2px solid var(--ux-focus);outline-offset:2px}.ux-fold .old{color:var(--ux-warn)}
section.ux-folded{padding-top:10px!important;padding-bottom:10px!important}section.ux-folded .head{margin-bottom:0!important}
/* decision banner: verdict + top blocker + next action; everything else behind "Details" */
.ux-banner .hd h2{font-size:20px!important;line-height:28px;font-weight:600!important}
.viz-root .ux-banner .row>b{font-size:13px!important;font-weight:400!important;color:var(--text-secondary)}
.ux-banner .row{grid-template-columns:110px minmax(0,1fr)}
.ux-banner>.ux-det>summary{cursor:pointer;font-size:13px;color:var(--text-secondary)}
.ux-banner>.ux-det>summary:focus-visible{outline:2px solid var(--ux-focus)}
.ux-banner .ux-detb{display:flex;flex-direction:column;gap:var(--ux-s2);margin-top:var(--ux-s2)}
.ux-banner .ux-detb .acts{margin-left:0}
.ux-own{color:var(--text-secondary)}
@media (max-width:600px){.ux-banner .row{grid-template-columns:minmax(0,1fr)}}
/* UX:CSS:END */
"""

TOKENS = r"""
<style id="rd-tokens">
/* RD:TOKENS - round 3 (expert review D_identity 3.8): the ONLY place colours are defined; last in <head>, so it wins.
   Cool-neutral greys, ONE indigo accent (links, primary button, selected tab, focus, info), status = ok / warn / bad (+ -bg),
   chart series never green / amber / red / indigo. Written by build_ux.py from ux_ui.TOKENS. */
:root{
  color-scheme:light;
  --bg:#f6f7f9; --surface-1:#ffffff; --surface-2:#f1f3f6;
  --border:#e2e5ea; --border-strong:#c7ccd4; --grid:#eceff3;
  --text-1:#14171c; --text-2:#475061; --text-3:#646c7a;
  --accent:#4c5bd4; --accent-hover:#3f4cc0; --accent-text:#4352c9; --accent-subtle:#eef0fd; --on-accent:#fff; --focus:#4c5bd4;
  --ok:#1b7a3d; --ok-bg:#e7f5ec; --warn:#8a5800; --warn-bg:#fdf4dc;
  --bad:#c0322d; --bad-bg:#fdecec; --info:#4352c9; --info-bg:#eef0fd;
  --series-1:#1479b0; --series-2:#9c8a66; --series-3:#4e586c; --series-4:#3a9da2; --series-5:#6d389e; --series-6:#cc6490;
  --seq-1:#bfe3fe; --seq-2:#91c5ea; --seq-3:#58a0d1; --seq-4:#287caf; --seq-5:#1d587c;
  --shadow-overlay:0 8px 24px rgba(20,23,28,.12),0 0 0 1px rgba(20,23,28,.06);
  --r-ctl:6px; --r-box:8px; --r-pill:999px;
  --font:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,"Cascadia Mono",Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  color-scheme:dark;
  --bg:#0f1115; --surface-1:#16191e; --surface-2:#1d2128;
  --border:#2a2f37; --border-strong:#3b414c; --grid:#22262d;
  --text-1:#e7e9ee; --text-2:#a9b0bc; --text-3:#8b93a1;
  --accent:#5865e8; --accent-hover:#4853d6; --accent-text:#9aa3f6; --accent-subtle:#1f2340; --on-accent:#fff; --focus:#9aa3f6;
  --ok:#4cc27a; --ok-bg:#10291a; --warn:#e3b04b; --warn-bg:#2e2410;
  --bad:#f2726b; --bad-bg:#331717; --info:#9aa3f6; --info-bg:#1f2340;
  --series-1:#54a7de; --series-2:#cdbc98; --series-3:#768095; --series-4:#76cfd3; --series-5:#a877dc; --series-6:#f28cb5;
  --seq-1:#13364d; --seq-2:#1c5274; --seq-3:#2676a6; --seq-4:#58a0d1; --seq-5:#9bcbee;
  --shadow-overlay:0 8px 24px rgba(0,0,0,.5),0 0 0 1px #2a2f37;
}}
:root[data-theme="dark"]{ /* same values as the media block: keep the two in sync */
  color-scheme:dark;
  --bg:#0f1115; --surface-1:#16191e; --surface-2:#1d2128;
  --border:#2a2f37; --border-strong:#3b414c; --grid:#22262d;
  --text-1:#e7e9ee; --text-2:#a9b0bc; --text-3:#8b93a1;
  --accent:#5865e8; --accent-hover:#4853d6; --accent-text:#9aa3f6; --accent-subtle:#1f2340; --on-accent:#fff; --focus:#9aa3f6;
  --ok:#4cc27a; --ok-bg:#10291a; --warn:#e3b04b; --warn-bg:#2e2410;
  --bad:#f2726b; --bad-bg:#331717; --info:#9aa3f6; --info-bg:#1f2340;
  --series-1:#54a7de; --series-2:#cdbc98; --series-3:#768095; --series-4:#76cfd3; --series-5:#a877dc; --series-6:#f28cb5;
  --seq-1:#13364d; --seq-2:#1c5274; --seq-3:#2676a6; --seq-4:#58a0d1; --seq-5:#9bcbee;
  --shadow-overlay:0 8px 24px rgba(0,0,0,.5),0 0 0 1px #2a2f37;
}
/* legacy aliases: old names keep working */
:root,:root:not([data-theme="light"]),:root[data-theme]{
  --surface-0:var(--bg); --text-primary:var(--text-1); --text-secondary:var(--text-2); --text-muted:var(--text-3);
  --ux-accent:var(--accent-text); --ux-focus:var(--focus);
  --good:var(--ok); --good-text:var(--ok); --ux-ok:var(--ok);
  --warning:var(--warn); --ux-warn:var(--warn);
  --critical:var(--bad); --crit-text:var(--bad); --ux-fail:var(--bad); --muted-text:var(--text-3);
  --seq-250:var(--seq-2); --seq-450:var(--seq-4); --seq-600:var(--seq-5);
  --ux-r-sm:var(--r-ctl); --ux-r-md:var(--r-box); --ux-r-lg:var(--r-box); --ux-r-pill:var(--r-pill); --ux-e1:none; --ux-e2:var(--shadow-overlay);
}
/* showcase frames (#ux) draw both themes side by side */
.ux-th-light{
  color-scheme:light;
  --bg:#f6f7f9; --surface-1:#ffffff; --surface-2:#f1f3f6;
  --border:#e2e5ea; --border-strong:#c7ccd4; --grid:#eceff3;
  --text-1:#14171c; --text-2:#475061; --text-3:#646c7a;
  --accent:#4c5bd4; --accent-hover:#3f4cc0; --accent-text:#4352c9; --accent-subtle:#eef0fd; --on-accent:#fff; --focus:#4c5bd4;
  --ok:#1b7a3d; --ok-bg:#e7f5ec; --warn:#8a5800; --warn-bg:#fdf4dc;
  --bad:#c0322d; --bad-bg:#fdecec; --info:#4352c9; --info-bg:#eef0fd;
  --series-1:#1479b0; --series-2:#9c8a66; --series-3:#4e586c; --series-4:#3a9da2; --series-5:#6d389e; --series-6:#cc6490;
  --seq-1:#bfe3fe; --seq-2:#91c5ea; --seq-3:#58a0d1; --seq-4:#287caf; --seq-5:#1d587c;
  --shadow-overlay:0 8px 24px rgba(20,23,28,.12),0 0 0 1px rgba(20,23,28,.06);
  --surface-0:var(--bg); --text-primary:var(--text-1); --text-secondary:var(--text-2); --text-muted:var(--text-3);
  --ux-accent:var(--accent-text); --ux-focus:var(--focus);
  --good:var(--ok); --good-text:var(--ok); --ux-ok:var(--ok);
  --warning:var(--warn); --ux-warn:var(--warn);
  --critical:var(--bad); --crit-text:var(--bad); --ux-fail:var(--bad); --muted-text:var(--text-3);
  --seq-250:var(--seq-2); --seq-450:var(--seq-4); --seq-600:var(--seq-5);
  --ux-r-sm:var(--r-ctl); --ux-r-md:var(--r-box); --ux-r-lg:var(--r-box); --ux-r-pill:var(--r-pill); --ux-e1:none; --ux-e2:var(--shadow-overlay);}
.ux-th-dark{
  color-scheme:dark;
  --bg:#0f1115; --surface-1:#16191e; --surface-2:#1d2128;
  --border:#2a2f37; --border-strong:#3b414c; --grid:#22262d;
  --text-1:#e7e9ee; --text-2:#a9b0bc; --text-3:#8b93a1;
  --accent:#5865e8; --accent-hover:#4853d6; --accent-text:#9aa3f6; --accent-subtle:#1f2340; --on-accent:#fff; --focus:#9aa3f6;
  --ok:#4cc27a; --ok-bg:#10291a; --warn:#e3b04b; --warn-bg:#2e2410;
  --bad:#f2726b; --bad-bg:#331717; --info:#9aa3f6; --info-bg:#1f2340;
  --series-1:#54a7de; --series-2:#cdbc98; --series-3:#768095; --series-4:#76cfd3; --series-5:#a877dc; --series-6:#f28cb5;
  --seq-1:#13364d; --seq-2:#1c5274; --seq-3:#2676a6; --seq-4:#58a0d1; --seq-5:#9bcbee;
  --shadow-overlay:0 8px 24px rgba(0,0,0,.5),0 0 0 1px #2a2f37;
  --surface-0:var(--bg); --text-primary:var(--text-1); --text-secondary:var(--text-2); --text-muted:var(--text-3);
  --ux-accent:var(--accent-text); --ux-focus:var(--focus);
  --good:var(--ok); --good-text:var(--ok); --ux-ok:var(--ok);
  --warning:var(--warn); --ux-warn:var(--warn);
  --critical:var(--bad); --crit-text:var(--bad); --ux-fail:var(--bad); --muted-text:var(--text-3);
  --seq-250:var(--seq-2); --seq-450:var(--seq-4); --seq-600:var(--seq-5);
  --ux-r-sm:var(--r-ctl); --ux-r-md:var(--r-box); --ux-r-lg:var(--r-box); --ux-r-pill:var(--r-pill); --ux-e1:none; --ux-e2:var(--shadow-overlay);}
.viz-root{background:var(--bg);color:var(--text-1)}
/* accent split (D_identity 2 / 3.7): UI = accent; --series-* is for chart marks only */
.viz-root a:not(.ux-btn):not(.ux-pill):not(.tr-btn):not(.goto-btn),.viz-root a:not(.ux-btn):not(.ux-pill):not(.tr-btn):not(.goto-btn):visited{color:var(--accent-text)}
.viz-root :focus-visible{outline-color:var(--focus)!important}
.viz-root .ux-btn.pri,.viz-root .tr-btn.pri,.viz-root .obs-bar button.pri{background:var(--accent)!important;border-color:var(--accent)!important;color:var(--on-accent)!important}
.viz-root .ux-btn.pri:hover,.viz-root .tr-btn.pri:hover{background:var(--accent-hover)!important}
.viz-root :is(.goto-btn,.pm-pr,.ux-ev,.tdy-ev){color:var(--accent-text)}
.viz-root .pills button[aria-selected="true"]::after{background:var(--accent)!important}
.viz-root .seg button[aria-selected="true"]{box-shadow:0 0 0 1px var(--border-strong)!important}
/* one filled status chip (D_identity 3.2): tinted background, no border, no glyph; colour only from the status */
.viz-root :is(.ux-chip,.dk-chip,.tdy-v,.dk-stale,.pi-chip,.gch){border:0!important;border-radius:var(--r-pill)!important;box-shadow:none!important;background:var(--surface-2)!important}
.viz-root :is(.ux-chip.ok,.dk-chip.green,.tdy-v.t-ok,.gch.s-ok){color:var(--ok)!important;background:var(--ok-bg)!important}
.viz-root :is(.ux-chip.warn,.ux-chip.stale,.dk-chip.amber,.dk-stale,.tdy-v.t-do,.gch.s-run){color:var(--warn)!important;background:var(--warn-bg)!important}
.viz-root :is(.ux-chip.fail,.dk-chip.red,.tdy-v.t-act,.gch.s-fail){color:var(--bad)!important;background:var(--bad-bg)!important}
.viz-root .ux-chip.info{color:var(--info)!important;background:var(--info-bg)!important}
.viz-root :is(.ux-chip.unk,.dk-chip.gray,.gch.s-none,.tdy-v[data-verb="no_data"]){color:var(--text-2)!important;background:var(--surface-2)!important}
.viz-root .ux-chip.na{color:var(--text-2)!important;background:transparent!important;padding:0!important}
.viz-root .ux-chip::before{content:""!important;width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.viz-root .ux-chip.na::before,.viz-root .tdy-v[data-verb="no_data"]::before{display:none!important}
.viz-root :is(.tr-term,.tr-term-note) .gch[class]{background:transparent!important;color:#e6edf3!important}
/* no decorative left bars, no view badges (D_identity 1.2 #5, 4) */
.viz-root .ux-banner{border:1px solid var(--border)!important;border-radius:var(--r-box)!important}
.viz-root :is(.ux-pill,.ops-verdict,.ob-hero){border-left:1px solid var(--border)!important}
.viz-root :is(.sdesc,.callout,.ops-rule,.rv-tanote,.r11-q,.r11-qnote,.ops-why){border-left:0!important}
.viz-root h3[style*="border-left"],.viz-root [style*="border-left:2px"],.viz-root [style*="border-left:3px"]{border-left:0!important;padding-left:0!important}
.vnav .seg .ic{display:none!important}
header h1 .h1-pre{color:var(--text-3);font-weight:400}
/* group labels only in Tests & gates (D_identity 3.6) */
body:is([data-v="gates"],[data-v="cpu"],[data-v="gpu"]) .vnav .pills .grp{display:inline!important;font-size:13px;color:var(--text-3);padding:0 4px 0 12px;border-left:1px solid var(--border)}
</style>
"""

JS = r"""
<!-- UX:JS:START -->
<script>
/* UX layer (build_ux.py / ux_ui.py): decision banner, stale guard, search / jump, keyboard, deep links, print view,
   since-yesterday, rebase-now, design-system showcase (#ux). Local data only. */
(function(){
  const J=id=>{try{return JSON.parse((document.getElementById(id)||{}).textContent||'null')||{};}catch(e){return {};}};
  // data scripts can sit after this script in the page: read them when the DOM is complete (load())
  let UXD={},DESK={},OPS={},TODAY={},O={},AGES={};const redIdx={};
  function load(){UXD=J('uxData');DESK=J('deskData');OPS=J('opsData');TODAY=J('todayData');O=DESK.overview||{};
    AGES=Object.fromEntries((O.ages||[]).map(a=>[a.key,a]));
    if(window.PI&&!PI.data.reg.some(r=>r.src==='known_red'))(UXD.red||[]).forEach(r=>{redIdx[r.pipe]=PI.data.reg.length;PI.data.reg.push(r);});}
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en,L=a=>Array.isArray(a)?T(a[0],a[1]):(a&&a.en?T(a.en,a.vi):(a||''));
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const raw=s=>`<span class="obsraw">${esc(s)}</span>`;
  const STALE_H=48;   // review P1-11: 'now' is read on every call (a page left open must not freeze the data ages)
  /** @param {string} iso @returns {number} hours since */
  const ageH=iso=>{const t=Date.parse(String(iso||'').replace(' ','T')+(/(Z|[+-]\d\d:?\d\d)$/.test(iso||'')?'':'Z'));return isNaN(t)?NaN:(Date.now()-t)/36e5;};
  const ageTxt=h=>!isFinite(h)?T('age unknown','không rõ tuổi'):h<1?T('< 1 h','< 1 giờ'):h<48?Math.round(h)+T(' h',' giờ'):Math.round(h/24)+T(' d',' ngày');
  const chip=(k,txt,title)=>`<span class="ux-chip ${k}"${title?` title="${esc(title)}"`:''}>${txt}</span>`;
  // round 3: data age is never green or red (fresh = grey, old = amber "10 d old" / "cũ 10 ngày"); data-age marks it for ux_round3.py
  const ageChip=(label,h,lim)=>{lim=lim||STALE_H;const k=isNaN(h)?'unk':h>lim?'stale':'na';return `<span class="ux-chip ${k}" data-age="${isNaN(h)?'':Math.round(h)}"${h>lim?` title="${esc(T(`older than ${lim} h: not current`,`cũ hơn ${lim} giờ: không còn hiện hành`))}"`:''}>${esc(label)} · ${h>lim?T(`${ageTxt(h)} old`,`cũ ${ageTxt(h)}`):ageTxt(h)}</span>`;};
  const srcAge=k=>AGES[k]?ageH(AGES[k].at):NaN;
  const copy=(txt,btn)=>{const done=()=>{if(!btn)return;const o=btn.textContent;btn.textContent=T('copied','đã copy');setTimeout(()=>btn.textContent=o,1300);};
    if(navigator.clipboard)navigator.clipboard.writeText(txt).then(done,()=>prompt('',txt));else prompt('',txt);};
  const linkTo=h=>location.href.split('#')[0]+h;
  // ---------------------------------------------------------------- red dev gates -> backward Inspector entries
  const gateAge=g=>ageH(g&&g.last&&g.last.created_at);
  // ---------------------------------------------------------------- decision banner (Now · Release Desk)
  function verdict(){const st=O.status;const gates=O.dev_gates||[];const oldest=Math.max(...gates.map(gateAge).filter(x=>!isNaN(x)),srcAge('observe_snapshot')||0);
    const stale=oldest>STALE_H;const S=tagOf(O.stable),B=(O.blockers||[]).filter(b=>!b.stale&&b.gating!==false),W=O.watch||null;
    // round 3 (B_content 2.5): one status ladder for a release line. c = the state chip, t = what it means / what to do (<= 8 words)
    const miss=(((O.releases||[]).find(r=>r.tag===S)||{}).missing||[]).length,md=s=>String(s||'').slice(5,10);
    const SH=T('Shipped','Đã phát hành'),SHG=miss?T(`Shipped · ${miss} gaps`,`Đã phát hành · thiếu ${miss}`):SH;
    if(O.shipped&&W&&W.over)return {k:W.next_prep?'warn':'unk',c:SHG,t:W.next_prep?T(`Next line ${W.next_line}: see its prep doc`,`Dòng tiếp theo ${W.next_line}: xem tài liệu chuẩn bị`):T(`${S} watch is over: start ${W.next_line}`,`Hết theo dõi ${S}: bắt đầu ${W.next_line}`)};
    if(O.shipped&&B.length)return {k:'warn',c:SHG,t:T(`${S} — decide: post1 or known issue`,`${S} — cần quyết: post1 hay known issue`)};
    if(O.shipped&&st==='unverified')return {k:'warn',c:SHG,t:T(`${S} shipped · CI data too old to confirm`,`${S} đã phát hành · dữ liệu CI quá cũ để xác nhận`)};
    if(O.shipped)return {k:'ok',c:SHG,t:T(`${S} · watch issues to ${W?md(W.until):'T+7'}`,`${S} · theo dõi issue tới ${W?md(W.until):'T+7'}`)};
    if(st==='unverified')return {k:'warn',c:T('Unverified','Chưa kiểm chứng'),t:T('Only red evidence is older than 48 h','Bằng chứng đỏ duy nhất đã cũ hơn 48 giờ')};
    if(st==='red')return {k:'fail',c:T('Blocked','Bị chặn'),t:T('Fix the blockers before the next rc','Xử lý blocker trước khi cắt rc tiếp')};
    if(st==='green'&&stale)return {k:'warn',c:T('Unverified','Chưa kiểm chứng'),t:T(`Looks ready · CI data ${ageTxt(oldest)} old`,`Có vẻ sẵn sàng · dữ liệu CI cũ ${ageTxt(oldest)}`)};
    if(st==='green')return {k:'ok',c:T('Ready to ship','Sẵn sàng phát hành'),t:T('Ready for the next rc','Sẵn sàng cho rc tiếp theo')};
    return {k:'warn',c:T('Preparing','Đang chuẩn bị'),t:T('Almost ready for the next rc','Gần sẵn sàng cho rc tiếp theo')};}
  const staleSrc=()=>(O.ages||[]).filter(a=>ageH(a.at)>STALE_H).map(a=>a.label.split(' (')[0]);
  const KINDN={publish:['publish failed','publish lỗi'],artifact:['missing artifact','thiếu artifact'],ci:['dev red','dev đỏ'],pr:['bug not fixed','bug chưa sửa'],carryover:['carried over','chuyển tiếp']};
  const tagOf=x=>(x&&(x.tag||x))||'?';
  const polChip=b=>!b||b.gating!==false?'':b.policy==='decision'?chip('unk',T(`waits on ${b.policy_ref}`,`chờ ${b.policy_ref}`)):b.policy==='other_line'?chip('unk',T(`belongs to ${b.policy_ref}`,`thuộc ${b.policy_ref}`)):chip('info',T('known issue (not gating)','known issue (không chặn)'));
  function relState(){const st=tagOf(O.stable),la=O.latest||{},h=ageH(la.at);
    const out=st===tagOf(la)&&la.kind==='final';
    const miss=((O.releases||[]).find(r=>r.tag===st)||{}).missing||[];
    const gd=O.good&&O.good.tag,ml=miss.map(m=>String(m.label).replace(/^PyPI (\S+)$/,'$1 (PyPI)')).join(', ');
    // round 3 (B_content #5): fragments, not sentences; known issues are in Blockers, the prep-doc note is in the cockpit
    return out?T(`${st} · shipped ${ageTxt(h)} ago${miss.length?` · missing ${ml}`:''} · rollback ${gd||'none'}`,`${st} · phát hành ${ageTxt(h)} trước${miss.length?` · thiếu ${ml}`:''} · rollback ${gd||'không có'}`)
      :T(`Line ${O.line} · latest ${tagOf(la)} (${ageTxt(h)} ago) · stable ${st}`,`Dòng ${O.line} · mới nhất ${tagOf(la)} (${ageTxt(h)} trước) · stable ${st}`);}
  function phaseLine(){const c=document.querySelector('section[data-ops="nr-ck"] .nr-ph.cur');
    if(!c)return `${chip('unk',T('unknown','chưa biết'))} ${T('the release cockpit has not drawn its phases','release cockpit chưa vẽ các phase')}`;
    const b=c.querySelector('b'),n=c.querySelector('.nr-pn'),g=c.querySelector('.gch');
    return `<span class="obsraw">${esc((n?n.textContent.replace(/^\D+/,'')+' · ':'')+(b?b.textContent:''))}</span>${g?' · '+esc(g.textContent):''} <a href="#obs/coming" class="ux-ev" title="Release cockpit">→</a>`;}
  function queueLine(){const rv=(OPS.overlap||{}).review||{},items=[...(rv.queue||[]),...(rv.running||[])];
    const must=items.filter(x=>(x.clash||[]).some(c=>/^p[0-2]$/.test(c.level))).length,chk=items.filter(x=>(x.clash||[]).some(c=>c.level==='p3')).length;
    const oh=ageH((OPS.overlap||{}).at);   // round 2 (A3/B1/D1/F2): no green on old data; round 3: the snapshot age lives in the header "Data" item
    const none=oh<=24?chip('ok',T('none must rebase','không PR nào phải rebase')):chip('unk',T(`rebase need unknown · overlap data ${ageTxt(oh)} old`,`chưa rõ cần rebase · dữ liệu chồng lấn cũ ${ageTxt(oh)}`));
    const rdy=(TODAY.ready||[]).length;
    return `${must?chip('fail',T(`${must} rebase now`,`${must} cần rebase`)):none}${chk?` · <span title="${T('p3 overlap: same file','chồng lấn p3: cùng file')}">${T(`${chk} check`,`${chk} cần xem`)}</span>`:''} · <span title="${T("approved, waiting for the 'full' label","đã duyệt, chờ nhãn 'full'")}">${rdy} ${T('ready','sẵn sàng')}</span> <a href="#obs/overlap" class="ux-ev" title="${T('Rebase risk','Rủi ro rebase')}">→</a>`;}
  // round 3 (A_visual 5.2, B_content 3.1, C_ia P1): 3 visible lines (verdict, top blocker + owner, next action + copy); the rest in "Details"
  const OWNR={assignee:['assignee','người được giao'],author:['PR author','tác giả PR'],codeowners:['publish CODEOWNERS','CODEOWNERS publish']};
  function ownerTxt(o){if(!o||!o.who)return '';const tk=String(o.who).split(/[\s,]+/).filter(Boolean);
    const n=tk.filter(x=>!/^\+\d+$/.test(x)).length+tk.filter(x=>/^\+\d+$/.test(x)).reduce((a,x)=>a+(+x.slice(1)),0);const r=OWNR[o.how]||[o.how||'',o.how||''];
    return ` <span class="ux-own" title="${esc(o.who)}">· ${T('owner','phụ trách')}: ${esc(T(r[0],r[1]))}${n>1?` (${n})`:''}</span>`;}
  function shortTitle(b){const m=String(b.title||'').match(/PyPI (\S+) — uploaded (\S+) instead/);
    if(m)return [T(`${m[1]} on PyPI is a dev build (${m[2]})`,`${m[1]} trên PyPI là bản dev (${m[2]})`),false];
    return [String(T(b.title,b.title_vi||b.title)).replace(/\s*\((a pre-release|bản pre-release)[^)]*\)\)?/,'').replace(/^v[\d.]+\w*:\s*/,''),true];}
  function nextShort(top){if(!top)return '';if(top.decide_cmd&&!top.decided&&top.kind==='artifact')return T('Choose post1, upload or known issue','Chọn post1, upload bù hay known issue');
    if(top.kind==='publish'&&top.cmd)return T('Fix the build error, then re-run the publish job','Sửa lỗi build, rồi chạy lại job publish');return top.next?L(top.next):'';}
  function banner(){const B=O.blockers||[],top=B[0],v=verdict();
    const by={};B.forEach(b=>{by[b.kind]=(by[b.kind]||0)+1;});
    const red=(O.dev_gates||[]).filter(g=>g.last&&g.last.state==='failed');
    const gating=B.filter(b=>b.gating!==false&&!b.stale).length,recheck=B.filter(b=>b.gating!==false&&b.stale).length,known=B.filter(b=>b.gating===false).length;
    const decBtn=top&&top.decide_cmd&&!top.decided?` <button type="button" class="ux-btn pri" data-ux-copy="${esc(top.decide_cmd)}" title="${esc(top.decide_cmd)}">${T('Copy command','Chép lệnh')}</button>`:'';
    const evA=top&&top.evidence?` <a class="ux-ev" href="${esc(top.evidence)}" target="_blank" rel="noopener">${top.kind==='publish'?T('Failed job','Job lỗi'):T('Evidence','Bằng chứng')} ↗</a>`:'';
    const ns=nextShort(top),nl=top&&top.next?L(top.next):'';
    const nextAct=top?(ns?`<span${nl&&nl!==ns?` title="${esc(nl)}"`:''}>${esc(ns)}</span>${decBtn}${evA}`:top.cmd?`<button type="button" class="ux-btn pri" data-ux-copy="${esc(top.cmd)}" title="${esc(top.cmd)}">${T('Copy command','Chép lệnh')}</button>${evA}`:evA):'';
    const st=top?shortTitle(top):null;
    // 2026-11-26: the weekly full build (own tab #obs/weekly) shows here as one row: newest run with a result
    const WK=O.weekly||{},wl=WK.latest,WKS={passed:['ok','passed','đạt'],failed:['fail','failed','lỗi'],timed_out:['warn','timed out','quá giờ'],running:['info','running','đang chạy']};
    const wkRow=wl?`<div class="row"><b>${T('Weekly full build','Weekly full build')}</b><span data-ux="weekly">${chip((WKS[wl.verdict]||['unk'])[0],esc(T(...(WKS[wl.verdict]||[0,wl.verdict,wl.verdict]).slice(1))))}`+
      `${ageH(WK.last_run_at)>192?' '+chip('stale',T('no run in 8+ days','không có run trong 8+ ngày')):''} <a class="ux-ev" href="#obs/weekly">#${esc(wl.run_number)} · ${esc(String(wl.created_at||'').slice(0,10))} →</a></span></div>`:'';
    const topRow=top?`<div class="row"><b>${T('Top blocker','Blocker chính')}</b><span data-ux="top-blocker">${chip(top.gating===false?'info':top.stale?'stale':'fail',esc(T(...(KINDN[top.kind]||[top.kind,top.kind]))))}${polChip(top)}${top.decided?' '+chip('info',T(`decided: ${top.decided.action.replace('_',' ')} · ${String(top.decided.at).slice(0,10)}`,`đã quyết: ${top.decided.action.replace('_',' ')} · ${String(top.decided.at).slice(0,10)}`),top.decided.reason):''} <span${st[1]?' class="obsraw"':''} title="${esc(T(top.title,top.title_vi||top.title))}">${esc(st[0])}</span>${ownerTxt(top.owner)}${srcAge(top.src)>STALE_H?' '+ageChip(T('data','dữ liệu'),srcAge(top.src)):''}</span></div>`
      :`<div class="row"><b>${T('Top blocker','Blocker chính')}</b><span data-ux="top-blocker">${chip('ok',T('none','không có'))}</span></div>`;
    const det=[`<div class="row"><b>${T('Release','Release')}</b><span data-ux="release-state">${relState()}</span></div>`,
      `<div class="row"><b>${T('Phase','Giai đoạn')}</b><span data-ux="phase">${phaseLine()}</span></div>`,
      `<div class="row"><b>${T('Merge queue','Hàng đợi merge')}</b><span>${queueLine()}</span></div>`,
      `<div class="row"><b>${T('Blockers','Blocker')}</b><span title="${esc(Object.entries(by).map(([k,n])=>`${n} ${T(...(KINDN[k]||[k,k]))}`).join(' · '))}">${B.length} · ${T(`${gating} blocking · ${recheck} re-check · ${known} known`,`${gating} đang chặn · ${recheck} cần kiểm lại · ${known} known issue`)} <a href="#" class="ux-ev" data-ux-jump="dkBlock">${T('List','Danh sách')} ↓</a></span></div>`,
      red.length?`<div class="row"><b>${T('Dev red','Dev đỏ')}</b><span>${red.map(g=>`<span class="ux-gate">${raw(g.slug)}${gateAge(g)>STALE_H?' '+chip('stale',T(`${ageTxt(gateAge(g))} old`,`cũ ${ageTxt(gateAge(g))}`)):''}${redIdx[g.slug]!=null?` <button type="button" class="ux-btn" data-ux="find-cause" data-pi="reg:${redIdx[g.slug]}">${T('Find cause','Tìm nguyên nhân')} →</button>`:''}</span>`).join(' ')}</span></div>`:''].filter(Boolean);
    return `<div class="ux-banner ${v.k}" data-ux="banner"><div class="hd">${chip(v.k,esc(v.c))}<h2 data-ux="verdict" class="ux-vh">${esc(v.t)}</h2></div>`+topRow+
      (nextAct?`<div class="row"><b>${T('Do next','Việc cần làm')}</b><span data-ux="next-action">${nextAct}</span></div>`:'')+wkRow+
      `<details class="ux-det" data-ux="banner-details"><summary title="${T('Release, phase, merge queue, blockers, dev red','Release, giai đoạn, hàng đợi merge, blocker, dev đỏ')}">${T('Details','Chi tiết')} (${det.length})</summary><div class="ux-detb">${det.join('')}`+
      `<div class="acts"><button type="button" class="ux-btn" data-ux-copylink="#obs/today">${T('Copy link','Chép liên kết')}</button><a class="ux-btn" href="#decision">${T('Print / share view','Bản in / chia sẻ')}</a></div></div></details></div>`;}
  function specLine(){const KB=(window.PIKB&&PIKB.docs)||{},ids=Object.keys(KB);const frs=ids.filter(i=>i.startsWith('frs:')),rfc=ids.filter(i=>i.startsWith('rfc:'));
    const st=ids.filter(i=>(KB[i].proposals||[]).length);
    return `${frs.length} FRS · ${rfc.length} RFC · ${st.length?chip('stale',T(`${st.length} with update proposals`,`${st.length} có đề xuất cập nhật`)):chip('info',T('no update pending','không có cập nhật chờ'))} <span class="pi-why">${T('docs match the local facts; those facts are only as fresh as the data ages above','tài liệu khớp fact local; fact chỉ mới như tuổi dữ liệu ở trên')}</span> <a href="#docs" class="ux-ev">${T('Open the FRS list','Mở danh sách FRS')} →</a>`;}
  function docsList(){const KB=(window.PIKB&&PIKB.docs)||{};const D=(window.PI&&PI.data)||{areas:{}};
    const rows=Object.entries(KB).filter(([i])=>i.startsWith('frs:')).sort((a,b)=>b[1].proposals.length-a[1].proposals.length||a[0].localeCompare(b[0]));
    return `<div class="in"><div class="bar"><h1>${T('Specs (FRS per code area)','Đặc tả (FRS theo code area)')}</h1><a class="ux-btn" href="#obs/today">${T('Close','Đóng')}</a></div>`+
      `<p class="pi-why">${T('One FRS per code area, versioned in ops.db. Stale = an update proposal is open (facts changed). Type an F-id (F05) in the jump box to filter by feature.','Mỗi code area một FRS, có version trong ops.db. Cũ = có đề xuất cập nhật đang mở (fact đã đổi). Gõ F-id (F05) vào ô nhảy để lọc theo feature.')}</p>`+
      `<table class="ux-t2c" data-ux="docs-list"><thead><tr><th>FRS</th><th>${T('Features','Feature')}</th><th>${T('Version','Phiên bản')}</th><th>${T('State','Trạng thái')}</th></tr></thead><tbody>${rows.map(([id,d])=>`<tr><td data-l="FRS"><a href="#" class="ux-ev" data-pi="doc:${esc(id)}">${esc(id.slice(4))}</a> <span class="obsraw">${esc((D.areas[id.slice(4)]||{}).t||'')}</span></td><td data-l="${T('Features','Feature')}">${esc(((D.areas[id.slice(4)]||{}).F||[]).join(' '))}</td><td data-l="${T('Version','Phiên bản')}">v${esc(d.v)}</td><td data-l="${T('State','Trạng thái')}">${window.PIKB&&PIKB.docAge?PIKB.docAge(d):''}</td></tr>`).join('')}</tbody></table></div>`;}
  function drawBanner(){let s=document.getElementById('uxDecision');const where=document.getElementById('dkWhere');if(!where)return;
    if(!s){s=document.createElement('section');s.id='uxDecision';s.className='card ux-sec';s.dataset.view='obs';s.dataset.tab='today';
      const bar=document.getElementById('obsBar');(bar&&!bar.closest('.ux-age')&&(bar.compareDocumentPosition(where)&Node.DOCUMENT_POSITION_FOLLOWING)?bar:where).before(s);}   // decision above the snapshot bar
    s.innerHTML=banner();}
  // ---------------------------------------------------------------- round 3 (C_ia P3 / P6 / P9): Today keeps the banner and the inbox open;
  // 0B / 0C / 0D start folded with a one-line summary (count · worst state · age). Kept per viewer. (Weekly full build: own tab + one banner row.)
  const FOLD_KEY='uxFold:';
  function setFold(s,open){if(!s)return;s.classList.toggle('ux-folded',!open);const b=s.querySelector('.ux-fold');if(b){b.setAttribute('aria-expanded',String(open));const a=b.querySelector('.ar');if(a)a.textContent=open?'▾':'▸';}}
  function foldToday(){const od=h=>h>STALE_H?` · <span class="old">${T(`${ageTxt(h)} old`,`cũ ${ageTxt(h)}`)}</span>`:'';
    const B=O.blockers||[],D=O.decisions||[],G=O.dev_gates||[];
    const openD=D.filter(d=>d.status==='open').length,red=G.filter(g=>g.last&&g.last.state==='failed').length,gh=Math.min(...G.map(gateAge).filter(x=>!isNaN(x)));
    const gating=B.filter(b=>b.gating!==false&&!b.stale).length,recheck=B.filter(b=>b.gating!==false&&b.stale).length,known=B.filter(b=>b.gating===false).length;
    const S={dkDecide:T(`${openD} open of ${D.length}`,`${openD} còn mở / ${D.length}`)+(openD?od(srcAge('release_prep')):''),
      dkBlock:T(`${B.length} · ${gating} blocking · ${recheck} re-check · ${known} known`,`${B.length} · ${gating} đang chặn · ${recheck} cần kiểm lại · ${known} known issue`),
      dkGates:T(`${red} of ${G.length} red`,`${red} / ${G.length} đỏ`)+od(gh)};
    Object.entries(S).forEach(([id,txt])=>{const s=document.getElementById(id);const hd=s&&s.querySelector('.head');if(!hd)return;let b=hd.querySelector('.ux-fold');
      if(!b){b=document.createElement('button');b.type='button';b.className='ux-fold';b.setAttribute('aria-controls',id);const h2=hd.querySelector('h2');if(h2)h2.after(b);else hd.prepend(b);
        b.addEventListener('click',()=>{const open=s.classList.contains('ux-folded');setFold(s,open);try{localStorage.setItem(FOLD_KEY+id,open?'1':'0');}catch(e){}});
        let open=false;try{open=localStorage.getItem(FOLD_KEY+id)==='1';}catch(e){}s.classList.toggle('ux-folded',!open);}
      const open=!s.classList.contains('ux-folded');b.innerHTML=`<span class="ar" aria-hidden="true">${open?'▾':'▸'}</span> ${txt}`;b.setAttribute('aria-expanded',String(open));});}
  // ---------------------------------------------------------------- round 3 (A_visual 4.6, B_content 2.4): data age in one place, on the build-stamp line;
  // the PR / CI snapshot strip (#obsBar, with its warnings) moves into this popover
  function drawAge(){const hb=document.getElementById('hdrBuilt');if(!hb)return;let d=document.getElementById('uxAge');
    if(!d){d=document.createElement('details');d.id='uxAge';d.className='ux-age';d.dataset.ux='data-age';
      const rs=document.getElementById('hdrRefreshMore')||document.getElementById('hdrRefreshSt');(rs&&rs.parentNode===hb.parentNode?rs:hb).after(d);
      document.addEventListener('click',e=>{if(d.open&&!d.contains(e.target))d.open=false;});
      d.addEventListener('keydown',e=>{if(e.key==='Escape'&&d.open){d.open=false;d.querySelector('summary').focus();e.stopPropagation();}});}
    const A=(O.ages||[]).map(a=>({lab:a.label.split(' (')[0],h:ageH(a.at),at:a.at})).sort((x,y)=>(isNaN(y.h)?0:y.h)-(isNaN(x.h)?0:x.h)),old=A.filter(a=>a.h>STALE_H);
    const bar=document.getElementById('obsBar');if(bar&&d.contains(bar))bar.remove();
    d.classList.toggle('old',old.length>0);const wasOpen=d.open;
    d.innerHTML=`<summary>${old.length?T(`Data: ${old.length} sources old`,`Dữ liệu: ${old.length} nguồn cũ`):T('Data: up to date','Dữ liệu: mới')} ▸</summary><div class="pop" role="group" aria-label="${T('Data sources','Nguồn dữ liệu')}"><table><tbody>`+
      A.map(a=>`<tr><td class="obsraw">${esc(a.lab)}</td><td class="${a.h>STALE_H?'old':''}">${a.h>STALE_H?T(`${ageTxt(a.h)} old`,`cũ ${ageTxt(a.h)}`):ageTxt(a.h)}</td><td class="m">${esc(String(a.at||'').slice(0,16).replace('T',' '))}</td></tr>`).join('')+
      `</tbody></table><p class="m">${T('Older than 48 h counts as old. The 07:00 daily run or "Refresh data" updates it.','Cũ hơn 48 giờ là cũ. Lần chạy 07:00 hằng ngày hoặc nút "Làm mới dữ liệu" sẽ cập nhật.')}</p><div class="ux-agebar"></div></div>`;
    d.open=wasOpen;if(bar)d.querySelector('.ux-agebar').appendChild(bar);}
  // ---------------------------------------------------------------- stale guard: green on old data is neutralised and labelled
  function staleGuard(){const g=document.getElementById('dkGates');if(!g)return;const hs=(O.dev_gates||[]).map(gateAge).filter(x=>!isNaN(x));const h=hs.length?Math.min(...hs):NaN;
    const stale=!(h<=STALE_H);g.classList.toggle('ux-stalescope',stale);let n=g.querySelector('.ux-stalebox');
    if(stale){if(!n){n=document.createElement('div');n.className='ux-stalebox';const hd=g.querySelector('#dkGatesSub')||g.firstElementChild;hd.after(n);}
      n.innerHTML=`${chip('stale',T(`${ageTxt(h)} old`,`cũ ${ageTxt(h)}`))} ${T('Dev builds are old. Refresh before you decide.','Build dev đã cũ. Làm mới trước khi quyết.')}`;}
    else if(n)n.remove();}
  // ---------------------------------------------------------------- since yesterday (History)
  function since(){const ov=OPS.overlap||{},at=ov.at,out=[];
    const merged=(ov.merged||[]).filter(m=>{const d=Date.parse(at)-Date.parse(m.at);return d>=0&&d<=864e5;});
    if(!(ageH(at)<=24))out.push(`<li>${chip('stale',T('no data for the last 24 h','không có dữ liệu 24 giờ qua'))} <b>${T('Merges into dev','Merge vào dev')}</b> <span class="why">${T(`the overlap data ends ${esc((at||'?').replace('T',' ').slice(0,16))} UTC (${ageTxt(ageH(at))} ago); the line below is the 24 h before that, not yesterday`,`dữ liệu chồng lấn dừng ở ${esc((at||'?').replace('T',' ').slice(0,16))} UTC (${ageTxt(ageH(at))} trước); dòng bên dưới là 24 giờ trước mốc đó, không phải hôm qua`)}</span></li>`);
    out.push(`<li><b>${T(`${merged.length} PRs merged into dev`,`${merged.length} PR merge vào dev`)}</b> <span class="why">${T('in the 24 h to','trong 24 giờ tới')} ${esc((at||'?').replace('T',' ').slice(0,16))} UTC</span> ${ageChip(T('data','dữ liệu'),ageH(at),24)}<div>${merged.slice(0,10).map(m=>`<a href="#" class="ux-pr" data-pi="pr:${esc(m.num)}"><b>#${esc(m.num)}</b><span class="obsraw">${esc(m.title)}</span></a>`).join(' ')}${merged.length>10?` +${merged.length-10}`:''}</div></li>`);
    const opsAt=AGES.ops_db&&AGES.ops_db.at;const rel=(O.releases||[]).filter(r=>{const d=Date.parse(opsAt)-Date.parse(r.published_at||r.tagged_at);return d>=0&&d<=864e5;});
    out.push(`<li><b>${rel.length?T(`New release tags: ${rel.map(r=>r.tag).join(', ')}`,`Tag release mới: ${rel.map(r=>r.tag).join(', ')}`):T('No new release tag','Không có tag release mới')}</b> <span class="why">${T('in the 24 h to','trong 24 giờ tới')} ${esc((opsAt||'?').replace('T',' ').slice(0,16))} UTC · ${T('latest','mới nhất')} ${raw((O.latest&&O.latest.tag)||O.latest||'?')}</span> ${ageChip('ops.db',ageH(opsAt))}</li>`);
    const flips=(O.dev_gates||[]).filter(g=>g.recent&&g.recent.length>1&&g.recent[0]!==g.recent[1]);
    out.push(`<li><b>${flips.length?T('Dev gates that changed state','Gate dev đổi trạng thái'):T('No dev gate changed state','Không gate dev nào đổi trạng thái')}</b> ${flips.map(g=>`${chip(g.recent[0]==='failed'?'fail':'ok',raw(g.slug))} ${esc(g.recent[1])} → ${esc(g.recent[0])}`).join(' · ')} <span class="why">${T('between the last two builds','giữa hai build gần nhất')}</span> ${ageChip(T('newest dev build','build dev mới nhất'),Math.min(...(O.dev_gates||[]).map(gateAge)))}</li>`);
    const KB=(window.PIKB&&PIKB.docs)||{};const props=Object.entries(KB).flatMap(([id,d])=>(d.proposals||[]).filter(p=>ageH(p.at)<=24).map(p=>[id,p]));
    out.push(`<li><b>${T(`${props.length} knowledge base update proposals`,`${props.length} đề xuất cập nhật knowledge base`)}</b> <span class="why">${T('opened in the last 24 h','mở trong 24 giờ qua')}</span> ${props.slice(0,6).map(([id])=>`<a href="#" class="ux-pr" data-pi="doc:${esc(id)}"><b>${esc(id)}</b></a>`).join(' ')}</li>`);
    const RS=((window.RESEARCH&&RESEARCH.data)||{}).reports||[];const rs=RS.filter(r=>!r.sample&&ageH(r.created_at)<=24);
    out.push(`<li><b>${T(`${rs.length} research reports`,`${rs.length} research report`)}</b> <span class="why">${T('created in the last 24 h (shipped samples not counted)','tạo trong 24 giờ qua (không tính bản mẫu)')}</span></li>`);
    return `<h2>${T('Since yesterday','Từ hôm qua')}</h2><p class="sub">${T('What changed in the 24 h before each source was last refreshed. Each line shows its own data age.','Những gì thay đổi trong 24 giờ trước lần làm mới gần nhất của từng nguồn. Mỗi dòng ghi tuổi dữ liệu riêng.')}</p><ul class="ux-list" data-ux="since-yesterday">${out.join('')}</ul>`;}
  function drawSince(){const h=document.getElementById('dkHist');if(!h)return;let s=document.getElementById('uxSince');
    if(!s){s=document.createElement('section');s.id='uxSince';s.className='card ux-sec';s.dataset.view='obs';s.dataset.tab='hist';h.before(s);}s.innerHTML=since();}
  // ---------------------------------------------------------------- rebase now (Rebase risk)
  function rebaseNow(){const rv=(OPS.overlap||{}).review||{},items=[...(rv.queue||[]),...(rv.running||[])];
    const must=items.filter(x=>(x.clash||[]).some(c=>/^p[0-2]$/.test(c.level)));const check=items.filter(x=>!must.includes(x)&&(x.clash||[]).some(c=>c.level==='p3'));
    const li=(x,k)=>{const c=(x.clash||[]).slice().sort((a,b)=>a.level.localeCompare(b.level))[0];
      const inReady=(TODAY.ready||[]).some(r=>String(r.num)===String(x.num));
      return `<li>${chip(k,esc(c.level))}${inReady&&k==='fail'?' '+chip('warn',T("also in the ready-for-'full' queue: rebase first","cũng trong hàng đợi gắn 'full': rebase trước")):''} <a href="#" class="ux-pr" data-pi="pr:${esc(x.num)}" data-pi-view="5"><b>#${esc(x.num)}</b><span class="obsraw">${esc(x.title)}</span></a> <span class="why">${T('overlaps merged','chồng lấn với PR đã merge')} <a href="#" data-pi="pr:${esc(c.m)}">#${esc(c.m)}</a>: <span class="obsraw">${esc(L(c.same))}</span></span></li>`;};
    const at=(OPS.overlap||{}).at;
    return `<h2>${T('Rebase now','Rebase ngay')}</h2><p class="sub" title="${T('p0 = a symbol it uses was removed, p1 = same function, p2 = nearby lines, p3 = same file (check, not urgent), p4 = imports / config only','p0 = symbol nó dùng đã bị xoá, p1 = cùng hàm, p2 = dòng gần nhau, p3 = cùng file (cần xem, chưa gấp), p4 = chỉ import / config')}">${T('Overlap a merge from the last 24 h (p0–p2). Rebase, then re-run required checks.','Chồng lấn merge 24 giờ qua (p0–p2). Rebase, rồi chạy lại check bắt buộc.')} ${ageChip(T('overlap data','dữ liệu chồng lấn'),ageH(at),24)}</p>`+
      `<ul class="ux-list" data-ux="rebase-now">${must.length?must.map(x=>li(x,'fail')).join(''):!(ageH(at)<=24)?`<li class="ux-empty">${chip('unk',T('unknown','chưa biết'))} ${T(`The overlap data is ${ageTxt(ageH(at))} old, so the merges of the last 24 h are not known: re-run overlap_collect.py before trusting "nothing to rebase".`,`Dữ liệu chồng lấn đã ${ageTxt(ageH(at))}, nên chưa biết các merge 24 giờ qua: chạy lại overlap_collect.py trước khi tin "không có gì phải rebase".`)}</li>`:`<li class="ux-empty">${T('No open PR must rebase now (no p0–p2 overlap with the last 24 h of merges).','Không PR mở nào phải rebase ngay (không có chồng lấn p0–p2 với các merge 24 giờ qua).')}</li>`}</ul>`+
      (check.length?`<details class="ux-more"><summary>${T(`${check.length} to check, not urgent (p3: same file, different lines)`,`${check.length} cần xem, chưa gấp (p3: cùng file, khác dòng)`)}</summary><ul class="ux-list">${check.slice(0,12).map(x=>li(x,'warn')).join('')}</ul></details>`:'')+inactiveHot();}
  // round 2 F7: draft / conflicting PRs that overlap a recent merge at p0-p2 (rebase before they are reopened)
  function inactiveHot(){const G=((OPS.overlap||{}).groups||[]).filter(x=>x.inactive&&/^p[0-2]$/.test(x.level||''));if(!G.length)return '';
    const sub={draft:T('draft','nháp'),conflict:T('conflicting','đang xung đột'),old:T('inactive','không hoạt động')};
    return `<details class="ux-more"><summary>${T(`${G.length} draft / conflicting PRs also overlap at p0–p2: rebase before they are reopened`,`${G.length} PR nháp / đang xung đột cũng chồng lấn mức p0–p2: rebase trước khi mở lại`)}</summary><ul class="ux-list">${G.slice(0,12).map(x=>`<li>${chip('warn',esc(x.level))} ${chip('info',sub[x.p_sub]||esc(x.p_sub||''))} <a href="#" class="ux-pr" data-pi="pr:${esc(x.p)}" data-pi-view="5"><b>#${esc(x.p)}</b> <span class="obsraw">${esc(x.p_title||'')}</span></a></li>`).join('')}</ul></details>`;}
  function drawRebase(){const first=document.getElementById('ovReady')||document.querySelector('section[data-ops="overlap"]');if(!first)return;let s=document.getElementById('uxRebase');
    if(!s){s=document.createElement('section');s.id='uxRebase';s.className='card ux-sec';s.dataset.view='obs';s.dataset.tab='overlap';first.before(s);}s.innerHTML=rebaseNow();
    const top=document.querySelector('section[data-view="obs"][data-tab="overlap"]');if(top&&top!==s)top.before(s);}   // the ready-for-'full' queue moves itself on render: keep "Rebase now" first
  const keepFirst=()=>{const s=document.getElementById('uxRebase'),top=document.querySelector('section[data-view="obs"][data-tab="overlap"]');if(s&&top&&top!==s)top.before(s);};
  let kfObs=null;const watchRebase=()=>{const s=document.getElementById('uxRebase');if(!s||kfObs)return;kfObs=new MutationObserver(()=>{kfObs.disconnect();keepFirst();kfObs.observe(s.parentNode,{childList:true});});kfObs.observe(s.parentNode,{childList:true});};
  addEventListener('viewchange',e=>{if(e.detail&&e.detail.t==='overlap'){const s=document.getElementById('uxRebase'),top=document.querySelector('section[data-view="obs"][data-tab="overlap"]');if(s&&top&&top!==s)top.before(s);}});
  // ---------------------------------------------------------------- PR Inspector: merge verdict + copy link
  // expert review B1: the verdict uses ALL required checks of branch protection (PI.data.req), not only the gates the
  // change class implies, plus the review decision and the mergeable state; missing / stale / unknown-age data is never "Safe".
  function mergeVerdict(n){const M=PI.model(n),p=M.p||{};const g=PI.gstates(p);let snapH=ageH(PI.data.snap_at);if(isNaN(snapH))snapH=Infinity;
    // review 2026-11-26: required list and every N/N count come from PI.data.req (branch protection); gate states are the
    // merged rv.g / ck.g (PI.gstates, same merge as the gate tables) in the shared vocabulary (PI.stateWord)
    const req=(PI.data.req&&PI.data.req.length?PI.data.req:['DCO','Check code quality','k3-unit-tests','k3-multiprocess-test']),NR=req.length;
    const KEY=PI.gkey||{'DCO':'dco','Check code quality':'quality','k3-unit-tests':'unit','k3-multiprocess-test':'mp','k3-multiprocess-smoke':'smoke'};
    const W=(v,k)=>PI.stateWord(v,k);
    const rd=(p.ck||{}).rd,mg=(p.ck||{}).mg,head=(p.ck||{}).sha;
    const st=req.map(x=>[x,PI.stateNorm(g[KEY[x]])]);
    const mpBy=st.some(([x,v])=>KEY[x]==='mp'&&v==='bypass'),smoke=PI.stateNorm(g.smoke);
    // #6731: a bypassed heavy MP is green for branch protection, but it is not an MP result: the smoke run must pass
    const passed=([x,v])=>v==='ok'||(v==='bypass'&&smoke==='ok');
    const failed=st.filter(x=>x[1]==='fail'||x[1]==='cancel');if(mpBy&&(smoke==='fail'||smoke==='cancel'))failed.push(['k3-multiprocess-smoke',smoke]);
    const isDraft=p.st==='draft'||!!(p.ck||{}).dr;
    const notPassed=st.filter(x=>!passed(x)&&x[1]!=='fail'&&x[1]!=='cancel'&&!(isDraft&&x[1]==='draft'));   // a draft's 'draft' states are covered by the draft reason
    const nOk=st.filter(passed).length;
    const hot=(p.c24||[]).filter(c=>/^p[0-2]$/.test(c.lv||''));const ovH=ageH(PI.data.ov_at),ovOld=!(ovH<=24);
    const RW={REVIEW_REQUIRED:T('no approval yet','chưa có approval'),CHANGES_REQUESTED:T('changes requested','được yêu cầu sửa'),APPROVED:T('approved','đã approve')};
    const rdW=rd?(RW[rd]||rd.toLowerCase().replace(/_/g,' ')):T('review unknown','chưa rõ review');
    const MW={MERGEABLE:T('no conflict with dev','không xung đột với dev'),CONFLICTING:T('conflicts with dev','xung đột với dev')};
    const mgW=MW[mg]||T('mergeable unknown','chưa rõ có merge được không');
    const merged=p.st==='merged'||(p.rel||[]).length>0,noData=!p.rv&&!p.ck,snapDay=String(PI.data.snap_at||'?').slice(0,10);
    const firstOf=(x,v)=>{const k=KEY[x];
      if(k==='quality')return v==='running'?T('wait for Check code quality: the GitHub Test and CPU device jobs start only after it (#6730)','chờ Check code quality: job GitHub Test và CPU device chỉ chạy sau nó (#6730)')
        :T('get Check code quality to run: it gates the GitHub Test and CPU device jobs (#6730)','cho Check code quality chạy: nó chặn trước job GitHub Test và CPU device (#6730)');
      if(k==='mp'&&v==='label')return T('push or rebase so k3-multiprocess-test reports (bypass after #6731), or add the label full, force-ci or mp for the full run','push hoặc rebase để k3-multiprocess-test báo kết quả (bỏ qua sau #6731), hoặc thêm nhãn full, force-ci hay mp để chạy đủ');
      if(k==='mp'&&v==='bypass')return T('wait for k3-multiprocess-smoke: with MP bypassed it is the PR’s MP signal (#6731)','chờ k3-multiprocess-smoke: khi MP được bỏ qua, nó là tín hiệu MP của PR (#6731)');
      if(v==='running')return T(`wait for ${x} to finish`,`chờ ${x} chạy xong`);
      if(v==='draft')return T('mark the PR ready for review: unit tests and MP build ready PRs only','chuyển PR sang sẵn sàng review: unit test và MP chỉ build PR sẵn sàng');
      return T(`get ${x} to run: push a commit or re-run it`,`cho ${x} chạy: push commit mới hoặc chạy lại`);};
    // every blocking reason, in priority order: the first is the headline, the others go to "Also"
    const B=[];const add=(k,t,s,first,view,id)=>B.push({k,t,s,first,view:view||1,id});
    if(!M.p) add('unk',T(`#${n} is not in the local index: open it on GitHub.`,`#${n} không có trong index local: mở trên GitHub.`),'',null,1,'absent');
    else if(merged) add('info',T(`Already merged${(p.rel||[]).length?' · shipped in '+p.rel.join(', '):''}: review for history and bug analysis only.`,`Đã merge${(p.rel||[]).length?' · phát hành trong '+p.rel.join(', '):''}: chỉ xem để tra lịch sử và phân tích lỗi.`),'',null,1,'merged');
    else if(p.st&&p.st!=='open'&&p.st!=='draft') add('unk',T(`State: ${p.st}.`,`Trạng thái: ${p.st}.`),'',null,1,'state');
    else if(noData) add('unk',p.st?T(`Not in the PR snapshot of ${snapDay}: check it on GitHub.`,`Không có trong snapshot PR ngày ${snapDay}: xem trên GitHub.`):T(`State missing: the PR is in the local index but not in the PR snapshot of ${snapDay}. Check it on GitHub.`,`Thiếu trạng thái: PR có trong index local nhưng không có trong snapshot PR ngày ${snapDay}. Xem trên GitHub.`),'',null,1,'nodata');
    else{
      if(isDraft) add('warn',T('Draft PR: not ready to merge.','PR nháp: chưa sẵn sàng merge.'),T('draft','nháp'),T('mark the PR ready for review: k3-unit-tests and the MP pipelines build ready PRs only (#6730, #6731)','chuyển PR sang sẵn sàng review: k3-unit-tests và các pipeline MP chỉ build PR sẵn sàng (#6730, #6731)'),1,'draft');
      if(failed.length){const nm=failed.map(x=>x[0]),cx=failed.filter(x=>x[1]==='cancel').map(x=>x[0]);
        add('fail',T(`Not safe to merge: ${nm.join(', ')} ${cx.length===nm.length?'cancelled':'failed'}.`,`Chưa an toàn để merge: ${nm.join(', ')} ${cx.length===nm.length?'đã bị huỷ':'thất bại'}.`),T(`${nm.join(', ')} not passed`,`${nm.join(', ')} chưa đạt`),
          cx.length===nm.length?T(`re-run ${nm[0]} (cancelled, not failed)`,`chạy lại ${nm[0]} (bị huỷ, không phải lỗi)`):KEY[nm[0]]==='quality'?T('fix Check code quality first: it gates the GitHub Test and CPU device jobs (#6730)','sửa Check code quality trước: nó chặn trước job GitHub Test và CPU device (#6730)'):T(`open the failing run of ${nm[0]}, then fix it or re-run it`,`mở run lỗi của ${nm[0]}, rồi sửa hoặc chạy lại`),3,'fail');}
      if(mg==='CONFLICTING') add('fail',T('Not mergeable: the branch has conflicts with dev. Rebase first.','Chưa merge được: nhánh xung đột với dev. Rebase trước.'),T('conflicts with dev','xung đột với dev'),T('rebase on dev and resolve the conflicts','rebase lên dev và giải quyết xung đột'),5,'conflict');
      // review P1-6: the age of the overlap data is checked BEFORE the confident "Rebase first"
      if(hot.length&&ovOld) add('warn',T(`Overlap may be stale: #${hot[0].m} (${hot[0].lv}) overlapped, but the overlap data is ${ageTxt(ovH)} old.`,`Chồng lấn có thể đã cũ: #${hot[0].m} (${hot[0].lv}) chồng lấn, nhưng dữ liệu chồng lấn đã ${ageTxt(ovH)}.`),T(`${hot[0].lv} overlap (data may be stale)`,`chồng lấn ${hot[0].lv} (dữ liệu có thể cũ)`),T('re-run overlap_collect.py or compare with dev on GitHub before you rebase','chạy lại overlap_collect.py hoặc so với dev trên GitHub trước khi rebase'),5,'hotOld');
      else if(hot.length) add('warn',T(`It overlaps #${hot[0].m} merged in the last 24 h (${hot[0].lv}): rebase on dev, then re-run the required checks.`,`Chồng lấn với #${hot[0].m} vừa merge trong 24 giờ (${hot[0].lv}): rebase lên dev rồi chạy lại các check bắt buộc.`),T(`${hot[0].lv} overlap with #${hot[0].m}`,`chồng lấn ${hot[0].lv} với #${hot[0].m}`),T('rebase on dev, then re-run the required checks','rebase lên dev, rồi chạy lại các check bắt buộc'),5,'hot');
      if(notPassed.length){const nm=notPassed.map(x=>x[0]+(x[1]==='bypass'?' ('+T('bypassed; smoke','được bỏ qua; smoke')+' '+W(smoke,'smoke').t+')':''));
        add('warn',T(`Not ready: ${nm.join(', ')} ${notPassed.length>1?'have':'has'} not passed yet on head commit ${head||'?'}.`,`Chưa sẵn sàng: ${nm.join(', ')} chưa đạt trên commit head ${head||'?'}.`),T(`checks not passed: ${notPassed.map(x=>x[0]).join(', ')}`,`check chưa đạt: ${notPassed.map(x=>x[0]).join(', ')}`),firstOf(...notPassed[0]),1,'notrun');}
      if(rd!=='APPROVED') add('warn',T(`Not ready: the review says ${rdW} (1 approval needed).`,`Chưa sẵn sàng: review đang ở trạng thái ${rdW} (cần 1 approval).`),rdW,
        rd==='CHANGES_REQUESTED'?T('the author must address the requested changes and push','tác giả cần xử lý các yêu cầu sửa rồi push'):T('ask a code owner for an approval (1 needed)','nhờ một code owner approve (cần 1)'),1,'review');
      if(mg!=='MERGEABLE'&&mg!=='CONFLICTING') add('unk',T(`Mergeability unknown (GitHub says ${mg||'nothing'}): check the PR on GitHub.`,`Chưa biết merge được không (GitHub báo ${mg||'không có'}): xem PR trên GitHub.`),T('mergeable unknown','chưa rõ có merge được không'),T('open the PR on GitHub and look at the merge box','mở PR trên GitHub và xem ô merge'),1,'mg');
      if(p.sha&&head&&String(p.sha).slice(0,7)!==String(head).slice(0,7)) add('warn',T(`Not verified: the checks are for commit ${head}, the PR head is ${p.sha}. Wait for CI on the new head.`,`Chưa kiểm chứng: check thuộc commit ${head}, head của PR là ${p.sha}. Chờ CI trên head mới.`),T('checks for an older commit','check của commit cũ hơn'),T('wait for CI on the new head commit','chờ CI trên commit head mới'),1,'sha');
      if(/^(FAILURE|ERROR)$/.test(String((p.ck||{}).state||''))&&!failed.length) add('warn',T('Not ready: another (non-required) check failed. Look at it before merging.','Chưa sẵn sàng: một check khác (không bắt buộc) thất bại. Xem trước khi merge.'),T('another check failed','một check khác thất bại'),T('open the Checks tab on GitHub and read the failed check','mở tab Checks trên GitHub và đọc check thất bại'),1,'other');
      if(ovOld&&!hot.length) add('warn',T(`Unverified: the overlap data is ${ageTxt(ovH)} old, so the need to rebase is unknown.`,`Chưa kiểm chứng: dữ liệu chồng lấn đã ${ageTxt(ovH)}, chưa biết có cần rebase.`),T('overlap data old','dữ liệu chồng lấn cũ'),T('re-run overlap_collect.py or compare with dev on GitHub','chạy lại overlap_collect.py hoặc so với dev trên GitHub'),5,'ovOld');
      if((p.c24||[]).some(c=>c.lv==='p3')) add('warn',T('Check first: it edits a file that a merge of the last 24 h also changed (p3).','Xem trước: PR sửa một file mà merge 24 giờ qua cũng đổi (p3).'),T('p3 overlap','chồng lấn p3'),T('read the shared file in both PRs: same file, different lines','đọc file chung trong cả hai PR: cùng file, khác dòng'),5,'p3');
      if(snapH>STALE_H) add('warn',T(`Looks mergeable, but unverified: PR data is ${ageTxt(snapH)} old.`,`Có vẻ merge được nhưng chưa kiểm chứng: dữ liệu PR đã ${ageTxt(snapH)}.`),T(`stale data (PR data ${ageTxt(snapH)} old)`,`dữ liệu cũ (dữ liệu PR đã ${ageTxt(snapH)})`),T('re-check the PR on GitHub before merging','kiểm tra lại PR trên GitHub trước khi merge'),1,'stale');
    }
    let k,t,view=1,first;
    if(B.length){k=B[0].k;t=B[0].t;view=B[0].view;first=B[0].first;}
    else{k='ok';t=T(`Safe to merge on the CI evidence: ${nOk}/${NR} required checks passed and approved.`,`An toàn để merge theo bằng chứng CI: ${nOk}/${NR} check bắt buộc đạt và đã được approve.`);}
    // review P1-7: "Check first" follows the verdict reason; the concurrency view only when nothing blocks
    if(first==null){if(k==='ok'){const conc=M.files.some(f=>((PI.data.scan[f[0]]||{}).h||[]).some(h=>h[0]==='c'&&(f[4].includes(h[3])||f[5].includes(h[3]))));if(conc)view=4;}
      first=(PI.check?PI.check(M,view):[])[0]||'';}
    const also=B.slice(1).filter(r=>r.s);
    const lnk=(x,v,h)=>{const u=(g._url||{})[KEY[x]];return u&&(v==='fail'||v==='cancel')&&/^https:\/\//.test(u)?`<a href="${esc(u)}" target="_blank" rel="noopener" title="${T('Open the failing run','Mở run lỗi')}">${h} ↗</a>`:h;};   // round 2 F8
    const SHORT={fail:T('Not safe','Chưa an toàn'),warn:B.length&&B[0].id==='hot'?T('Rebase first','Rebase trước'):B.length&&B[0].id==='draft'?T('Draft','Nháp'):T('Not mergeable yet','Chưa merge được'),ok:T('Safe','An toàn'),info:T('Merged','Đã merge'),unk:T('Unknown','Chưa biết')};
    const ckChip=(x,v)=>{const w=W(v,KEY[x]);const txt=v==='bypass'?T('bypassed (#6731: smoke is the PR signal)','được bỏ qua (#6731: smoke là tín hiệu của PR)'):w.t;
      return lnk(x,v,chip(passed([x,v])?'ok':w.ux,`${esc(x)}: ${esc(txt)}`,w.tip));};
    const hist=!M.p||merged||noData||(p.st&&p.st!=='open'&&p.st!=='draft');
    const line=!M.p?T(`Not in the local index: open #${n} on GitHub.`,`Không có trong index local: mở #${n} trên GitHub.`):merged?T('Merged: CI gates are history.','Đã merge: các CI gate giờ là lịch sử.'):
      noData&&!p.st?T('State missing: the CI gates of this PR are not known here.','Thiếu trạng thái: chưa biết các CI gate của PR này ở đây.'):noData?T(`Not in the PR snapshot of ${snapDay}: open GitHub.`,`Không có trong snapshot PR ngày ${snapDay}: mở GitHub.`):T(`State ${p.st}: CI gates are not tracked.`,`Trạng thái ${p.st}: không theo dõi CI gate.`);
    const gh=`<a href="https://github.com/LMCache/LMCache/pull/${esc(n)}" target="_blank" rel="noopener">GitHub ↗</a>`;
    return `<div class="ux-banner ${k==='info'||k==='unk'?'':k}" data-ux="merge-verdict"><div class="hd">${chip(k,esc(SHORT[k]))}<b class="ux-vt">${esc(t)}</b></div>`+
      (also.length?`<div class="row" data-ux="also"><b>${T('Also','Ngoài ra')}</b><span>${also.map(r=>esc(r.s)).join(' · ')}</span></div>`:'')+
      (hist?`<div class="row" data-ux="gates-history"><b>${T('CI gates','CI gate')}</b><span>${esc(line)} ${gh}</span></div>`:
      `<div class="row"><b>${T('Check first','Kiểm tra trước')}</b><span>${esc(first)} <button type="button" class="ux-btn" data-ux-pv="${view}">${T('view','góc nhìn')} ${view} · ${esc(T(...((PI.views||[])[view-1]||['',''])))} →</button></span></div>`+
      `<div class="row"><b>${T('Required checks','Kiểm tra bắt buộc')} (${nOk}/${NR})</b><span data-ux="req-checks">${st.map(([x,v])=>ckChip(x,v)).join(' ')}${mpBy||g.smoke?' '+ckChip('k3-multiprocess-smoke',smoke)+` <span class="m">· ${T('smoke: not required yet','smoke: chưa bắt buộc')}</span>`:''}${head?` <span class="m">· ${T('head','commit head')} <code class="obsraw">${esc(head)}</code></span>`:''}</span></div>`+
      `<div class="row"><b>${T('Review · merge','Review · merge')}</b><span>${chip(rd==='APPROVED'?'ok':rd?'warn':'unk',esc(rdW))} ${chip(mg==='MERGEABLE'?'ok':mg==='CONFLICTING'?'fail':'unk',esc(mgW))} <span class="m">${T(`branch protection: ${NR} checks + 1 approval`,`branch protection: ${NR} check + 1 approval`)}</span></span></div>`)+
      `<div class="row"><b>${T('Owners','Người sở hữu')}</b><span>${(p.own||[]).length?p.own.map(o=>`<span class="obsraw">${esc(o)}</span>`).join(', ')+` <span class="m">CODEOWNERS</span>`:`<span class="m">${T('no CODEOWNERS rule for these files','không có luật CODEOWNERS cho các file này')}</span>`}</span></div>`+
      `<div class="row"><b>${T('Data age','Tuổi dữ liệu')}</b><span>${ageChip(T('PR snapshot','snapshot PR'),snapH)} ${ageChip(T('patches','patch'),ageH(PI.data.patches_at))} ${ageChip(T('overlap','chồng lấn'),ovH,24)}</span></div></div>`;}
  addEventListener('pirender',e=>{const d=e.detail||{},dr=document.getElementById('piDrawer');if(!d.key||!dr)return;
    const bar=dr.querySelector('.pi-bar');if(bar&&!bar.querySelector('[data-ux="copy-link"]')){const b=document.createElement('button');b.type='button';b.className='pi-btn';b.dataset.ux='copy-link';b.textContent=T('Copy link','Sao chép liên kết');bar.appendChild(b);}
    if(d.key.startsWith('pr:')&&d.dir==='fwd'){const body=dr.querySelector('#piBody');if(body&&!body.querySelector('[data-ux="merge-verdict"]'))body.insertAdjacentHTML('afterbegin',mergeVerdict(d.key.slice(3)));}});
  // ---------------------------------------------------------------- search / jump box
  let IDX=null;
  function index(){if(IDX)return IDX;const D=window.PI?PI.data:{prs:{},F:{},areas:{}},E=(window.ENT&&ENT.data&&ENT.data.nodes)||{},KB=(window.PIKB&&PIKB.docs)||{};IDX=[];
    Object.entries(D.prs).forEach(([n,p])=>IDX.push({k:'pr',key:'pr:'+n,l:'#'+n+' '+(p.t||''),s:p.st||'',n}));
    Object.entries(D.F||{}).forEach(([f,x])=>IDX.push({k:'feature',key:'F:'+f,l:f+' '+(x.name||''),s:T('FRS docs','tài liệu FRS'),f}));
    Object.entries(KB).forEach(([id,d])=>IDX.push({k:id.startsWith('frs')?'frs':'rfc',key:'doc:'+id,l:id+' '+(d.title||''),s:'v'+d.v+(d.proposals.length?' · '+d.proposals.length+' ⚑':'')}));
    Object.entries(D.areas||{}).forEach(([a,x])=>IDX.push({k:'area',key:'feature:'+a,l:a+' '+(x.t||''),s:(x.F||[]).join(' ')}));
    Object.values(E).forEach(nd=>{if(nd.kind==='ci')IDX.push({k:'gate',key:'ci:'+nd.id,l:nd.id+' '+(nd.title||''),s:nd.required?T('required','bắt buộc'):''});
      if(nd.kind==='release')IDX.push({k:'release',key:'release:'+nd.id,l:nd.id,s:nd.at||''});});
    (((window.RESEARCH&&RESEARCH.data)||{}).reports||[]).forEach(r=>IDX.push({k:'research',key:'rs:'+r.id,l:r.title+(r.pr?' #'+r.pr.number:''),s:r.context}));
    // expert review U7: tabs (with the words people use) and section headings are searchable too
    Object.entries(TABWORDS).forEach(([vt,w])=>IDX.push({k:'tab',key:'tab:'+vt,l:T(w[0],w[1])+' · '+w[2],s:'#'+vt}));
    const seen=new Set();document.querySelectorAll('section[data-view][data-tab]').forEach((sx,i)=>{const h=sx.querySelector('h2,h3');if(!h)return;const l=h.textContent.replace(/\s+/g,' ').trim();if(!l||seen.has(l))return;seen.add(l);
      if(!sx.id)sx.id='uxSec'+i;IDX.push({k:'section',key:'sec:'+sx.dataset.view+'/'+sx.dataset.tab+'/'+sx.id,l:l.slice(0,90),s:'#'+sx.dataset.view+'/'+sx.dataset.tab});});
    return IDX;}
  const TABWORDS={'obs/today':['Now · Release Desk','Bây giờ · Release Desk','today decision banner go no-go'],'obs/hist':['History','Lịch sử','since yesterday trend'],
    'obs/release':['Releases & trace','Bản phát hành & trace','registry publish tracer'],'obs/coming':['Next release','Bản phát hành tiếp theo','release cockpit runbook phase'],
    'obs/cost':['CI cost','Chi phí CI','cpu gpu job-min'],'obs/overlap':['Rebase risk','Rủi ro rebase','rebase now merge safety overlap queue full'],'obs/research':['Research intake','Tiếp nhận nghiên cứu','research reports'],
    'gates/guide':['Guide & gates','Hướng dẫn & gate','onboarding mental model'],'gates/tiers':['Tiers & impact','Tầng & tác động','tiers'],'cpu/overview':['CPU tests','Test CPU','overview'],
    'cpu/tiers':['CPU coverage & explorer','Độ phủ & explorer CPU','coverage explorer'],'cpu/cost':['CPU cost & findings','Chi phí & phát hiện CPU','findings'],'gpu/overview':['GPU overview','Tổng quan GPU','findings'],
    'gpu/tiers':['GPU workloads & cost','Workload & chi phí GPU','tiers cost'],'gpu/explore':['GPU mindmap','Sơ đồ tư duy GPU','mindmap explorer'],'r1130/baseline':['Report 1130 · baseline','Báo cáo 1130 · baseline','gpu cpu'],
    'r1130/green':['Report 1130 · time to green','Báo cáo 1130 · thời gian tới xanh','time to green merges'],'r1130/retry':['Report 1130 · retry','Báo cáo 1130 · chạy lại','retry waste'],
    'r1130/prs':['Report 1130 · PRs','Báo cáo 1130 · PR','per pr cost'],'r1130/track':['Report 1130 · track','Báo cáo 1130 · theo dõi','24 h now'],'r1130/quality':['Report 1130 · data quality','Báo cáo 1130 · chất lượng dữ liệu','inputs']};
  function search(q){q=q.trim().toLowerCase().replace(/^#/,'');if(!q)return [];const I=index();
    const fm=q.match(/^f(\d{1,2})$/);const fid=fm?'F'+fm[1].padStart(2,'0'):null;
    if(fid){const docs=Object.entries(PI.data.areas).filter(([a,x])=>(x.F||[]).includes(fid)).map(([a])=>I.find(e=>e.key==='doc:frs:'+a)).filter(Boolean);
      const f=I.find(e=>e.key==='F:'+fid);return [...docs,...(f?[f]:[])];}
    const exact=I.filter(e=>e.k==='pr'&&e.n===q);const sw=I.filter(e=>!exact.includes(e)&&e.l.toLowerCase().startsWith(q));
    const has=I.filter(e=>!exact.includes(e)&&!sw.includes(e)&&e.l.toLowerCase().includes(q));
    return [...exact,...sw,...has].slice(0,14);}
  function act(e){if(!e)return;const k=e.key;closeRes();
    if(k.startsWith('pr:')||k.startsWith('doc:'))return piOpen(k);
    if(k.startsWith('F:')){const r=search(k.slice(2));if(r[0]&&r[0].key.startsWith('doc:'))return piOpen(r[0].key);return;}
    if(k.startsWith('tab:')){const [v,t]=k.slice(4).split('/');return vizNav.show(v,t);}
    if(k.startsWith('sec:')){const [v,t,id]=k.slice(4).split('/');vizNav.show(v,t);return setTimeout(()=>{const x=document.getElementById(id);if(x){x.scrollIntoView({block:'start'});const h=x.querySelector('h2,h3');if(h){h.tabIndex=-1;h.focus({preventScroll:true});}}},60);}
    if(k.startsWith('rs:')){vizNav.show('obs','research');setTimeout(()=>{const c=document.getElementById('rs-'+k.slice(3));if(c){c.classList.add('focus');c.scrollIntoView({block:'center'});}},60);return;}
    if(window.openEntity)openEntity(k);}
  let res=[],sel=0,box,inp;
  function drawRes(){box.innerHTML=res.length?res.map((e,i)=>`<button type="button" role="option" id="uxOpt${i}" tabindex="-1" data-kind="${e.k}" data-i="${i}" aria-selected="${i===sel}"><span class="k">${esc(e.k)}</span><span class="obsraw">${esc(e.l.slice(0,90))}</span><span class="s obsraw">${esc(e.s||'')}</span></button>`).join(''):
    `<div class="ux-empty">${T('No match. Try a PR number, F05, a gate (k3-unit-tests), a tag (v0.5.8) or a code area (smcore).','Không khớp. Thử số PR, F05, một gate (k3-unit-tests), một tag (v0.5.8) hoặc code area (smcore).')}</div>`;box.classList.add('on');inp.setAttribute('aria-expanded','true');
    if(res.length)inp.setAttribute('aria-activedescendant','uxOpt'+sel);else inp.removeAttribute('aria-activedescendant');
    const lv=document.getElementById('uxLive');if(lv)lv.textContent=inp.value.trim()?(res.length?T(`${res.length} results`,`${res.length} kết quả`):T('No match','Không khớp')):'';}
  function closeRes(){if(box){box.classList.remove('on');inp.setAttribute('aria-expanded','false');inp.removeAttribute('aria-activedescendant');}}
  function drawPill(){const row=document.querySelector('.vnav .row');if(!row)return;let a=document.getElementById('uxPill');
    if(!a){a=document.createElement('a');a.id='uxPill';a.className='ux-pill';a.href='#obs/today';a.dataset.ux='pill';row.appendChild(a);}
    const v=verdict(),top=(O.blockers||[])[0],old=staleSrc().length;
    a.className='ux-pill '+v.k;a.innerHTML=`${chip(v.k,esc(v.c))} <span class="t">${esc(v.t)}</span>`;   // round 3: same state ladder as the banner; data age lives in the header
    a.title=v.t+(top?' · '+top.title:'');a.setAttribute('aria-label',T('Release decision: ','Quyết định release: ')+v.t);}
  function mountSearch(){const row=document.querySelector('.vnav .row');if(!row||document.getElementById('uxSearch'))return;
    const w=document.createElement('div');w.className='ux-search';w.innerHTML=`<input id="uxSearch" data-ux="search" type="search" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="uxRes" aria-label="${T('Go to a PR, feature, gate, release, tab or section','Đi tới PR, tính năng, gate, bản phát hành, tab hoặc mục')}" placeholder="${T('Search PR #, tag, check…','Tìm PR #, tag, check…')}"><span id="uxLive" class="ux-sr" role="status" aria-live="polite"></span><kbd>/</kbd><div class="ux-res" id="uxRes" role="listbox" data-ux="search-results"></div>`;
    const sp=row.querySelector('.sp');(sp||row.lastChild).before(w);inp=w.querySelector('input');box=w.querySelector('.ux-res');
    inp.addEventListener('input',()=>{res=search(inp.value);sel=0;drawRes();});
    inp.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();sel=Math.max(0,Math.min(res.length-1,sel+(e.key==='ArrowDown'?1:-1)));drawRes();}
      else if(e.key==='Enter'){e.preventDefault();act(res[sel]);inp.blur();}else if(e.key==='Escape'){closeRes();inp.blur();}});
    box.addEventListener('mousedown',e=>{const b=e.target.closest('[data-i]');if(b){e.preventDefault();act(res[+b.dataset.i]);}});
    inp.addEventListener('blur',()=>setTimeout(closeRes,150));}
  // ---------------------------------------------------------------- keyboard shortcuts on / off (expert review U3, WCAG 2.1.4)
  let keysOff=false;try{keysOff=localStorage.getItem('uxKeys')==='off';}catch(e){}
  // round 2 E2: while a modal is open, the page-level view / language / search keys must not change the page behind it
  // (the drawer's own keys such as j / k and 1-5 still work)
  addEventListener('keydown',e=>{const behind=typeof MODAL!=='undefined'&&MODAL.el&&/^[mtgecuorlbs\/]$/i.test(e.key);if(!(keysOff||behind)||e.ctrlKey||e.metaKey||e.altKey||e.key.length!==1)return;const t=e.target;if(t&&t.closest&&t.closest('input,textarea,select,[contenteditable]'))return;e.stopImmediatePropagation();},true);
  function mountKeys(){const row=document.querySelector('.vnav .row');if(!row||document.getElementById('uxKeys'))return;const b=document.createElement('button');b.type='button';b.id='uxKeys';b.className='ux-btn ux-keys';
    const draw=()=>{b.setAttribute('aria-pressed',String(!keysOff));b.textContent=keysOff?T('Shortcuts off','Phím tắt: tắt'):T('Shortcuts on','Phím tắt: bật');b.title=T('Single-key shortcuts: / search, j / k, O T U E, L. Turn off if they get in the way (speech input).','Phím tắt một phím: / tìm, j / k, O T U E, L. Tắt nếu bị vướng (nhập bằng giọng nói).');};
    b.addEventListener('click',()=>{keysOff=!keysOff;try{localStorage.setItem('uxKeys',keysOff?'off':'on');}catch(e){}draw();});draw();
    const s=document.querySelector('.ux-search');(s||row.lastChild).after(b);}
  // ---------------------------------------------------------------- keyboard: / search, j / k lists, Esc overlays
  const LISTS='#piDrawer.on .pi-items>li,#piDrawer.on .pi-check li,.ux-list>li,section[data-view]:not(.vhide) .tdy-row:not(.hd),section[data-view]:not(.vhide) .rs-card,section[data-view]:not(.vhide) tbody tr';
  document.addEventListener('keydown',e=>{const t=e.target;if(e.ctrlKey||e.metaKey||e.altKey)return;
    if(t&&t.closest&&t.closest('input,textarea,select,[contenteditable]'))return;
    if(e.key==='/'){e.preventDefault();const s=document.getElementById('uxSearch');if(s){s.focus();s.select();}return;}
    if(e.key==='j'||e.key==='k'){const dr=document.getElementById('piDrawer');const scope=dr&&dr.classList.contains('on')?'#piDrawer.on ':'';
      const L=[...document.querySelectorAll(LISTS)].filter(x=>(scope?x.closest('#piDrawer'):!x.closest('#piDrawer'))&&x.getBoundingClientRect().height>0);if(!L.length)return;
      const i=L.indexOf(document.activeElement);const n=L[Math.max(0,Math.min(L.length-1,i<0?0:i+(e.key==='j'?1:-1)))];
      document.querySelectorAll('.ux-kf').forEach(x=>x.classList.remove('ux-kf'));if(!n.hasAttribute('tabindex'))n.tabIndex=-1;n.classList.add('ux-kf');n.focus({preventScroll:true});n.scrollIntoView({block:'nearest'});e.preventDefault();}
    if(e.key==='Escape'){closeOverlays();}});
  // ---------------------------------------------------------------- print / share view (#decision) and showcase (#ux)
  function printView(){const v=verdict(),B=O.blockers||[];
    return `<div class="in"><div class="bar"><h1>${T('Release decision','Quyết định release')} · ${raw(O.line||'')}</h1><button type="button" class="ux-btn pri" onclick="print()">${T('Print','In')}</button><button type="button" class="ux-btn" data-ux-copylink="#decision">${T('Copy link','Copy link')}</button><a class="ux-btn" href="#obs/today">${T('Close','Đóng')}</a></div>`+
      banner().replace('data-ux="banner"','data-ux="print-banner"').replace('<details class="ux-det"','<details class="ux-det" open').replace(/ data-ux="(verdict|top-blocker|find-cause)"/g,'')+
      `<table class="ux-t2c"><thead><tr><th>${T('Blocker','Blocker')}</th><th>${T('Kind','Loại')}</th><th>${T('Data','Dữ liệu')}</th><th>${T('Evidence','Bằng chứng')}</th></tr></thead><tbody>${B.map(b=>`<tr><td data-l="${T('Blocker','Blocker')}" class="obsraw">${esc(b.title)}</td><td data-l="${T('Kind','Loại')}">${esc(T(...(KINDN[b.kind]||[b.kind,b.kind])))}</td><td data-l="${T('Data','Dữ liệu')}">${ageChip(b.src||'',srcAge(b.src))}</td><td data-l="${T('Evidence','Bằng chứng')}">${b.evidence?`<a class="ux-ev" href="${esc(b.evidence)}" target="_blank" rel="noopener">${T('open','mở')} ↗</a>`:'—'}</td></tr>`).join('')}</tbody></table>`+
      `<table class="ux-t2c"><thead><tr><th>${T('Open decision','Quyết định còn mở')}</th><th>${T('Question','Câu hỏi')}</th></tr></thead><tbody>${(O.decisions||[]).map(d=>`<tr><td data-l="ID">${esc(d.id)}</td><td data-l="${T('Question','Câu hỏi')}" class="obsraw">${esc(d.question||d.text||(d.cols||[])[0]||'')}</td></tr>`).join('')}</tbody></table>`+
      `<p class="pi-why">${T('Generated from local data at','Tạo từ dữ liệu local lúc')} ${esc(new Date().toISOString().slice(0,16).replace('T',' '))} UTC · ${T('every row shows its data age; older than 48 h = stale.','mỗi dòng ghi tuổi dữ liệu; cũ hơn 48 giờ = stale.')}</p></div>`;}
  function gallery(){const card=(lab,val,unit,dl,good,pts,def,p90)=>`<div class="ux-card"><span class="lab">${lab}</span><span class="val">${val}<small>${unit}</small></span><span class="dl ${good===null?'flat':good?'good':'bad'}">${dl}</span>`+
      `<svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts.map((y,i)=>`${i*100/(pts.length-1)},${28-y}`).join(' ')}"/></svg>${p90?`<span class="def">p90 ${p90}</span>`:''}<span class="def">${def}</span></div>`;
    return `<h4>${T('Tokens','Token')}</h4><div class="ux-swatch">${['surface-0','surface-1','surface-2','text-primary','text-secondary','ux-ok','ux-warn','ux-fail','ux-accent'].map(v=>`<span style="background:var(--${v})" title="--${v}"></span>`).join('')}</div>`+
      `<div class="ux-scale">${[4,8,12,16,24,32].map(s=>`<i style="height:${s}px" title="${s}px"></i>`).join('')} <span class="pi-why">4 · 8 · 12 · 16 · 24 · 32 px</span></div>`+
      `<div><span style="font-size:var(--ux-fs-xl);font-weight:700">24 Aa</span> <span style="font-size:var(--ux-fs-lg)">17 Aa</span> <span style="font-size:var(--ux-fs-md)">14 Aa</span> <span style="font-size:var(--ux-fs-sm)">12.5 Aa</span> <span style="font-size:var(--ux-fs-xs)">11.5 Aa</span></div>`+
      `<h4>${T('Status chip','Chip trạng thái')}</h4><div>${chip('ok',T('passed','pass'))} ${chip('warn',T('almost','gần xong'))} ${chip('fail',T('failed','fail'))} ${chip('stale',T('9 d old','cũ 9 ngày'))} ${chip('unk',T('unknown','chưa biết'))} ${chip('info','info')}</div>`+
      `<h4>${T('Metric card','Thẻ metric')}</h4><div class="ux-cards">${card(T('CPU job-min / day','CPU job-min / ngày'),'5,629','job-min',T('▼ 4% vs last week · lower is better','▼ 4% so với tuần trước · thấp hơn là tốt'),true,[10,14,12,18,15,13,11],T('GitHub Actions job start → end, PR runs, 24 h','Job GitHub Actions từ start → end, PR, 24 giờ'),'')}${card(T('GPU build p50','Build GPU p50'),'87','min',T('▲ 6% vs last week','▲ 6% so với tuần trước'),false,[8,9,10,12,11,14,16],T('passed k3-multiprocess-test builds, wall-clock','build k3-multiprocess-test pass, thời gian thực'),'288 min')}</div>`+
      `<h4>${T('Decision banner','Banner quyết định')}</h4><div class="ux-banner fail"><div class="hd">${chip('fail',T('Not ready','Chưa sẵn sàng'))}<h2>${T('Not ready for the next RC','Chưa sẵn sàng cho RC tiếp theo')}</h2></div><div class="row"><b>${T('Top blocker','Blocker đầu')}</b><span>${T('publish failed: Build MUSA wheel','publish lỗi: Build MUSA wheel')} ${chip('ok','ops.db · 8 h')}</span></div><div class="row"><b>${T('Next action','Việc tiếp theo')}</b><span><button type="button" class="ux-btn pri">${T('Copy: gh run rerun','Copy: gh run rerun')}</button></span></div></div>`+
      `<h4>${T('PR chip · gate chip · evidence link','Chip PR · chip gate · link bằng chứng')}</h4><div><a href="#" class="ux-pr"><b>#6572</b><span>${T('whole_chunk fetching policy','chính sách whole_chunk')}</span></a> <span class="ux-gate">${chip('ok','k3-unit-tests')}<span class="m">${T('required','bắt buộc')}</span></span> <span class="ux-gate">${chip('warn','k3-multiprocess-test')}<span class="m">${T('not run','chưa chạy')}</span></span> <a class="ux-ev" href="#">${T('evidence','bằng chứng')} ↗</a></div>`+
      `<h4>${T('Table to card (phone)','Bảng thành thẻ (điện thoại)')}</h4><table class="ux-t2c"><thead><tr><th>PR</th><th>${T('Gate','Gate')}</th><th>${T('State','Trạng thái')}</th></tr></thead><tbody><tr><td data-l="PR">#5673</td><td data-l="${T('Gate','Gate')}">k3-multiprocess-test</td><td data-l="${T('State','Trạng thái')}">${chip('warn',T('waiting for full','chờ full'))}</td></tr><tr><td data-l="PR">#6098</td><td data-l="${T('Gate','Gate')}">k3-unit-tests</td><td data-l="${T('State','Trạng thái')}">${chip('ok',T('passed','pass'))}</td></tr></tbody></table>`+
      `<h4>${T('Drawer','Drawer')}</h4><div style="border:1px solid var(--border);border-radius:var(--ux-r-md);box-shadow:var(--ux-e2);background:var(--surface-1);padding:10px"><b>#5673</b> ${T('PR Inspector · forward / backward · 5 views · Esc closes','PR Inspector · xuôi / ngược · 5 góc nhìn · Esc để đóng')}</div>`+
      `<h4>${T('States','Trạng thái hiển thị')}</h4><div class="ux-skel" style="width:70%"></div><div class="ux-skel" style="width:45%"></div><div class="ux-empty">${T('Empty: nothing to decide now.','Trống: hiện không có gì để quyết.')}</div><div class="ux-unk">${chip('unk',T('unknown','chưa biết'))} ${T('No evidence in local data: shown as unknown, never guessed.','Không có bằng chứng trong dữ liệu local: hiện là chưa biết, không đoán.')}</div><div class="ux-stalebox">${chip('stale',T('stale','cũ'))} ${T('Data 9 d old: no green verdict on old data.','Dữ liệu cũ 9 ngày: không hiện kết luận xanh trên dữ liệu cũ.')}</div><div class="ux-err"><b>${T('Error','Lỗi')}:</b> ${T('a part of the page failed to draw. The data is unchanged; reload the page.','một phần trang không vẽ được. Dữ liệu không đổi; hãy tải lại trang.')}</div>`;}
  function showcase(){return `<div class="in" id="uxShowIn"><div class="bar"><h1>${T('Design system','Design system')}</h1><a class="ux-btn" href="#obs/today">${T('Close','Đóng')}</a></div>`+
    `<p class="pi-why">${T('Tokens live on .viz-root; components use the ux- prefix. Each frame sets its own tokens; the phone frame is 390 px wide and uses container queries, so the components switch to their phone layout inside it.','Token nằm trên .viz-root; component dùng tiền tố ux-. Mỗi khung tự đặt token; khung điện thoại rộng 390 px và dùng container query, nên component chuyển sang bố cục điện thoại bên trong.')}</p>`+
    `<div class="ux-frames"><div class="ux-frame ux-th-light" data-frame="light"><h3>${T('Light','Sáng')}</h3>${gallery()}</div><div class="ux-frame ux-th-dark" data-frame="dark"><h3>${T('Dark','Tối')}</h3>${gallery()}</div><div class="ux-frame m ux-th-light" data-frame="mobile"><h3>${T('Phone · 390 px','Điện thoại · 390 px')}</h3>${gallery()}</div></div></div>`;}
  // expert review U4 / U5: one modal helper for the PR drawer and the overlays
  const MODAL={el:null,back:null,inerted:[]};
  function modalOn(el){if(MODAL.el===el)return;modalOff(false);MODAL.el=el;const a=document.activeElement;MODAL.back=a&&a!==document.body?a:MODAL.back;
    el.setAttribute('role','dialog');el.setAttribute('aria-modal','true');const h=el.querySelector('h1,h2,#piTitle');if(h){if(!h.id)h.id=el.id+'Title';el.setAttribute('aria-labelledby',h.id);}
    let n=el;while(n&&n!==document.body){const par=n.parentElement;if(!par)break;[...par.children].forEach(c=>{if(c!==n&&!c.inert&&c.tagName!=='SCRIPT'&&c.tagName!=='STYLE'&&!(window.WSTACK&&WSTACK.has(c))){c.inert=true;MODAL.inerted.push(c);}});n=par;}}
  function modalOff(ret=true){MODAL.inerted.forEach(c=>c.inert=false);MODAL.inerted=[];const back=MODAL.back;MODAL.el=null;
    if(ret&&back&&document.contains(back)&&back.focus){back.focus({preventScroll:true});}MODAL.back=null;}
  document.addEventListener('keydown',e=>{if(e.key!=='Tab'||!MODAL.el)return;const F=[...MODAL.el.querySelectorAll('a[href],button:not([disabled]),input,select,textarea,summary,[tabindex]:not([tabindex="-1"])')].filter(x=>x.getClientRects().length);
    if(!F.length)return;const i=F.indexOf(document.activeElement);if(e.shiftKey&&(i<=0)){e.preventDefault();F[F.length-1].focus();}else if(!e.shiftKey&&(i===F.length-1||i<0)){e.preventDefault();F[0].focus();}});
  addEventListener('piopen',()=>{const d=document.getElementById('piDrawer');if(d)setTimeout(()=>modalOn(d),0);});
  addEventListener('piclose',()=>{if(MODAL.el&&MODAL.el.id==='piDrawer')modalOff(true);});
  const WS=window.WSTACK||(window.WSTACK=(function(){const S=[];const z=()=>S.forEach((x,i)=>{x.el.style.zIndex=String(80+i);});const drop=el=>{const i=S.findIndex(x=>x.el===el);if(i>=0)S.splice(i,1);};const live=()=>{for(let i=S.length-1;i>=0;i--){if(S[i].el.isConnected&&S[i].on())return S[i];S.splice(i,1);}return null;};addEventListener('keydown',e=>{if(e.key!=='Escape'||e.defaultPrevented)return;const t=e.target;if(t&&t.closest&&t.closest('input,textarea,select'))return;const top=live();if(!top)return;e.preventDefault();e.stopImmediatePropagation();top.close();},true);return{push(el,close,on){drop(el);S.push({el,close,on:on||(()=>el.classList.contains('on'))});el.inert=false;z();},pop(el){drop(el);el.style.zIndex='';z();},top(){const t=live();return t&&t.el;},has(el){return S.some(x=>x.el===el);}};})());
  function overlay(id,html){let o=document.getElementById(id);if(!o){o=document.createElement('div');o.id=id;o.className='ux-ov';o.setAttribute('role','dialog');o.setAttribute('aria-modal','true');(document.getElementById('root')||document.body).appendChild(o);}
    const a=document.activeElement;o.innerHTML=html;o.hidden=false;WS.push(o,closeOverlays,()=>!o.hidden);modalOn(o);if(a&&a!==document.body)MODAL.back=a;const f=o.querySelector('a,button');if(f)f.focus({preventScroll:true});}
  function closeOverlays(){['uxPrint','uxShow','uxDocs'].forEach(id=>{const o=document.getElementById(id);if(o&&!o.hidden){o.hidden=true;WS.pop(o);if(MODAL.el===o)modalOff(true);if(/^#(decision|ux|docs)$/.test(location.hash))history.replaceState(null,'','#obs/today');}});}
  function route(){const h=location.hash;if(h==='#decision')overlay('uxPrint',printView());else if(h==='#ux')overlay('uxShow',showcase());else if(h==='#docs')overlay('uxDocs',docsList());else closeOverlays();}
  addEventListener('hashchange',route);
  const prAlias=()=>{const m=location.hash.match(/^#pr[:\/](\d+)$/);if(m)location.replace('#e/pr/'+m[1]);};prAlias();addEventListener('hashchange',prAlias);
  // ---------------------------------------------------------------- clicks
  document.addEventListener('click',e=>{if(e.target.closest&&e.target.closest('#uxDocs [data-pi]')){const o=document.getElementById('uxDocs');if(o)o.hidden=true;}
    const pv=e.target.closest&&e.target.closest('[data-ux-pv]');if(pv){const b=document.querySelector(`#piDrawer [data-pi-v="${pv.dataset.uxPv}"]`);if(b)b.click();return;}
    const c=e.target.closest&&e.target.closest('[data-ux-copy],[data-ux-copylink],[data-ux="copy-link"],[data-ux-jump],[data-ux-goto]');if(!c)return;
    if(c.dataset.uxCopy!=null){e.preventDefault();return copy(c.dataset.uxCopy,c);}
    if(c.dataset.uxCopylink!=null){e.preventDefault();return copy(linkTo(c.dataset.uxCopylink),c);}
    if(c.dataset.ux==='copy-link'){e.preventDefault();return copy(location.href,c);}
    if(c.dataset.uxJump){e.preventDefault();const t=document.getElementById(c.dataset.uxJump);if(t&&t.classList.contains('ux-folded'))setFold(t,true);if(t)t.scrollIntoView({block:'start'});return;}
    if(c.dataset.uxGoto){e.preventDefault();const [v,t]=c.dataset.uxGoto.split('/');vizNav.show(v,t);const s=c.dataset.uxScroll;if(s)setTimeout(()=>{const x=document.getElementById(s);if(x)x.scrollIntoView({block:'start'});},60);}});
  // ---------------------------------------------------------------- error state: a failed renderer says so instead of leaving a hole
  addEventListener('error',ev=>{let t=document.getElementById('uxErr');if(!t){t=document.createElement('div');t.id='uxErr';t.className='ux-toast';(document.getElementById('root')||document.body).appendChild(t);}
    t.innerHTML=`<div class="ux-err" role="alert"><b>${T('Error','Lỗi')}:</b> ${T('a part of the page failed to draw','một phần trang không vẽ được')} (<span class="obsraw">${esc(String(ev.message||'').slice(0,120))}</span>). ${T('The data is unchanged; reload the page.','Dữ liệu không đổi; hãy tải lại trang.')} <button type="button" class="ux-btn" onclick="this.closest('.ux-toast').remove()">${T('Dismiss','Ẩn')}</button></div>`;});
  // sections added here are not in the nav's list: show them with their tab (same rule as the nav: members of the merged tab)
  function syncVis(){const st=window.vizNav&&vizNav.state;if(!st)return;const all=document.body.dataset.all==='1';
    {const pl=document.getElementById('uxPill');if(pl)pl.hidden=st.v==='obs'&&st.t==='today';}
    document.querySelectorAll('.ux-sec').forEach(x=>{
      const on=all||(x.dataset.view===st.v&&(vizNav.members?vizNav.members(st.v,st.t):[st.t]).includes(x.dataset.tab));x.classList.toggle('vhide',!on);});}
  addEventListener('viewchange',syncVis);
  // contrast guard: text on a coloured fill gets black or white, whichever has the higher contrast on the real fill
  const cv=document.createElement('canvas');cv.width=cv.height=1;const cx=cv.getContext('2d',{willReadFrequently:true});
  const rgb=c=>{cx.clearRect(0,0,1,1);cx.fillStyle='#000';cx.fillStyle=c;cx.fillRect(0,0,1,1);const d=cx.getImageData(0,0,1,1).data;return [d[0],d[1],d[2],d[3]/255];};
  const lum=c=>{const f=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4);};return .2126*f(c[0])+.7152*f(c[1])+.0722*f(c[2]);};
  const AC='[style*="background:var(--series"],[style*="background: var(--series"],#ovl>div,#hm td[style],.div,.seg2,.tr-btn.pri,.step-num,.tierchip,.seg .ic,.n,.badge';
  function autoContrast(){document.querySelectorAll(AC).forEach(el=>{const b=rgb(getComputedStyle(el).backgroundColor);if(b[3]<.6)return;const L=lum(b);
    el.style.setProperty('color',(L+.05)/.05>=1.05/(L+.05)?'#111':'#fff','important');});}
  let acT=0;const acSoon=()=>{clearTimeout(acT);acT=setTimeout(autoContrast,60);};
  addEventListener('viewchange',acSoon);addEventListener('langchange',acSoon);addEventListener('piopen',acSoon);
  new MutationObserver(acSoon).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  // Report 1130: inputs the report expects but the local folder lacks -> counts that depend on them are unknown, not 0
  const R11_NEED=['raw/builds_30d.json','raw/builds_k3-unit-tests_30d.json','raw/gh_checks_30d.json','raw/gh_run_jobs_30d.jsonl','raw/fail_signatures.json'];
  function drawR11Gap(){const R=J('r11Data');const have=((R.quality||{}).inputs||[]).map(i=>String(i.path).replace(/^outputs\/[^/]+\//,''));const miss=R11_NEED.filter(x=>!have.includes(x));
    if(!miss.length)return;['baseline','prs','repro','quality'].forEach((t,ti)=>{const first=document.querySelector(`section[data-view="r1130"][data-tab="${t}"]`);if(!first)return;
      let s=document.getElementById('uxGap-'+t);if(!s){s=document.createElement('div');s.id='uxGap-'+t;s.style.marginBottom='10px';first.prepend(s);}   // inside the tab's own section: section lists stay as they are
      if(ti>0){s.innerHTML=`<div class="ux-stalebox" data-ux="data-gap">${chip('unk',T('data gap','thiếu dữ liệu'))} ${T(`${miss.length} input files are missing: build counts are unknown, not zero.`,`Thiếu ${miss.length} file đầu vào: số build là chưa biết, không phải 0.`)} <a href="#r1130/baseline" class="ux-ev">${T('details','chi tiết')}</a></div>`;return;}
      s.innerHTML=`<div class="ux-stalebox" data-ux="data-gap">${chip('unk',T('data gap','thiếu dữ liệu'))} ${T(`This report expects ${miss.length} input file(s) that are not in the local folder:`,`Báo cáo này cần ${miss.length} file đầu vào không có trong thư mục local:`)} ${miss.map(m=>`<code class="obsraw">${esc(m)}</code>`).join(' ')}. ${T('Counts that come from them (Buildkite builds, check runs, run jobs) are unknown, not zero. Copy the raw files from the build PC or re-run the ETL window export.','Các số lấy từ chúng (build Buildkite, check run, run job) là chưa biết, không phải 0. Chép file raw từ máy build hoặc chạy lại ETL window export.')}</div>`;});}
  // decision first on the analysis tabs: the question the tab answers, the answer in one line, what to do next, the data window
  addEventListener('r11range',()=>{try{tabQ();}catch(_){}});
  function tabQ(){const R=J('r11Data'),X_=window.R11X||null,G=X_?X_.gpu:(R.gpu||{}),C=X_?X_.cpu:(R.cpu||{}),W=(R.window||[]),win=W.length?`${W[0]} → ${W[1]}`:'?',rwin=X_?X_.W:win,rdays=X_?X_.days:R.days,PRS_=X_?X_.prs:(R.prs||[]);
    const req=(window.PI&&PI.data.req)||[];const fmtN=x=>x==null?'?':Number(x).toLocaleString('en-US');
    const TT=((R.ttg||{}).all)||{},OM=((R.ttg||{}).open_to_merge)||{},WK=(((R.merges||{}).weeks)||[]).filter(w=>!w.partial).slice(-1)[0]||{},RT=(X_?X_.retry:R.retry)||{};
    const TOPSIG=(((RT.sigs||[])[0]||{}).name?T(...RT.sigs[0].name):'?')+` (${fmtN(((RT.sigs||[])[0]||{}).n)})`;const TOPPR=PRS_.slice().sort((a,b)=>(b[9]||0)-(a[9]||0))[0]||[];
    const Q={
      'gates/guide':[['What must pass before a merge and before a release?','Cần pass gì trước khi merge và trước khi release?'],[`Merge needs ${req.length} required checks: ${req.join(', ')}.`,`Merge cần ${req.length} check bắt buộc: ${req.join(', ')}.`],['gates/tiers','Which tests a change must run →','Một thay đổi phải chạy test nào →'],'branch protection 2026-11-09'],
      'gates/tiers':[['Which tiers and tests must a given change run?','Một thay đổi phải chạy tier và test nào?'],['Pick the change class (row) to see the required tiers; the impact box lists the tests and workloads per code area.','Chọn nhóm thay đổi (hàng) để xem tier bắt buộc; ô impact liệt kê test và workload theo code area.'],['cpu/tiers','Find the tests of a file →','Tìm test của một file →'],'P8 rules, 100 PRs'],
      'cpu/overview':[['How big is the CPU unit suite, and which runner runs which test?','Bộ unit test CPU lớn cỡ nào, runner nào chạy test nào?'],['Most tests run on both runners; the GPU-only and GHA-only parts are the risk (see the bar).','Đa số test chạy trên cả hai runner; phần chỉ-GPU và chỉ-GHA là rủi ro (xem thanh).'],['cpu/tiers','Coverage per feature →','Độ phủ theo feature →'],'commit 05d8eb84'],
      'cpu/tiers':[['Which tests cover a feature or a file, and which never run on CPU?','Test nào phủ một feature hay một file, test nào không bao giờ chạy trên CPU?'],['Read the feature matrix row, or type a path in the test explorer (section 8).','Đọc hàng của feature matrix, hoặc gõ đường dẫn vào test explorer (mục 8).'],['cpu/cost','Where CPU time goes →','Thời gian CPU đi đâu →'],'commit 05d8eb84'],
      'cpu/cost':[['Where does CPU CI time go, and what can fail fast?','Thời gian CI CPU đi đâu, cái gì có thể fail sớm?'],['Same unit tests take ~24 min on the GPU pod after a 25 min queue; the findings list the cheapest early fails.','Cùng bộ unit test mất ~24 phút trên GPU pod sau 25 phút chờ; phần findings liệt kê cách fail sớm rẻ nhất.'],['obs/cost','CI cost of the last 24 h →','Chi phí CI 24 giờ qua →'],'P1 window'],
      'gpu/overview':[['Where does one PR build spend GPU time, and what is wrong per layer?','Một build PR tiêu thời gian GPU ở đâu, mỗi layer có vấn đề gì?'],[`Most of a PR build's GPU time is setup and engine start, not tests (section 2). The cards below use the first 30-day window (3,099 GPU-h, 2026-10-05 → 11-04); Report 1130 uses ${win} (${fmtN(G.gpu_h)} GPU-h).`,`Phần lớn thời gian GPU của một build PR là setup và khởi động engine, không phải test (mục 2). Các thẻ bên dưới dùng cửa sổ 30 ngày đầu (3,099 GPU-h, 2026-10-05 → 11-04); Report 1130 dùng ${win} (${fmtN(G.gpu_h)} GPU-h).`],['gpu/tiers','Cost per workload →','Chi phí theo workload →'],win],
      'gpu/tiers':[['Which MP workload costs most, and where should it run?','Workload MP nào tốn nhất, nên chạy ở đâu?'],['Read the GPU-min bars; "new home" says the cheaper place for each workload.','Đọc thanh GPU-min; "new home" nói nơi rẻ hơn cho từng workload.'],['gpu/explore','From a PR to the tests it runs →','Từ PR tới test nó chạy →'],'P1 cost_by_workload.csv'],
      'gpu/explore':[['From a change, which tier, test, check and function are involved?','Từ một thay đổi, tier, test, check và hàm nào liên quan?'],['Search a path or a class in the mindmap; a PR number is faster in the jump box (/).','Tìm đường dẫn hoặc lớp trong mindmap; với số PR thì dùng ô nhảy (/) nhanh hơn.'],['obs/overlap','Open PRs that must rebase →','PR mở phải rebase →'],'gates.py'],
      'r1130/baseline':[[`What does PR CI cost on GPU in the selected ${rdays} days?`,`CI của PR tốn bao nhiêu GPU trong ${rdays} ngày đã chọn?`],[`${fmtN(G.gpu_h)} GPU-h, ${fmtN(G.gpu_h_day)} GPU-h/day, ${fmtN(G.prs)} PRs.`,`${fmtN(G.gpu_h)} GPU-h, ${fmtN(G.gpu_h_day)} GPU-h/ngày, ${fmtN(G.prs)} PR.`],['r1130/track','Last 24 h vs this baseline →','24 giờ qua so với baseline →'],rwin],
      'r1130/cpu':[['What does PR CI cost on CPU (GitHub Actions) in the baseline?','CI của PR tốn bao nhiêu CPU (GitHub Actions) trong baseline?'],[`${fmtN(C.job_h)} job-h (${fmtN(C.job_h_day)} job-h/day): ${fmtN(C.jobs)} jobs in ${fmtN(C.runs)} runs for ${fmtN(C.prs)} PRs.`,`${fmtN(C.job_h)} job-h (${fmtN(C.job_h_day)} job-h/ngày): ${fmtN(C.jobs)} job trong ${fmtN(C.runs)} lần chạy cho ${fmtN(C.prs)} PR.`],['r1130/green','Time to green →','Thời gian tới xanh →'],rwin],
      'r1130/green':[['How long from push to green, and how many merges per week?','Từ push tới xanh mất bao lâu, mỗi tuần merge bao nhiêu?'],[`Time to green: median ${fmtN(TT.p50)} h, p90 ${fmtN(TT.p90)} h (${fmtN(TT.n)} merged PRs). Open to merge: median ${fmtN(OM.p50)} h, p90 ${fmtN(OM.p90)} h. Last full week: ${fmtN(WK.n)} merges.`,`Tới xanh: trung vị ${fmtN(TT.p50)} h, p90 ${fmtN(TT.p90)} h (${fmtN(TT.n)} PR đã merge). Mở tới merge: trung vị ${fmtN(OM.p50)} h, p90 ${fmtN(OM.p90)} h. Tuần đủ gần nhất: ${fmtN(WK.n)} merge.`],['r1130/retry','What was run again →','Cái gì phải chạy lại →'],win],
      'r1130/retry':[['What had to run again, and what never passes?','Cái gì phải chạy lại, cái gì không bao giờ pass?'],[`${fmtN(RT.n)} retries cost ${fmtN(RT.gpu_h)} GPU-h (${fmtN(RT.share_gpu)}% of GPU time) and ${fmtN(RT.cpu_h)} job-h; top cause: ${TOPSIG}.`,`${fmtN(RT.n)} lần chạy lại tốn ${fmtN(RT.gpu_h)} GPU-h (${fmtN(RT.share_gpu)}% thời gian GPU) và ${fmtN(RT.cpu_h)} job-h; nguyên nhân hàng đầu: ${TOPSIG}.`],['obs/today','Red dev gates → Find cause','Gate dev đỏ → Tìm nguyên nhân'],rwin],
      'r1130/prs':[['Which PRs and commits cost most CI?','PR và commit nào tốn CI nhất?'],[`${fmtN(PRS_.length)} PRs. Most GPU: #${TOPPR[0]||'?'} (${fmtN(Math.round(TOPPR[9]||0))} GPU-min ≈ ${fmtN(Math.round((TOPPR[9]||0)/60))} GPU-h). Click a PR number for its Inspector.`,`${fmtN(PRS_.length)} PR. Tốn GPU nhất: #${TOPPR[0]||'?'} (${fmtN(Math.round(TOPPR[9]||0))} GPU-min ≈ ${fmtN(Math.round((TOPPR[9]||0)/60))} GPU-h). Bấm số PR để mở Inspector.`],['obs/overlap','Open PRs that must rebase →','PR mở phải rebase →'],rwin],
      'r1130/track':[['Is the last 24 h better or worse than the baseline?','24 giờ qua tốt hơn hay tệ hơn baseline?'],['Each metric: baseline vs last 24 h, with the change; "no data yet" = the 24 h source is missing.','Mỗi metric: baseline so với 24 giờ qua, kèm thay đổi; "no data yet" = thiếu nguồn 24 giờ.'],['obs/cost','CI cost now →','Chi phí CI hiện tại →'],'ops_ci_24h.json'],
      'r1130/repro':[['How do I rebuild these numbers?','Làm sao dựng lại các số này?'],['Run the listed commands on the listed input files (sha shown).','Chạy các lệnh đã liệt kê trên các file đầu vào đã liệt kê (có sha).'],['r1130/quality','Data quality →','Chất lượng dữ liệu →'],win],
      'r1130/quality':[['How well do the sources join, and what is missing?','Các nguồn ghép với nhau tốt tới đâu, còn thiếu gì?'],['Join coverage per source and the entity link health.','Độ phủ ghép theo nguồn và sức khoẻ liên kết entity.'],['r1130/baseline','Back to the baseline →','Về baseline →'],win]};
    Object.entries(Q).forEach(([h,q])=>{const [v,t]=h.split('/');const first=document.querySelector(`section[data-view="${v}"][data-tab="${t}"]`);if(!first)return;
      let d=document.getElementById('uxQ-'+v+'-'+t);if(!d){d=document.createElement('div');d.id='uxQ-'+v+'-'+t;d.className='ux-q';const h2=first.querySelector('h2');(h2?h2.parentNode===first?h2:first.firstChild:first.firstChild).before(d);}
      d.innerHTML=`<div class="ux-banner" data-ux="tab-question"><div class="row"><b>${T('Question','Câu hỏi')}</b><span>${esc(T(q[0][0],q[0][1]))}</span></div><div class="row"><b>${T('Answer','Trả lời')}</b><span>${esc(T(q[1][0],q[1][1]))}</span></div>`+
        `<div class="row"><b>${T('Next','Tiếp theo')}</b><span><a href="#${q[2][0]}" class="ux-ev">${esc(T(q[2][1],q[2][2]))}</a> <span class="pi-why">${T('data','dữ liệu')}: <span class="obsraw">${esc(q[3])}</span></span>${q[3]==='ops_ci_24h.json'?' '+ageChip('ops_ci_24h.json',srcAge('ops_ci_24h')):''}</span></div></div>`;
      if(h==='gpu/overview'){const tl=document.querySelector('.tiles[data-view="gpu"]');if(tl&&d.parentNode!==tl.parentNode){d.classList.add('ux-sec');d.dataset.view='gpu';d.dataset.tab='overview';tl.before(d);}}});}
  function staleNotes(){const h=srcAge('observe_snapshot');const old=h>STALE_H;
    const bar=document.getElementById('obsBar');if(bar){bar.classList.toggle('ux-stalescope',old);let c=document.getElementById('uxBarStale');
      if(old){if(!c){c=document.createElement('span');c.id='uxBarStale';bar.prepend(c);}c.innerHTML=chip('stale',T(`snapshot ${ageTxt(h)} old: not current`,`snapshot cũ ${ageTxt(h)}: không hiện hành`))+' ';}else if(c)c.remove();}
    // one place per fact: the banner has the blocker total and the open decisions; the tiles that repeat them step back
    document.querySelectorAll('#dkWhere .dk-tile').forEach(t=>{const l=(t.textContent||'').toLowerCase();if(/^\s*(blocking|open decisions|đang chặn|quyết định còn mở|stable \(users have\)|stable \(người dùng|latest tag|bản stable|tag mới nhất)/.test(l))t.classList.add('ux-dup');});
    // research: the three contexts at a glance
    const rs=document.querySelector('section[data-research="ci"]');if(rs){let g=document.getElementById('uxRsSum');const RS=(((window.RESEARCH&&RESEARCH.data)||{}).reports)||[];
      if(!g){g=document.createElement('div');g.id='uxRsSum';g.style.margin='0 0 10px';rs.prepend(g);}
      const C=[['CI Validation','ci'],['LMCache optimization','opt'],['New product feature','feat']];
      g.innerHTML=`<div class="ux-banner" data-ux="research-contexts"><div class="row"><b>${T('Contexts','Context')}</b><span>${C.map(([c,k])=>{const r=RS.filter(x=>x.context===c);const real=r.filter(x=>!x.sample).length;
        const rr=r.find(x=>!x.sample);return `<a href="#" class="ux-ev" data-ux-jump="rs${k[0].toUpperCase()+k.slice(1)}">${esc(c)}</a> ${real?chip('info',real+T(' real',' thật'))+' '+esc(rr.verdict):chip('unk',T('no real report · sample only','chưa có report thật · chỉ có mẫu'))}`;}).join(' · ')}</span></div></div>`;}
    const rv=document.getElementById('relBody');if(rv){let n=document.getElementById('uxRelStale');
      if(old){if(!n){n=document.createElement('div');n.id='uxRelStale';n.className='ux-stalebox';n.style.marginBottom='8px';rv.before(n);}
        n.innerHTML=`${chip('stale',T(`PR snapshot ${ageTxt(h)} old`,`snapshot PR cũ ${ageTxt(h)}`))} ${T('Verdicts here use the PR snapshot; a release published after it shows "no publish data". The publish runs of ops.db (fresher) are on Now · Release Desk.','Kết luận ở đây dùng snapshot PR; release publish sau đó sẽ hiện "chưa có dữ liệu publish". Lần publish trong ops.db (mới hơn) ở Now · Release Desk.')} <a href="#obs/today" class="ux-ev">Now →</a>`;}else if(n)n.remove();}
    document.querySelectorAll('section[data-research]').forEach(sec=>{const cards=[...sec.querySelectorAll('.rs-card')];if(!cards.length)return;const real=cards.filter(c=>!c.querySelector('.rs-badge'));
      let n=sec.querySelector('.ux-samplenote');if(!real.length){if(!n){n=document.createElement('div');n.className='ux-stalebox ux-samplenote';n.style.margin='6px 0';cards[0].before(n);}
        n.innerHTML=`${chip('unk',T('no real report yet','chưa có report thật'))} ${T('The card below is a shipped SAMPLE: illustrative numbers, not measured. Real reports appear here when the Research App drops a file into research_intake/inbox/.','Thẻ bên dưới là MẪU đi kèm: số minh hoạ, không đo thật. Report thật xuất hiện ở đây khi Research App thả file vào research_intake/inbox/.')}`;}else if(n)n.remove();});}
  function r11Honesty(){const R=J('r11Data');const have=((R.quality||{}).inputs||[]).map(i=>String(i.path));const noBuilds=!have.some(p=>/raw\/builds_30d\.json$/.test(p));
    if(noBuilds)document.querySelectorAll('section[data-r11="baseline"] td').forEach(td=>{if(/^\s*0 \(/.test(td.textContent)&&!td.querySelector('.ux-chip')){td.insertAdjacentHTML('afterbegin',chip('unk',T('unknown','chưa biết'))+' ');td.title=T('raw/builds_30d.json is missing: this count is unknown, not zero','thiếu raw/builds_30d.json: số này là chưa biết, không phải 0');}});
    const tr=document.querySelector('section[data-r11="track"]');if(tr){let n=document.getElementById('uxTrackAge');const h=srcAge('ops_ci_24h');
      if(h>24){if(!n){n=document.createElement('div');n.id='uxTrackAge';n.className='ux-stalebox';n.style.margin='0 0 10px';const q=tr.querySelector('.ux-q');(q?q.nextSibling:tr.firstChild)?(q?q.after(n):tr.prepend(n)):tr.append(n);}
        n.innerHTML=`${chip('stale',T(`"Now" is ${ageTxt(h)} old`,`"Now" đã cũ ${ageTxt(h)}`))} ${T(`"Now" below is the 24 h file ops_ci_24h.json collected ${String((AGES.ops_ci_24h||{}).at||'?').slice(0,16).replace('T',' ')} UTC, not the last 24 h.`,`"Now" bên dưới là file 24 giờ ops_ci_24h.json thu lúc ${String((AGES.ops_ci_24h||{}).at||'?').slice(0,16).replace('T',' ')} UTC, không phải 24 giờ vừa qua.`)}`;}else if(n)n.remove();}}
  // ---------------------------------------------------------------- CI cost home (expert review C5 / C9 / U9): one place that
  // reconciles every cost figure of the page (window, unit, definition, where), with $ rates the reader sets and owners
  function costHome(){const fmtN=x=>x==null||isNaN(x)?'?':Number(x).toLocaleString('en-US');const R=J('r11Data'),G=R.gpu||{},C=R.cpu||{},RT=R.retry||{},P1=UXD.p1||{},OW=UXD.owners||{};
    const V=(((OPS.opt||{}).v3||{}).stage_costs)||{},cell=k=>(V.cells||{})[k]||{},at=(AGES.ops_ci_24h||{}).at;
    let rate={};try{rate=JSON.parse(localStorage.getItem('uxRates')||'{}');}catch(e){}
    // round 2 G3: CPU rate per runner class (Linux / macOS); the old single 'cpu' rate is read as the Linux rate
    const rL=rate.cpu_linux>0?rate.cpu_linux:(rate.cpu>0?rate.cpu:0),rM=rate.cpu_mac>0?rate.cpu_mac:rL,OS=C.os_h||{},osT=Object.values(OS).reduce((a,b)=>a+b,0);
    const cpuRate=()=>osT?((osT-(OS.macOS||0))*rL+(OS.macOS||0)*rM)/osT:rL;
    const usdV=(x,k)=>x==null?null:k==='gpu'?(rate.gpu>0?x*rate.gpu:null):(rL>0||rM>0?x*cpuRate():null);
    const usd=(x,k)=>{const v=usdV(x,k);return v!=null?' · ≈ $'+fmtN(Math.round(v)):'';};
    // round 2 G8: age of each window, from its (exclusive) end
    const d10=x=>String(x||'').slice(0,10),lastDay=u=>{const t=Date.parse(u);return isNaN(t)?d10(u):new Date(t-864e5).toISOString().slice(0,10);};
    const ageD=end=>{const t=Date.parse(end);return isNaN(t)?null:Math.max(0,Math.floor((Date.now()-t)/864e5));};
    const ageS=d=>d==null?'':T(` · ${d} d old`,` · cũ ${d} ngày`);
    const rEnd=R.until||(R.window?R.window[1]+'T23:59:59Z':null),pEnd=P1.until||null,sEnd=at||null;
    const win=(R.window?`${R.window[0]} → ${R.window[1]}`:'?')+ageS(ageD(rEnd)),p1w=(P1.since?`${d10(P1.since)} → ${lastDay(P1.until)}`:'?')+ageS(ageD(pEnd));
    const d24=(at?T(`24 h to ${String(at).slice(0,16).replace('T',' ')} UTC (one sample)`,`24 giờ tới ${String(at).slice(0,16).replace('T',' ')} UTC (một mẫu)`):T('24 h','24 giờ'))+ageS(ageD(sEnd));
    const IV={r:[R.since||(R.window||[])[0],rEnd],p:[P1.since,pEnd],s:[at?new Date(Date.parse(at)-864e5).toISOString():null,sEnd]};
    // [metric, window, value, rate/share, definition, link, window key, $ value]
    const rows=[
      [T('PR GPU time, MP + unit pipelines','Thời gian GPU của PR, pipeline MP + unit'),win,fmtN(G.gpu_h)+' GPU-h',`${fmtN(G.gpu_h_day)} GPU-h/${T('day','ngày')}`+usd(G.gpu_h,'gpu'),T('Buildkite jobs of PR builds, GPU-min = run min × GPUs','job Buildkite của build PR, GPU-phút = phút chạy × số GPU'),'r1130/baseline','r',usdV(G.gpu_h,'gpu')],
      [T('PR GPU time, MP pipeline only','Thời gian GPU của PR, chỉ pipeline MP'),p1w,fmtN(P1.gpu_h)+' GPU-h',`${fmtN(P1.builds)} ${T('builds','build')} · ${fmtN(P1.prs)} PR`+usd(P1.gpu_h,'gpu'),T('first 30-day window (outputs/P1): the GPU tab cards','khung 30 ngày đầu (outputs/P1): các thẻ ở tab GPU'),'gpu/overview','p',usdV(P1.gpu_h,'gpu')],
      [T('CPU time, GitHub Actions','Thời gian CPU, GitHub Actions'),win,fmtN(C.job_h)+' job-h',`${fmtN(C.job_h_day)} job-h/${T('day','ngày')} = ${fmtN(Math.round((C.job_h_day||0)*60))} job-min/${T('day','ngày')}`+(osT?` · macOS ${fmtN(OS.macOS||0)} job-h`:'')+usd(C.job_h,'cpu'),T('jobs of PR commits','job của commit PR'),'r1130/cpu','r',usdV(C.job_h,'cpu')],
      [T('CPU time, PR stage','Thời gian CPU, giai đoạn PR'),d24,fmtN(cell('created|CPU').total)+' job-min',T('not comparable with a 30-day mean (one day, weekday matters)','không so được với trung bình 30 ngày (một ngày, phụ thuộc thứ)'),T('GitHub Actions runs with a pull_request event','run GitHub Actions có event pull_request'),'obs/cost','s',null],
      [T('GPU time, PR + approve stages','Thời gian GPU, giai đoạn PR + approve'),d24,fmtN((cell('created|GPU').total||0)+(cell('approve|GPU').total||0))+' job-min',T('job-min, GPUs per job not applied','job-phút, chưa nhân số GPU mỗi job'),T('Buildkite jobs','job Buildkite'),'obs/cost/gpu','s',null],
      [T('GPU lost to failed first tries','GPU mất vì lần đầu fail'),win,fmtN(RT.gpu_h)+' GPU-h',`${RT.share_gpu}% ${T('of PR GPU','GPU của PR')} · ${T(`the same ${fmtN(RT.queue_jobs)} tries queued`,`cùng ${fmtN(RT.queue_jobs)} lần thử đó chờ`)} ${fmtN(RT.gpu_h_queue_add)} h ${T('wall clock','giờ thực')}`+usd(RT.gpu_h,'gpu'),T('run time of the first try that failed and that Buildkite retried','thời gian chạy của lần thử đầu bị fail mà Buildkite chạy lại'),'r1130/retry','r',usdV(RT.gpu_h,'gpu')],
      [T('GPU retries in the first window','GPU chạy lại ở khung đầu'),p1w,fmtN(P1.retry_gpu_min)+' GPU-min',`${P1.gpu_h?(P1.retry_gpu_min/60/P1.gpu_h*100).toFixed(1):'?'}% ${T('of MP PR GPU','GPU PR của MP')}`,T('all retried attempts, MP only','mọi lần chạy lại, chỉ MP'),'gpu/overview','p',null],
      [T('CPU re-runs','CPU chạy lại'),win,fmtN(C.rerun_h)+' job-h',`${C.rerun_share}% · ${T('of which failed first tries','trong đó lần đầu fail')} ${fmtN(RT.cpu_h)} job-h`,T('every re-run job (manual + automatic)','mọi job chạy lại (tay + tự động)'),'r1130/cpu','r',null],
      [T('Cancelled GPU','GPU bị huỷ'),win,fmtN(G.cancel_gpu_h)+' GPU-h',usd(G.cancel_gpu_h,'gpu').replace(' · ',''),T('run time of cancelled jobs (new push, fast-fail)','thời gian chạy của job bị huỷ (push mới, fast-fail)'),'r1130/baseline','r',usdV(G.cancel_gpu_h,'gpu')]];
    // round 3 (B_content #54): owners as a count; the names per pipeline are the tooltip
    const ownL=Object.entries(OW).filter(([k,v])=>v&&v.length),ownU=[...new Set(ownL.flatMap(([k,v])=>v))],ownSame=ownL.length>1&&ownL.every(([k,v])=>v.join(' ')===ownL[0][1].join(' '));
    const own=ownL.length?`<span title="${esc(ownL.map(([k,v])=>k+': '+v.join(' ')).join(' · '))}">${ownSame?T(`${ownU.length} CODEOWNERS, same for all CI`,`${ownU.length} CODEOWNERS, chung cho mọi CI`):T(`${ownU.length} CODEOWNERS across ${ownL.length} pipelines`,`${ownU.length} CODEOWNERS trên ${ownL.length} pipeline`)} ▸</span>`:'';
    // G8: one "data as of" line for the whole table
    const stamp=(lab,end,txt)=>{const d=ageD(end);return chip(d==null?'unk':d>2?'stale':'na',`${esc(lab)} ${esc(txt)}${d==null?'':esc(ageS(d))}`);};
    const asof=`<p class="sub" data-ux="cost-asof">${T('Data as of','Dữ liệu tính tới')}: ${stamp(T('30-day baseline (Buildkite + GitHub) to','baseline 30 ngày (Buildkite + GitHub) tới'),rEnd,(R.window||['','?'])[1])} ${stamp(T('first window (P1) to','khung đầu (P1) tới'),pEnd,lastDay(P1.until))} ${stamp(T('24 h sample to','mẫu 24 giờ tới'),sEnd,String(at||'?').slice(0,16).replace('T',' ')+' UTC')}</p>`;
    // G3: monthly run-rate from the main window only (never adds rows of other windows or rows that are parts of a total)
    const days=R.days||30,gM=usdV(G.gpu_h,'gpu'),cM=usdV(C.job_h,'cpu'),mon=x=>x==null?null:x/days*30;
    const monthly=(gM!=null||cM!=null)?`<p class="sub" data-ux="cost-month"><b>${T('Monthly run-rate','Chi phí mỗi tháng')}: ≈ $${fmtN(Math.round((mon(gM)||0)+(mon(cM)||0)))}</b> = GPU ${gM!=null?'$'+fmtN(Math.round(mon(gM))):T('(no rate)','(chưa có đơn giá)')} + CPU ${cM!=null?'$'+fmtN(Math.round(mon(cM))):T('(no rate)','(chưa có đơn giá)')} · ${T(`30 × the daily mean of ${win}; GPU = row "MP + unit", CPU = row "GitHub Actions" (Linux ${fmtN(Math.round(osT-(OS.macOS||0)))} job-h at $${rL||0}, macOS ${fmtN(OS.macOS||0)} job-h at $${rM||0}). Other rows are parts of these or another window, so they are not added.`,`30 × trung bình mỗi ngày của ${win}; GPU = dòng "MP + unit", CPU = dòng "GitHub Actions" (Linux ${fmtN(Math.round(osT-(OS.macOS||0)))} giờ job giá $${rL||0}, macOS ${fmtN(OS.macOS||0)} giờ job giá $${rM||0}). Các dòng khác là một phần của các dòng này hoặc thuộc khung khác, nên không cộng.`)}</p>`:'';
    // G3: warn when two rows with a $ figure have overlapping windows (adding them double-counts)
    const ov=[];rows.forEach((a,i)=>rows.forEach((b,j)=>{if(j<=i||a[7]==null||b[7]==null||a[2].includes('GPU')!==b[2].includes('GPU'))return;const A_=IV[a[6]],B_=IV[b[6]];if(!A_[0]||!B_[0])return;
      if(Date.parse(A_[0])<Date.parse(B_[1])&&Date.parse(B_[0])<Date.parse(A_[1]))[a[0],b[0]].forEach(n=>{if(!ov.includes(n))ov.push(n);});}));
    const warn=ov.length?`<p class="sub ux-stalebox" data-ux="cost-overlap">${chip('stale',T('do not add','không cộng'))} ${T(`These rows with a $ figure overlap in time or are parts of one another, so a sum double-counts: `,`Các dòng có số $ này chồng nhau về thời gian hoặc là một phần của nhau, nên cộng lại sẽ tính trùng: `)}<span>${esc(ov.join(' · '))}</span></p>`:'';
    return `<h2>${T('CI cost at a glance','Chi phí CI tổng quan')}</h2><p class="sub">${T('All CI cost figures. Different windows are not comparable.','Mọi số chi phí CI. Khác khung thời gian thì không so được.')}</p>`+asof+
      `<div class="ux-t2c-wrap"><table class="ux-t2c" data-ux="cost-home"><thead><tr><th>${T('Metric','Chỉ số')}</th><th>${T('Window','Khung')}</th><th>${T('Value','Giá trị')}</th><th>${T('Rate / share / $','Tốc độ / tỷ lệ / $')}</th><th>${T('Definition','Định nghĩa')}</th><th></th></tr></thead><tbody>`+
      rows.map(r=>`<tr><td data-l="${T('Metric','Chỉ số')}">${esc(r[0])}</td><td data-l="${T('Window','Khung')}">${esc(r[1])}</td><td data-l="${T('Value','Giá trị')}"><b>${esc(r[2])}</b></td><td data-l="${T('Rate','Tốc độ')}">${esc(r[3])}</td><td data-l="${T('Definition','Định nghĩa')}">${esc(r[4])}</td><td><a href="#${r[5]}" class="ux-ev">${T('details','chi tiết')} →</a></td></tr>`).join('')+`</tbody></table></div>`+
      monthly+warn+
      `<p class="sub" data-ux="cost-rates">${T('$ estimate: set your rates (kept in this browser only)','Ước tính $: nhập đơn giá (chỉ lưu trong trình duyệt này)')} · <label>$/GPU-h <input type="number" min="0" step="0.01" data-ux-rate="gpu" value="${rate.gpu||''}" style="width:80px"></label> · <label>${T('$/CPU job-h, Linux','$/giờ job CPU, Linux')} <input type="number" min="0" step="0.001" data-ux-rate="cpu_linux" value="${rate.cpu_linux||rate.cpu||''}" style="width:80px"></label> · <label>${T('$/CPU job-h, macOS','$/giờ job CPU, macOS')} <input type="number" min="0" step="0.001" data-ux-rate="cpu_mac" value="${rate.cpu_mac||''}" placeholder="${T('= Linux','= Linux')}" style="width:80px"></label></p>`+
      `<p class="sub">${T('Owners','Phụ trách')}: ${own||T('no CODEOWNERS rule for the pipeline files','không có luật CODEOWNERS cho file pipeline')}</p>`;}
  function drawCostHome(){const mem=(window.vizNav&&vizNav.members)?vizNav.members('obs','cost'):['cost'];
    const first=[...document.querySelectorAll('section[data-view="obs"]')].find(x=>mem.includes(x.dataset.tab)&&x.id!=='uxCost');if(!first)return;let s=document.getElementById('uxCost');
    if(!s){s=document.createElement('section');s.id='uxCost';s.className='card ux-sec';s.dataset.view='obs';s.dataset.tab=first.dataset.tab;first.before(s);
      s.addEventListener('change',e=>{const k=e.target.dataset&&e.target.dataset.uxRate;if(!k)return;let r={};try{r=JSON.parse(localStorage.getItem('uxRates')||'{}');}catch(x){}r[k]=parseFloat(e.target.value)||0;try{localStorage.setItem('uxRates',JSON.stringify(r));}catch(x){}s.innerHTML=costHome();});}
    s.innerHTML=costHome();
    const homes=['cpu/cost','gpu/tiers'].flatMap(vt=>{const [v,t]=vt.split('/');const m=(window.vizNav&&vizNav.members)?vizNav.members(v,t):[t];return m.map(x=>`section[data-view="${v}"][data-tab="${x}"]`);});
    [...new Set(homes.map(sel=>document.querySelector(sel)).filter(Boolean)),...document.querySelectorAll('section[data-r11="baseline"],section[data-r11="retry"]')].forEach(x=>{
      if(x.querySelector('.ux-costhome'))return;const h=x.querySelector('h2');if(!h)return;h.insertAdjacentHTML('afterend',`<p class="sub ux-costhome">${T('All CI cost figures, reconciled across windows:','Mọi con số chi phí CI, đối chiếu giữa các khung:')} <a href="#obs/cost" class="ux-ev">${T('CI cost at a glance','Chi phí CI tổng quan')} →</a></p>`);});}
  // ---------------------------------------------------------------- section numbers follow the merged tabs (review U8):
  // in Release Management, tab N (TABS number) holds sections NA, NB, ... in page order; the old numbers came from the old tabs
  const TABNUM={today:0,hist:1,release:2,coming:3,cost:4,overlap:5,research:6,weekly:7,impact:8};
  function renumber(){if(!window.vizNav||!vizNav.members)return;
    Object.entries(TABNUM).forEach(([t,N])=>{const mem=new Set(vizNav.members('obs',t)||[t]);let i=0;
      document.querySelectorAll('section[data-view="obs"] h2').forEach(h=>{const sx=h.closest('section[data-view]');if(!sx||!mem.has(sx.dataset.tab))return;
        const tw=document.createTreeWalker(h,NodeFilter.SHOW_TEXT);let tn=null;while(tw.nextNode()){if(tw.currentNode.textContent.trim()){tn=tw.currentNode;break;}}if(!tn)return;const m=tn.textContent.match(/^(\s*)\d+[A-Z]?(\s·\s)/);if(!m)return;
        tn.textContent=m[1]+N+String.fromCharCode(65+i)+m[2]+tn.textContent.slice(m[0].length);i++;});});}
  addEventListener('viewchange',()=>setTimeout(renumber,0));
  // round 2 D4: sections that describe the PROPOSED tier policy say so next to their title (today: 4 required checks)
  function proposedTags(){document.querySelectorAll('section[data-view="gates"] h2').forEach(h=>{const tx=h.textContent;
      if(!/Change class|Change impact|Loại thay đổi|Tác động thay đổi/.test(tx))return;let b=h.querySelector('.ux-prop');
      if(!b){b=document.createElement('span');b.className='ux-chip warn ux-prop';b.style.marginLeft='8px';h.append(b);}
      b.textContent=T('proposed policy · today: the 4 required checks','chính sách đề xuất · hiện tại: 4 check bắt buộc');});}
  // round 2 A5 / D3: release sections built from the PR / CI snapshot say so when it is old (newer releases are missing there)
  function snapScope(){const h=srcAge('observe_snapshot'),old=h>STALE_H,at=String((AGES.observe_snapshot||{}).at||'?').slice(0,16).replace('T',' ');
    const tr=document.getElementById('obsTrain');[tr&&tr.closest('section'),document.querySelector('section[data-ops="ta-release"]')].forEach(sx=>{if(!sx)return;
      sx.classList.toggle('ux-stalescope',old);let n=sx.querySelector(':scope > .ux-snapbox');
      if(!old){if(n)n.remove();return;}
      if(!n){n=document.createElement('div');n.className='ux-stalebox ux-snapbox';n.style.margin='0 0 10px';const hd=sx.querySelector('.head');hd?hd.after(n):sx.prepend(n);}
      n.innerHTML=`${chip('stale',T(`snapshot ${ageTxt(h)} old`,`snapshot đã ${ageTxt(h)}`))} ${T(`Built from the PR / CI snapshot of ${at} UTC: releases tagged after it are missing here. The verdict banner, 2A and the release table use the current release data.`,`Dựng từ snapshot PR / CI lúc ${at} UTC: các release tag sau thời điểm đó không có ở đây. Banner verdict, 2A và bảng release dùng dữ liệu release hiện tại.`)}`;});}
  function ruleDesc(){document.querySelectorAll('[data-rule]:not([aria-description])').forEach(c=>{const r=c.getAttribute('data-rule');if(r)c.setAttribute('aria-description',r);});}
  function drawAll(){proposedTags();ruleDesc();snapScope();drawPill();drawCostHome();setTimeout(renumber,0);setTimeout(renumber,800);landmarks();staleNotes();r11Honesty();drawR11Gap();tabQ();drawBanner();staleGuard();foldToday();drawAge();drawSince();drawRebase();keepFirst();watchRebase();syncVis();acSoon();}
  window.UX={autoContrast,verdict,search,index:()=>index(),drawAll,closeAll:()=>{closeOverlays();closeRes();},mergeVerdict};
  // round 3 (D_identity 4): the browser tab says which tab is open
  function uxTitle(){const b=document.querySelector('#vPills button[aria-selected="true"]');const n=b?[...b.childNodes].filter(x=>x.nodeType===3).map(x=>x.textContent).join('').trim():'';document.title=(n?n+' · ':'')+'Release Desk';}
  addEventListener('viewchange',()=>setTimeout(uxTitle,80));addEventListener('langchange',()=>setTimeout(uxTitle,80));
  function landmarks(){const root=document.getElementById('root');if(root&&!document.querySelector('main,[role="main"]')){const sec=root.querySelector('section[data-view]');const host=sec&&sec.parentElement;
      if(host&&host!==document.body){host.setAttribute('role','main');host.id=host.id||'content';}}
    const m=document.querySelector('[role="main"],main');if(m&&!document.getElementById('uxSkip')){const a=document.createElement('a');a.id='uxSkip';a.className='ux-skip';a.href='#';a.textContent=T('Skip to content','Bỏ qua tới nội dung');
      a.addEventListener('click',e=>{e.preventDefault();const s=m.querySelector('section[data-view]:not(.vhide) h2')||m;s.tabIndex=-1;s.focus();});document.body.prepend(a);}
    const tb=document.getElementById('themeBtn');if(tb){const sync=()=>{tb.setAttribute('aria-pressed',String((document.documentElement.dataset.theme||'')==='dark'));tb.textContent='◐';tb.title=T('Dark theme','Giao diện tối');tb.setAttribute('aria-label',T('Dark theme','Giao diện tối'));};sync();if(!tb.dataset.uxp){tb.dataset.uxp=1;tb.addEventListener('click',()=>setTimeout(sync,0));}}
    document.documentElement.lang=(window.I18N&&I18N.lang==='vi')?'vi':'en';
    // review VI: the hidden texts a screen reader reads follow the language too
    uxTitle();   // round 3 (D_identity 4): "{Tab} · Release Desk"
    const h1=document.querySelector('header h1');if(h1)h1.title=T('Release decisions, CI health and test gates for LMCache','Quyết định release, sức khỏe CI và cổng test của LMCache');
    const seg=document.querySelector('.vnav .seg');if(seg){seg.setAttribute('aria-label',T('View','Góc nhìn'));seg.title=T('Keys: O = management · T / U / E = exploration · ← → = tab · L = EN / VI','Phím: O = quản lý · T / U / E = khám phá · ← → = tab · L = EN / VI');}
    const pl=document.getElementById('vPills');if(pl)pl.setAttribute('aria-label',T('Sections','Mục'));
    document.querySelectorAll('[aria-label="Page views"],[data-ux-al="views"]').forEach(x=>{x.dataset.uxAl='views';x.setAttribute('aria-label',T('Page views','Các góc nhìn của trang'));});}
  const start=()=>{load();mountSearch();mountKeys();landmarks();drawAll();route();addEventListener('langchange',()=>{drawAll();const s=document.getElementById('uxSearch');if(s){s.placeholder=T('Search PR #, tag, check…','Tìm PR #, tag, check…');}route();});
    // dkGates is redrawn by its own script: keep the stale guard on it
    const g=document.getElementById('dkGates');if(g)new MutationObserver(()=>{if(!g.querySelector('.ux-stalebox'))staleGuard();}).observe(g,{childList:true,subtree:false});
    const w=document.getElementById('dkWhereB');if(w)new MutationObserver(()=>{if(w.querySelector('.dk-tile:not(.ux-dup)'))staleNotes();}).observe(w,{childList:true});setTimeout(staleNotes,300);};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
</script>
<!-- UX:JS:END -->
"""
