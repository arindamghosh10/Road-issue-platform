# RoadWatch

Citizens report damaged roads, bridges and flyovers with an in-app photo. The platform
verifies each report, merges duplicates into one ticket, routes it to the right ward,
municipality, district, state or road authority, escalates it when deadlines pass, and
publishes a public dashboard of what the government has fixed.

**Reporters are verified but anonymous:** the platform knows each reporter is a real,
unique citizen; the government never learns who they are.

Full product brief: [`docs/brief.md`](docs/brief.md). Build status: **all five phases
done** — backend, dashboards, citizen app and hardening. What's still stubbed or needs a
decision is listed under "Before a pilot" at the end.

## Repository layout

| Path | What |
|---|---|
| `backend/` | Python / FastAPI API, database models, migrations, seed script, tests |
| `web/` | Next.js public + government dashboards (see `web/README.md`) |
| `mobile/` | Expo / React Native citizen app (see `mobile/README.md`) |
| `infra/` | Deployment notes / manifests |
| `docs/` | Product brief and design notes |
| `docker-compose.yml` | Local stack |

## Quick start

Requires Docker with Compose v2.24 or newer.

```bash
cp .env.example .env               # optional; defaults work in dev
docker compose up -d --build       # DBs, Redis, MinIO, Mailpit, API, worker, scheduler, web
docker compose exec api python -m app.seed         # load SAMPLE Kolkata data
docker compose exec api python -m app.seed.demo    # optional: ~80 DEMO tickets for the dashboards
```

Then open **http://localhost:3000** for the dashboards (government sign-in: see the
demo officials below).

If you ran Phase 0 before, recreate the database volumes once so the test databases
get created: `docker compose down -v && docker compose up -d --build` (this wipes local data).

Then open:

| URL | What |
|---|---|
| http://localhost:3000 | Public dashboard; `/gov` for the government dashboard |
| http://localhost:8000/health | Both databases reachable? |
| http://localhost:8000/docs | Interactive API docs |
| http://localhost:8000/api/v1/public/jurisdictions | Drill-down (add `?parent_id=1`) |
| http://localhost:9001 | MinIO console (`roadwatch` / `roadwatch_dev_pw`) |
| http://localhost:8025 | Mailpit (all outgoing email lands here) |

Re-seed from scratch: `docker compose exec api python -m app.seed --reset`.

Demo officials (password `roadwatch-demo`, dev only), all `@demo.roadwatch.in`:

| Login | Sees |
|---|---|
| `state@` | all of West Bengal |
| `district.kolkata@` | Kolkata district |
| `kmc@` | all 144 KMC wards (also KMC roads authority) |
| `kmc.ward001@`, `kmc.ward002@` | only their own ward |
| `hmc@` | Howrah Municipal Corporation |
| `nhai@`, `pwd@` | whole state (node) + roads their authority owns |
| `admin@` | tenant admin, whole state |
| `platform@` | RoadWatch operator (not government): moderation + audit log only |

### Try the citizen flow (what the mobile app will do)

The easiest way is the interactive docs at http://localhost:8000/docs.

1. `POST /api/v1/citizen/auth/otp/request` with `{"phone": "9876543210"}`.
2. Read the code from the API log: `docker compose logs api | grep "OTP STUB"`.
3. `POST /api/v1/citizen/auth/otp/verify` with the `challenge_id` and code → a token.
   Click **Authorize** in the docs page and paste the token.
4. `POST /api/v1/citizen/reports` with a photo, `category=pothole`, a location inside
   Kolkata (e.g. `lat=22.5431`, `lon=88.3552`), `gps_accuracy_m=8`, `captured_at` = now
   in ISO format with timezone (e.g. `2026-09-28T10:00:00Z`) and
   `capture_source=in_app_camera`. It returns `under_verification`.
5. A few seconds later `GET /api/v1/citizen/reports/{id}` shows `verified` (with the
   ticket reference) or `rejected` with the reason and each check's result.
6. `GET /api/v1/public/tickets` shows what everyone sees: aggregates and cleaned photos,
   no identity.

### Try the government flow

1. `POST /api/v1/gov/auth/login` with `{"email": "kmc@demo.roadwatch.in", "password":
   "roadwatch-demo"}` → token; click **Authorize** in the docs page.
2. `GET /api/v1/gov/tickets` — the work queue for your area, most urgent first.
3. `POST /api/v1/gov/tickets/{ref}/status` with `{"status": "acknowledged"}`, then
   `in_progress`. Add notes (`/notes`, `public: true` shows them on the public timeline)
   and assign (`/assignees`, `/assign`).
4. `POST /api/v1/gov/tickets/{ref}/fix-proof` with an after-photo taken within 50 m of
   the ticket. Accepted → `fix_submitted`, and each original reporter is asked
   "Is this fixed?" (`GET /api/v1/citizen/confirmations`,
   `POST /api/v1/citizen/tickets/{ref}/confirm` with `yes` / `no` / `partly`).
5. Emails to officials land in Mailpit: http://localhost:8025.
6. Optional 2FA: `POST /api/v1/gov/auth/2fa/setup`, put the `otpauth_uri` in an
   authenticator app, then `POST /api/v1/gov/auth/2fa/enable` with a code.

To see escalation without waiting days, push a ticket's deadline into the past:
`docker compose exec core-db psql -U roadwatch_core -c "UPDATE tickets SET sla_due_at = now() - interval '1 hour'"`.
Within 5 minutes the scheduler moves it one level up and alerts that level.

### Running tests

```bash
docker compose exec api pytest
```

Tests use the separate `roadwatch_core_test` / `roadwatch_vault_test` databases (created
automatically on first start), so they never touch your dev data. Without those
databases configured, only the unit tests run and the database tests are skipped.

## Architecture: two databases on purpose

```
            ┌────────────────────┐          ┌──────────────────────────┐
 citizen ──▶│ auth service       │─────────▶│ vault-db  (identity)     │
            │ (Phase 1)          │          │ encrypted phone, HMACs,  │
            └─────────┬──────────┘          │ identity ↔ reporter_id   │
                      │ opaque reporter_id  └──────────────────────────┘
                      ▼
            ┌────────────────────┐          ┌──────────────────────────┐
 gov / ────▶│ API                │─────────▶│ core-db  (PostGIS)       │
 public     └────────────────────┘          │ tickets, reports,        │
                                            │ jurisdictions — no PII   │
                                            └──────────────────────────┘
```

- **core-db** holds tickets, reports and the jurisdiction tree. Citizens appear only as
  random IDs like `R-8f3a…`. A full dump of this database cannot identify anyone.
- **vault-db** is a separate Postgres server with its own credentials. It holds the
  phone number (encrypted), keyed hashes for uniqueness and bans, and the only link
  between a person and their `reporter_id`.
- The Aadhaar number is **never stored**. When Aadhaar/DigiLocker is plugged in, only a
  keyed hash is kept, to enforce "one person, one account" and make bans stick.
- `backend/tests/test_anonymity_schema.py` fails if personal-data columns appear in the
  core schema or if the two databases get linked by a foreign key.

### Key custody

`VAULT_ENCRYPTION_KEY` (encrypts phone numbers) and `IDENTITY_HASH_PEPPER` (keys the
identity hashes) are **held by the platform operator only, never by government
tenants**, even when a tenant hosts other parts of the system. Whoever holds these keys
and the vault database can re-identify reporters, so:

- Store them in a secrets manager, not in the repo or in tenant-controlled infrastructure.
- Do not give government tenants credentials for `vault-db`.
- Write "no reporter identity disclosure" into tenant contracts.

In dev, empty values fall back to deterministic dev-only keys (with a warning). With
`APP_ENV=prod` the app refuses to start without real keys.

## How a report is verified (Phase 1)

```
upload ─▶ original photo → private bucket, report = under_verification
            │  (queued to the worker via Redis)
            ▼
worker ─▶ sanitize: strip EXIF, blur faces & number plates, perceptual hash
       ─▶ checks (each gives a score 0–1 and a reason):
            capture_integrity  in-app camera only, fresh (<24 h), GPS accurate
            location           inside a known ward; near a mapped road
            vision             stub or Gemini: is this the claimed damage? severity 1–5
            duplicate_image    same photo not submitted before
       ─▶ any hard failure → rejected with reason
          weighted score ≥ 0.6 → verified
       ─▶ verified: publish cleaned photo, merge into a ticket within 30 m
          (150 m for bridges) or open a new one, routed to
          ward → municipality → district → state + road authority, with an SLA deadline
```

Code map: `app/imaging` (sanitize), `app/verification` (checks + scoring),
`app/vision` (stub + Gemini), `app/tickets` (routing, clustering, priority),
`app/identity` (OTP + vault; the only code that touches the vault), `app/api`.

Known limits: the OpenCV face/plate detectors are basic and miss some angles and
Indian plate styles; the stub vision verifier cannot really see damage (use Gemini for
real checks); device attestation is a stub until the mobile app exists.

## Government workflow (Phase 2)

- **Who sees what:** an official attached to node N sees every ticket whose
  jurisdiction path contains N (N and everything below it), plus — for road authorities
  like NHAI — every ticket on roads they own. Tickets outside that scope return 404.
  Enforced as a SQL condition in `app/gov/access.py`.
- **Lifecycle:** `open → acknowledged → in_progress → fix_submitted → resolved`, or
  `reopened` if reporters dispute the fix. Officials can only move a ticket as far as
  `in_progress` by hand; `fix_submitted` needs an accepted fix proof and `resolved`
  needs the close rule. Every action is recorded in the audit trail.
- **SLA and escalation:** deadlines per category and severity (tenant-configurable).
  The scheduler (`scheduler` service, every 5 min) warns at 80% of the time, and on a
  breach moves responsibility one level up (ward → municipality → district → state),
  restarts the clock there, alerts that level and records the breach publicly.
- **Closing:** a fix proof is refused if taken more than 50 m away, more than 24 h ago,
  or if the vision model says the damage is still there. Once accepted, reporters are
  asked "Is this fixed?". Resolved when "yes" reaches 50% of reporters; reopened and
  escalated when "no"/"partly" pass 50%. After 7 days it's decided on the answers
  received; with no answers it resolves only if the vision check passed.
  The government sees only counts ("2 of 3 confirmed"), never who answered.
- **Notifications:** in-app inbox for everyone, email for officials, push for
  citizens (see "Push notifications" below). Officials hear about new tickets, deadlines, escalations, assignments;
  citizens hear about verification, fix confirmation requests and outcomes.

Code map: `app/gov/access.py`, `app/tickets/lifecycle.py`, `app/tickets/sla.py`,
`app/tickets/resolution.py`, `app/notifications/`, `app/api/gov.py`, `app/api/views.py`.

## Dashboards (Phase 3)

Public numbers come from `/api/v1/public/stats/*`, government numbers from
`/api/v1/gov/stats/*`, which apply the same area scoping as the work queue, so an
official's figures only count tickets they can see. Definitions:

- **Open**: not yet resolved (includes in progress and fix awaiting confirmation).
- **Average time to fix**: creation to resolution, resolved tickets only.
- **Fixed within deadline**: of tickets whose deadline was "tested" (resolved, or the
  deadline passed), the share that never missed a deadline.

`python -m app.seed.demo` fills the dashboards with ~80 DEMO tickets spread over 12
weeks (fake phones 90000xxxxx, synthetic photos, real verification pipeline). Dev only.

Running without Docker: set `STORAGE_BACKEND=local` and
`S3_PUBLIC_BASE_URL=http://localhost:8000/media`; the API then serves the sanitized
photo folder (never the originals).

## Citizen app (Phase 4)

`mobile/` is an Expo (React Native) app; try it on a phone with the free Expo Go app
(steps in `mobile/README.md`). New backend pieces for it:

- `GET /api/v1/citizen/tickets/nearby` — issues around the citizen, nearest first, with
  "you reported this" / "you confirmed this" flags.
- `POST /api/v1/citizen/tickets/{ref}/seen` — **"I see this too"**: allowed only within
  150 m of the issue with decent GPS, once per citizen, not for your own reports. It is
  shown as "also seen by N" and adds a little to priority, but does **not** count as a
  verified report (no photo).

**Push notifications (decided: tokens in the identity vault).** A push token identifies
a physical phone, so it is treated like the phone number:

- The app sends its Expo push token to `PUT /api/v1/citizen/push-token` after sign-in.
  It is stored **only in the vault** (`push_tokens`), Fernet-encrypted, with an HMAC
  lookup hash, linked to the identity — never to reports, and nothing about it is in the
  core DB. Government and admin APIs cannot reach it.
- **Pushes carry no details.** Every push says only "You have an update on your
  reports"; the specifics are in the in-app Inbox, fetched over our signed-in API.
  Pushes pass through Expo, Google (FCM) and Apple (APNs), who can tie a device to an
  account; a ticket number in the text would tell them which issue this person reported.
- Pushes go out **after** the change commits (dropped on rollback), from the worker,
  one per person per change. Tokens Expo reports as dead (app uninstalled) are deleted;
  sign-out removes the device; a ban forgets all of a person's devices; at most 5
  devices per person.
- `PUSH_BACKEND=log` (default) records pushes instead of sending; `PUSH_BACKEND=expo`
  sends through Expo's free push service. On the phone this needs a development/store
  build (not Expo Go) and an EAS project id; see `mobile/README.md`.

Code map: `app/identity/push.py`, `app/notifications/service.py`, `mobile/src/lib/push.ts`.

## Hardening (Phase 5)

- **Rate limits** (`app/security/ratelimit.py`, Redis-backed, shared by all API
  processes): official logins per IP and per account, OTP requests and code guesses per
  IP (plus the existing per-phone limit), reports, "I see this too", fix answers, CSV
  exports and repair photos. Over the limit → HTTP 429 with `Retry-After`, and an audit
  entry. Keys are hashed; if Redis is down the limiter fails open rather than taking the
  service down.
- **Abuse bans without de-anonymizing** (`/api/v1/admin`, platform operator only): the
  admin works from a *report* and sees only the sender's anonymous track record
  ("14 reports, 11 rejected"). "Ban sender" marks the identity banned inside the vault,
  so the same phone number can't sign back in, kills their existing tokens, and
  optionally withdraws their reports and recounts the affected tickets. Nobody, the
  admin included, sees a phone number or reporter id. Bans can be lifted.
- **Device attestation hook** (`app/security/attestation.py`): the interface and
  configuration for Play Integrity / App Attest. A forged token rejects the report;
  `REQUIRE_ATTESTATION=true` rejects uploads that weren't checked. The provider itself
  isn't implemented yet (it needs Google/Apple credentials); the file explains the steps.
- **Security audit log** (`audit_log` table, `GET /api/v1/admin/audit`): official
  logins (success and failure), 2FA enabled, CSV exports, bans, rate-limit hits, citizen
  sign-ins. IPs are stored only as keyed hashes and **never** for citizen actions; in
  the admin view citizen ids are replaced by pseudonyms.
- **Route-wide tests** (`tests/test_phase5_hardening.py`) read the app's own OpenAPI
  route list, so every future endpoint is covered automatically:
  - every government, admin and citizen route refuses callers who aren't signed in, and
    citizen tokens can't use government or admin routes;
  - every GET endpoint of the government, public and admin APIs is called with real data
    present, and the raw responses are scanned for reporter ids, phone digits and
    identity field names.

  To prove this works, a deliberately leaky endpoint was added: the test flagged it
  without any new test code.
- **Concurrency**: eight reports of the same pothole processed at the same instant
  produce exactly one ticket with eight reporters (advisory lock in clustering).
- **Load test** at 100,000 tickets (`scripts/loadtest.py`, results in
  [`docs/load-test.md`](docs/load-test.md)). It found four slow spots, all fixed:
  clustering ignored the spatial index (100 → 6 ms), dashboards looked up breach history
  ticket by ticket (summaries ~5× faster via an `sla_breached` flag), area scoping
  couldn't use its index (now `@>`), and leaderboards tested every area against every
  ticket (572 → 85 ms). Every dashboard query is now under 100 ms at that size.

## Languages: English, Hindi, Bengali

Every screen of the citizen app and both dashboards is available in English, हिन्दी and
বাংলা.

- **Choosing:** the app follows the phone's language and has a picker on the sign-in
  screen and under My reports. The dashboards follow the browser's language and have a
  menu in the header. The choice is remembered (on the phone; in a cookie on the web),
  and the dashboard server renders the right language from the first page load.
- **Server text is sent as codes.** Verification results, rejection reasons,
  notifications and escalation reasons carry a stable code plus values (for example
  `capture.too_old` with `{"hours": 24}`), and the apps turn them into sentences. The
  English text is still sent, as a fallback for older reports and future codes.
  Category, status and area-level names are translated by code as well; place names
  (wards, municipalities) and officials' own notes stay as written.
- **Pushes** use the app's language too: the app sends it with its push token (stored
  in the vault next to the token), and the generic "you have an update" text goes out
  in Hindi, Bengali or English.
- **Digits** stay Latin (0–9) in every language, so ticket numbers, dates and chart
  axes read the same everywhere; month names are translated.
- **Checks:** TypeScript refuses to build if a Hindi or Bengali string is missing, and
  `npm test` (in `web/` and `mobile/`) fails if a translation drops a `{placeholder}`
  or is still in English.
- **Adding a language:** copy `messages/en.ts`, translate it, and add the code to
  `LOCALES` in `lib/i18n.ts` (web) and `src/lib/i18n.ts` (app), plus `BODIES` in
  `backend/app/identity/push.py`.

The translations are careful drafts, not yet reviewed by native speakers; see
"Before a pilot".

## Free services used

| Need | Dev | When hosted |
|---|---|---|
| Vision model | offline `stub` | Gemini API free tier (`VISION_PROVIDER=gemini`) |
| Photo storage | MinIO (or `STORAGE_BACKEND=local` folder) | Cloudflare R2 free tier |
| Email | Mailpit | Brevo free tier |
| OTP | stub (code in server log) | Deferred to pilot |
| Maps / roads | OpenStreetMap | OpenStreetMap / OpenFreeMap |
| Street-level baseline | off | optional Mapillary |

Only sanitized photos (EXIF stripped, faces and number plates blurred) are ever sent to
Gemini, because Google may use free-tier data to improve its products.

## Sample data

All jurisdictions, road segments and authorities created by the seed are **sample
data** (`is_sample = true`, LGD codes prefixed `SAMPLE-`). The 144 KMC wards are a
generated grid, not real ward boundaries. Replace them with real LGD codes and
boundaries (e.g. from DataMeet) before any pilot.

## Build phases

0. **Foundation** ✓ repo layout, docker-compose, migrations, seed, README.
1. **Reporting & verification** ✓ OTP stub, vault, uploads, photo sanitization, verification pipeline, clustering.
2. **Government workflow** ✓ official auth + 2FA, scoped access, ticket lifecycle, SLA escalation, fix proof, reporter confirmation, notifications, CSV export.
3. **Web dashboards** ✓ public dashboard (figures, map, trends, leaderboards, drill-down, ticket pages) and government dashboard (scoped queue, map, drill-down, ageing, actions, CSV export).
4. **Citizen mobile app** ✓ OTP sign-in, camera-only reporting with GPS, live verification status, my reports, nearby map with "I see this too", inbox with fix confirmation.
5. **Hardening** ✓ rate limits, abuse bans without de-anonymizing, attestation hook, security audit log, route-wide access and anonymity tests, concurrency test, load test with fixes.

## Before a pilot

Stubbed or needing your decision:

- **Push notifications**: built (tokens in the vault, generic text). To switch on:
  create an EAS project (`extra.eas.projectId` in `mobile/app.json`), upload FCM / APNs
  credentials with `eas credentials`, ship a development or store build, and set
  `PUSH_BACKEND=expo` on the worker.
- **Device attestation**: implement Play Integrity / App Attest behind
  `app/security/attestation.py` (needs Google/Apple credentials), then turn on
  `REQUIRE_ATTESTATION`.
- **SMS OTP** (needs a paid SMS gateway) and **Aadhaar/DigiLocker** (needs UIDAI-licensed
  access). Both are behind interfaces.
- **Real boundaries and roads**: replace the SAMPLE wards with real LGD codes and ward
  maps, and import the OSM road network (then turn on `REQUIRE_ROAD_SNAP`).
- **Gemini key** for real photo checks (`VISION_PROVIDER=gemini`).
- **Native-speaker review** of the Hindi and Bengali text (drafts are in
  `web/lib/messages/` and `mobile/src/lib/messages/`), ideally by staff of the pilot
  municipality, who know the official terms they use.
- **Hosting**: set real secrets (`VAULT_ENCRYPTION_KEY`, `IDENTITY_HASH_PEPPER`,
  `JWT_SECRET`), `APP_ENV=prod`, `TRUST_PROXY=true` behind a proxy, and keep the vault
  keys with the platform, not government tenants.
