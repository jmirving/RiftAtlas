# RiftAtlas

RiftAtlas is a League of Legends draft-relationship evidence layer.

It consumes the canonical one-row-per-game draft artifact published by
`lol-pro-data-processor` and turns observed drafts into explicit,
context-preserving relationship observations.

## v1 scope

RiftAtlas v1 models three relationships:

- `co_pick`: two champions appeared on the same team.
- `opposition`: two champions appeared on opposing teams.
- `draft_response`: the target champion was selected after the source champion
  was already visible on the opposing team.

These names are intentionally descriptive rather than evaluative. RiftAtlas v1
does not claim that co-picks are synergistic, that opposition pairs are
counters, or that a later pick was caused by an earlier pick.

The initial output is deterministic JSON Lines. Each relationship preserves the
game, patch, league, split/year, side, pick slot, and absolute pick-event
positions needed for later aggregation and analysis.

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

See `docs/CURRENT_STATE.md` for the present architecture and
`docs/VISION.md` for possible longer-term directions.
