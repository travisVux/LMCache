# Release Desk on the web: Cloudflare Access in front

Two ways, same sign-in rule (company e-mail domain + one-time PIN, no user list):

| | Cloudflare Pages + Access (**in use: no domain needed**) | Cloudflare Tunnel + Access (later, with a domain) |
|---|---|---|
| URL | `https://<project>.pages.dev` | `https://release-desk.<domain>` |
| Needs this PC on | no (static copy) | yes |
| Data | the published build, uploaded by `pages.py deploy` | live from 127.0.0.1:8765 |
| `/healthz` | no | yes |

## In use now: Cloudflare Pages + shared password (free, no payment card)

Zero Trust (Access) asks for a payment card even on the free plan, so the site currently uses a password gate in
Pages Functions instead: `pages-functions/functions/_middleware.js` runs before every file, on the production name and
on every deployment URL, and asks for user `release` + one shared password (only its SHA-256 is stored at Cloudflare,
secret `RD_PASS_SHA256`; no secret -> 503). The password is in `cloudflare-credentials.txt` (git-ignored).

```
python -X utf8 deploy\pages.py set-password   # new password (old one stops working on new deployments) - then deploy
python -X utf8 deploy\pages.py deploy         # stage + privacy scan + gate check + upload + check the new URL
```
Change the password when someone leaves, then deploy. Older deployment URLs keep the password they were made with:
delete them in the dashboard (Deployments) if needed. Moving to Access later: `cf_access.py apply`, nothing else changes.

## Cloudflare Pages + Access (needs Zero Trust)

Order matters: the project gets a placeholder first, Access goes on, and only then the real build is uploaded
(`pages.py deploy` refuses otherwise).

1. **Account + token.** Free Cloudflare account. My Profile > API Tokens > *Create token* > custom:
   permission `Account / Cloudflare Pages / Edit`, this account only. Copy the account id from the dashboard.
2. **Node.js** (wrangler runs on it): `winget install OpenJS.NodeJS.LTS`. Then in `deploy/ops-app.env`:
   ```
   OPS_PAGES_PROJECT=release-desk-<something-unguessable>
   CLOUDFLARE_API_TOKEN=<token>
   CLOUDFLARE_ACCOUNT_ID=<account id>
   ```
   and create the project with a placeholder (no data): `python -X utf8 deploy\pages.py init`
3. **Access** (Zero Trust, free plan; pick a team name when asked):
   - Workers & Pages > the project > Settings > *Enable access policy* (this protects the preview names
     `*.<project>.pages.dev`);
   - Zero Trust > Access > Applications > open the application it made > add the production name
     `<project>.pages.dev` to it, so both names are covered;
   - policy *Allow*, Include **Emails ending in** `@<company domain>`; Authentication: **One-time PIN**.
4. **Check, then upload:**
   ```
   python -X utf8 deploy\pages.py check            # both names must say OK
   python -X utf8 deploy\pages.py deploy --dry-run  # stage + privacy scan + check, no upload
   python -X utf8 deploy\pages.py deploy
   ```
5. **Every day:** set `OPS_PAGES_AUTO=1` in `ops-app.env` and the 07:00 refresh uploads each new build after it went
   live locally. A failed upload leaves the local site live and shows as `warn` in `logs/last-refresh.json`.

Safety nets: only `releases/CURRENT/site` is uploaded (never `ops.db`); privacy scan on the staged copy; nothing is
uploaded unless `<project>.pages.dev` and a random preview name both answer with an Access sign-in to a cookie-less
request; the new deployment URL is checked again after upload (`logs/pages-last.json`); `_headers` adds CSP,
`noindex` and frame / permissions headers; `robots.txt` disallows all.
Take it offline: Workers & Pages > the project > Settings > *Delete project*.

---

## Cloudflare Tunnel (own domain)

The site keeps running on this PC (`ops-app-server`, 127.0.0.1:8765, refreshed 07:00). `cloudflared` opens an
**outbound** connection to Cloudflare, so there is no router port-forward and no inbound firewall rule. Cloudflare
Access sits in front: nobody sees a byte of the page before signing in.

```
viewer ──https──> Cloudflare edge ──[Access: email ends @<company>?]──> tunnel ──> cloudflared (this PC) ──> 127.0.0.1:8765
```

Cost: Cloudflare Free plan + Zero Trust Free (up to 50 users). You need one domain on Cloudflare (Access cannot
protect a `trycloudflare.com` quick tunnel).

### No user management: one rule for the whole company

The Access policy allows **"Emails ending in @<company domain>"** and the login method is **One-time PIN** (Cloudflare
emails a code). Nobody has to be added or removed by hand; someone who leaves the company loses the mailbox and so the
access. Later you can swap One-time PIN for Google / Microsoft login, or add a list of people, without touching this PC.

### Steps (owner, once; about 20 minutes)

1. **Domain.** In the Cloudflare dashboard add the company domain (or a cheap separate one) and let Cloudflare run its DNS.
2. **Tunnel.** Zero Trust > Networks > Tunnels > *Create a tunnel* > *Cloudflared* > name `release-desk`.
   Copy the token shown in the install command (the long string after `--token`). Do **not** run the install command
   it shows (that installs a Windows service and needs admin); this repo runs it as a user task instead.
   *Public hostname*: `release-desk.<domain>` -> Service `HTTP` -> `127.0.0.1:8765`.
3. **Access application** (before the hostname is shared). Zero Trust > Access > Applications > *Add* > *Self-hosted*:
   - domain `release-desk.<domain>`; session duration 24 h (or 1 week);
   - policy *Allow*, Include **Emails ending in** `@<company domain>`;
   - Settings > Authentication: **One-time PIN** on.
4. **This PC.** In `deploy/ops-app.env` set
   ```
   OPS_TUNNEL_TOKEN=<token from step 2>
   OPS_TUNNEL_HOSTNAME=release-desk.<domain>
   ```
   then install cloudflared and restart the server so it reads the new hostname:
   ```powershell
   winget install --id Cloudflare.cloudflared
   Restart-ScheduledTask ops-app-server        # or: Stop-ScheduledTask / Start-ScheduledTask
   powershell -ExecutionPolicy Bypass -File deploy\run-tunnel.ps1            # try it in a window first
   powershell -ExecutionPolicy Bypass -File deploy\run-tunnel.ps1 -Install   # then as task ops-app-tunnel
   ```
5. **Check** from a phone on mobile data: `https://release-desk.<domain>/` must show the Cloudflare login first;
   after the PIN, the page; `/healthz` gives the short (non-local) answer.

### Safety nets in this repo

| What | Where |
|---|---|
| A tunnel request without the Access header gets **403** (Access app missing, disabled or mis-scoped: fail closed) | `backend/server.py` `_access_ok` |
| `run-tunnel.ps1` refuses to start if the running server would answer such a request | `deploy/run-tunnel.ps1` self-test |
| Host must be `OPS_TUNNEL_HOSTNAME` (or localhost), else 421 | `server.py` `ALLOWED_HOSTS` |
| CSP, HSTS, frame and permissions headers on tunnel responses (Caddy is not in front) | `server.py` `EDGE_HEADERS` |
| `/healthz` build details only to this PC, not through the tunnel | `server.py` `_direct` |
| Access log records the viewer IP from `Cf-Connecting-Ip` | `server.py` `log_message` |
| Token never on the command line; `ops-app.env` is git-ignored | `run-tunnel.ps1` |

The JWT is checked for presence, not signature: the origin listens on 127.0.0.1 only and the tunnel is outbound, so the
Cloudflare edge (where Access runs) is the only way in from outside.

### Limits

- The site is up only while this PC is on and you are logged on (user-level tasks). A box that stays on, or an admin
  running `install-services.ps1` (S4U), removes that.
- Everyone with a company mailbox can read it, including GitHub logins and CODEOWNERS names on the page. Before
  widening the policy beyond the company, run the privacy decision in `plan-2026-11/outputs/expert_review/SUMMARY.md`.
- Data is only as fresh as the 07:00 refresh (Buildkite needs `BUILDKITE_API_TOKEN`).

### Take it offline

`run-tunnel.ps1 -Uninstall` (or disable the Access app's hostname / delete the tunnel in the dashboard). The local site
on 127.0.0.1:8765 keeps working.
