// GET /api/sync-status -> one answer for the whole app: which snapshot every tab and API answer shows.
// { sync_id, label, last_synced_at, sync_status: synced|partial|syncing|error|unknown, partial_errors[],
//   data_build (D1 snapshot), page_build (this deployment's data/), in_sync, last_attempt, queue }
import { J, current } from "../../lib/api.js";

export async function onRequestGet({ env, request }) {
  const out = { source: "cloudflare", sync_id: null, label: null, last_synced_at: null, sync_status: "unknown",
                partial_errors: [], data_build: null, page_build: null, in_sync: null, last_attempt: null, queue: null,
                d1: null, run: null };   // same keys as backend/dbapi.sync_info
  try {
    const m = await env.ASSETS.fetch(new URL("/data/manifest.json", request.url));
    if (m.ok) { const j = await m.json(); out.page_build = j.build || null; out.page_made = j.made || null; }
  } catch (e) { /* page without the data split */ }
  if (env.RD_DB) {
    try {
      const c = await current(env.RD_DB);
      if (c) Object.assign(out, c);
      const a = await env.RD_DB.prepare("SELECT sync_id, label, status, started_at, switched_at FROM rd_sync ORDER BY sync_id DESC LIMIT 1").first();
      out.last_attempt = a || null;
      out.sync_status = !c || !c.sync_id ? "unknown"
        : a && a.sync_id > c.sync_id && a.status === "failed" ? "error"
        : a && a.sync_id > c.sync_id && a.status === "writing" ? "syncing"
        : (c.partial_errors || []).length ? "partial" : "synced";
    } catch (e) {
      out.sync_status = "error";
      out.partial_errors = [{ source: "d1", error: String(e && e.message || e).slice(0, 200) }];
    }
  }
  if (env.RD_CTL) {
    try {
      const [req, st] = await Promise.all([env.RD_CTL.get("request", "json"), env.RD_CTL.get("status", "json")]);
      out.queue = { queued: !!req, status: st };
      if (req || (st && st.state === "running")) out.sync_status = "syncing";
    } catch (e) { /* KV optional */ }
  }
  out.in_sync = out.page_build && out.data_build ? out.page_build === out.data_build : null;
  return J(out, 200, out.sync_id ? { "X-Sync-Id": String(out.sync_id) } : {});
}
