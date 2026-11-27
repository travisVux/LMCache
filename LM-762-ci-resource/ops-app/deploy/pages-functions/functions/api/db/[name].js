// GET /api/db/<table or view>?tag=&branch=&env=&range=7d&since=&until=&<column>=&limit=&offset=
// Contract: backend/dbapi.py docstring. Tables are read at ONE pinned snapshot (the pointer is read once, then the
// history table is filtered by it). Views read the current snapshot at query time (marked "pinned": false).
import { J, E, guard, current, buildQuery, parseIntStrict, LIMIT_DEFAULT, LIMIT_MAX } from "../../../lib/api.js";

const qi = (n) => '"' + String(n).replace(/"/g, '""') + '"';

export const onRequestGet = guard(async ({ env, params, request }) => {
  if (!env.RD_DB) return E("no_database", "D1 is not bound to this project (binding RD_DB)", 503);
  const name = String(params.name || "");
  const ex = await env.RD_DB.prepare("SELECT s FROM rd_meta WHERE k = 'exposed'").first();
  const exposed = ex ? JSON.parse(ex.s) : {};
  if (!Object.prototype.hasOwnProperty.call(exposed, name))
    return E("unknown_table", `no table or view '${name}'`, 404, { tables: Object.keys(exposed).sort() });
  const sync = await current(env.RD_DB);
  if (!sync || !sync.sync_id) return E("no_snapshot", "no snapshot yet", 503);
  const info = exposed[name], q = new URL(request.url).searchParams;
  let limit, offset;
  try {
    limit = parseIntStrict(q.get("limit"), LIMIT_DEFAULT, 1, LIMIT_MAX);
    offset = parseIntStrict(q.get("offset"), 0, 0, 1e9);
  } catch (e) { return E("bad_param", `limit / offset must be digits (got ${e.message})`, 400); }
  const anchor = sync.last_synced_at ? Date.parse(sync.last_synced_at) : Date.now();
  let built;
  try { built = buildQuery(info, q, anchor); }
  catch (e) {
    if (e.bad) return E("filter_not_applicable", `${name} has no column for: ${e.bad.join(", ")}`, 400, { columns: info.cols, time: info.time });
    return E("bad_param", "range must look like 24h or 7d", 400);
  }
  const { where, args, applied } = built;
  const table = info.kind !== "view";
  const from = table ? qi("h_" + name) : qi(name);
  if (table) { where.unshift("_from <= ? AND (_to IS NULL OR _to > ?)"); args.unshift(sync.sync_id, sync.sync_id); }
  if (args.length > 90) return E("bad_param", "too many filters", 400);
  const w = where.length ? " WHERE " + where.join(" AND ") : "";
  const order = (info.time ? [`${qi(info.time)} DESC`] : []).concat((info.pk && info.pk.length ? info.pk : (info.cols || []).slice(0, 1)).map(qi));
  const sel = (info.cols || []).length ? info.cols.map(qi).join(", ") : "*";
  const [cnt, r] = await env.RD_DB.batch([   // one batch: the count and the rows see the same data
    env.RD_DB.prepare(`SELECT COUNT(*) AS n FROM ${from}${w}`).bind(...args),
    env.RD_DB.prepare(`SELECT ${sel} FROM ${from}${w}` + (order.length ? ` ORDER BY ${order.join(", ")}` : "") + ` LIMIT ${limit} OFFSET ${offset}`).bind(...args),
  ]);
  const total = cnt.results[0].n, rows = r.results;
  return J({ sync, name, as_of: sync.last_synced_at || null, pinned: table, filters: applied, n: rows.length, total, limit, offset,
             next_offset: offset + rows.length < total ? offset + rows.length : null, rows },
           200, { "X-Sync-Id": String(sync.sync_id) });
});
