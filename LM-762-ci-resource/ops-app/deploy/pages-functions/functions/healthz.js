// GET /healthz on the web copy: the age of the database snapshot. 200 when the snapshot is younger than MAX_AGE_H,
// 503 with ?strict=1 when it is older or missing (for an uptime monitor; review 5.1 / R2). Behind the password gate.
import { J, current } from "../lib/api.js";

const MAX_AGE_H = 48;

export async function onRequestGet({ env, request }) {
  const strict = new URL(request.url).searchParams.has("strict");
  let c = null;
  try { c = env.RD_DB ? await current(env.RD_DB) : null; } catch (e) { c = null; }
  const at = c && c.last_synced_at ? Date.parse(c.last_synced_at) : NaN;
  const age_h = Number.isFinite(at) ? Math.round((Date.now() - at) / 36e5 * 10) / 10 : null;
  const ok = age_h !== null && age_h <= MAX_AGE_H;
  return J({ ok, status: ok ? "ok" : c ? "stale" : "no database", sync_id: c ? c.sync_id : null, label: c ? c.label : null,
             last_synced_at: c ? c.last_synced_at : null, age_h, max_age_h: MAX_AGE_H }, strict && !ok ? 503 : 200);
}
