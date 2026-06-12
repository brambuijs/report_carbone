# report_carbone — on-premise patches (BB Open Solutions)

This repository contains our patched version of the **`report_carbone`** Odoo
module (Mangono, AGPL-3, v19.0.1.0.9) together with the changes we needed to run
it against a **self-hosted `carbone-ee`** server (Carbone Enterprise on-prem,
v5.8.0) instead of the Carbone cloud.

We're sharing this with the Carbone / Mangono developers: every change below
fixes a real incompatibility we hit when pointing the module at an on-prem
`carbone-ee` instance with `CARBONE_EE_AUTHENTICATION=true`. We'd love to see
these (or equivalent) fixes upstream.

- `report_carbone/` — the full patched module.
- `onprem-patches.diff` — unified diff vs. pristine 19.0.1.0.9 (4 files, ~41 lines).
- `patches/000N-*.patch` — the same changes as a `git am`-able series (one per fix).

## Environment

- Odoo 19.0
- `report_carbone` 19.0.1.0.9 (Odoo Apps Store)
- `carbone-ee` v5.8.0, **stateful** (`CARBONE_DATABASE_NAME` set), behind an
  HTTPS ingress, `CARBONE_EE_AUTHENTICATION=true` (ES512 JWT render-token).
- Carbone Studio embedded in Odoo via the module's `initiate_studio.js`, loading
  the studio JS from the public CDN (`bin.carbone.io/studio/5.1.1`) and pointing
  its `origin` at the on-prem server.

## The fixes

### 1. Render against the on-prem server, not the cloud — `models/base/ir_actions_report.py`
`get_carbone_sdk()` created `carbone_sdk.CarboneSDK(token)` but never set the API
URL, so the SDK used its built-in default `https://api.carbone.io`. Our on-prem
render-token has `aud = <our server>`, so the cloud rejected every render with
**`Invalid JSON Web Token audience`**. Fix: call `csdk.set_api_url(...)` from the
configured `carbone_studio_url` when present.

### 2. Tolerate a stateless / non-200 `/templates` response — `models/base/ir_actions_report.py`
`get_extension_file_from_api()` does `res.get("data")` on the `/templates`
response. On our server some responses come back as an error **string** (e.g.
code `w130`) rather than a dict, raising `'str' object has no attribute 'get'`
when setting a template id. Fix: guard `if not isinstance(res, dict): return ".docx"`.

### 3. Studio close: v5.1.1 has no `closeTemplate()` — `static/src/js/report/initiate_studio.js`
`safeCloseTemplate()` calls `studio.closeTemplate()`, but the Carbone Studio
build we load (5.1.1) exposes `close()` / `destroy()` and **not** `closeTemplate`.
The `TypeError` fired on every re-render and tore the embedded studio down. Fix:
feature-detect — `closeTemplate` → `close` → `destroy`.

### 4. Studio flicker: skip re-entrant refresh during template load — `static/src/js/report/initiate_studio.js`
`onWillLoadRoot` can fire again while `safeOpenTemplate()` is still in its ~2s
async `openTemplate` window. The second `refreshStudio()` re-evaluated
`getIsCarboneReport()` (transiently false) and hid the just-mounted studio
("appears then disappears"). Fix: skip a re-entrant `refreshStudio` while
`isTemplateLoading` is set, and reset that flag on the early `launchCarbone`
return so it can't dead-lock the guard.

### 5. `post_install` default points at the on-prem server — `post_install.py`
`API_REPORT_URL` defaulted to `https://api.carbone.io`, so a (re)install reset
`carbone_studio_url` back to the cloud and broke both the embedded studio and
server-side render. **Deployment-specific:** replace the URL with your own
`carbone-ee` endpoint. The studio JS URL already defaults to the public CDN,
which is correct for on-prem too (self-contained, no auth / CORP issues).

### 6. App menu had no icon — `views/carbone/report_carbone_menu.xml`
The `Document Generation` root `menuitem` set no `web_icon`, so the app showed a
blank/non-loading icon in the Odoo apps menu. Fix: point it at the bundled
`static/description/icon.png`.

## Notes for on-prem deployment (not code, but relevant)

- The embedded studio loads its JS from the **public CDN** and only talks to the
  on-prem server for data/render (XHR + Bearer token) — serving the studio JS
  from the auth-protected on-prem server fails, because a cross-origin
  `<script>` load can't send the Bearer/basic-auth and gets `401`.
- The studio token comes from `retrieve_carbone_api_key(test_mode_key=True)`,
  i.e. the **stage** key — make sure `report-engine.stage_api_key` is populated,
  otherwise the controller returns `{"token": false}` and the studio never
  connects.
- `carbone_studio_url` is used both as the browser studio `origin` and the
  server-side render endpoint, so it must be **browser-reachable** (public
  HTTPS), not an internal cluster address.

---
Original module © Mangono, AGPL-3.0. These patches are shared under the same
license.
