# Engine Deployment Posture (INV-18 — privileged engine routes)

**Status:** ACCEPTED (network isolation). Owner decision 2026-06-10; **ratified 2026-06-11 — option A (network isolation) confirmed; option B (in-app cookie/session operator auth) declined as disproportionate for a single-operator panel.** This is a sign-off, not an open gap: INV-18's release criterion is met.
**Scope:** the engine execution-control API — `GET/POST /api/engine/runner` (toggle auto-exec,
manual-approval) and `/api/engine/queue` (approve / reject / cancel queued ops), served by
engine-web on **port 7000**, plus its browser panel at `/engine`.

## The problem

These routes drive real money movement (they arm auto-execution and approve queued arb/peg ops),
but they are **same-origin, browser-driven** — engine-web's own `/engine` page (`apps/web`,
`'use client'`) calls them with relative `fetch`, and there is no external/server caller. That
forecloses the easy fixes:

- A **static bearer token** would have to ship in the client JS bundle → readable by anyone who
  loads the page → forgeable. That is security theater against the actual threat ("anyone who can
  reach the port"), not a control. We refused to green-wash INV-18 with it.
- **Cookie/session operator login** is the real in-app fix, but it needs a login surface + browser
  QA and is disproportionate for a single-operator panel.

## The decision: the network is the auth boundary

The engine runs **operator-only**. It is never reachable from the public internet; only the
operator reaches it, over an authenticated/private path. With no unauthenticated party able to
reach engine-web at all, an in-bundle token is moot — isolation *is* the control.

Concretely, two supported topologies:

### A. Engine on a separate box (prod)
- Bind engine-web to a private interface (not a public `0.0.0.0`), or firewall port 7000.
- Reach it over **VPN / Tailscale / SSH tunnel** with an IP allowlist, **or** behind a reverse
  proxy that enforces auth (`auth_basic` / SSO) on the engine paths.
- Do **not** add a public, unauthenticated nginx `location` for `/engine` or `/api/engine`.

### B. Engine on the shared testnet host (current testnet-v2)
This is already isolated by the documented setup — **no extra work needed for the default path**:
- `docs/setup/testnet-v2.md` §"Server Setup Checklist" firewalls 7000 (`ufw ... never open 7000`).
- The documented nginx only proxies `/api/` → 7051 (bridge-api) and `/` → 7050 (bridge-web).
  **It does not proxy 7000**, so the engine panel/API is not publicly reachable.
- The operator reaches the panel via an **SSH tunnel**:
  ```bash
  ssh -L 7000:localhost:7000 user@testnet-host    # then browse http://localhost:7000/engine
  ```

### If you DO want browser access without a tunnel
Add an authenticated nginx location — **never** an open one:
```nginx
# Engine operator panel + control API — operator-only. REQUIRE auth; do not expose open.
location /engine     { auth_basic "engine"; auth_basic_user_file /etc/nginx/.htpasswd-engine;
                       proxy_pass http://127.0.0.1:7000; }
location /api/engine { auth_basic "engine"; auth_basic_user_file /etc/nginx/.htpasswd-engine;
                       proxy_pass http://127.0.0.1:7000; }
# create the htpasswd:  htpasswd -c /etc/nginx/.htpasswd-engine <operator>
# (or IP-allowlist instead of basic-auth:  allow <your.ip>; deny all;)
```
Prefer basic-auth over TLS, or an IP allowlist, or both. Either way the engine paths must be
gated at the proxy.

## Why this is AMBER, not GREEN

The invariant ("privileged routes require authentication") is satisfied at the **deployment**
layer, not by per-request code auth. The scenario tests
(`tests/scenario/security/test_privileged_routes.py::test_sec_engine_{runner,queue}_unauth`) run
**on the host against `localhost:7000`**, where the route is intentionally reachable (200) — that
is the accepted posture, so they are marked `@accepted_risk` (AMBER, non-fatal), not green. If a
future build adds in-app auth and the route starts returning 401, those tests flip — that is the
signal to promote INV-18 to HELD and drop the marker.

## Residual / revisit triggers
- If engine-web is ever exposed publicly (a new nginx `location` for 7000 without auth, or 7000
  opened in the firewall), this posture is **violated** — re-isolate or add `auth_basic`.
- The bridge-api `/debug/*` half of INV-18 is a real code control (ADMIN_TOKEN-gated,
  destructive GET removed) and remains HELD — see `FINDINGS.md` and `test_sec_debug_backup_requires_auth`.
