# RiftAtlas

RiftAtlas is a League of Legends draft-relationship evidence layer.

It consumes the canonical one-row-per-game draft artifact published by
`lol-pro-data-processor` and turns observed drafts into explicit,
context-preserving relationship observations that can support draft exploration.

## v1 product

The first user-facing RiftAtlas question is deliberately narrow:

> We are already going to pick X. What else is good with this partial allied draft?

RiftAtlas does not need to know why X was chosen. Given one or more locked allied
picks, v1 should recommend plausible continuations using observed professional
draft evidence, score each candidate against the **entire current partial team**,
and expose the evidence behind the recommendation.

The UI may feel like walking a graph, but the ranking must not be a naive
`X -> Y -> Z` chain. Once `X + Y` are locked, candidate `Z` is evaluated
against `{X, Y}`, not only against Y.

The intended v1 endpoint is an evidence-backed, role-feasible path from a partial
allied draft toward a coherent five-champion team. RiftAtlas v1 does **not**
claim to identify the objectively strongest draft.

See `docs/V1_PRODUCT.md` for the working product contract.

## Relationship evidence

The current observation layer models three relationships:

- `co_pick`: two champions appeared on the same team.
- `opposition`: two champions appeared on opposing teams.
- `draft_response`: the target champion was selected after the source champion
  was already visible on the opposing team.

These names are intentionally descriptive rather than evaluative. RiftAtlas
does not claim that co-picks are synergistic, that opposition pairs are
counters, or that a later pick was caused by an earlier pick.

The initial output is deterministic JSON Lines. Each relationship preserves the
game, patch, league, split/year, side, pick slot, and absolute pick-event
positions needed for later aggregation and recommendation evidence.

## Input

The current consumer contract is `drafts` schema version 1 from
`jmirving/lol-pro-data-processor`.

RiftAtlas reads the canonical draft artifact directly. It does not depend on
DraftSage and does not require changes to DraftSage's legacy data inputs.

## Development

Requires Python 3.12+ and has no runtime third-party dependencies.

Install locally with `python -m pip install -e .`.

Run tests with `python -m unittest discover -s tests -v`.

Build relationships with:

`rift-atlas build --input path/to/drafts.csv --output build/relationships.jsonl`

Recommend additions to a partial allied draft with deterministic, inspectable
evidence:

`rift-atlas recommend --input path/to/drafts.csv --pick Maokai --pick Jinx --limit 20`

The JSON result reports candidate and locked-champion sample counts, pairwise
co-pick support, popularity-normalized lift, confidence-adjusted lift, coverage,
exact and subset joint support, supporting patches/leagues, and every ranking
component. Role feasibility is explicitly `not_evaluated` unless `--role-data`
points to caller-supplied JSON such as `{"Maokai":["jungle","support"]}`.

See `docs/CURRENT_STATE.md` for the present architecture,
`docs/V1_PRODUCT.md` for the first product milestone, and
`docs/VISION.md` for possible longer-term directions.
