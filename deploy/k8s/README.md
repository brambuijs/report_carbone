# carbone-ee on Kubernetes - example deploy

Minimal, cluster-agnostic manifests for a self-hosted **carbone-ee** server that
`report_carbone` can render against. This is a sanitized version of how BB Open
Solutions runs it in production; adapt storageClass, ingressClass, host and TLS
to your own cluster.

## What's here

| File | Purpose |
|---|---|
| `deployment.yaml` | carbone-ee + an nginx CORP-proxy sidecar (non-root) |
| `service.yaml` | ClusterIP `4000` -> sidecar -> carbone |
| `pvc.yaml` | RWO PVC for SQLite DB + template files (stateful) |
| `corp-proxy-configmap.yaml` | nginx config that rewrites the CORP header |
| `ingress.yaml` | public HTTPS entrypoint (placeholder host) |
| `kustomization.yaml` | `kubectl apply -k deploy/k8s/` |

## Prerequisite: stable keypair Secret

carbone-ee signs/verifies render-tokens with an ES512 (P-521) keypair. If you let
it generate one on each start, every restart invalidates previously issued
render-tokens. Generate once and mount it as a Secret:

```sh
openssl ecparam -genkey -name secp521r1 -noout -out key.pem
openssl ec -in key.pem -pubout -out key.pub
kubectl -n <namespace> create secret generic carbone-keys \
  --from-file=key.pem=key.pem --from-file=key.pub=key.pub
```

## Deploy

```sh
# set namespace + edit pvc.yaml (storageClass) and ingress.yaml (host/class/TLS) first
kubectl apply -k deploy/k8s/ -n <namespace>
```

## Gotchas (the ones that cost us time)

- **`enableServiceLinks: false` is required.** With a Service named `carbone`, k8s
  injects `CARBONE_PORT=tcp://<ip>:4000`, which carbone-ee reads as its listen
  port and crashes (NaN). Already set in `deployment.yaml`.
- **No `CARBONE_EE_STUDIOUSER`.** Basic-auth on the studio breaks the embedded
  studio in Odoo: a cross-origin `<script>` load of the studio JS gets `401`.
  The render API stays protected by `CARBONE_EE_AUTHENTICATION=true` (Bearer).
- **CORP-proxy sidecar is mandatory for the embedded studio.** carbone-ee sets
  `Cross-Origin-Resource-Policy: same-origin`; the sidecar rewrites it to
  `cross-origin` so Odoo can load the studio assets.
- **Stateful mode.** `CARBONE_DATABASE_NAME` enables the `/templates` endpoint and
  studio versioning that `report_carbone` depends on.
- **The ingress host must be browser-reachable public HTTPS** - it's used both as
  the browser studio origin and the server-side render endpoint.

## report_carbone module config (after the server is up)

1. `post_install` `API_REPORT_URL` -> your carbone-ee endpoint (the ingress host).
2. `carbone_studio_url` -> same public HTTPS endpoint (browser-reachable).
3. `report-engine.stage_api_key` populated, else the controller returns
   `{"token": false}` and the studio never connects.

Server-side render (button / cron) works as soon as steps 1 + 3 are set; the
embedded Studio editor additionally needs the CORP-proxy + step 2.
