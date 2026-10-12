# Load test results (Phase 5)

**Data:** 100,000 tickets and 199,798 verified reports, spread over the sample Kolkata
(90%) and Howrah (10%) wards, 180 days of history, a realistic status mix, and ~10% of
tickets with an SLA breach. **Machine:** one local PostgreSQL 16 + PostGIS 3 instance
(the development sandbox, shared CPU). Absolute numbers will differ on real servers;
the before/after comparison is the point.

Every figure times the **application's own functions** (the same code the API runs),
20 calls each. Regenerate with:

```bash
cd backend
LOAD_CORE_DATABASE_URL=postgresql+psycopg://…/roadwatch_load \
  python scripts/loadtest.py --tickets 100000 --out ../docs/load-test.md
```

(The script wipes and refills that database, so it must be a dedicated one; it refuses
any database whose name doesn't contain "load".)

## Results

| Operation | Before (median ms) | After (median ms) | After p95 (ms) |
|---|---:|---:|---:|
| Routing: which ward + road authority | 3.8 | 3.5 | 4.6 |
| **Clustering: find an open ticket within 30 m** | **100.3** | **6.0** | 8.2 |
| Duplicate-photo check (perceptual hash) | 74.1 | 85.4 | 98.2 |
| **Public: summary figures** | **416.2** | **64.6** | 81.4 |
| **Public: leaderboard, all wards** | **572.2** | **85.3** | 96.2 |
| **Public: drill-down, wards of KMC** | **553.7** | **74.5** | 90.6 |
| **Public: road-authority table** | **463.6** | **46.5** | 56.5 |
| Public: issues by type | 44.6 | 33.6 | 36.9 |
| Public: 12-week trend | 59.7 | 60.2 | 79.5 |
| Public: map, 1,000 tickets serialized | 175.8 | 167.1 | 226.3 |
| Gov: work queue top 200, ward officer | 62.5 | 33.9 | 42.1 |
| **Gov: summary, ward officer** | **64.4** | **11.7** | 15.0 |
| Gov: work queue top 200, KMC | 71.1 | 73.4 | 128.5 |
| **Gov: summary, KMC** | **430.8** | **83.5** | 91.0 |
| Gov: work queue top 200, state | 73.5 | 82.3 | 93.7 |
| **Gov: summary, state** | **458.3** | **83.3** | 104.0 |

Small differences in the unchanged rows (±10–20 ms) are run-to-run noise on the shared
sandbox.

## What was found and fixed

1. **Distance checks ignored the spatial index.** Clustering (and "nearby", and the
   fix-proof distance check) measure metres with `location::geography`, but the only
   index was on the geometry column, so every report did a full table scan (~100 ms at
   100k tickets, growing linearly). Added a GiST index on `(location::geography)`:
   **100 → 6 ms**.
2. **Dashboards looked up history ticket by ticket.** "Did this ticket ever miss a
   deadline?" was answered by searching each ticket's event history — 100,000 lookups,
   twice per query. The SLA sweep now sets a `sla_breached` flag when the breach happens
   (backfilled by migration `0005`), so it's a column read: summaries **~5× faster**.
3. **Area scoping couldn't use its index.** `node = ANY(jurisdiction_path)` can't use a
   GIN index; `jurisdiction_path @> ARRAY[node]` can. Switched everywhere (access control,
   filters). A ward officer's scope is now an index lookup (2.9 ms in the database).
   For KMC or the whole state (90–100% of tickets) a full scan is still the right plan,
   and PostgreSQL chooses it.
4. **Leaderboards tested every area against every ticket.** They now "unnest" each
   ticket's stored area path once and hash-join to the areas: **572 → 85 ms**.

## Known limits and next steps

- **Duplicate-photo check (~85 ms)** compares the new photo's 64-bit hash against every
  stored report. It runs in the background worker, not in the user's request, so this is
  acceptable now; it grows linearly (~0.4 ms per 1,000 reports). Past about a million
  reports, switch to an indexed nearest-neighbour search (multi-index hashing over hash
  chunks, or a BK-tree / vector index).
- **Whole-state summaries (~85 ms)** scan all tickets. That's fine at this size; at
  millions of tickets, cache these figures for a minute or keep per-area daily roll-ups.
  The public dashboard makes ~7 of these calls per load, so a short cache (30–60 s) is
  the cheapest next win.
- **Map with 1,000 markers (~170 ms)**: mostly serialization. The dashboard already
  limits the map to what's in view; a lighter "markers only" endpoint would halve it.

## Query plans after the fixes

### Government scope, ward officer

```
Bitmap Heap Scan on tickets (actual rows=625 loops=1)
  Recheck Cond: ((jurisdiction_path @> '{26}'::integer[]) AND (jurisdiction_path @> '{1}'::integer[]))
  ->  Bitmap Index Scan on ix_tickets_jurisdiction_path (actual rows=688 loops=1)
Execution Time: 2.901 ms
```

### Clustering radius search (30 m)

```
Index Scan using ix_tickets_location_geog on tickets (actual rows=0 loops=1)
  Index Cond: ((location)::geography && _st_expand(<point>::geography, '30'))
  Filter: status <> 'resolved' AND category_id = 1 AND st_dwithin(location::geography, <point>, 30)
Execution Time: 0.090 ms
```

## Concurrency

Separately from timing, `tests/test_phase5_hardening.py` fires eight reports of the same
pothole at the same instant from eight threads and checks the result is exactly **one**
ticket with eight reporters — the per-category advisory lock in clustering prevents
duplicate tickets under concurrent load.
