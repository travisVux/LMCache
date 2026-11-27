/* LMCache Release Desk — frontend. Reads the local API, or api/*.json in a static export. */
(() => {
  "use strict";
  const STATIC = !!window.OPS_STATIC;
  const store = { get(k, d) { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } },
                  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } } };
  let LANG = store.get("opsLang", "vi");
  const T = (en, vi) => (LANG === "vi" ? vi : en);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // Text from RELEASE_PREP.md: escape first, then allow `code` and **bold** only.
  const md = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  const day = (s) => (s ? String(s).slice(0, 10) : "—");
  const ago = (s) => {
    if (!s) return "";
    const h = (Date.now() - Date.parse(s)) / 36e5;
    if (h < 1) return T("just now", "vừa xong");
    if (h < 48) return T(`${Math.round(h)} h ago`, `${Math.round(h)} giờ trước`);
    return T(`${Math.round(h / 24)} days ago`, `${Math.round(h / 24)} ngày trước`);
  };
  const link = (url, text) => (url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${text}</a>` : text);
  const api = async (name) => {
    const url = STATIC ? `api/${name}.json` : `/api/${name}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
  };
  const cache = {};
  const get = async (name) => (cache[name] ??= api(name));

  // ───────── words ─────────
  const VERDICT = {
    shipped: ["green", "Shipped", "Đủ artifact"],
    partial: ["amber", "Missing artifacts", "Thiếu artifact"],
    publish_failed: ["red", "Not shipped", "Chưa phát hành"],
    in_progress: ["blue", "Publishing", "Đang publish"],
    no_data: ["gray", "Not checked", "Chưa kiểm tra"],
  };
  const KIND = {
    publish: ["red", "Publish failed", "Publish lỗi", "A job in publish.yml failed on the latest tag; jobs after it were skipped.", "Một job của publish.yml fail trên tag mới nhất; các job sau nó bị bỏ qua."],
    artifact: ["red", "Missing artifact", "Thiếu artifact", "Checked in PyPI, GitHub Releases and Docker Hub — not only the run result.", "Kiểm tra trực tiếp PyPI, GitHub Releases, Docker Hub — không chỉ dựa vào kết quả run."],
    ci: ["red", "dev is red", "dev đang đỏ", "Latest finished dev build of a gate pipeline failed.", "Build dev gần nhất của pipeline gate bị fail."],
    pr: ["amber", "Bug not fixed", "Bug chưa sửa", "Found by the Trace Agent in a released tag.", "Trace Agent tìm thấy trong một tag đã phát hành."],
    carryover: ["gray", "Carried over", "Mang từ bản trước", "From release-<line>/RELEASE_PREP.md. Status comes from the doc; facts are added when we can check them.", "Từ release-<line>/RELEASE_PREP.md. Trạng thái theo tài liệu; có thêm dữ kiện khi kiểm tra được."],
  };
  // data age per source (header badges) and the STALE chip shown on the rows that use a stale source
  let AGES = {};
  const fmtAge = (h) => (h == null ? "?" : h < 1 ? "<1 h" : h < 48 ? Math.round(h) + " h" : Math.round(h / 24) + " d");
  const staleChip = (key) => { const a = AGES[key]; return a && a.stale ? `<span class="stale-chip" title="${esc(a.label)} · ${esc(a.at || "")}">STALE (${Math.round(a.age_h / 24)}d)</span>` : ""; };
  function renderAges(list) {
    AGES = Object.fromEntries((list || []).map((a) => [a.key, a]));
    document.getElementById("ages").innerHTML = `<span class="age"><b>${T("Data age", "Tuổi dữ liệu")}</b></span>` + (list || []).map((a) =>
      `<span class="age${a.stale ? " stale" : ""}" title="${esc(a.at || T("unknown", "không rõ"))}">${esc(a.label)} · <b>${fmtAge(a.age_h)}</b>${a.stale ? " · STALE" : ""}</span>`).join("");
  }
  const copyBtn = (cmd, tag) => cmd ? `<button type="button" class="copy" data-cmd="${esc(cmd)}" title="${esc(cmd)}">${T("copy cmd", "copy lệnh")}${tag ? " · " + esc(tag) : ""}</button>` : "";
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("button.copy[data-cmd]");
    if (!b) return;
    const c = b.dataset.cmd, was = b.textContent, done = () => { b.textContent = T("copied", "đã copy"); setTimeout(() => (b.textContent = was), 1500); };
    if (navigator.clipboard) navigator.clipboard.writeText(c).then(done, () => prompt("", c)); else prompt("", c);
  });
  const ownerTxt = (o) => (o && o.who ? `<span class="owner"><b>${esc(o.who)}</b>${o.how === "author" ? " (" + T("author", "tác giả") + ")" : ""}</span>` : "");
  const chip = (cls, text) => `<span class="chip ${cls}">${esc(text)}</span>`;
  const vchip = (v) => { const x = VERDICT[v] || VERDICT.no_data; return chip(x[0], T(x[1], x[2])); };
  const concl = (c, s) => {
    if (s && s !== "completed") return chip("blue", s);
    return { success: chip("green", "success"), failure: chip("red", "failure"), cancelled: chip("gray", "cancelled") }[c] || chip("gray", c || "—");
  };

  // ───────── NOW ─────────
  function hero(o) {
    const nb = o.blockers.length;
    const st = { red: T("Not ready for next RC", "Chưa sẵn sàng cho RC tiếp"), amber: T("Ready with open items", "Sẵn sàng, còn việc mở"), green: T("Ready", "Sẵn sàng") }[o.status];
    const byKind = {};
    o.blockers.forEach((b) => (byKind[b.kind] = (byKind[b.kind] || 0) + 1));
    const kinds = Object.entries(byKind).map(([k, n]) => `${n} ${T(KIND[k][1], KIND[k][2]).toLowerCase()}`).join(" · ");
    return `<section class="card">
      <h2>${T("Where we are", "Đang ở đâu")} <span class="status ${o.status}">● ${esc(st)}</span></h2>
      <p class="why">${esc(T(o.phase.en, o.phase.vi))}</p>
      <div class="hero">
        <div class="tile"><div class="k">${T("Stable (users get this)", "Stable (người dùng đang dùng)")}</div>
          <div class="v">${link(o.stable?.url, esc(o.stable?.tag || "—"))}</div><div class="d">${day(o.stable?.at)} · ${ago(o.stable?.at)}</div></div>
        <div class="tile rb"><div class="k">${T("Rollback target ($GOOD)", "Bản rollback ($GOOD)")}</div>
          <div class="v">${link(o.good?.url, esc(o.good?.tag || "—"))}</div>
          <div class="d" title="${esc(T("Rule: newest final/post tag whose core artifacts are present and correct: ", "Luật: tag final/post mới nhất có đủ artifact lõi: ") + (o.good?.core || []).join(", "))}">${T("newest final/post with core artifacts OK ⓘ", "final/post mới nhất có đủ artifact lõi ⓘ")}${o.good && o.good.gaps.length ? "<br>" + T("not core, missing: ", "ngoài lõi, thiếu: ") + esc(o.good.gaps.join(", ")) : ""}</div></div>
        <div class="tile"><div class="k">${T("Latest tag", "Tag mới nhất")}</div>
          <div class="v">${link(o.latest?.url, esc(o.latest?.tag || "—"))}</div><div class="d">${day(o.latest?.at)} · ${ago(o.latest?.at)}</div></div>
        <div class="tile"><div class="k">${T("Open decisions", "Quyết định còn mở")}</div>
          <div class="v">${o.decisions.filter((d) => d.status === "open").length} / ${o.decisions.length}</div>
          <div class="d">${o.decisions.filter((d) => d.status === "open" && d.hint).length} ${T("look decided in practice", "có vẻ đã quyết trên thực tế")}</div></div>
        <div class="tile"><div class="k">${T("Blockers", "Đang chặn")}</div><div class="v">${nb}</div><div class="d">${esc(kinds)}</div></div>
      </div></section>`;
  }

  function decisions(o) {
    if (!o.decisions.length) return "";
    const rows = o.decisions.map((d) => `<tr>
      <td><b>${esc(d.code)}</b></td>
      <td>${md(d.question)}${staleChip("release_prep")}${d.options ? `<div class="muted" style="font-size:12.5px">${md(d.options)}</div>` : ""}
        ${d.hint ? `<span class="hint">⚑ ${T("Evidence", "Bằng chứng")}: ${esc(T(d.hint.en, d.hint.vi))} ${d.hint.url ? link(d.hint.url, "↗") : ""}</span>` : ""}</td>
      <td>${d.status === "open" ? (d.hint ? chip("amber", T("open in doc · confirm", "mở trong doc · cần xác nhận")) : chip("red", T("open", "mở"))) : chip("green", esc(d.choice || T("decided", "đã quyết")))}</td>
    </tr>`).join("");
    return `<section class="card"><h2><span class="num">1</span>${T("Decide", "Cần quyết")} · v${esc(o.line)}</h2>
      <p class="why">${T("From release-" + o.line + "/RELEASE_PREP.md. ⚑ = facts suggest it was already decided: write the choice in the doc.", "Từ release-" + o.line + "/RELEASE_PREP.md. ⚑ = dữ kiện cho thấy đã quyết trên thực tế: ghi lựa chọn vào tài liệu.")}</p>
      <div class="scroll"><table class="tbl"><thead><tr><th>#</th><th>${T("Question", "Câu hỏi")}</th><th>${T("Status", "Trạng thái")}</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }

  function blockers(o) {
    // Same failing job in push and release runs → one row, two events.
    const merged = [];
    o.blockers.forEach((b) => {
      const same = b.kind === "publish" && merged.find((x) => x.kind === "publish" && x.code === b.code && x.detail === b.detail);
      if (same) { same.events.push(b.title.match(/\((\w+)\)/)?.[1]); if (b.cmd && same.cmd !== b.cmd) same.cmd2 = b.cmd; return; }
      merged.push({ ...b, events: b.kind === "publish" ? [b.title.match(/\((\w+)\)/)?.[1]] : [] });
    });
    const groups = {};
    merged.forEach((b) => (groups[b.kind] ??= []).push(b));
    const body = Object.entries(groups).map(([k, bs]) => {
      const K = KIND[k];
      const rows = bs.map((b) => `<tr>
        <td style="width:34%"><b>${esc(b.code)}</b>
          ${b.events?.length ? `<div class="muted" style="font-size:12px">${T("runs", "run")}: ${esc(b.events.filter(Boolean).join(" + "))}</div>` : ""}</td>
        <td>${b.kind === "publish" ? "" : md(b.title)}${staleChip(b.src)}
          ${b.detail ? `<span class="err">${esc(b.detail)}</span>` : ""}
          ${b.fact ? `<span class="fact">▸ ${esc(b.fact)}</span>` : ""}
          ${b.fix_ref && b.kind === "carryover" ? `<div class="muted" style="font-size:12px">${T("Fix", "Cách sửa")}: ${md(b.fix_ref)}</div>` : ""}</td>
        <td style="white-space:nowrap">${ownerTxt(b.owner)}${b.cmd ? "<br>" + copyBtn(b.cmd, b.cmd2 ? b.events[0] : "") : ""}${b.cmd2 ? "<br>" + copyBtn(b.cmd2, b.events[1]) : ""}</td>
        <td style="white-space:nowrap">${b.evidence ? link(b.evidence, T("evidence ↗", "bằng chứng ↗")) : ""}</td></tr>`).join("");
      return `<div class="group">${chip(K[0], T(K[1], K[2]))} <span style="text-transform:none;font-weight:400">${esc(T(K[3], K[4]))}</span></div>
        <div class="scroll"><table class="tbl"><tbody>${rows}</tbody></table></div>`;
    }).join("");
    return `<section class="card"><h2><span class="num">2</span>${T("Blocking the next RC", "Đang chặn RC tiếp theo")} <span class="chip red">${merged.length}</span></h2>
      <p class="why">${T("Ordered by what stops a release first: publish → artifacts → dev CI → bugs → carried-over items.", "Xếp theo thứ tự chặn release: publish → artifact → CI dev → bug → việc mang từ bản trước.")}</p>${body}</section>`;
  }

  function readyCard(o) {
    const R = o.ready || [];
    if (!R.length) return "";
    const rows = R.map((p) => `<tr><td>${link(`https://github.com/LMCache/LMCache/pull/${p.num}`, "#" + p.num)}</td>
      <td>${esc(p.title)} ${p.review === "APPROVED" ? chip("green", "APPROVED") : ""} ${p.verb === "rebase" ? chip("amber", T("rebase first", "rebase trước")) : ""}</td>
      <td>${ownerTxt(p.owner)}</td><td class="muted">${p.age_d != null ? Math.round(p.age_d) + " d" : ""}</td><td class="muted">${esc(p.mergeable || "")}</td><td>${copyBtn(p.cmd)}</td></tr>`).join("");
    const nA = R.filter((p) => p.review === "APPROVED").length;
    return `<section class="card"><h2><span class="num">3</span>${T("Ready for 'full'", "Sẵn sàng gắn 'full'")} <span class="chip blue">${R.length}</span></h2>
      <p class="why">${T(`Green on DCO, code quality and GPU unit; the required MP suite has not run. ${nA} approved (first). Owner = GitHub assignee, else the author.`, `Đã xanh DCO, code quality và GPU unit; bộ MP bắt buộc chưa chạy. ${nA} PR đã duyệt (lên đầu). Owner = người được giao trên GitHub, không có thì là tác giả.`)}${staleChip("observe_snapshot")}</p>
      <details${nA ? " open" : ""}><summary class="muted">${T("show the queue", "xem hàng đợi")}</summary><div class="scroll"><table class="tbl"><thead><tr><th>PR</th><th>${T("Title", "Tiêu đề")}</th><th>Owner</th><th>${T("Age", "Tuổi")}</th><th>Mergeable</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></details></section>`;
  }

  function matrixCard(o) {
    const tags = o.focus.filter((t) => o.matrix[t]);
    if (!tags.length) return "";
    const specs = o.matrix[tags[0]].map((r) => r.code);
    const by = {};
    tags.forEach((t) => o.matrix[t].forEach((r) => ((by[r.code] ??= {})[t] = r)));
    const cell = (r) => {
      if (!r || !r.expected) return `<span class="cell na" title="${T("not expected for this kind of tag", "không yêu cầu cho loại tag này")}">—</span>`;
      if (r.present == null) return `<span class="cell na">?</span>`;
      const cls = r.ok ? "ok" : r.present ? "warn" : "bad";
      const sym = r.ok ? "✓" : r.present ? "!" : "✗";
      const tip = [r.ref, r.detail].filter(Boolean).join(" · ");
      return `${link(r.url, `<span class="cell ${cls}" title="${esc(tip)}">${sym}</span>`)}${!r.ok && r.detail ? `<div class="muted" style="font-size:11.5px">${esc(r.detail)}</div>` : ""}`;
    };
    const rows = specs.map((c) => {
      const lab = by[c][tags[0]].label;
      return `<tr><td>${esc(lab)}</td>${tags.map((t) => `<td class="c">${cell(by[c][t])}</td>`).join("")}</tr>`;
    }).join("");
    const checked = o.matrix[tags[0]].find((r) => r.checked_at)?.checked_at;
    return `<section class="card"><h2><span class="num">4</span>${T("What users actually got", "Người dùng thực sự nhận được gì")}</h2>
      <p class="why">${T("Checked in the registries, not inferred from CI.", "Kiểm tra trực tiếp registry, không suy ra từ CI.")} ${checked ? T("Checked", "Kiểm tra lúc") + " " + esc(day(checked)) + " (" + ago(checked) + ")" : ""}</p>
      <div class="scroll"><table class="tbl mx"><thead><tr><th>Artifact</th>${tags.map((t) => `<th class="c">${esc(t)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="legend"><span><span class="cell ok">✓</span> ${T("present and correct", "có và đúng")}</span><span><span class="cell warn">!</span> ${T("present but wrong (e.g. per-arch only)", "có nhưng sai (vd. chỉ per-arch)")}</span>
      <span><span class="cell bad">✗</span> ${T("missing", "thiếu")}</span><span><span class="cell na">—</span> ${T("not expected", "không yêu cầu")}</span></div></section>`;
  }

  function devGates(o) {
    const rows = o.dev_gates.map((g) => `<tr><td><b>${esc(g.slug)}</b></td>
      <td><div class="strip">${g.recent.map((s) => `<i class="${s === "passed" ? "p" : s === "failed" ? "f" : "o"}" title="${esc(s)}"></i>`).join("")}</div></td>
      <td>${g.last.state === "passed" ? chip("green", "passed") : chip("red", "failed")} ${link(g.last.url, "#" + g.last.number)}</td>
      <td class="muted">${T("last pass", "lần xanh cuối")}: ${day(g.last_pass)}</td></tr>`).join("");
    return `<section class="card"><h2><span class="num">5</span>${T("dev gate pipelines", "Pipeline gate trên dev")}</h2>
      <p class="why">${T("Last 10 finished dev builds, oldest → newest. These must be green before cutting an RC.", "10 build dev gần nhất, cũ → mới. Phải xanh trước khi cắt RC.")}</p>
      <div class="scroll"><table class="tbl"><tbody>${rows}</tbody></table></div></section>`;
  }

  function releasesCard(o) {
    const rows = o.releases.map((r) => `<tr class="click" data-tag="${esc(r.tag)}">
      <td><b>${esc(r.tag)}</b><div class="muted" style="font-size:12px">${esc(r.kind)} · ${day(r.published_at || r.tagged_at)}</div></td>
      <td>${vchip(r.verdict)} <span class="muted">${r.n_ok}/${r.n_expected}</span>
        ${r.missing.length ? `<div class="muted" style="font-size:12px">${T("missing", "thiếu")}: ${esc(r.missing.map((m) => m.label).join(", "))}</div>` : ""}</td>
      <td>${r.publish.map((p) => `<div style="font-size:12px">${esc(p.event)} ${link(p.url, concl(p.conclusion, p.status))}</div>`).join("") || '<span class="muted">—</span>'}</td>
      <td>${r.bugs.map((b) => `${link(b.evidence, esc(b.code))} ${b.status === "fixed" ? chip("green", T("fixed", "đã sửa") + (b.fix_ref ? " " + b.fix_ref : "")) : chip("red", T("open", "mở"))}`).join("<br>") || '<span class="muted">—</span>'}</td>
      <td class="c">${r.n_prs || '<span class="muted">—</span>'}</td></tr>`).join("");
    return `<section class="card"><h2><span class="num">6</span>${T("Release history", "Lịch sử release")}</h2>
      <p class="why">${T("Verdict comes from registries (artifacts), publish runs are shown separately: a red run does not always mean nothing shipped. Click a row for PRs and details.", "Kết luận lấy từ registry (artifact); run publish hiện riêng: run đỏ không có nghĩa là không có gì được phát hành. Bấm vào dòng để xem PR và chi tiết.")}</p>
      <div class="scroll"><table class="tbl"><thead><tr><th>Tag</th><th>${T("Verdict", "Kết luận")}</th><th>publish.yml</th><th>${T("Bugs found later", "Bug phát hiện sau")}</th><th class="c">PRs</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }

  async function renderNow(el) {
    const o = await get("overview");
    renderAges(o.ages);
    el.innerHTML = hero(o) + decisions(o) + blockers(o) + readyCard(o) + matrixCard(o) + devGates(o) + releasesCard(o);
    el.querySelectorAll("tr[data-tag]").forEach((tr) => tr.addEventListener("click", () => openRelease(tr.dataset.tag)));
    foot(o);
  }

  // ───────── release drawer ─────────
  async function openRelease(tag) {
    const d = document.getElementById("drawer");
    document.getElementById("drawer-title").textContent = tag;
    const body = document.getElementById("drawer-body");
    body.innerHTML = `<p class="muted">${T("Loading…", "Đang tải…")}</p>`;
    d.hidden = false;
    const r = await get("release/" + encodeURIComponent(tag));
    const mx = r.matrix.filter((m) => m.expected).map((m) => `<tr><td>${esc(m.label)}</td><td>${m.present == null ? "?" : m.ok ? '<span class="cell ok">✓</span>' : m.present ? '<span class="cell warn">!</span>' : '<span class="cell bad">✗</span>'}</td><td class="muted">${esc([m.ref, m.detail].filter(Boolean).join(" · "))}</td><td>${link(m.url, "↗")}</td></tr>`).join("");
    const runs = r.runs.map((x) => `<div style="margin:6px 0">${esc(x.event)} · ${link(x.url, concl(x.conclusion, x.status))} <span class="muted">${T("attempt", "lần")} ${x.attempt} · ${x.jobs} jobs · ${x.skipped} skipped</span>
      ${x.failed_jobs.map((j) => `<div style="margin-left:12px">✗ ${link(j.url, esc(j.name))}${j.error_line ? `<span class="err">${esc(j.error_line)}</span>` : ""}</div>`).join("")}</div>`).join("");
    const feats = {};
    r.prs.forEach((p) => (p.features || "").split(",").filter(Boolean).forEach((f) => (feats[f] = (feats[f] || 0) + 1)));
    const prs = r.prs.slice(0, 300).map((p) => `<tr><td>${link(p.url, "#" + p.number)}</td><td>${esc(p.title || "")}</td><td class="muted">${esc(p.author || "")}</td></tr>`).join("");
    const hist = r.verdict_history.map((h) => `<tr><td class="muted">${day(h.taken_at)}</td><td>${h.verdict.startsWith("old:") ? chip("gray", h.verdict) : vchip(h.verdict)}</td><td class="muted">${esc(h.reason || "")}</td></tr>`).join("");
    body.innerHTML = `<p>${vchip(r.verdict)} ${link(r.url, "GitHub release ↗")} <span class="muted">${day(r.published_at || r.tagged_at)}</span></p>
      <h3>${T("Artifacts", "Artifact")}</h3><table class="tbl"><tbody>${mx}</tbody></table>
      <h3>publish.yml</h3>${runs || '<p class="muted">—</p>'}
      <h3>${T("Changed areas", "Vùng code thay đổi")}</h3><p>${Object.entries(feats).sort((a, b) => b[1] - a[1]).map(([f, n]) => chip("blue", `${f} ${n}`)).join(" ") || '<span class="muted">—</span>'}</p>
      <h3>PRs (${r.prs.length})</h3><div class="scroll"><table class="tbl"><tbody>${prs || '<tr><td class="muted">' + T("No PR range for this tag", "Không có dải PR cho tag này") + "</td></tr>"}</tbody></table></div>
      <h3>${T("Verdict history", "Lịch sử kết luận")}</h3><table class="tbl"><tbody>${hist || '<tr><td class="muted">—</td></tr>'}</tbody></table>`;
  }
  document.getElementById("drawer-close").addEventListener("click", () => (document.getElementById("drawer").hidden = true));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") document.getElementById("drawer").hidden = true; });

  // ───────── TRENDS ─────────
  function bars(series, { h = 120, keys, colors, labels }) {
    const W = Math.max(series.length * 18, 300), pad = 22;
    const max = Math.max(1, ...series.map((s) => keys.reduce((a, k) => a + (s[k] || 0), 0)));
    const bw = (W - pad) / Math.max(series.length, 1);
    let g = `<line class="ax" x1="${pad}" y1="${h}" x2="${W}" y2="${h}"/>` + `<text x="0" y="10">${max}</text>`;
    series.forEach((s, i) => {
      let y = h;
      keys.forEach((k, j) => {
        const v = s[k] || 0, bh = (v / max) * (h - 12);
        if (v) g += `<rect x="${pad + i * bw + 2}" y="${y - bh}" width="${bw - 4}" height="${bh}" fill="${colors[j]}"><title>${esc(labels(s))} · ${k}: ${v}</title></rect>`;
        y -= bh;
      });
      if (i % Math.ceil(series.length / 8) === 0) g += `<text x="${pad + i * bw}" y="${h + 12}">${esc(labels(s))}</text>`;
    });
    return `<div class="chart"><svg viewBox="0 0 ${W} ${h + 16}" role="img">${g}</svg></div>`;
  }
  function spark(vals, color) {
    const v = vals.filter((x) => x != null);
    if (v.length < 2) return "";
    const W = 160, H = 34, mx = Math.max(...v), mn = Math.min(...v), r = mx - mn || 1;
    const pts = v.map((x, i) => `${(i / (v.length - 1)) * W},${H - 3 - ((x - mn) / r) * (H - 6)}`).join(" ");
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"><polyline fill="none" stroke="${color}" stroke-width="2" points="${pts}"/></svg>`;
  }
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  async function renderHistory(el) {
    const h = await get("history");
    const G = css("--green"), R = css("--red"), M = css("--muted"), A = css("--amber");
    // KPI cards: definition, latest value, change vs previous day, direction.
    const KPI = [
      ["observe_history.prs.open", T("Open PRs", "PR đang mở"), T("Open PRs on GitHub at snapshot time.", "Số PR đang mở lúc chụp snapshot."), "down"],
      ["observe_history.prs.merged_unreleased", T("Merged, not released", "Đã merge, chưa phát hành"), T("PRs merged since the last stable tag.", "PR merge sau tag stable gần nhất."), "down"],
      ["observe_history.queue.k3-unit-tests.w90", T("k3-unit wait p90 (min)", "Chờ k3-unit p90 (phút)"), T("90th percentile GPU queue wait, last 20 builds. Median hides the long waits.", "Phân vị 90 thời gian chờ GPU, 20 build gần nhất. Trung vị che mất các lần chờ lâu."), "down"],
      ["observe_history.queue.k3-multiprocess-test.w90", T("k3-mp wait p90 (min)", "Chờ k3-mp p90 (phút)"), T("Same, for the multiprocess pipeline.", "Như trên, cho pipeline multiprocess."), "down"],
      ["ops_hist.tot.GPU_failed", T("GPU job-min failed / 24 h", "Phút job GPU fail / 24 giờ"), T("GPU job minutes spent on failed jobs in the last 24 h.", "Phút job GPU tiêu cho job fail trong 24 giờ."), "down"],
    ];
    const kv = {};
    h.kpi.forEach((r) => (kv[r.key] ??= []).push(r));
    const cards = KPI.map(([k, name, def, better]) => {
      const s = kv[k] || [];
      const last = s.at(-1), prev = s.at(-2);
      const d = last && prev ? last.value - prev.value : null;
      const good = d == null || d === 0 ? null : (d < 0) === (better === "down");
      return `<div class="metric"><h3>${esc(name)}</h3><p class="def">${esc(def)}</p>
        <span class="val">${last ? Math.round(last.value * 10) / 10 : "—"}</span>
        ${d != null ? `<span class="chip ${good == null ? "gray" : good ? "green" : "red"}">${d > 0 ? "▲" : d < 0 ? "▼" : "="} ${Math.abs(Math.round(d * 10) / 10)}</span>` : ""}
        <span class="muted" style="font-size:12px">${last ? day(last.day) : ""} · n=${s.length} ${T("days", "ngày")}</span>
        <div>${spark(s.map((x) => x.value), M)}</div></div>`;
    }).join("");
    // dev gates heat strips
    const pipes = {};
    h.gates.forEach((g) => (pipes[g.pipeline] ??= []).push(g));
    const heat = Object.entries(pipes).map(([p, ds]) => `<tr><td><b>${esc(p)}</b></td><td><div class="strip">${ds.map((d) => {
      const c = d.pass_pct == null ? M : d.pass_pct >= 90 ? G : d.pass_pct >= 50 ? A : R;
      return `<i style="background:${c}" title="${esc(d.day)}: ${d.passed}/${d.passed + d.failed} ${T("passed", "xanh")}"></i>`;
    }).join("")}</div></td><td class="muted">${ds.length} ${T("days", "ngày")}</td></tr>`).join("");
    const nightly = h.nightly.map((n) => `<a href="${esc(n.url)}" target="_blank" rel="noopener"><i class="${n.conclusion === "success" ? "p" : n.conclusion === "failure" ? "f" : "o"}" title="${esc(n.day)} ${esc(n.conclusion || "")}"></i></a>`).join("");
    const nf = h.nightly.slice().reverse().findIndex((n) => n.conclusion === "success");
    // publish weekly: sum events
    const wk = {};
    h.publish_weekly.forEach((r) => { const w = (wk[r.week] ??= { week: r.week, ok: 0, failed: 0, cancelled: 0 }); w.ok += r.ok; w.failed += r.failed; w.cancelled += r.cancelled; });
    const cyc = h.cycle.map((c) => `<tr><td><b>${esc(c.line)}</b></td><td>${day(c.first_rc_at)}</td><td>${day(c.final_at)}</td><td>${c.n_rc}</td><td>${c.n_post}</td>
      <td>${c.rc_to_final_days != null ? `<span style="display:inline-block;height:10px;width:${Math.min(120, c.rc_to_final_days * 5)}px;background:${M};border-radius:3px"></span> ${c.rc_to_final_days} ${T("d", "ngày")}` : chip("blue", T("in progress", "đang làm"))}</td></tr>`).join("");
    const jobs = h.failing_jobs.map((j) => `<tr><td>${esc(j.name)}</td><td class="c">${j.failures}</td><td class="muted">${day(j.last_at)}</td><td>${j.last_error ? `<span class="err clamp" title="${esc(j.last_error)}">${esc(j.last_error)}</span>` : ""}</td></tr>`).join("");
    el.innerHTML = `
      <section class="card"><h2>${T("Key numbers per day", "Chỉ số chính theo ngày")}</h2><p class="why">${T("From the daily snapshots. ▲▼ = change vs the previous snapshot day; green = better.", "Từ snapshot hằng ngày. ▲▼ = thay đổi so với ngày snapshot trước; xanh = tốt hơn.")}</p>
        <div class="grid2">${cards}</div></section>
      <div class="grid2">
        <section class="card"><h2>${T("Nightly image build", "Build image nightly")}</h2><p class="why">${T("Last 30 runs, oldest → newest.", "30 run gần nhất, cũ → mới.")} ${nf === -1 ? `<b style="color:${R}">${T("No success in this window.", "Không có lần thành công nào trong khoảng này.")}</b>` : `${T("Failures since last success", "Số lần fail từ lần xanh cuối")}: <b>${nf}</b>`}</p>
          <div class="strip">${nightly}</div></section>
        <section class="card"><h2>${T("publish.yml per week", "publish.yml theo tuần")}</h2><p class="why">${T("All events (tag push, release, dev push). Green ok · red failed · gray cancelled.", "Mọi event (push tag, release, push dev). Xanh ok · đỏ fail · xám cancelled.")}</p>
          ${bars(Object.values(wk), { keys: ["ok", "failed", "cancelled"], colors: [G, R, M], labels: (s) => s.week.slice(5) })}</section>
      </div>
      <section class="card"><h2>${T("dev gate pass rate per day (30 days)", "Tỉ lệ xanh của gate trên dev theo ngày (30 ngày)")}</h2><p class="why">${T("Green ≥ 90 % · amber ≥ 50 % · red < 50 %. Hover for counts.", "Xanh ≥ 90 % · vàng ≥ 50 % · đỏ < 50 %. Rê chuột để xem số.")}</p>
        <div class="scroll"><table class="tbl"><tbody>${heat}</tbody></table></div></section>
      <div class="grid2">
        <section class="card"><h2>${T("Release cycle", "Chu kỳ release")}</h2><p class="why">${T("First RC → final tag, per release line.", "Từ RC đầu tiên → tag final, theo từng bản.")}</p>
          <div class="scroll"><table class="tbl"><thead><tr><th>Line</th><th>rc1</th><th>final</th><th>#rc</th><th>#post</th><th>${T("days", "ngày")}</th></tr></thead><tbody>${cyc}</tbody></table></div></section>
        <section class="card"><h2>${T("Jobs that fail most", "Job fail nhiều nhất")}</h2><p class="why">${T("publish / nightly jobs, with the last error line we read.", "Job publish / nightly, kèm dòng lỗi cuối cùng đã đọc.")}</p>
          <div class="scroll"><table class="tbl"><thead><tr><th>Job</th><th class="c">#</th><th>${T("last", "gần nhất")}</th><th>${T("error", "lỗi")}</th></tr></thead><tbody>${jobs}</tbody></table></div></section>
      </div>`;
  }

  // ───────── shell ─────────
  function foot(o) {
    document.getElementById("foot").innerHTML = `${T("Data sources (local runs only)", "Nguồn dữ liệu (chỉ chạy local)")}: ` +
      o.sources.slice(0, 8).map((s) => `<span class="src">${esc(s.source)} · ${day(s.taken_at)} ${esc(String(s.taken_at).slice(11, 16))}Z</span>`).join("") +
      (STATIC ? ` · ${T("static copy", "bản tĩnh")}` : "");
  }
  function applyStatic() {
    document.documentElement.lang = LANG;
    document.querySelectorAll("[data-t]").forEach((n) => { const [en, vi] = n.dataset.t.split("|"); n.textContent = T(en, vi); });
    document.querySelectorAll("[data-lang]").forEach((b) => b.classList.toggle("on", b.dataset.lang === LANG));
  }
  // ───────── unified navigation: native views + every view of the existing page (legacy.html, embed mode) ─────────
  // [id, group, EN, VI, native | [[sub, legacy hash, EN, VI, subgroup?], ...]]
  const ROUTES = [
    ["now", "rm", "Now", "Bây giờ", "now"],
    ["history", "rm", "Trends", "Xu hướng", "history"],
    ["today", "rm", "Today inbox", "Hộp việc hôm nay", [["", "obs/today"]]],
    ["weekly", "rm", "Weekly full build", "Weekly full build", [["", "obs/weekly"]]],
    ["impact", "rm", "CI impact", "Tác động CI", [["", "obs/impact"]]],
    ["releases", "rm", "Releases", "Releases", [["", "obs/release"]]],
    ["trace", "rm", "Release trace", "Truy vết release", [["", "obs/trace"]]],
    ["coming", "rm", "Next release", "Release tới", [["", "obs/coming"]]],
    ["ci-cost", "rm", "CI cost", "Chi phí CI", [["cpu", "obs/opt_cpu", "CPU · GitHub Actions", "CPU · GitHub Actions"], ["gpu", "obs/opt_gpu", "GPU · Buildkite", "GPU · Buildkite"]]],
    ["rebase-risk", "rm", "Rebase risk & PR queue", "Rủi ro rebase & hàng đợi PR", [["", "obs/overlap"]]],
    ["gates", "ref", "Quality gates", "Cổng chất lượng", [["guide", "gates/guide", "Guide & gates", "Hướng dẫn & cổng"], ["tiers", "gates/tiers", "Tiers & impact", "Tầng & tác động"]]],
    ["tests", "ref", "Tests (CPU · GPU)", "Test (CPU · GPU)", [
      ["cpu-overview", "cpu/overview", "Overview", "Tổng quan", "CPU"], ["cpu-coverage", "cpu/tiers", "Coverage", "Độ phủ", "CPU"],
      ["cpu-cost", "cpu/cost", "Cost & time", "Chi phí & thời gian", "CPU"], ["cpu-findings", "cpu/findings", "Findings", "Phát hiện", "CPU"],
      ["cpu-explorer", "cpu/explore", "Test explorer", "Khám phá test", "CPU"],
      ["gpu-overview", "gpu/overview", "Overview", "Tổng quan", "GPU"], ["gpu-workloads", "gpu/tiers", "Workloads", "Workload", "GPU"],
      ["gpu-cost", "gpu/cost", "Cost & time", "Chi phí & thời gian", "GPU"], ["gpu-findings", "gpu/findings", "Findings", "Phát hiện", "GPU"],
      ["gpu-mindmap", "gpu/explore", "Mindmap", "Mindmap", "GPU"]]],
    ["r1130", "ref", "CI Baseline", "Baseline CI", [
      ["baseline", "r1130/baseline", "GPU Usage", "Tiêu thụ GPU"], ["cpu", "r1130/cpu", "CPU Usage", "Tiêu thụ CPU"],
      ["green", "r1130/green", "Time to green", "Thời gian tới xanh"], ["retry", "r1130/retry", "Retry & Waste", "Chạy lại & Lãng phí"],
      ["prs", "r1130/prs", "Per PR", "Theo PR"], ["track", "r1130/track", "Track vs baseline", "So với baseline"],
      ["repro", "r1130/repro", "Reproduce", "Tái lập"], ["quality", "r1130/quality", "Data quality", "Chất lượng dữ liệu"]]],
  ];
  const GROUPS = { rm: ["Release management", "Quản lý release"], ref: ["Explore & baseline", "Khám phá & baseline"] };
  const BY_ID = Object.fromEntries(ROUTES.map((r) => [r[0], r]));
  const BY_LEGACY = {};
  ROUTES.forEach((r) => Array.isArray(r[4]) && r[4].forEach((x) => (BY_LEGACY[x[1]] = [r[0], x[0]])));
  const parse = () => { const [id, sub] = (location.hash || "#now").slice(1).split("/"); return BY_ID[id] ? [id, sub || ""] : ["now", ""]; };

  function renderNav(id, sub) {
    let g = "";
    document.getElementById("tabs").innerHTML = ROUTES.map((r) => {
      const head = r[1] !== g ? `<span class="grp">${esc(T(...GROUPS[(g = r[1])]))}</span>` : "";
      return head + `<a href="#${r[0]}" data-tab="${r[0]}" role="tab" aria-selected="${r[0] === id}" class="${r[0] === id ? "on" : ""}">${esc(T(r[2], r[3]))}</a>`;
    }).join("");
    const r = BY_ID[id], st = document.getElementById("subtabs");
    const subs = Array.isArray(r[4]) && r[4].length > 1 ? r[4] : null;
    st.hidden = !subs;
    if (subs) {
      let sg = "";
      const cur = sub || subs[0][0];
      st.innerHTML = subs.map((x) => (x[4] && x[4] !== sg ? `<span class="grp">${esc((sg = x[4]))}</span>` : "") +
        `<a href="#${id}/${x[0]}" role="tab" aria-selected="${x[0] === cur}" class="${x[0] === cur ? "on" : ""}">${esc(T(x[2], x[3]))}</a>`).join("");
    } else st.innerHTML = "";
    const on = document.querySelector(".tabs a.on");
    if (on) { const nav = on.parentElement; nav.scrollLeft = Math.max(0, on.offsetLeft - nav.clientWidth / 3); }
  }

  // ── the existing page in an iframe (same origin): driven through its hash, I18N, data-theme and its own checkboxes
  const frame = document.getElementById("legacy"), wrap = document.getElementById("legacyWrap");
  let frameReady = false, fromShell = false;
  const fwin = () => (frameReady ? frame.contentWindow : null);
  function syncFrame() {
    const w = fwin();
    if (!w) return;
    try {
      if (w.I18N && w.I18N.lang !== LANG) w.I18N.setLang(LANG);
      const t = document.documentElement.dataset.theme;
      if (t) w.document.documentElement.dataset.theme = t; else delete w.document.documentElement.dataset.theme;
      for (const [mine, theirs] of [["optDesc", "vDesc"], ["optAll", "vAll"]]) {
        const a = document.getElementById(mine), b = w.document.getElementById(theirs);
        if (b && b.checked !== a.checked) { b.checked = a.checked; b.dispatchEvent(new Event("change", { bubbles: true })); }
      }
    } catch (e) { console.warn("legacy sync", e); }
  }
  function sizeFrame() {
    if (wrap.hidden) return;
    const top = wrap.getBoundingClientRect().top;
    frame.style.height = Math.max(420, window.innerHeight - Math.max(0, top)) + "px";
  }
  function showLegacy(hash) {
    wrap.hidden = false;
    document.getElementById("app").hidden = true;
    if (!frame.getAttribute("src")) {
      frame.addEventListener("load", () => {
        frameReady = true;
        syncFrame();
        frame.contentWindow.addEventListener("hashchange", () => {   // a link inside the page moved it: follow in the shell
          if (fromShell) return;
          const m = BY_LEGACY[frame.contentWindow.location.hash.slice(1)];
          if (m) { const want = "#" + m[0] + (m[1] ? "/" + m[1] : ""); if (location.hash !== want) { history.replaceState(null, "", want); renderNav(m[0], m[1]); } }
        });
      });
      frame.src = "legacy.html#" + hash;
    } else if (frameReady && frame.contentWindow.location.hash.slice(1) !== hash) {
      fromShell = true;
      frame.contentWindow.location.hash = hash;
      setTimeout(() => (fromShell = false), 50);
    }
    requestAnimationFrame(sizeFrame);
  }

  async function route() {
    const [id, sub] = parse();
    renderNav(id, sub);
    const r = BY_ID[id];
    const el = document.getElementById("app");
    if (Array.isArray(r[4])) {
      const x = r[4].find((s) => s[0] === sub) || r[4][0];
      showLegacy(x[1]);
      get("overview").then((o) => { renderAges(o.ages); foot(o); }).catch(() => {});
      return;
    }
    wrap.hidden = true;
    el.hidden = false;
    try {
      if (id === "history") { await renderHistory(el); get("overview").then((o) => { renderAges(o.ages); foot(o); }); }
      else await renderNow(el);
    } catch (e) {
      el.innerHTML = `<section class="card"><h2>${T("Cannot load data", "Không tải được dữ liệu")}</h2><p class="err">${esc(e.message)}</p>
        <p class="muted">${T("Start the server: python -X utf8 backend/server.py", "Chạy server: python -X utf8 backend/server.py")}</p></section>`;
    }
  }
  document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => {
    LANG = b.dataset.lang; store.set("opsLang", LANG); store.set("ciMapLang", LANG); applyStatic(); syncFrame(); route();
  }));
  const theme = store.get("opsTheme", "");
  if (theme) document.documentElement.dataset.theme = theme;
  document.getElementById("theme").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    store.set("opsTheme", document.documentElement.dataset.theme);
    syncFrame();
    if (wrap.hidden) route();
  });
  // descriptions / show all: the page's own switches (#vDesc, #vAll), mirrored here because its bar is hidden in embed mode
  document.getElementById("optDesc").checked = store.get("ciMapDesc", "1") !== "0";
  ["optDesc", "optAll"].forEach((k) => document.getElementById(k).addEventListener("change", () => {
    if (k === "optDesc") { store.set("ciMapDesc", document.getElementById(k).checked ? "1" : "0"); document.body.classList.toggle("nodesc", !document.getElementById(k).checked); }
    syncFrame();
  }));
  document.body.classList.toggle("nodesc", !document.getElementById("optDesc").checked);
  window.addEventListener("hashchange", route);
  window.addEventListener("resize", sizeFrame);
  applyStatic();
  route();
})();
