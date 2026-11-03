# DPS standalone service execution

Status, November 3, 2026: implementation and real-snapshot local acceptance
complete on `feat/dps-standalone-service`. Hosted QA is intentionally omitted.
The user-approved new Starter production service is live; public HTTP/browser
acceptance remains blocked from this executor. No merge or changes to existing
Render services occurred. See [deployment evidence](RENDER_DEPLOYMENT.md).

## Scope and implementation

Implementation follows `DPS-Standalone-Web-Service-Plan.md`, Library file
`libfile_8e7ba89c2b188191bef3bdce69e2a72b`. The complete plan was read locally
for snapshot integration. This separate clone started at feature commit
`7d342a6dcbfc5ff54a33ed05838cd3410c0a553f`, based on main
`6a441fca999225f0e2c1af1eaddc81971156e3ec`. Existing main checkouts were unchanged.

The shared relationship engine, validated loader, FastAPI/Uvicorn boundary,
readiness, bounded versioned API, DPS frontend, dependency locks, installed-wheel
CI and browser smoke checks are implemented. Baseline main passed 43 tests.
Synthetic fixtures remain isolated and rejected by the production loader.
The recommendation CLI and existing explorer remain supported.

## Real snapshot and provenance

The upstream download was initially blocked in the cloud environment. The user
identified a local Oracle's Elixir export and canonical snapshot in WSL.
To establish a producing revision, processor source was exported using
`git archive` at `16493bdcfa4d6b4a362b8cc37e4bbb78c7bbac41`, built and tested
in a separate workspace, then run against the checksum-verified raw export.
All 20 processor tests passed. The regenerated CSV is byte-for-byte identical
to the earlier November 1 snapshot; that earlier run's revision is unknown.

The committed [manifest](../data/manifest.json) and
[provenance](../data/provenance.json) accompany the 2,616,886-byte CSV:

- Dataset: `manual-2026-11-01-rebuilt-16493bdcfa4d`.
- SHA-256: `9f5e50854cbf2f3b87ba18ebc9e17bf2558613807dd24623ef0fe6900aa40754`.
- 9,243 unique games; 44 leagues, 20 patches; dates January 1–November 1, 2026.
- Generated November 3 at 18:50:53 UTC; original source download time unknown.
- Local import was November 1 at 21:02:07 UTC; this is not asserted as download
  time or proof of current source freshness.
- No role mapping supplied; feasibility remains not evaluated.

The raw export and local absolute paths are not committed. See
[data notes](../data/README.md) for exclusion counts, source attribution,
source-year discrepancies, and reproduction instructions.

## Verification and local measurements

`python -m unittest discover -s tests -v` passed **60 tests in 7.412 seconds**
against a clean installed package. Real-data checks exercise the production
loader, readiness, provenance, assets, all three modes, one/two/four pins,
league and patch filters, explicit empty scope, deterministic API/engine
equivalence, and following a node while preserving pins.
`python -m rift_atlas.dataset` passes with default data paths.
Existing service CI automatically discovers the new real-data tests.

An uncontended `python scripts/measure_service.py` run used one Uvicorn worker
on WSL, Python 3.12.3, with the installed package. This differs from the
3.12.14 deployment pin. Full results are in
[REAL_SNAPSHOT_MEASUREMENTS.json](REAL_SNAPSHOT_MEASUREMENTS.json).

| Measurement | Local result |
| --- | --- |
| Index load | 0.354 s |
| Process launch to HTTP readiness | 2.306 s |
| Peak resident memory including queries | 101.16 MiB |
| Warm single/two/four-pin median | 45.6 / 52.6 / 110.5 ms |
| Warm league-filter / patch-range median | 12.7 / 45.5 ms |
| Warm empty-scope / 50-result median | 4.2 / 64.0 ms |
| Two HTTP clients, 20 requests | 1.872 s wall time |
| Concurrent request median / maximum | 123.6 / 293.4 ms |

Each warm scenario has one warmup and five measured requests. Concurrent clients
start together and make ten sequential requests each. These measurements support
evaluating a small production instance; they do not establish Render performance or deployed
two-browser behavior. No caching or database is justified by this baseline.

## Remaining QA and approval gates

The user rejected consuming shared free credits for hosted QA. Local/CI QA is
the default; no standing QA service or automatic preview is proposed. Existing
services remain untouched. Full preview environments and workspace upgrades
are not needed.

The new production `dps` service runs on `0.5c-512mb` at
US $7/month base compute, one worker/instance, bundled data, and manual deploys
from `feat/dps-standalone-service`. Creation was explicitly approved and the first deploy is live.
Build and bandwidth overages remain separate; no total bill cap is implied.
See [deployment instructions](DEPLOYMENT.md) for the exact configuration,
pricing sources, and connector limitations.

CI succeeded for code/data revision
`2476d82296ebcfb238a9a9fe3f95e14d0f1b19cf` on both push and PR runs. Remaining:
real-data browser/direct API comparison, restart recovery, deployed concurrency checks,
and final approval before any merge or source switch to main. Paid instances
do not have the free plan's idle cold-start behavior; measure startup/restart
instead. Issues #2 and #9 still need acceptance reconciliation; no closure is
claimed. Only the new DPS service was created; existing resources were unchanged.
