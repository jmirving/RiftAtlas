# RiftAtlas v1 Product Contract

Status: working v1 definition  
Date: 2026-09-20

## Product question

RiftAtlas v1 starts from a user decision, not from a blank draft:

> We are going to pick X because of reasons outside RiftAtlas. What else is good
> with this?

The reason X was chosen is intentionally out of scope. The caller may lock one
or more allied champions. RiftAtlas should help grow that partial team toward a
coherent, role-feasible five-champion composition using explainable evidence
from observed professional drafts.

## Core interaction

The interaction can feel like walking a graph:

1. Lock X.
2. Inspect candidate companions and their evidence.
3. Choose Y.
4. Recompute recommendations for the entire state `{X, Y}`.
5. Continue until the allied team is complete or the user stops exploring.

The implementation must not be a naive last-edge traversal. If `Z` is strongly
related to Y but poorly supported with X, that should be visible in Z's evidence
and ranking.

## First output shape

For a request containing a set of locked allied champions, return ranked
candidate additions.

A candidate result should be capable of exposing at least:

- champion identity
- compatibility/evidence against each locked champion
- exact joint support count for `locked + candidate`, when present
- pairwise support counts
- coverage across the locked set
- patch persistence at per-pair, any-pair union, and exact-joint levels
- league persistence at per-pair, any-pair union, and exact-joint levels
- role feasibility / remaining role possibilities
- enough source counts/context to explain why the candidate appears

The initial interface may be CLI/library output. A web UI is not required to
prove the product.

## Ranking principles

The first ranking should be deterministic and explainable.

Candidate evidence should consider:

### 1. Association

How strongly does the candidate co-occur with each locked champion relative to
ordinary champion popularity?

Raw co-pick count alone is insufficient because highly popular champions would
otherwise dominate every result.

### 2. Joint support

How often has the candidate appeared in an actual allied composition containing
all currently locked champions?

Exact joint support is powerful when it exists but must not become a hard
requirement because observations become sparse as the partial team grows.

### 3. Coverage

Does the candidate have reasonable evidence with the entire locked set, or is
one strong pair carrying an otherwise weak recommendation?

Ranking should reward broad compatibility with the current state.

### 4. Confidence

A tiny sample should not outrank a well-supported relationship merely because
its raw association ratio is extreme.

Return sample evidence explicitly. Avoid presenting false precision.

### 5. Persistence

Relationships observed across multiple patches and/or leagues are more robust
than relationships isolated to one narrow pocket of the professional meta.

Persistence should remain inspectable rather than silently hiding context.
For each candidate, every locked-champion pair reports the patches and leagues
supporting that pair. Candidate-level `any_pair_supporting_patches` and
`any_pair_supporting_leagues` are the unions of those pair contexts; they do
not imply that the whole partial team appeared in each context. The separate
`exact_joint_patches` and `exact_joint_leagues` fields report only observations
containing every locked champion plus the candidate and are empty when there is
no exact joint support. All context arrays are sorted for deterministic output.

### 6. Role feasibility

Recommendations should preserve the possibility of a valid five-role team.

Role feasibility must come from an explicit role source or role-policy input.
Draft pick order is not a role label.

Flex champions should retain multiple plausible assignments until other picks
narrow the state.

## Evidence fallback as the draft grows

Historical support naturally gets sparse:

- At one locked champion, pairwise evidence is abundant.
- At two locked champions, exact trios are often available.
- At three or four locked champions, exact historical matches become rarer.

RiftAtlas should degrade gracefully:

1. Prefer exact joint support when meaningful.
2. Use smaller-subset and pairwise evidence when exact support is sparse.
3. Preserve coverage/confidence so a candidate is not justified by one isolated
   relationship.
4. Never interpret absence of an exact historical composition as proof that the
   composition is bad.

## What "decent draft result" means in v1

For v1, a decent result means:

- all five allied champions are distinct
- the composition is role-feasible
- each added champion has explainable historical relationship support with the
  partial team
- the path does not rely on one misleading edge while ignoring the rest of the
  composition
- the evidence and its sample sizes are visible

It does **not** yet guarantee:

- optimal matchup into the enemy team
- high expected win rate
- ideal engage/disengage structure
- balanced physical/magic damage
- lane priority
- waveclear
- scaling profile
- player champion-pool fit
- tactical suitability for a specific team

Those are future semantic or consumer layers.

## Optional complete-path exploration

Once candidate ranking works, the same machinery can search forward from X and
surface several supported complete composition paths.

These should be described as graph-supported or evidence-supported paths, not
"the best drafts."

Path search must score each expansion against the full partial state and obey
role feasibility. Beam search is a plausible implementation, but the product
contract does not require a particular search algorithm.

## Non-goals for the first implementation

- No graph database requirement.
- No GNN or embedding requirement.
- No opaque learned ranking.
- No enemy-draft response logic yet.
- No ban recommendation logic yet.
- No win-rate optimization.
- No requirement for a dedicated UI.
- No attempt to explain why the initial locked champion was selected.

## Success criterion

Given one or more locked allied champions, RiftAtlas can return candidate
additions that a coach can inspect and say:

> I can see why this champion is being suggested with the team I already chose,
> how much evidence supports it, and whether continuing down this branch can
> still produce a valid five-role composition.
