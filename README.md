# Strava Lens

A self-hosted training analytics application for Strava bulk exports, with ten dashboards and 28 parameterized panels migrated from Training Lens for Splunk. FastAPI and PostgreSQL provide durable imports and analytics; React and TypeScript provide the reactive dashboard UI. The parser remains an independently installable Python package.

Start with the [installation and operations guide](docs/operations.md), [architecture](docs/architecture.md), [dashboard parity mapping](docs/dashboard-parity.md) and [migration plan](docs/migration-plan.md).

## Run the web app

One time: copy `.env.example` to `.env`, set the two independent secrets described there, and create your external Strava inbox. Then start everything with one command:

```sh
mkdir -p "$HOME/StravaLens/inbox"
docker compose up
```

Open http://localhost:8080, enter your configured token, and upload an export in Setup or drop the original ZIP into **`$HOME/StravaLens/inbox`** on your computer. Set `STRAVA_INBOX_DIR` in `.env` to use another absolute folder, including an external disk. The folder is mounted read-only into the worker; your originals remain on the host. See the [operations guide](docs/operations.md#drop-a-strava-export) for safe copying, permissions and progress monitoring. Imports run in a separate durable worker. Overlapping exports retain versioned summaries while each dashboard counts only one selected ready snapshot.

Overview, Training, Sport Performance, Gear and Sports, Geography, Activity Detail, Social, Vitals, Data Health and Setup share data-driven metric dropdowns, unit-aware legends, historical filters and coverage indicators. Unavailable source measurements remain unavailable; the app does not invent VO₂ max, HRV or historic follower dates.

## Install

Python 3.10 or newer:

```bash
python -m pip install .
```

## Parse an export

```python
from strava_lens_parser import inspect_export, iter_export

identity = inspect_export("export.zip", timezone="America/New_York")
print(identity.snapshot_id)

# Persist the first observation time in your job and reuse it on retries.
for record in iter_export(
    "export.zip",
    timezone="America/New_York",
    observed_at=1792252800,
):
    stage(record)  # Your persistence adapter; records remain provisional.
```

`stage` represents caller-owned persistence, not a package function. Only activate an import after successful iterator exhaustion and verification of the final `kind="snapshot"` manifest. Fatal errors can occur after earlier records have been yielded. The terminal manifest describes expected groups; it does not assert database readiness.

Both functions accept `decode_streams`, `timezone`, `athlete_id`, and `config`. `iter_export` also accepts `observed_at` (Unix seconds). Supply an immutable staged ZIP for the duration of inspection/parsing. Parsing writes no spool files, manifests, locks, logs, or global state. Repeated parsing emits the same logical IDs; consumers must enforce uniqueness and snapshot membership themselves.

For a local validation/count report that does not save or print personal records:

```bash
python -m strava_lens_parser export.zip --timezone America/New_York
```

This CLI consumes the complete iterator before reporting success. It prints counts only; use the Python API to stage normalized records.

## Supported data

- Duplicate-header-aware activities CSV with explicit SI normalization, source fields, quality flags, corrections, reporting dates, HR and original-unit weight.
- FIT/FIT.GZ through MIT-licensed fitdecode; the tested GPX/GPX.GZ adapter, including supported HR/cadence/power extensions.
- Device laps, timer-aware HR zones, splits, continuous best efforts and privacy-masked geographic cells. Exact GPS remains opt-in.
- Native follower/following observations and outgoing comments/kudos. Incoming actor-level interactions require the supplemental `social_interactions.csv` contract.
- Configured goals, gear thresholds and structured exercise records.

Unknown stream formats (including TCX in this version) are quarantined while valid CSV summaries remain available. Archive/schema failures reject the import. No VO2 max, HRV, resting HR, unknown units or follow dates are invented. XML entities, unsafe ZIP paths, symlinks, encryption and excessive expansion are rejected.

The package release version is `0.1.0`. The extracted normalization/parser version remains `1.0.3` to preserve existing snapshot/revision identity semantics. This is not a new on-disk parser format.

## Development

```bash
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
python -m build
```

All committed examples and tests use synthetic data. Do not commit personal exports or parsed records. See [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES) for provenance and dependency licensing.
