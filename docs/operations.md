# Running Strava Lens

Strava Lens is a single-athlete application. The Python parser remains independently installable. The web application adds FastAPI, PostgreSQL, a durable worker and React/TypeScript dashboards. See [dashboard parity](dashboard-parity.md) for source-to-panel mappings and data limitations.

## Docker Compose

Install Docker Desktop or Docker Engine with Compose v2. Run the following from the repository root. The first run builds the images automatically; Python and Node.js are not required on the host.

### One-time configuration

Copy `.env.example` to `.env`. Set `POSTGRES_PASSWORD` and `TRAINING_LENS_TOKEN` to **different random URL-safe values**, for example by running `openssl rand -hex 32` twice. Do not commit `.env`.

Create a folder on your computer for Strava exports. By default the app watches **`$HOME/StravaLens/inbox`**, outside the repository:

```sh
mkdir -p "$HOME/StravaLens/inbox"
```

To use another folder or an external disk, set an absolute path in `.env`:

```dotenv
STRAVA_INBOX_DIR=/Volumes/Fitness/Strava/inbox
```

Create that folder before startup. Paths with spaces can be quoted, for example `STRAVA_INBOX_DIR="/Volumes/My Drive/Strava/inbox"`. On Windows, use a Docker-accessible absolute path such as `C:/Users/Alex/StravaLens/inbox`. Docker Desktop may ask you to share the folder or external drive. On macOS, a VM may also need permission to access protected folders such as Documents; choose a shared folder outside those locations if necessary. The worker runs as UID 10001: on Linux, give that user read access to the ZIPs and read/traverse access to the inbox. The mount is read-only; the app never modifies the original ZIPs.

### Start the app

```sh
docker compose up
```

This builds missing images, starts PostgreSQL, runs schema migrations, starts the API and import worker, then serves the UI after the API is healthy. Open **http://localhost:8080** and enter `TRAINING_LENS_TOKEN` from `.env`. To run in the background, use `docker compose up -d`. Change the optional `STRAVA_PORT` setting if port 8080 is occupied.

### Drop a Strava export

Download your bulk export from Strava and put the **original ZIP, without unzipping it**, into the configured host inbox. For the default location:

```sh
cp /path/to/export.zip "$HOME/StravaLens/inbox/export.zip.partial"
mv "$HOME/StravaLens/inbox/export.zip.partial" "$HOME/StravaLens/inbox/export.zip"
```

Using a temporary suffix and renaming after the copy finishes prevents an incomplete large file from being picked up. Files must end in lowercase `.zip` and be directly in the inbox; subfolders are not scanned. Later exports can be dropped into the same folder under different names. Leave ZIPs unchanged while importing.

The worker discovers the file automatically. Open **Setup → Imports** to follow progress, then use the dashboards once the snapshot is ready. Large archives take several minutes. Existing dashboards stay visible during subsequent imports. Browser upload from Setup is also supported.

Only the worker mounts your host inbox. API and worker share a Docker-managed staging volume; PostgreSQL uses its own persistent volume. `docker compose down` stops the stack without deleting those volumes or your original ZIPs. `docker compose up` starts it again. Use `docker compose up --build` after pulling application source changes so existing images are rebuilt.

The web port binds to loopback. For access across machines, configure an authenticated TLS reverse proxy. Keep the application token private. This is a single-athlete application.

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

If startup reports a missing bind source, create the configured host inbox and confirm Docker can access it. If files are not detected, check the `.zip` suffix and folder permissions. Run `docker compose ps` to check service health and `docker compose logs -f worker` to follow ingestion.

Check `docker compose logs api worker migrate`, the Imports screen and `/api/health`. A failed migration must be fixed before startup. Unsupported telemetry files can be quarantined while valid activity summaries remain available; dashboard coverage exposes these gaps. Missing HR, unknown cadence conventions, unavailable incoming social interactions, VO2 max and HRV are displayed as unavailable rather than inferred.

Container configuration follows Docker’s [startup dependency guidance](https://docs.docker.com/compose/how-tos/startup-order/) and [bind-mount behavior](https://docs.docker.com/engine/storage/bind-mounts/).
