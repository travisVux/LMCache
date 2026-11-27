// Shared by the /api functions (behind _middleware.js). Data: D1 binding RD_DB, filled by deploy/d1_sync.py.
// SAME CONTRACT as backend/dbapi.py on the release PC (its docstring is the reference; tests/check_api_contract.py
// diffs both on the same snapshot). Change both together.
export const J = (o, s = 200, extra = {}) =>
  new Response(JSON.stringify(o), { status: s, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...extra } });

export const E = (code, message, status, extra = {}) => J({ error: { code, message }, ...extra }, status);

export const SHARED = { tag: ["release_tag", "tag"], branch: ["branch", "head_branch", "base"], env: ["device", "env", "pipeline"] };
export const RESERVED = new Set(["tag", "branch", "env", "range", "since", "until", "limit", "offset"]);
export const LIMIT_MAX = 5000, LIMIT_DEFAULT = 1000;

// digits only, else bad_param; clamped (same rule as dbapi.parse_int)
export function parseIntStrict(v, def, lo, hi) {
  if (v == null || v === "") return def;
  if (!/^\d{1,9}$/.test(v)) throw new Error(String(v));
  return Math.min(Math.max(Number(v), lo), hi);
}

// range counts back from the snapshot's as_of, never from "now" (same answer while the snapshot stays the same)
export function rangeStart(v, anchorMs) {
  const m = /^(\d{1,4})([hd])$/.exec(String(v || ""));
  if (!m) return null;
  const ms = Number(m[1]) * (m[2] === "h" ? 3600e3 : 86400e3);
  return new Date(anchorMs - ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export async function current(db) {
  const r = await db.prepare(
    "SELECT m.v AS sync_id, s.label, s.data_build, COALESCE(s.as_of, s.switched_at) AS switched_at, s.status, s.partial_errors " +
    "FROM rd_meta m LEFT JOIN rd_sync s ON s.sync_id = m.v WHERE m.k = 'current'").first();
  if (!r) return null;
  let pe = [];
  try { pe = JSON.parse(r.partial_errors || "[]"); } catch (e) { pe = []; }
  return { sync_id: r.sync_id, label: r.label, data_build: r.data_build, last_synced_at: r.switched_at, partial_errors: pe };
}

// -> { where, args, applied } or throws { bad: [names] } / Error("range")
export function buildQuery(info, q, anchorMs) {
  const cols = info.cols || [], time = info.time, where = [], args = [], applied = {}, bad = [];
  const qi = (n) => '"' + String(n).replace(/"/g, '""') + '"';
  for (const [p, cands] of Object.entries(SHARED)) {
    const v = q.get(p);
    if (v == null || v === "") continue;
    const c = cands.find((x) => cols.includes(x));
    if (!c) { bad.push(p); continue; }
    where.push(`${qi(c)} = ?`); args.push(v); applied[p] = c;
  }
  let lo = q.get("since");
  if (q.get("range")) { lo = rangeStart(q.get("range"), anchorMs); if (!lo) throw new Error("range"); }
  const hi = q.get("until");
  for (const [name, val, op] of [["since", lo, ">="], ["until", hi, "<"]]) {
    if (!val) continue;
    if (!time) { bad.push(name === "since" && q.get("range") ? "range" : name); continue; }
    const v = time === "day" ? val.slice(0, 10) : val;   // day columns hold YYYY-MM-DD
    where.push(`${qi(time)} ${op} ?`); args.push(v); applied[name] = v;
  }
  for (const [k, v] of q) {
    if (RESERVED.has(k)) continue;
    if (!cols.includes(k)) { bad.push(k); continue; }
    where.push(`${qi(k)} = ?`); args.push(v); applied[k] = k;
  }
  if (bad.length) { const e = new Error("filter"); e.bad = bad; throw e; }
  return { where, args, applied };
}

// a function body that never answers HTML or a stack trace
export const guard = (fn) => async (ctx) => {
  try { return await fn(ctx); }
  catch (e) { return E("server_error", String((e && e.message) || e).slice(0, 200), 500); }
};
