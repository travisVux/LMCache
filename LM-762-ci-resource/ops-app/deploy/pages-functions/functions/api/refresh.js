// "Refresh data" on the web copy (round 3). Runs behind the password gate (_middleware.js).
// POST /api/refresh        -> queue one refresh request in KV (binding RD_CTL); the release PC picks it up (web_refresh.py)
// GET  /api/refresh        -> the last status the release PC wrote (queued / running / done / failed)
// The page never runs anything itself: the PC polls Cloudflare (outbound only), runs the 07:00 pipeline, deploys again.
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

export async function onRequestGet({ env }) {
  if (!env.RD_CTL) return J({ enabled: false });
  const [req, st] = await Promise.all([env.RD_CTL.get("request", "json"), env.RD_CTL.get("status", "json")]);
  return J({ enabled: true, queued: !!req, request: req, status: st });
}

export async function onRequestPost({ request, env }) {
  if (!env.RD_CTL) return J({ enabled: false }, 503);
  if (request.headers.get("X-Release-Desk") !== "refresh") return J({ error: "forbidden" }, 403);
  const o = request.headers.get("Origin");
  if (o && new URL(o).host !== new URL(request.url).host) return J({ error: "forbidden" }, 403);
  const st = await env.RD_CTL.get("status", "json");
  if (st && st.state === "running") return J({ queued: false, status: st }, 409);
  // review S7: one run per COOLDOWN_MIN after the last one ended (each run costs ~2k GitHub calls and D1 writes)
  const COOLDOWN_MIN = 15;
  const ago = st && st.at ? (Date.now() - Date.parse(st.at)) / 60000 : Infinity;
  if (st && (st.state === "done" || st.state === "failed") && ago < COOLDOWN_MIN)
    return J({ queued: false, status: st, retry_after_min: Math.ceil(COOLDOWN_MIN - ago) }, 429);
  const req = await env.RD_CTL.get("request", "json");
  if (req) return J({ queued: true, request: req, status: st }, 202);
  const r = { at: new Date().toISOString() };
  await env.RD_CTL.put("request", JSON.stringify(r), { expirationTtl: 3600 });   // an hour without the PC = dropped
  return J({ queued: true, request: r, status: st }, 202);
}
