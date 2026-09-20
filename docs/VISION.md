# RiftAtlas Potential End States

This document is intentionally broader than a roadmap.

RiftAtlas begins with one concrete product: grow a user-chosen allied partial
draft into evidence-backed, role-feasible candidate continuations. The
underlying asset is a contextual history of how League drafts relate champions
to one another. Several broader end states are possible, and the project should
preserve the option to reach them without pretending today that all of them are
required.

The active v1 product contract lives in `V1_PRODUCT.md`.

## Stable identity: the atlas, not the storage engine

The durable concept is an atlas of draft relationships.

"Graph" describes the shape of much of the information, but RiftAtlas should not
be forced into a graph database, graph neural network, or any particular
storage/query technology. A relational store, columnar artifacts, graph store,
embeddings, or a combination may be appropriate at different scales.

The public semantics should outlive the implementation.

## End state A: trustworthy allied draft companion

The nearest mature end state is a queryable companion for growing an allied
partial draft.

Examples:

- We are picking X; what is well supported with it?
- Given X + Y, what candidates fit both rather than only Y?
- Which candidates have exact historical trio/four-champion support?
- Which branches remain role-feasible?
- Which relationships persist across patches or leagues?
- What are several coherent graph-supported five-champion paths from X?

This version needs strong aggregation, filtering, confidence/sample-size
reporting, role feasibility, and stable consumer contracts. It does not require
machine learning.

## End state B: semantic champion relationship atlas

Observed relationships can support derived concepts once their definitions are
made explicit.

Possible derived edges or properties include:

- likely synergy
- draft response strength
- matchup/counter evidence
- role compatibility
- flex/role openness
- composition fit
- engage/disengage relationships
- damage-profile complementarity
- front-line/back-line structure
- scaling or tempo alignment

Some of these require DDragon/static champion context. Others require game
outcomes, player roles, or learned models. They should not all be inferred from
co-occurrence alone.

A mature atlas should distinguish raw observation edges from derived semantic
edges and expose provenance for both.

## End state C: meta map and drift system

Because every observation is time- and patch-aware, RiftAtlas can become a map
of how drafting relationships evolve.

Potential capabilities:

- identify emerging champion clusters before they dominate raw pick-rate tables
- compare regions or leagues
- detect relationships that survive balance patches
- identify patch-specific pairings that are disappearing
- quantify whether a team's draft habits follow or diverge from the broader meta
- separate persistent champion structure from temporary professional fashion

This turns the graph from a static relationship lookup into a temporal system.

## End state D: team and opponent intelligence substrate

Team/player context can turn generic relationships into scouting evidence.

Questions could include:

- What responses does this team prefer after showing X?
- Which branches of the global draft graph does this team avoid?
- Does a player constrain otherwise-common champion transitions?
- Which opponent tendencies are stable enough to plan around?
- Where does an opponent's observed graph differ materially from the league
  baseline?

Clairvoyance could consume these views rather than independently reinventing
relationship calculations.

## End state E: DraftEngine knowledge layer

DraftEngine can use RiftAtlas as empirical context without allowing historical
frequency to become the definition of a good draft.

Potential uses include:

- rank plausible continuations
- surface common professional responses
- warn when a suggested branch has almost no historical support
- explain why two choices are related
- supply priors to deterministic search
- compare a proposed composition with known archetype neighborhoods

DraftEngine should remain free to reason about strategically strong novel drafts.
RiftAtlas supplies evidence, not an oracle.

## End state F: learned representation layer

Once the observation graph and evaluation discipline are trustworthy, RiftAtlas
may produce learned representations.

Candidates include:

- champion embeddings from heterogeneous relationship edges
- temporal embeddings that capture meta movement
- team-style embeddings
- graph clustering for composition/archetype discovery
- link prediction for plausible but unobserved relationships
- graph neural networks for context-conditioned relationships

Learned outputs should be versioned derived artifacts, not replacements for the
raw evidence graph.

The primary evaluation question is not "does the embedding look interesting?"
It is whether it improves a concrete downstream task without hiding leakage or
destroying interpretability.

## End state G: counterfactual draft reasoning

The most ambitious form of RiftAtlas would represent not just champion-to-
champion relationships but draft-state transitions.

A state-aware atlas could answer questions such as:

- Given everything shown so far, what branches were historically available?
- Which pick preserves the largest number of viable future compositions?
- Which ban removes the most valuable opponent branches?
- Where did a real draft become unusually constrained?
- Which unseen option is structurally similar to historically successful
  options?

At that point nodes may include draft states, roles, archetypes, teams, and
patches in addition to champions.

This is also where the boundary with a dedicated draft model becomes important.
RiftAtlas should provide graph/state evidence and reusable representations;
prediction or optimization systems can consume them without forcing all
responsibilities into one service.

## Data that may eventually enrich the atlas

Potential sources include:

- canonical professional draft artifacts
- DDragon champion/static context
- role priors
- game outcome and duration
- player and team identity
- tournament/series context
- item/rune/build context where strategically meaningful
- amateur or solo-queue data if its population is kept explicitly separate

Population boundaries matter. Professional drafting evidence should never be
silently presented as universal player behavior.

## Likely consumer ecosystem

RiftAtlas can become shared infrastructure rather than another standalone UI.

- Clairvoyance: opponent-specific tendencies and deviations from baseline.
- DraftEngine: empirical relationships and explainable continuation priors.
- Nexus: common identity/auth/orchestration surfaces if a user-facing entry
  point becomes useful.
- Future coaching/review tools: explanations of draft structure and meta
  context.

A dedicated RiftAtlas UI may be useful for exploration and debugging, but it is
not required for the project to succeed.

## Architectural properties worth preserving

Whatever end state is chosen, the following properties should remain stable:

1. Raw observations and derived claims are distinguishable.
2. Every derived claim has provenance and a versioned definition.
3. Time, patch, league, and population context are first-class.
4. Consumer contracts are versioned.
5. Historical frequency is not silently equated with strategic quality.
6. New data sources cannot silently change the meaning of existing metrics.
7. Storage technology is replaceable behind stable semantics.
8. The system can explain enough of its evidence to be useful to a human coach.

## A useful definition of success

RiftAtlas succeeds when another League tool can ask a relationship question and
receive an answer that is more useful than raw pick-rate statistics, while still
being able to explain where that answer came from.

The project does not need to reach every end state in this document to achieve
that.
