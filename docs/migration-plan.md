# Training Lens standalone migration

Status: approved approach; parser extraction complete and locally verified on `feat/v0.1.0`.

## Goal and boundaries

Build a self-hosted, single-athlete reactive application with a Python API and TypeScript frontend. Preserve the existing ten dashboards/28 panels, metric semantics, privacy controls, source availability and replacement-export behavior. PostgreSQL and a separate worker replace Splunk indexing/SPL/readiness; React/TypeScript replaces Dashboard Studio. Multiple users, hosted subscriptions, Strava API sync and new proprietary metrics are deferred.

## Parser decision

Own Strava archive/CSV interpretation and normalized records. Reuse `fitdecode` for FIT; retain the tested GPX adapter initially and evaluate gpxpy only against a representative corpus. Do not implement a FIT binary decoder. Add TCX only when supported fixtures justify it. Do not infer missing VO2 max/HRV or source units.

## Milestones and acceptance

1. **Standalone parser package — complete.** Extract archive, CSV, FIT/GPX, social, derivation and privacy code into `src/strava_lens_parser/`. Build a normal Python package with an iterator API and pinned FIT dependency. Preserve source parser version/record identity, permit a caller-supplied observation timestamp, and emit a terminal snapshot manifest. No Splunk, API, database, filesystem spool, watcher or application-global state dependency. Preserve third-party licensing. Run adapted regression tests, hostile archive tests, partial-stream tests, repeat/reordered export identity tests, isolated wheel installation and CLI smoke tests. Compare emitted records to the original importer using synthetic fixtures.
2. **Persistence/import worker.** PostgreSQL, SQLAlchemy and Alembic; durable jobs with leases/retries, immutable activity/stream revisions and snapshot membership. Stage batches, reconcile all expected groups, then atomically activate a ready snapshot. Interrupted parses must not activate partial data. The parser emits deterministic records but does not itself prevent a caller from storing duplicates: persistence supplies unique constraints and revision reuse. Browser uploads and watched-folder imports share one pipeline.
3. **Python API/analytics.** FastAPI/Pydantic, generated OpenAPI types, endpoints for imports, snapshots, activities, streams, configuration, dimensions and typed metrics. Replace SPL with SQL/Python aggregation; retain weighted denominators, timezone/YTD rules, nulls, original weight units, explicit cadence convention and source coverage. Verify independent golden fixtures and Splunk reference results.
4. **Reactive vertical slice.** React/TypeScript/Vite, TanStack Query, ECharts; upload → durable progress → active snapshot → Overview → Activity Detail. SSE with polling fallback. URL filters and cache keys include snapshot/configuration/metric/unit/grain; no mixed-snapshot display.
5. **Dashboard parity.** Remaining eight routes, shared parameterized charts/tables, goals/zones/settings, masked geography and social limitations. Bounded server-side telemetry aggregation preserves gaps/peaks. Every existing workflow maps to an implementation or documented exclusion.
6. **Operational release.** Authentication and exact-GPS access separation; backups/restore, retention/deletion, schema upgrades, Docker Compose, health diagnostics, accessibility and browser tests. Verify clean install, large archives, retries, overlapping/reduced/reordered exports, 219→220 unique workouts, worker failure, privacy changes and runtime performance without transferring full telemetry to browsers.

## Parser contract and review focus

- `inspect_export(path, ...)` returns deterministic identity without writing files.
- `iter_export(path, ..., observed_at=...)` yields schema-versioned dictionaries and one final `kind="snapshot"` manifest; consuming successfully to the end is required before accepting an import.
- A corrupt/missing individual stream retains its CSV summary and status; archive/schema/aggregate-limit failures reject the import. Earlier yielded records remain provisional.
- UTC timestamps and configured reporting dates remain separate; config/parser version changes affect snapshot identity. Identical bytes/settings/observation timestamp yield identical records. Changed archive ordering may change snapshot identity but must not change unchanged stream event IDs.
- Raw coordinates remain outside ordinary samples; exact GPS is opt-in. Social comments/names are excluded. Native contributions are outgoing; supplied actor-level records are required for incoming ranks.
- Validate archive limits before decoding; reject traversal, duplicate members, symlinks, encryption and XML entities. Never extract/execute source members.
- Original ZIPs are the preferred migration input. No SQL schema, web framework, or Splunk JSON-spool compatibility adapter is implemented in this first milestone.

## Execution order

Milestone 1 passed 40 local tests on Python 3.13, including exact parity for 16 synthetic records generated by the original importer at `66ef6802d854394cbb4753c727672e1c6416336c`. Wheel and source distributions build successfully; the wheel installs and passes a CLI smoke test from a separate environment outside the checkout. Dependency checks and independent code review found no blockers. CI also targets Python 3.10; that version has not been tested locally. No package registry or GitHub release has been published.

Proceed next to milestone 2, persistence and the import worker. The existing Splunk repository remains unchanged; adapting its importer to this package is a separate change after parity validation. Subsequent milestone interfaces and implementation tasks will be refined before their code is started.
