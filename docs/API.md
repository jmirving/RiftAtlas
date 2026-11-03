# DPS API v1

Run the same-origin explorer and API with the instructions in [DEPLOYMENT.md](DEPLOYMENT.md).
The standalone service requires a validated canonical snapshot and manifest.
The local `rift-atlas explore` CLI remains available without web dependencies;
its compatibility routes do not verify provenance and are not the hosted API contract.

## Read-only endpoints

| Route | Response |
| --- | --- |
| `GET /healthz` | 200 with `status: ready` and dataset ID only after the index loads; 503 otherwise |
| `GET /api/v1/dataset` | Public identity, provenance, coverage, role status, capabilities |
| `GET /api/v1/champions?q=mao&limit=20` | `champions`, `api_version`, `dataset_id` |
| `GET /api/v1/relationships?champion=Maokai` | Whole-composition evidence, graph hints, normalized context, API version and dataset ID |

`/docs` and `/openapi.json` describe parameter types. API version `1` is separate
from drafts CSV version `1`, relationships JSONL version `1`, and recommendation
version `2`. No recommendation endpoint is exposed. `co_pick` is queryable;
`opposition` and `draft_response` remain export-only.

## Relationship controls

| Parameter | Behavior |
| --- | --- |
| `champion` | Required known focus, case-insensitive; navigation only |
| `pinned` | Repeated known, distinct champions; one to four; omitted defaults to focus |
| `mode` | `established` (default), `frequent`, or `surprising` |
| `minimum_support` | Integer 1–100000, default 1 |
| `limit` | Integer 0–50, default 12; search allows 0–100, default 20 |
| `patch` | Exact patch; cannot combine with a range |
| `patch_from`, `patch_to` | Inclusive naturally sorted patch range |
| `league` | Repeated league labels; omitted means all, `league=` means explicitly none |
| `hide_role_infeasible` | Boolean, default false; unknown roles are not presumed infeasible |
| `relationship` | Only `co_pick` (default) |

Labels/search are bounded to 128 characters; at most 100 league entries and
8192 query bytes. Unknown parameters and repeated scalar parameters are errors.
Invalid input returns 400 `{"error":"..."}`. Unexpected failures return a generic
500 `{"error":"Internal server error"}` with diagnostic detail only in server
logs. A valid empty population returns 200, empty candidates, and zero counts.

All modes first rank coverage across the **entire pinned set**. Established then
uses the weakest confidence-adjusted pairwise lift; frequent uses total pair
support; surprising uses weakest raw lift. The response's `mode_definition`
documents tie-breaks, and candidate fields expose ranking components. Pairwise,
subset, exact joint, and any-pair union support remain distinct. These are
observations of co-selection, not estimates of synergy, counters, or win chance.

`dataset.active_filters` reports normalized scope; `games_in_scope` and
`team_observations_in_scope` sit alongside total counts. `pinned_champions`,
`pinned_edges`, `neighbors`, and candidate evidence can be consumed without
using the optional visual encoding fields. `dataset.input_identifier` is the
public dataset ID, never the configured deployment path. Identical inputs to
the same snapshot and role policy yield deterministic results.

Roles are `not_evaluated` without an explicit mapping. An incomplete mapping
leaves affected compositions `unknown`; infeasibility is reported separately.
Pick order is never interpreted as role assignment.

## Executable examples

Set `DPS_URL` to the locally running service or future QA URL. Champion names
must exist in that snapshot; these examples assume Maokai and Jinx are present.

```sh
export DPS_URL=http://127.0.0.1:8000
curl --fail "$DPS_URL/healthz"
curl --fail "$DPS_URL/api/v1/dataset"
curl --fail --get "$DPS_URL/api/v1/champions" --data-urlencode q=mao --data-urlencode limit=20
curl --fail --get "$DPS_URL/api/v1/relationships" \
  --data-urlencode champion=Maokai --data-urlencode pinned=Maokai \
  --data-urlencode pinned=Jinx --data-urlencode mode=established \
  --data-urlencode league=LCK --data-urlencode league=LPL --data-urlencode limit=12
curl --fail --get "$DPS_URL/api/v1/relationships" --data-urlencode champion=Maokai --data-urlencode league=
```

No CORS middleware is enabled: the explorer shares the API origin, and ordinary
server-to-server HTTP clients need no CORS configuration. Authentication,
accounts, and persistent client state are outside this release.
