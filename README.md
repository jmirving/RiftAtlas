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

Explore the observed allied co-pick graph in a lightweight local UI:

`rift-atlas explore --input path/to/drafts.csv`

The command opens `http://127.0.0.1:8765/` by default (use `--no-open` to only
print the URL). Search for a champion, click a connection to inspect its raw and
normalized evidence, or click a neighboring champion to re-center the graph.
Edge width encodes confidence-adjusted lift, edge opacity encodes observed
co-pick support, and node size encodes baseline team support. Exact co-pick
counts are labeled on the graph. Node radii use a bounded logarithmic scale so
large support differences remain visible without letting common champions
dominate the graph. The visible legend documents these encodings, and the UI
describes co-picks as observations rather than recommendations or claims of
synergy.

The explorer offers three deterministic relationship views over the same edge
evidence. Confidence-adjusted lift is `lift × support / (support + 2)`.
**Established** (the default) orders by confidence-adjusted lift, then co-pick
support, then champion name. **Frequent** orders by co-pick support, then
confidence-adjusted lift, then champion name. **Surprising** orders by raw lift,
then co-pick support, then champion name. The highest-ranked visible
relationship is placed at 12 o'clock and rank continues clockwise. A minimum
co-pick control filters low-sample relationships at query time; it does not
change or permanently discard the underlying evidence.

The JSON result reports candidate and locked-champion sample counts, pairwise
co-pick support, popularity-normalized lift, confidence-adjusted lift, coverage,
exact and subset joint support, per-pair supporting patches/leagues, explicitly
named any-pair union context, exact-joint context, and every ranking component.
The union fields do not imply that the entire partial team appeared in each
listed context. Role feasibility is explicitly `not_evaluated` unless `--role-data`
points to caller-supplied JSON such as `{"Maokai":["jungle","support"]}`.

See `docs/CURRENT_STATE.md` for the present architecture,
`docs/V1_PRODUCT.md` for the first product milestone, and
`docs/VISION.md` for possible longer-term directions.
