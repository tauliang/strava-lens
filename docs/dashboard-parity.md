# Dashboard parity contract

Baseline: Training Lens 1.0.1, training-lens commit
`66ef6802d854394cbb4753c727672e1c6416336c`, Dashboard Studio definitions
under `build/training_lens/default/data/ui/views` and its validated metric catalog.
The standalone application retains ten routes and 28 parameterized panels.

| Original dashboard | Standalone panels | Details / alternate views |
| --- | --- | --- |
| overview | Selected volume; activity history; activities and coverage | Recent activities, coverage, annual category counts and year-over-year changes |
| training | Training history; configured goals; training details | Weekly log, preceding four recorded weeks effort comparison, observed/unobserved/paused HR seconds, effort coverage |
| run_performance | Sport performance history; best efforts; comparable runs | Distance, ratio pace/speed, confirmed running cadence, weighted exercise HR, annual coverage |
| gear_sports | Gear/sport history; equipment thresholds; gear/sport details | Lifetime mileage thresholds, gear usage, sport summaries, strength sessions, annual coverage |
| geography | Privacy-masked cell visits; geography details | Top 1,000 cells; sport coverage; no exact GPS exposed |
| activity_detail | Activity summary; telemetry; activity details | HR, pace, speed, altitude, cadence, power; laps, splits, zones, exercises |
| social | Network history; interactions; followers; source availability | Given/received interactions, current follower ranking, roster, observed changes |
| vitals | Exercise vitals history; zone history; coverage/limitations | Average and peak HR comparison, recorded weight, annual coverage |
| data_health | Readiness; coverage history; diagnostics | Committed manifests, live availability, completeness, quality issues, worker diagnostics |
| setup | Configuration | Parser version, timezone, GPS setting, snapshot identity; import/settings controls provided by the application shell |

## Shared semantics

`metrics.py` reads the original 30-entry metric CSV. Only fixed metric identifiers
are accepted. Display labels, legends and metric/imperial conversion factors come
from this registry; request parameters never become executable SQL. API responses
supply eligible metric availability so controls can disable unavailable choices.
Unknown metrics fail explicitly. Empty charts carry a no-observations message.

Moving pace is total eligible seconds divided by total eligible meters. Moving
speed is total eligible meters divided by total eligible seconds. Exercise heart
rate and running cadence use moving-time weights. Invalid duration/distance are
excluded under Validated mode; Flagged mode selects flagged activities. Cadence
requires an explicit steps/strides convention and doubles strides only when
confirmed. Weight remains in export units. Peak HR cannot be below average HR.

Week/month/year history uses normalized local dates. Annual history spans the
selected snapshot's history and supports comparable YTD using its import calendar
date. Chart years with no observations are null gaps. The annual changes table
uses zero activity counts for missing years before computing changes, matching
the source table's distinct behavior. Pace and speed split by sport to avoid
combining skiing and running into a misleading average.

Only committed snapshots are visible. Activity totals use a single selected
snapshot. Samples and derived records join by stream revision, including shared
revisions that were first recorded in another snapshot. Record IDs are deduplicated.
Network history consists of import observations, rather than invented follow dates.
Received interaction rankings include only recorded interactions from current
followers. VO₂ max, HRV and resting HR remain explicitly unsupported; no proxy
measurements are manufactured. Geographic panels consume privacy-masked coarse
cells produced by the parser, never raw GPS streams.

## Intentional platform substitutions

Splunk index reconciliation is replaced by transactionally committed snapshot
manifests and database identities. Five-minute availability lookup caches are
replaced by live eligibility calculations. Worker diagnostics use application job
status rather than Splunk operational indexes. These preserve the user-visible
purpose without reproducing Splunk administrative machinery.

## Verification

`tests/test_analytics.py` tests the ten-route/28-panel inventory, weighted HR,
ratio pace and speed, imperial conversion, explicit cadence conventions, snapshot
selection and duplicate IDs, annual gaps, metric allowlists, invalid measurement
handling, coverage denominators, shared telemetry revisions, follower ranking,
and privacy-safe geography. Parser fixtures separately assert original-importer
record parity. API integration and frontend tests validate the delivery layer.
