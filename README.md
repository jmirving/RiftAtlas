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
print the URL). Search for a champion, pin up to four allied champions, and
inspect candidates connected to all or part of that set. Selecting a candidate
shows its coverage, exact joint support, and subset support; Follow node changes
the focus without clearing the pins. Each edge remains independently inspectable.
Edge width encodes confidence-adjusted lift, edge opacity encodes observed
co-pick support, and node size encodes baseline team support. Exact co-pick
counts are labeled on the graph. Node radii use a bounded logarithmic scale so
large support differences remain visible without letting common champions
dominate the graph. The visible legend documents these encodings, and the UI
describes co-picks as observations rather than recommendations or claims of
synergy.

The explorer offers three deterministic relationship views over the same edge
evidence. All prioritize coverage across the pinned set before their named
signal. Confidence-adjusted lift is `lift × support / (support + 2)`.
**Established** emphasizes the weakest confidence-adjusted pair, **Frequent**
emphasizes total pair support, and **Surprising** emphasizes the weakest raw
pairwise lift. Exact joint evidence and deterministic name ordering break later
ties. The highest-ranked visible candidate is placed at 12 o'clock and rank
continues clockwise. A minimum co-pick control determines which pairwise edges
count toward coverage and visibility; it does not discard the underlying
evidence shown in the candidate details.

Optional patch-range and multi-select league filters rebuild the graph metrics
from only the team observations in scope. League controls include Select all,
Clear all, and an explicit Top regions preset. The dataset inspector reports
both filtered and total game/team-observation counts. Selecting a relationship
shows its co-pick support as patch and league count distributions, making narrow
contextual concentration visible without assigning an unexplained persistence
score.

The primary relationship controls and active filter summary stay visible while
the detailed patch/league tray collapses to return space to the graph. Dragging
empty graph space pans the shared node-and-edge viewport; Reset view restores
its centered position. Query-driven graph refreshes preserve that pan position,
including when following a connected champion.

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

## License and reuse

This repository is not open source. Copyright © 2026 Joseph Irving. All rights reserved.

No permission is granted to copy, modify, distribute, sublicense, sell, or incorporate this repository's original code, documentation, designs, prompts, schemas, models, or other original material into another project without prior written permission from the copyright owner.

Third-party software, data, trademarks, game assets, APIs, and other third-party materials remain subject to their respective owners' rights and licenses. See [LICENSE](LICENSE).
