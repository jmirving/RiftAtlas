# DPS standalone service setup

A validated real processor-produced snapshot is bundled in `data/`; see
[data provenance](../data/README.md). Local real-data acceptance has passed.
Render QA provisioning and deployed acceptance remain pending; no Render
resource was created or modified. See [DPS_EXECUTION.md](DPS_EXECUTION.md).

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

## Future QA provisioning

Create only a new `dps-qa` free Python web service in Joseph's Workspace, linked
to `feat/dps-standalone-service`, after the real data and resource gates pass.
Build: `pip install -r requirements-web.lock && pip install --no-deps . && python -m rift_atlas.dataset`.
Start: `uvicorn rift_atlas.api:app --host 0.0.0.0 --port "$PORT" --workers 1`.
Health path: `/healthz`. Pin the Python runtime; deploy after checks pass.
No production credentials, existing env groups, disks, or databases are needed.
Do not deploy main or modify existing Render services before final approval.

Single-service PR previews can be free. A branch-linked QA service previews PRs
targeting that branch; its own code can be reviewed directly on the QA URL.
Full Blueprint preview environments require Pro. Check shared free hours,
build-minute/bandwidth allowances, and possible overages before any provisioning.
No paid compute or workspace upgrade is authorized without cost disclosure.

## Refresh and rollback

Produce a new canonical artifact upstream. Update the CSV and manifest together,
verify attribution, run `python -m rift_atlas.dataset`, run all tests and the real
snapshot checks, and review the feature-branch QA before approval. Never infer
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
