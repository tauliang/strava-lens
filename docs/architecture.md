# Architecture

The parser is a reusable Python package. The application is a modular monolith with a separate durable worker, allowing deployments on one machine without introducing a message broker. PostgreSQL is the authority for jobs, records, memberships, settings and ready snapshots. FastAPI serves typed HTTP resources, while React renders shared chart and table components using the metric registry. The worker handles CPU-bound parsing outside API request lifetimes.

## Import transaction boundary

Uploads and inbox discoveries use the same content-addressed staging function. Jobs capture parser configuration and a stable observation timestamp. Worker leases fence retries: a stale owner cannot publish a snapshot. Immutable logical records are stored once and linked to snapshot membership. Versioned summaries remain available without counting multiple copies in dashboards. Only the terminal manifest and successful count reconciliation permit atomic activation. Failed or interrupted imports leave the previous ready snapshot visible.

## Read boundary

A request resolves a specific ready snapshot before analytics. Filters, dimensions and metric definitions are explicit; clients include snapshot, units, grain, quality and configuration in query keys. Metric choices come from server-owned mappings, never executable expressions supplied by the browser. Unknown or inapplicable measurements remain null. Ratios use eligible denominators; sport and year comparisons use the same source fields and quality rules as the Splunk dashboards.

## Privacy and deployment

The API requires a bearer token; same-origin Nginx proxies requests and serves static assets. The Compose port is bound to loopback. Authentication is a single-athlete deployment boundary, not a multi-user role system. Parser geography masking is the default. Exact GPS requires explicit configuration and reimport; ordinary telemetry and tables do not contain coordinates. Export and backup storage must be protected as private data.

Database schema changes use Alembic. API and worker containers run without root. Frontend dependencies are locked with npm; backend dependencies are pinned. Python follows PEP 8 formatting with Ruff checks; TypeScript uses strict compiler settings. Tests cover parser identity, transactional readiness, replacement exports, analytics eligibility and UI state. Production deployments should measure database and dashboard performance with their own archive size before increasing worker concurrency.

Implementation references: [FastAPI container deployment](https://fastapi.tiangolo.com/deployment/docker/) and [SQLAlchemy transaction management](https://docs.sqlalchemy.org/en/21/orm/session_transaction.html).
