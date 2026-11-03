# DPS deployment record

Recorded November 3, 2026. This records a live deploy, not completed external
acceptance testing.

## Authorization and configuration

The user approved a new $7/month service conditional on matching Clairvoyance's
service kind and plan. Read-only inspection confirmed Clairvoyance
`srv-d7f93gpf9bms73ctn3fg` is `web_service` with compute plan `starter`.
DPS matches both. Clairvoyance uses Node and has a disk; DPS uses Python and has
no disk. No Clairvoyance or other pre-existing resource was changed.

| Field | Observed value |
| --- | --- |
| Public URL | https://dps-9bkr.onrender.com |
| Dashboard | https://dashboard.render.com/web/srv-dbl3d8mk1f9s73ed3b7g |
| Workspace | Joseph's Workspace (`tea-csppg056l47c73djsj5g`) |
| Service | `dps`, `srv-dbl3d8mk1f9s73ed3b7g` |
| Kind / compute | Web Service / Starter, one instance, 512 MB, 0.5 CPU |
| Region / runtime | Oregon / Python 3.12.14 |
| Branch | `feat/dps-standalone-service` |
| Deployed commit | `f2b1581e42502753213ac6916ad066f08012bad6` |
| Deploy ID | `dep-dbl3d96k1f9s73ed3c0g` |
| Deploy state | `live`, confirmed through Render |
| Started / finished | 19:31:48.521 / 19:32:45.579 UTC |
| Automatic deploys / previews | Both off |
| Health-check configuration | Default TCP probes; HTTP path is unset |

The approved base compute charge is $7/month. Shared build/bandwidth usage can
incur separate overages, as disclosed before approval. No workspace upgrade,
database, persistent disk, extra instance, or separate hosted QA was created.

## Verified through Render

- Build logs confirm checkout of the exact feature-branch commit and Python
  3.12.14. CI for that commit passed on both push and PR runs.
- Startup logs identify dataset `manual-2026-11-01-rebuilt-16493bdcfa4d`,
  **9,243 games**, and **0.735 seconds** to validate/load the index.
- Uvicorn listens on `0.0.0.0:10000` with one worker.
- Render reports the first deployment live; creation-to-live took about
  58 seconds including build and rollout, not a measured public cold start.
- First memory sample at 19:33 UTC: 99,545,090 bytes (about 94.93 MiB) against
  a 536,870,900-byte limit (about 512 MiB). This is a single startup/idle sample,
  not a peak-under-load measurement.
- An error-level log query after rollout returned no entries. This alone does
  not establish functional correctness.

## Verification blocked from this executor

Direct public HTTP requests could not be completed. The standard execution
request to `/healthz` failed with `CONNECT tunnel failed, response 403`; an
approved elevated attempt returned HTTP 403. The web-fetch tool also reported
the health and metadata URLs inaccessible. These are confirmed access failures;
their responses do not establish an application-origin error or a passing check.

Consequently, this run does **not** claim deployed health JSON, API/engine
equivalence, browser interaction, two-client latency, or restart recovery
passed. Local/CI tests and local performance evidence remain separately valid.

Next verification, from a client with access to the new URL:

1. Fetch `/healthz` and `/api/v1/dataset`; expect the dataset ID above, 9,243
   games, the committed checksum, and `test_only: false`.
2. Run the API examples and browser flow in [API.md](API.md), including pinning,
   following without losing pins, filters/empty scope, and source attribution.
3. Compare representative returned evidence with the same committed snapshot's
   local query engine; measure two concurrent clients.
4. Set `/healthz` in the **new DPS service's** Health Checks settings, then read
   back the configuration. The connector cannot set this field. Until then,
   Render uses TCP readiness; do not describe HTTP health monitoring as enabled.
5. Perform a same-revision restart and repeat readiness/data verification. The
   connector has redeploy but no restart action, so no extra build was triggered
   as a substitute. Paid Starter does not idle-sleep like the Free plan.

PR #11 remains draft. No merge or switch to main occurred. Documentation-only
commits after the deployed revision do not auto-deploy because auto-deploy is off.
