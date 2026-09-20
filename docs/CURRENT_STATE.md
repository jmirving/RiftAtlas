# RiftAtlas Current State

Status date: 2026-09-20

## Purpose

RiftAtlas is the relationship-evidence layer for League of Legends draft data.

Its job is to transform observed professional drafts into explicit graph-shaped
facts that other tools can aggregate, query, model, or explain.

RiftAtlas is deliberately separate from prediction and draft construction.
DraftSage is not a runtime dependency. DraftEngine is not a runtime dependency.
The first version is useful without either project.

## Upstream contract

The canonical input is the `drafts` artifact published by
`jmirving/lol-pro-data-processor`.

The current supported upstream contract is drafts schema version 1: one complete
row per game containing game/patch/league context, Blue and Red team IDs, five
picks per side, and five bans per side.

The processor added this artifact alongside its legacy outputs. RiftAtlas
consumes the new artifact directly, so adopting RiftAtlas does not require
changing DraftSage's existing inputs.

## What v1 implements

The initial codebase has one pipeline:

canonical drafts CSV -> validated DraftRecord -> relationship observations ->
deterministic JSONL

Every relationship observation retains enough context to be re-aggregated by
game, patch, league, split/year, side, pick slot, and absolute pick event.

### co_pick

Two champions were picked by the same team in the same game.

This is evidence of co-selection only. It is not yet a claim of synergy.

### opposition

Two champions appeared on opposite teams in the same game.

This is evidence of an observed matchup only. It is not yet a claim that either
champion counters the other.

### draft_response

The target champion was selected after the source champion was already visible
on the opposing team.

Direction is determined from the standard competitive pick order. This is an
observed sequencing relationship. It is not yet a claim that the source caused
the target pick or that the target is a counter.

## Current technical shape

- Python 3.12+
- no runtime third-party dependencies
- standard-library CSV ingestion and JSONL publication
- explicit input and output schema versions
- atomic output replacement
- unit coverage for relationship counts, response direction, schema rejection,
  and file generation
- GitHub Actions CI for the unit suite

There is no database, graph database, web server, model, embedding system, or
production publication target in v1.

## Known limitations

Champion identity currently uses the champion labels supplied by the canonical
draft artifact. A future identity layer should reconcile those labels against
the DDragon-derived champion mapping before multiple upstream sources are mixed.

Bans are validated because they are part of the canonical contract, but v1 does
not emit ban relationships. Ban intent is substantially easier to overstate than
pick ordering, especially in the first ban phase.

The graph currently represents observation evidence, not game outcome. It
therefore cannot by itself distinguish a commonly drafted response from an
effective response.

The JSONL artifact is an interchange format, not a commitment to the final
storage technology.

## Immediate next steps

1. Add a consumer contract test using a real processor-produced drafts artifact.
2. Decide how RiftAtlas artifacts are versioned and published by the League data
   refresh job.
3. Add deterministic aggregate views over relationship observations.
4. Reconcile champion labels to a canonical DDragon-backed champion identity.
5. Design ban relationships with explicit semantics for pre-pick bans and
   second-phase bans.
6. Add outcome/role/team/player context only when a concrete question requires
   it.
7. Expose a consumer interface after the useful query shapes are known; do not
   build an API merely because an API is conventional.

## Design rule

Prefer storing what was observed before storing what we infer.

Derived concepts such as synergy, counter strength, archetype, flexibility, or
draft quality should be traceable back to the observations and assumptions that
created them.
