# RiftAtlas Current State

Status date: 2026-09-20

## Purpose

RiftAtlas is the relationship-evidence layer for League of Legends draft data.

Its first concrete product goal is to help complete an **allied partial draft**.
The caller supplies one or more champions that are already locked for whatever
reason; RiftAtlas answers which champions are well supported as additions and
why.

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

## Current observation layer

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

## v1 recommendation layer

The implemented recommendation surface is:

`locked allied picks -> ranked candidate additions + evidence`

If X is locked, RiftAtlas can rank candidate companions. If X and Y are locked,
candidate Z must be evaluated against the whole set `{X, Y}`; the system must
not merely follow the most recent edge `Y -> Z`.

The ranking/evidence model remains explainable and returns:

- pairwise association with every locked champion
- exact joint support when the partial composition plus candidate has actually
  occurred
- coverage across the locked set, so one strong pair does not hide weak or
  absent relationships elsewhere
- sample confidence
- persistence across patches and leagues
- role feasibility

Exact-composition support will become sparse as the partial team grows. The
system therefore returns exact, subset, and pairwise evidence. Ranking considers
whole-set coverage first and does not reject a candidate merely because exact
joint support is zero.

The output should expose component evidence rather than immediately compressing
everything into an opaque universal "RiftAtlas score."

### Role feasibility

A five-champion recommendation is not useful if it cannot form a plausible
five-role team.

Role feasibility is therefore part of the v1 product requirement, but the
current canonical drafts artifact does not itself contain reliable champion-role
assignments. The recommendation API accepts an explicit role policy, and the CLI
can load a caller-supplied champion-to-roles JSON mapping. Neither infers role
from draft pick order. Without a role source, output says `not_evaluated`.

Flex champions should preserve multiple possible role assignments until the
partial composition logically narrows them.

## Current technical shape

- Python 3.12+
- no runtime third-party dependencies
- standard-library CSV ingestion and JSONL publication
- explicit input and output schema versions
- atomic output replacement
- unit coverage for relationship counts, response direction, schema rejection,
  file generation, recommendation evidence/ranking, and role feasibility
- an in-memory inverted observation index for repeatable recommendation queries
- deterministic machine-readable `rift-atlas recommend` JSON output
- a reusable, neutral co-pick relationship query index
- a dependency-free local relationship explorer with champion search,
  deterministic neighbor limits, graph navigation, edge evidence, and dataset
  context
- GitHub Actions CI for the unit suite

There is no database, graph database, model, embedding system, or production
publication target in v1. The explorer's HTTP server is local-only by default
and uses the Python standard library.

## Known limitations

Champion identity currently uses the champion labels supplied by the canonical
draft artifact. A future identity layer should reconcile those labels against
the DDragon-derived champion mapping before multiple upstream sources are mixed.

Bans are validated because they are part of the canonical contract, but v1 does
not emit ban relationships. Ban intent is substantially easier to overstate than
pick ordering, especially in the first ban phase.

The graph currently represents observation evidence, not game outcome. It
therefore cannot by itself distinguish a commonly drafted companion from an
effective companion.

The JSONL artifact is an interchange format, not a commitment to the final
storage technology.

## Immediate next steps

1. Add a consumer contract test using a real processor-produced drafts artifact.
2. Reconcile champion labels to a canonical DDragon-backed champion identity.
3. Decide how RiftAtlas artifacts are versioned and published by the League data
   refresh job.
4. Measure the in-memory aggregate against the full production artifact and add
   a persisted derived index only if startup or memory warrants it.
5. Design ban relationships only after the first allied-draft path is useful.

## Design rule

Prefer storing what was observed before storing what we infer.

Derived concepts such as synergy, counter strength, archetype, flexibility, or
draft quality should be traceable back to the observations and assumptions that
created them.
