# Project Brief: Civic Road & Bridge Issue Reporting Platform

> Working name: **RoadWatch** (placeholder — rename freely)
> Audience: Claude Code. Build this system in phases, as described in §13. Do not attempt everything in one pass.

---

## 0. Decisions made after the brief was written (these override the sections below)

| Topic | Decision |
|---|---|
| Cost | **Free services only** for now. Every external service stays behind an interface so a paid one can be swapped in later by config. |
| Language | **Python** (backend, workers, scripts). Web/mobile stack to be confirmed before Phase 3/4. |
| Vision model | **Google Gemini API free tier** for the demo (`VISION_PROVIDER=gemini`). A deterministic offline `stub` provider is the default so the stack runs with no keys. Only **sanitized** (EXIF-stripped, face/plate-blurred) images are ever sent to Gemini, because free-tier data may be used by Google to improve its products. |
| Face / plate blur | OpenCV (local, free). |
| Maps | MapLibre + OpenStreetMap / OpenFreeMap tiles. |
| Road network | OSM extracts from Geofabrik (ODbL, attribution required). |
| Street-level baseline | Google Street View **off**. Optional **Mapillary** (free) connector, only to confirm a road exists — never to judge damage or repairs. |
| Boundaries | LGD codes; DataMeet open boundaries where available, clearly-labelled sample polygons otherwise. |
| OTP | Stub (code printed to server log). Real SMS deferred to the pilot. |
| Email | Mailpit locally; Brevo free tier when hosted. |
| Push | Expo Push / FCM (free); stubbed until the app exists. |
| Object storage | MinIO locally; Cloudflare R2 free tier when hosted. |
| Hosting | docker-compose locally; Oracle Cloud Always Free (Indian region) later. |
| Anonymity limits | Small-area publication delay, legal wording, and court-order handling are tuned during production. Vault/ticket separation with separate keys is **built from day one**. |

---

## 1. Problem

Indian roads, bridges and flyovers deteriorate faster than they are repaired: potholes, leaking or cracked bridges, broken railings/dividers, missing signage, waterlogging. Citizens see these daily, but:

- They don't know which authority owns a road (ward/municipality, PWD, NHAI, state highways, cantonment).
- Complaints are scattered across helplines and social media and vanish without follow-up.
- Authorities receive duplicate, vague, unverifiable complaints with no precise location or severity.
- There is no public accountability for how fast (or whether) issues get fixed.

## 2. Solution summary

A government-facing SaaS platform plus a citizen mobile app:

1. Citizens report road/bridge issues with an **in-app photo** (GPS + timestamp captured at shot time).
2. The system **verifies** the report (vision model + location checks + corroboration from other reporters).
3. Reports of the same issue at the same spot are **merged into one ticket**.
4. Each ticket is **mapped to the full jurisdiction hierarchy** (ward → municipality → district → state) **and** to the road-owning authority.
5. Government officials at every level see and filter tickets under their responsibility.
6. Unresolved tickets **auto-escalate** up the hierarchy when SLAs are breached.
7. To close a ticket, the government uploads **proof of repair**, which is verified by the vision model **and** confirmed by the original reporters.
8. A **public dashboard** shows open/resolved counts, resolution times and performance by area and authority.

**Core principle: reporters are verified but anonymous.** The platform knows each reporter is a real, unique citizen; the government never learns who they are.

## 3. Users and roles

| Role | Description | Access |
|---|---|---|
| Citizen | Any verified resident | Report issues, upvote/confirm existing tickets, confirm/dispute fixes, view public dashboard |
| Gov Official | Tied to one jurisdiction node and level (ward, municipality, district, state) or to a road authority (e.g. NHAI regional office) | View/manage tickets in their node and all child nodes; assign, update status, upload fix proof |
| Gov Admin | Per-client admin | Manage officials, SLA rules, categories for their jurisdiction |
| Platform Admin | Us | Manage tenants, jurisdiction data, moderation, abuse bans |
| Public (unauthenticated) | Anyone | Read-only public dashboard and map |

Access control rule: an official at node N sees tickets whose jurisdiction path contains N (i.e. N and all descendants).

## 4. Anonymity & identity architecture (non-negotiable, build from day one)

- **Two separate data stores with separate encryption keys:**
  - `identity_vault` — phone number, verification status, hashed identity. Accessible only to the auth service.
  - `core_db` — tickets, reports, jurisdictions. Reporters appear only as random opaque IDs (e.g. `R-8f3a…`).
- The link between `reporter_id` and identity exists **only** inside the vault.
- **Never store the Aadhaar number.** After verification, store only a salted hash (for uniqueness/ban enforcement) and a `verified=true` flag.
- **MVP identity:** phone OTP. Build an `IdentityProvider` interface with a stub for Aadhaar/DigiLocker verification to plug in later (requires UIDAI-authorized route; do not implement real Aadhaar calls).
- **Government-facing APIs and UI must never expose** reporter IDs, phone numbers or any identity field. They see only aggregates like "12 verified citizens reported this" and "7 of 9 confirmed fixed".
- **Photo sanitization before any government/public view:**
  - Strip all EXIF (device model, serial, etc.). Keep original GPS/timestamp internally for verification only.
  - Auto-blur faces and vehicle number plates.
  - Show date or rounded time only, not exact timestamps.
- **Abuse handling without de-anonymizing:** ban by `reporter_id` + identity hash; the ban blocks re-registration.
- Keys for the vault must be held by the platform, never by government tenants. Document this in the README.

## 5. Core flows

### 5.1 Report an issue (citizen)
1. Open app → camera opens (**no gallery uploads**).
2. Capture photo; app records GPS, accuracy, timestamp, device attestation token.
3. Select category: `pothole`, `bridge_leak`, `bridge_crack`, `broken_railing`, `broken_divider`, `missing_signage`, `waterlogging`, `road_cave_in`, `other`. Optional short description.
4. Upload → backend runs verification pipeline (§6) asynchronously.
5. Citizen sees status: `under_verification` → `verified` (linked to a ticket) or `rejected` (with reason).

### 5.2 Verification & clustering → ticket
See §6 and §7. Output: either attach report to an existing ticket or create a new ticket.

### 5.3 Routing
Ticket gets `jurisdiction_path` (ward → municipality → district → state) and `road_authority`. Primary owner = road authority's responsible node if known, else the lowest jurisdiction node.

### 5.4 Government handling
Statuses: `open` → `acknowledged` → `in_progress` → `fix_submitted` → `resolved` | `reopened`. Officials can assign, add notes (visible to public in sanitized form), and submit fix proof.

### 5.5 Resolution
1. Official uploads fix proof via the official app/web (in-app camera, geotagged, must be within X metres of the ticket location).
2. Vision model compares before/after and checks the damage is no longer visible.
3. Platform notifies all original reporters: "Is this fixed? Yes / No / Partly" (through the platform, never via the government).
4. Close rule (configurable): vision check passes **and** ≥ 50% of responding reporters confirm (or no disputes within 7 days).
5. If disputed → `reopened` and escalated one level.

### 5.6 Escalation
SLA rules per category and severity (e.g. critical bridge issue: 48 h; pothole: 7 days). On breach, the ticket's escalation level moves up one node in the jurisdiction path, the new level gets an alert, and the breach is recorded publicly.

## 6. Verification pipeline

Build as a pluggable pipeline of checks, each returning a score and reason. A report is verified if the combined score passes a threshold.

1. **Capture integrity** — photo came from in-app camera, GPS accuracy acceptable, timestamp fresh, device attestation valid (Play Integrity / App Attest; stub in MVP).
2. **Location sanity** — coordinates snap to a road within N metres (use OpenStreetMap road network in PostGIS).
3. **Vision check** — model confirms the image shows the claimed damage category and returns a severity score (1–5). MVP: Gemini free tier behind a `VisionVerifier` interface (see §0); later swap in a fine-tuned detector (e.g. YOLO) or a paid model.
4. **Duplicate/fraud check** — perceptual hash to catch reused images across reports.
5. **Corroboration** — each additional independent reporter on the same cluster raises the ticket's confidence.
6. **Street-level baseline (optional, pluggable)** — only to confirm a road exists at the coordinates where coverage exists. Do not use it to judge current damage or repairs (imagery is not live). Mapillary connector behind a feature flag (see §0).

## 7. Clustering (duplicate merge)

A new verified report joins an existing open ticket if:
- distance ≤ 30 m (configurable, larger for bridges — match on the same bridge geometry if available), **and**
- same or compatible category, **and**
- (optional) image embedding similarity above threshold.

Use PostGIS `ST_DWithin` and/or H3 cell indexing. Report count and unique reporter count feed ticket priority:
`priority = f(severity, unique_reporters, road_class, age)`.

## 8. Jurisdiction model

- Hierarchy table using **LGD (Local Government Directory) codes** as the canonical IDs: state → district → municipality/ULB → ward (plus rural equivalents: block, gram panchayat).
- Boundaries stored as PostGIS polygons; ticket point → containing polygons via spatial join.
- Separate **road authority** layer: road segments tagged with owner (NHAI, State PWD, municipal, etc.), from OSM tags plus admin-uploaded overrides.
- Admin UI/CLI to import boundaries (GeoJSON/Shapefile) and road ownership data.
- Seed data for the pilot: **Kolkata Municipal Corporation wards**, West Bengal districts, a handful of NH segments. If exact boundaries aren't available, generate plausible sample polygons and clearly mark them as sample data.

## 9. Alerts & notifications

- Officials: new ticket in jurisdiction, SLA approaching (e.g. 80%), SLA breached/escalated to them, ticket reopened.
- Citizens: report verified/rejected, ticket status changes, fix confirmation request.
- Public: optional subscription to an area (ward) for weekly summaries.
- Channels: in-app + push (FCM) + email for officials. SMS later. Build a `Notifier` interface.

## 10. Dashboards

**Public dashboard (web, no login):**
- Map of tickets (clustered markers, colour by status), filter by category/area/status/date.
- KPIs: total reported, resolved, open, average resolution time, SLA compliance %.
- Leaderboard by ward/municipality/district/authority (resolution rate, avg time, breaches).
- Ticket detail page: sanitized before/after photos, timeline, report count, confirmation result.

**Government dashboard (login):**
- Same map/filters scoped to the official's jurisdiction subtree.
- Work queue sorted by priority and SLA remaining.
- Drill-down: state → district → municipality → ward.
- Trends: new vs resolved per week, backlog ageing, hotspots.
- Export CSV.

## 11. Data model (starting point — refine as needed)

**identity_vault (separate DB/schema, separate key):**
- `identities(id, phone_encrypted, identity_hash, verified_level, created_at, banned)`
- `reporter_links(identity_id, reporter_id)`

**core_db:**
- `reporters(reporter_id, trust_score, created_at, banned)` — no personal data
- `jurisdictions(id, lgd_code, name, level, parent_id, geom)`
- `road_segments(id, osm_id, name, road_class, authority_id, geom)`
- `authorities(id, name, type, jurisdiction_id)`
- `categories(id, name, default_sla_hours_by_severity)`
- `tickets(id, category_id, location, severity, priority, status, jurisdiction_path[], authority_id, owner_node_id, escalation_level, sla_due_at, created_at, resolved_at)`
- `reports(id, ticket_id, reporter_id, photo_original_key, photo_public_key, gps, gps_accuracy, captured_at, verification_score, verification_details jsonb, status)`
- `ticket_events(id, ticket_id, type, actor_type, actor_id_nullable, payload jsonb, created_at)` — audit trail; citizen actors never exposed
- `fix_proofs(id, ticket_id, official_id, photo_keys[], gps, captured_at, vision_result jsonb)`
- `fix_confirmations(ticket_id, reporter_id, response, created_at)`
- `officials(id, tenant_id, name, email, role, node_id, authority_id)`
- `tenants(id, name, root_node_id, config jsonb)`
- `sla_rules(tenant_id, category_id, severity, hours)`

## 12. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend API | Python, **FastAPI** | Async, typed, fast to build |
| DB | **PostgreSQL + PostGIS** | Spatial queries for jurisdictions and clustering |
| Identity vault | Separate Postgres DB with column-level encryption | Isolation of personal data |
| Spatial index | PostGIS + H3 (`h3-py`) | Fast clustering and aggregation |
| Background jobs | **Celery + Redis** | Verification pipeline, SLA timers, notifications |
| Object storage | S3-compatible (MinIO locally, R2 when hosted) | Photo originals and sanitized versions in separate buckets |
| Vision | Gemini free tier behind `VisionVerifier` interface | Free for the demo; swappable |
| Image processing | Pillow, OpenCV | Sanitization |
| Citizen app | React Native (Expo) — *to be confirmed, see §0* | Camera + GPS |
| Gov & public web | Next.js + MapLibre GL — *to be confirmed, see §0* | Maps and dashboards |
| Auth | Phone OTP for citizens (stubbed), email+password + 2FA for officials, JWT | |
| Infra | Docker + docker-compose | |
| Tests | pytest, Playwright for web | |

## 13. Build phases (do these in order; stop and report after each)

**Phase 0 — Foundation**
- Monorepo: `/backend`, `/web`, `/mobile`, `/infra`, `/docs`.
- docker-compose: Postgres+PostGIS (core), Postgres (vault), Redis, MinIO.
- DB migrations (Alembic), seed script with sample Kolkata jurisdictions, categories, a demo tenant and officials.
- README with setup steps.

**Phase 1 — Reporting & verification (backend)**
- Citizen auth (OTP stub), identity vault separation, reporter IDs.
- Report upload API, photo storage, EXIF strip + blur → public copy.
- Verification pipeline with capture/location/vision/phash checks.
- Clustering into tickets; jurisdiction + authority mapping.

**Phase 2 — Government workflow**
- Official auth, role/node-scoped access control.
- Ticket status lifecycle, assignment, notes, audit events.
- SLA engine + auto-escalation (scheduled job).
- Fix proof upload + vision before/after check + reporter confirmation flow.
- Notifications (in-app + email; push stub).

**Phase 3 — Web dashboards**
- Public dashboard: map, filters, KPIs, leaderboards, ticket detail.
- Government dashboard: scoped map, work queue, drill-down, trends, CSV export.

**Phase 4 — Citizen mobile app**
- OTP login, camera-only capture with GPS, category selection, submit.
- My reports, ticket status, fix confirmation prompts, nearby tickets map with upvote/"I see this too".

**Phase 5 — Hardening**
- Rate limiting, abuse bans, device attestation hooks, audit logging.
- Tests for access control (officials cannot see identity; officials cannot see tickets outside their subtree).
- Load test the clustering and dashboard queries.

## 14. Acceptance criteria (must pass)

- A government API response never contains any reporter identity field or reporter ID (automated test that scans all gov/public endpoint responses).
- Public photos have no EXIF and have faces/plates blurred.
- Five reports within 30 m of the same category produce one ticket with `unique_reporters = 5`.
- A ticket in a ward is visible to that ward's official and to the municipality, district and state officials above it, and invisible to officials of a sibling ward.
- A ticket past its SLA is escalated one level and an alert is created for the new level.
- A ticket closes only after the fix proof passes the vision check and the reporter confirmation rule is met; a dispute reopens it.
- Gallery images cannot be submitted from the mobile app.
- `docker compose up` + seed script gives a working demo with sample data.

## 15. Out of scope for now

- Real Aadhaar/UIDAI integration (interface + stub only).
- Real SMS gateway (stub).
- Google Street View integration (feature-flagged interface only).
- Integrations with CPGRAMS / state grievance portals (design an outbound `GrievanceConnector` interface; implement later).
- Regional language UI (structure i18n from the start; ship English + Hindi + Bengali strings later).

## 16. Notes for Claude Code

- Ask before making architecture changes that affect the identity/anonymity separation.
- Keep external services (vision, OTP, push, street-level imagery, grievance portals) behind interfaces with local stubs so everything runs offline in dev.
- Add clear inline comments and docstrings explaining what each component does and why it was chosen — the owner is an experienced data engineer but new to LLM/vision systems.
- Commit per phase with a short summary of what was built, what's stubbed, and what's next.
