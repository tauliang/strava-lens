# Implementation ledger

Plan: `docs/migration-plan.md`; baseline `a5bb41b` on `feat/v0.1.0`.

The user approved implementing the existing migration plan through dashboard parity and requested a PR to main. The existing feature checkout provides isolation from main. Parser and Splunk source repositories remain unchanged during application implementation.

## Work ownership

- Backend: PostgreSQL/Alembic, import worker, FastAPI and tests.
- Analytics: fixed metric registry, ten dashboard projections and source mapping.
- Frontend: React/TypeScript, parameterized chart components and workflows.
- Integration: deployment, operations, CI, PostgreSQL/browser verification and final review.

## Decisions

- Use the existing approved single-athlete architecture; token authentication is sufficient for the local deployment. A multi-tenant hosted service is outside scope.
- Use polling for durable import progress initially; it is the approved fallback and avoids passing bearer secrets in EventSource URLs.
- Keep original snapshot data immutable. Configuration changes apply to subsequent imports; viewing older snapshots preserves their original derived observations.
- Retention is documented as an operational limitation; automatic deletion of shared records requires a separately verified garbage collector.
- Docker daemon is unavailable locally. Verify with a temporary real PostgreSQL instance and native processes; CI builds containers separately.

## Verification

In progress. Do not interpret this ledger as a parity or deployment certification before the recorded checks complete.

## Completed verification

- Parser plus analytics: 62 tests pass (40 parser + 22 analytics).
- Backend: 10 tests pass with PostgreSQL enabled, including authenticated upload/worker/dashboard integration and overlapping 219 → 220 → 219 membership totals.
- Frontend: strict TypeScript production build and six tests pass; dependency audit reports zero vulnerabilities.
- Real original 580 MB export imported successfully in 228 seconds into temporary native PostgreSQL, producing roughly 1.4 million normalized records. No personal export or parsed data is committed.
- Python wheel and source distribution build successfully. Compose configuration validates; Docker image execution was not tested locally because the daemon is unavailable.
- Browser checked authentication, dashboard navigation, annual/imperial controls and metric switching. Comprehensive cross-browser/accessibility certification is not claimed.
- Fresh code review found telemetry gap rendering, mismatched grouping defaults and missing automatic metric selection. These were fixed with regression tests; scoped re-review found no blocking regression. Failed-import Retry and generated OpenAPI contracts were added as part of the fix pass.

## Remaining operational limitations

Polling is used for import progress. Automatic retention/garbage collection and multi-user hosting remain deferred. The chart bundle produces a nonfatal 500 KB warning (about 176 KB gzip). CI includes PostgreSQL tests, schema-drift checks, frontend build and container builds; hosted results must be checked on the PR.

## Docker deployment follow-up

Compose now supports a configurable external read-only host inbox (`STRAVA_INBOX_DIR`), defaulting to `$HOME/StravaLens/inbox`. Only the worker mounts it; absent folders fail startup rather than silently creating a different directory. Database/migration/API health dependencies, restart policies and an optional host port are configured. One-time secrets/folder setup is documented; normal startup is `docker compose up`.

Both images built and the full stack started successfully in an isolated project on the running Colima Docker context. The container smoke test passed external folder discovery, byte-identical archive skipping and unique totals for overlapping exports. The original current Docker context was stopped; no global context was changed. Temporary-folder sharing and macOS protected-folder limitations were encountered and documented. CI now runs this disposable Compose smoke test in addition to building the images.
