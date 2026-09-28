# RoadWatch

Citizens report damaged roads, bridges and flyovers with an in-app photo. The platform
verifies each report, merges duplicates into one ticket, routes it to the right ward,
municipality, district, state or road authority, escalates it when deadlines pass, and
publishes a public dashboard of what the government has fixed.

**Reporters are verified but anonymous:** the platform knows each reporter is a real,
unique citizen; the government never learns who they are.

Full product brief: [`docs/brief.md`](docs/brief.md). Build status: **Phase 0 (foundation)**.

## Repository layout

| Path | What |
|---|---|
| `backend/` | Python / FastAPI API, database models, migrations, seed script, tests |
| `web/` | Public + government dashboards (Phase 3) |
| `mobile/` | Citizen app (Phase 4) |
| `infra/` | Deployment notes / manifests |
| `docs/` | Product brief and design notes |
| `docker-compose.yml` | Local stack |

## Quick start

Requires Docker with Compose v2.24 or newer.

```bash
cp .env.example .env               # optional; defaults work in dev
docker compose up -d --build       # core DB, vault DB, Redis, MinIO, Mailpit, API
docker compose exec api python -m app.seed    # load SAMPLE Kolkata data
```

Then open:

| URL | What |
|---|---|
| http://localhost:8000/health | Both databases reachable? |
| http://localhost:8000/docs | Interactive API docs |
| http://localhost:8000/api/v1/public/jurisdictions | Drill-down (add `?parent_id=1`) |
| http://localhost:9001 | MinIO console (`roadwatch` / `roadwatch_dev_pw`) |
| http://localhost:8025 | Mailpit (all outgoing email lands here) |

Re-seed from scratch: `docker compose exec api python -m app.seed --reset`.

Demo officials (password `roadwatch-demo`, dev only): `state@`, `district.kolkata@`,
`kmc@`, `kmc.ward001@`, `kmc.ward002@`, `hmc@`, `nhai@`, `pwd@`, `admin@` — all
`@demo.roadwatch.in`. Login arrives in Phase 2.

### Running tests

```bash
docker compose exec api pytest
# or locally:
cd backend && pip install -e ".[dev]" && pytest
```

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

## Free services used

| Need | Dev | When hosted |
|---|---|---|
| Vision model | offline `stub` | Gemini API free tier (`VISION_PROVIDER=gemini`) |
| Photo storage | MinIO | Cloudflare R2 free tier |
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

0. **Foundation** ← current: repo layout, docker-compose, migrations, seed, README.
1. Reporting & verification: OTP stub, vault, uploads, photo sanitization, verification pipeline, clustering.
2. Government workflow: official auth, scoped access, ticket lifecycle, SLA escalation, fix proof, notifications.
3. Web dashboards (public + government).
4. Citizen mobile app.
5. Hardening: rate limits, bans, attestation, access-control tests, load tests.
