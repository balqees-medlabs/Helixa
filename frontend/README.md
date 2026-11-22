# Helixa Frontend (Spec 3)

Next.js 14 SPA for the Medlabs genomics workflow: auth/session with silent
refresh, role-bound navigation, the gated 8-stage sample workflow, role
dashboards, the shared TAT board, QC/batches/vendors, and reports with portal
delivery. Presentation only — every rule lives in the backend (constitution I.3).

## Requirements

- Node 20, `npm install`
- Backend reachable for anything beyond the mocked unit tests (see
  `../backend/README.md`); same-origin `/api` for the real thing

## Run (same-origin, like production)

```bash
npm run dev        # reverse proxy on :3000 + Next on :3001
```

Open <http://127.0.0.1:3000>. `npm run dev:next` runs Next alone (:3001) and
`npm run dev:proxy` runs only the proxy — useful when Next is already up.

The proxy (`dev-proxy/proxy.mjs`) mirrors the Caddy deployment: the SPA is
served at `/`, the backend is reverse-proxied under `/api` with the prefix
stripped, so cookies stay same-origin.

### Cookie-path note (research D1)

The backend's **access** cookie is `Path=/` and reaches `/api/*` as-is. The
**refresh** cookie is issued with `Path=/auth`, which would _not_ be sent to the
proxied `/api/auth/refresh`. Both the dev proxy and Caddy therefore rewrite
`Set-Cookie` path `/auth` → `/api/auth` on `/api/auth/*` responses. The backend
is untouched; if you front the API some other way, you must apply the same
rewrite or silent refresh will fail.

### Build & production

```bash
npm run build      # production build
npm run start      # serve the build on :3001 (put the proxy/Caddy in front)
```

## API contract (generated client)

Types are generated from `../backend/openapi.json`; do not hand-write API URLs
or call `fetch` outside `lib/api/client.ts` (enforced by ESLint).

```bash
npm run gen:client    # regenerate lib/api/schema.d.ts
npm run check:contract # fail if the committed client drifts from the contract
```

CI (`.github/workflows/frontend.yml`) runs `check:contract` first, then
typecheck/lint/format/tests/build; `tests/contract.test.ts` fails the unit suite
on drift too (SC-008). After any backend route/schema change: `npm run
gen:client` and commit the result.

## Tests

```bash
npm test             # Vitest + Testing Library + MSW against the mocked contract
npm run typecheck    # tsc --noEmit
npm run lint         # next lint (incl. the no-raw-fetch / no-handwritten-URL rules)
npm run format:check # Prettier
```

End-to-end (Playwright) runs the sign-in → register → advance-with-gate →
dashboard/board/upload journeys against a **live** backend + proxy:

```bash
npx playwright install chromium   # once
# backend + `npm run dev` (or the built app) must be running on :3000
npm run test:e2e
```

`e2e/global-setup.ts` provisions the admin and role users through the API and
seeds a QC-passed sample; accounts are `"{role}@e2e.helixa.test"` with
`E2E_PASSWORD` (default `e2e-password-123`).

## Configuration

| Variable             | Default                 | Purpose                                                              |
| -------------------- | ----------------------- | -------------------------------------------------------------------- |
| `PROXY_PORT`         | `3000`                  | dev reverse-proxy listen port                                        |
| `NEXT_URL`           | `http://127.0.0.1:3001` | where the proxy forwards the SPA                                     |
| `BACKEND_URL`        | `http://127.0.0.1:8000` | where the proxy forwards `/api`                                      |
| `NEXT_PUBLIC_LOCALE` | `en`                    | UI locale; RTL languages (`ar`, `fa`, `he`, `ur`) render `dir="rtl"` |
| `E2E_BASE_URL`       | `http://127.0.0.1:3000` | Playwright target                                                    |
| `E2E_PASSWORD`       | `e2e-password-123`      | password for seeded e2e accounts                                     |

## Accessibility & RTL

- Palette tokens in `styles/globals.css` are WCAG-AA verified by
  `tests/theme-contrast.test.ts` (text ≥ 4.5:1, focus ring ≥ 3:1).
- Layout uses logical utilities only (`ms/me/ps/pe/start/end`); physical
  direction classes are rejected by `tests/rtl.test.tsx`, which also renders
  the nav, TAT board, and sign-in form under `dir="rtl"`.
- Set `NEXT_PUBLIC_LOCALE=ar npm run dev:next` to preview the app in RTL.
