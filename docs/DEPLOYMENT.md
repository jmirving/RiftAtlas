# DPS standalone service setup

A validated real processor-produced snapshot is bundled in `data/`; see
[data provenance](../data/README.md). Local real-data acceptance has passed.
A new Starter production service is live from the feature branch. Public
endpoint/browser acceptance remains pending; existing services were unchanged.
See the [deployment record](RENDER_DEPLOYMENT.md). See [DPS_EXECUTION.md](DPS_EXECUTION.md).

## Install and run

Use Python 3.12.14 (recorded in `.python-version`). The CLI remains dependency-free;
the service uses the optional `web` extra. Resolved runtime dependencies are in
`requirements-web.lock`; test and browser requirements are separate.

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-web.lock
.venv/bin/python -m pip install --no-deps .
# Defaults use the bundled data/drafts.csv and data/manifest.json.
# Override DPS_DRAFTS_PATH and DPS_MANIFEST_PATH only for another validated release.
# Optional only when a validated mapping and matching manifest provenance exist:
# export DPS_ROLES_PATH=/absolute/path/to/roles.json
.venv/bin/python -m rift_atlas.dataset
.venv/bin/uvicorn rift_atlas.api:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
```

Default paths are `data/drafts.csv` and `data/manifest.json`, relative to the
working directory; there is no fallback if either is missing. Validation fails
startup for checksum/schema/coverage mismatches, empty data, duplicate games,
invalid provenance, or invalid configured roles. The index loads once per
process. No per-request upstream fetch or mutable external data is used.

## Manifest contract

The following describes fields, **not a usable manifest or production dataset**:

| Field | Required content |
| --- | --- |
| `dataset_id` | Stable 1–128 character identifier: letters, digits, dots, underscores, hyphens; starts alphanumeric |
| `draft_schema_version` | String `"1"` |
| `csv_sha256` | Exact lowercase SHA-256 of canonical CSV bytes |
| `source` | Object with original source `name` and public HTTPS `url`; Oracle's Elixir for the real snapshot |
| `processor` | `repository`: `https://github.com/jmirving/lol-pro-data-processor`; full 40-character `revision`; `artifact_id` string or null if unavailable |
| `generated_at` | Timezone-qualified ISO timestamp of snapshot generation |
| `source_retrieved_at` | Timezone-qualified retrieval timestamp, or null when unknown |
| `coverage` | Exact object with `game_count`, sorted unique `patches` and `leagues`, `match_date_from` and `match_date_to` in ISO date format |
| `attribution`, `source_notices` | Nonempty original attribution and applicable data notices; separate from code license |
| `roles` | Null when unused; otherwise `source` with name/HTTPS URL, `version`, and exact file `sha256` |
| `test_only` | Omitted/false for real data; true marks synthetic test inputs, rejected by production startup |

Coverage is recomputed from CSV records; generation timestamp is not proof of
source freshness. The optional role JSON maps champion names to nonempty lists
of `top`, `jungle`, `mid`, `bottom`, or `support`; incomplete champion coverage is
allowed and remains unknown. Configured malformed mappings fail startup.
Unrecognized manifest fields are not copied into public API metadata.

## Verification

```sh
.venv/bin/python -m pip install -r requirements-test.lock
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
PYTHONPATH=src:tests .venv/bin/python tests/browser_smoke.py
```

For an already installed Chromium, set `DPS_BROWSER_EXECUTABLE` to its path.
The browser test starts a localhost-only service with an explicit test loader,
temporary synthetic CSV, and a conspicuous test-only provenance panel. It does
not provide a production environment flag to bypass the fixture prohibition.
The suite also validates the bundled real snapshot and compares API responses
with direct engine results across all modes and representative populations.
Run `python scripts/measure_service.py` on Linux/WSL for installed-service HTTP
measurements. The recorded [local baseline](REAL_SNAPSHOT_MEASUREMENTS.json)
used Python 3.12.3, not the pinned Render patch (3.12.14): 0.354 s index load,
2.306 s process-to-readiness, and 101.16 MiB peak RSS. Seven warm-query medians
range from 4.2 to 110.5 ms. Two concurrent HTTP clients completed 20 requests
in 1.872 s (123.6 ms median, 293.4 ms maximum). These are local measurements,
not a Render capacity guarantee or two-browser acceptance. Deployed cold-start,
restart, and simultaneous browser-user checks remain required.

## Sustainable QA and production configuration

Updated November 3, 2026 after the user rejected a QA plan that consumes the
shared free-instance allowance. Do not create a standing `dps-qa` service.

QA uses the existing local and GitHub Actions checks: the dependency-free core,
installed-wheel API/real-snapshot contract checks, Chromium smoke, and local
resource/concurrency measurements. These incur no Render instance hours or
Render builds. GitHub Actions remains subject to its own account allowance.
Run local manual browser review against the bundled real data before each
release; CI's automated browser flow uses explicitly marked synthetic data.

Hosted previews are off by default. Do not enable automatic preview creation.
A temporary preview is optional only for a specific review that cannot be done
locally, with an approved lifetime/budget and an explicit teardown owner.
Free previews still use shared free hours and build/bandwidth allowances; paid
PR previews bill at the base service rate, prorated by the second. With no
verified workspace usage or automated teardown capability in the current
connector, no hosted preview is proposed for this launch.

The user approved the $7/month service after confirming Clairvoyance uses
the same Web Service kind and Starter compute plan. One new service was created:

| Setting | Proposed value |
| --- | --- |
| Workspace | Joseph's Workspace |
| Service name | `dps` — https://dps-9bkr.onrender.com |
| Repository | `https://github.com/jmirving/RiftAtlas` |
| Branch until final approval | `feat/dps-standalone-service` |
| Runtime / region | Python 3.12.14 / Oregon |
| Compute | `0.5c-512mb` (legacy `starter`), one instance, 512 MB, 0.5 CPU |
| Base compute price | **US $7/month**, verified November 3, 2026 |
| Automatic deploys / previews | Off; deliberately deploy an approved, CI-green revision |
| Build | `pip install -r requirements-web.lock && pip install --no-deps . && python -m rift_atlas.dataset` |
| Start | `uvicorn rift_atlas.api:app --host 0.0.0.0 --port "$PORT" --workers 1` |
| HTTP health target | `/healthz` |
| Data / dependencies | Bundled immutable snapshot; no database, disk, env group, or production credentials |

Creation and live-deploy readback are recorded in [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md).
Paid compute avoids the shared 750 free-instance-hour pool and idle
spindown. The local 101.16 MiB peak supports evaluating 512 MB, but CPU capacity,
platform overhead, and actual production behavior still require deployed checks.

The $7 price is **compute only**, not a total bill cap. Build minutes and outbound
bandwidth remain shared workspace usage. Public-internet bandwidth beyond the
workspace allowance costs **$0.15/GB**. Pipeline overage pricing depends on the
workspace tier and must be checked in its Dashboard; the connector cannot read
remaining allowances, build-tier pricing, or spending controls. Do not change
workspace settings or existing services to make room. No workspace upgrade,
second instance, database, disk, or paid preview was created or enabled.

The creation connector supports this plan and feature branch but cannot set
HTTP health-check path, checks-pass auto-deployment, or PR preview settings.
Keep auto-deploy disabled. Configure `/healthz` on the new service via Dashboard
when available; until then the connector-created service uses TCP readiness,
with separate direct HTTP readiness verification. Uvicorn completes startup
validation before accepting traffic. Do not claim HTTP monitoring is configured
unless readback confirms it.

The new service is live on the recorded CI-green commit. Direct health, metadata,
API/browser equivalence, restart recovery, and concurrent-client verification
remain pending because this executor cannot access its public URL. Keep main
and all pre-existing Render resources unchanged. Final approval is still
required before merging or switching the production source to main.

Pricing references: [compute](https://render.com/pricing),
[preview billing](https://render.com/docs/service-previews),
[outbound bandwidth](https://render.com/docs/outbound-bandwidth),
[build pipeline](https://render.com/docs/build-pipeline).

## Refresh and rollback

Produce a new canonical artifact upstream. Update the CSV and manifest together,
verify attribution, run `python -m rift_atlas.dataset`, run all tests and the real
snapshot checks, and review the feature-branch results before approval. Never infer
roles from pick order. Do not modify data at runtime.

The committed code/data pair is the rollback unit once real data is bundled.
Render free services retain only the two most recent previous deploys for native
rollback; older code/data pairs require rebuilding the selected Git revision.
Check auto-deploy behavior before a historical deploy so it is not immediately
replaced. Runtime filesystem changes do not survive restart/spindown.

References: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Render free limits](https://render.com/docs/free),
[service previews](https://render.com/docs/service-previews),
[preview environments](https://render.com/docs/preview-environments).
