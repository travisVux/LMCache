// GET /api/db -> the tables and views served by /api/db/<name>: {kind, cols, pk, time}.
import { J, E, guard, current } from "../../../lib/api.js";

export const onRequestGet = guard(async ({ env }) => {
  if (!env.RD_DB) return E("no_database", "D1 is not bound to this project (binding RD_DB)", 503);
  const ex = await env.RD_DB.prepare("SELECT s FROM rd_meta WHERE k = 'exposed'").first();
  const sync = await current(env.RD_DB);
  return J({ sync, tables: ex ? JSON.parse(ex.s) : {} }, 200, sync && sync.sync_id ? { "X-Sync-Id": String(sync.sync_id) } : {});
});
