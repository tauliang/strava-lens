# Running Strava Lens

Strava Lens is a single-athlete application. The Python parser remains independently installable. The web application adds FastAPI, PostgreSQL, a durable worker and React/TypeScript dashboards. See [dashboard parity](dashboard-parity.md) for source-to-panel mappings and data limitations.

## Docker Compose

Install Docker with Compose v2. Copy `.env.example` to `.env` and generate two independent random secrets (the example shows a command). Create an `inbox` directory, then run:

```sh
mkdir -p inbox
docker compose up --build -d
```

Open http://localhost:8080 and enter the token from `.env`. The web port binds to loopback. Use an authenticated TLS reverse proxy for access across machines; do not expose the database or plaintext HTTP publicly. Keep the application token private. The app is designed for one trusted athlete, not mutually untrusted tenants.

The migration service upgrades the database before API and worker startup. The worker and API share staged imports; the inbox is mounted read-only. Upload a Strava export using Imports, or copy a completed ZIP into `inbox` using a temporary filename followed by an atomic rename to `.zip`. Do not overwrite a file while importing. Worker progress and failed imports appear in Imports. Previously ready data remains visible while another import runs.

Identical logical records reuse deterministic IDs. Versioned summaries and snapshot memberships are retained; dashboards use a selected ready snapshot instead of summing all export versions. A smaller replacement export therefore shows its own membership. No partial or failed import replaces the ready snapshot. Changes to parser configuration require a new import.

## Verification and upgrades

Before upgrading, back up PostgreSQL and the imports volume. Review migration changes, rebuild images, then run Compose; migrations run before app startup. Never run two app versions against a database without checking schema compatibility.

```sh
docker compose exec -T db pg_dump -U lens -d lens -Fc > lens-backup.dump
# Restore into a separate empty database first; verify the restored dashboard counts.
docker compose exec -T db pg_restore -U lens -d lens_restore --no-owner < lens-backup.dump
```

Back up the imports volume separately if you need to reparse original archives. Database backups contain personal fitness and social information; protect them accordingly. Exercise restore procedures before relying on a backup. Do not delete individual database records to reclaim space: snapshots reference shared telemetry. Retention automation is deferred; use full-instance removal only when all local data should be deleted, after a verified backup.

To remove the local instance and all managed data: `docker compose down --volumes`. This is irreversible. The host inbox and any external backups remain and must be managed separately.

## Development

Use Python 3.10+ for the parser, Python 3.13 for the app and Node.js 22+ for the frontend. Install the parser editable, install `backend/requirements.txt`, set `PYTHONPATH=backend`, `DATABASE_URL`, `DATA_DIR` and `TRAINING_LENS_TOKEN`, then run:

```sh
alembic -c backend/alembic.ini upgrade head
uvicorn strava_lens.app:app --host 127.0.0.1 --port 8000
# In another terminal with the same environment:
python -m strava_lens.worker
# In frontend/:
npm ci
npm run dev
```

Frontend development proxies `/api` to port 8000. Use the same token for API and UI. Run parser/backend tests and frontend checks before submitting changes. The CI workflow records the supported test matrix.

## Troubleshooting

Check `docker compose logs api worker migrate`, the Imports screen and `/api/health`. A failed migration must be fixed before startup. Unsupported telemetry files can be quarantined while valid activity summaries remain available; dashboard coverage exposes these gaps. Missing HR, unknown cadence conventions, unavailable incoming social interactions, VO2 max and HRV are displayed as unavailable rather than inferred.
