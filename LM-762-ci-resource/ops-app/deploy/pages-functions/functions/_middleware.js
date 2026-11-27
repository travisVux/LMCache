// Release Desk on Cloudflare Pages: one shared login in front of every file (Pages Functions, free plan).
// Runs before any static file is served, on the production name and on every deployment URL.
// Secrets (set by deploy/pages.py set-password, never in this file):
//   RD_PASS_SHA256  hex SHA-256 of the shared password      RD_USER  user name (default "release")
// Fail closed: without RD_PASS_SHA256 every request gets 503.
const enc = new TextEncoder();

function same(a, b) {               // constant-time compare of two strings
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function sha256hex(s) {
  const d = await crypto.subtle.digest("SHA-256", enc.encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function onRequest(ctx) {
  const want = (ctx.env.RD_PASS_SHA256 || "").toLowerCase();
  const user = ctx.env.RD_USER || "release";
  if (!/^[0-9a-f]{64}$/.test(want)) {
    return new Response("Release Desk is locked: no password configured.", {
      status: 503, headers: { "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" } });
  }
  const h = ctx.request.headers.get("Authorization") || "";
  if (h.startsWith("Basic ")) {
    let dec = "";
    try { dec = atob(h.slice(6).trim()); } catch (e) { dec = ""; }
    const i = dec.indexOf(":");
    if (i > 0) {
      const okUser = same(dec.slice(0, i), user);
      const okPass = same(await sha256hex(dec.slice(i + 1)), want);
      if (okUser && okPass) {
        const r = await ctx.next();
        const res = new Response(r.body, r);
        // never in a shared cache; data/<build>/*.json (backend/split_page.py) changes path with its content
        const p = new URL(ctx.request.url).pathname;
        const immutable = /^\/data\/[0-9a-f]{12}\/[A-Za-z0-9_-]+\.json$/.test(p) && r.status === 200;
        // review 5.10: an API answer keeps its own no-store; the rest is private and revalidated
        if (!(p.startsWith("/api/") && /no-store/.test(r.headers.get("Cache-Control") || "")))
          res.headers.set("Cache-Control", immutable ? "private, max-age=31536000, immutable" : "private, no-cache");
        return res;
      }
    }
  }
  return new Response("Sign in required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Release Desk", charset="UTF-8"',
               "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" } });
}
