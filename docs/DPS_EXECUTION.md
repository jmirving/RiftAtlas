# DPS standalone service execution

Status: independent service implementation ready for draft review; real-snapshot
validation and deployment blocked, November 3, 2026.

## Scope and baseline

Implementation follows `DPS-Standalone-Web-Service-Plan.md`, Library file
`libfile_8e7ba89c2b188191bef3bdce69e2a72b`. The entire 186-line plan was read
through Library. Its required local materialization failed with
`library file transfer failed: download failed`; a readable local copy has not
been verified. Follow-up authorization explicitly permits implementation from
the complete Library read and test-only fixtures, without treating the missing
snapshot as a blocker to independent API/frontend work.

The isolated branch is `feat/dps-standalone-service`, based on current main
`6a441fca999225f0e2c1af1eaddc81971156e3ec`. Only feature branches are authorized
until final approval. No merge, production deployment, existing Render resource
modification, or credential-access expansion is part of this work.

Baseline validation on that revision:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

All 43 tests passed in 3.050 seconds. These include whole-pinned-composition
evidence, exact versus pairwise support, role constraints, missing role data,
patch/league filters, and explicitly empty league selection. Existing explorer
code and calculations remain unchanged.

Issues #2 and #9 remain open. Existing tests cover their described constrained
role assignments and explorer overlays; issue reconciliation should cite those
tests and include browser verification before claiming full acceptance.

## Snapshot gate

The required input is a real, attributable schema-version-1 canonical draft CSV
produced by `jmirving/lol-pro-data-processor`. Synthetic test inputs are not a
deployment substitute.

Checks completed:

- The processor checkout documents canonical drafts and its provenance source.
- No real draft CSV was found in the processor, downloader, refresh-orchestrator,
  or shared workspace paths inspected. The processor CSV under test resources
  is a test fixture, not an acceptable production snapshot.
- GitHub returned no published processor releases and no Actions artifacts for
  the processor or refresh orchestrator.
- Running the existing downloader executable for 2026 with manifests and JSON
  output failed with `DOWNLOAD_FAILED` / `ConnectException`, including an
  approved elevated execution attempt.
- A request to its documented public Google Drive source returned
  `403 Forbidden` from the execution environment's CONNECT proxy. This is an
  access blocker, not evidence that the source dataset is empty.

No production snapshot or provenance manifest was fabricated. Real-data load
time, peak memory, and query timings remain unmeasured.

## Independent implementation completed

- Extracted the existing query calculations intact into `relationships.py`;
  kept the legacy explorer import and CLI working.
- Added startup validation for schema/checksum/coverage/provenance and optional
  role mappings, with immutable per-process index initialization and no fallback.
- Added FastAPI/Uvicorn service, readiness, three versioned read-only endpoints,
  bounded queries, consistent 400s, generic 500s, and public dataset IDs.
- Added DPS branding, versioned frontend requests, provenance panel, loading
  and failure states, and cancellation/generation guards for superseded queries.
- Added resolved runtime/test dependency locks, Python runtime pin, API/setup
  guides, and CI for the lightweight core plus installed service/browser tests.
- Synthetic temporary fixtures are visibly marked `test_only`; default startup
  rejects them. Tests opt in through an explicit loader injection only.

Verification: the expanded unit/API suite, installed-wheel validation, and
Chromium smoke flow cover engine equivalence, errors/readiness, source metadata,
pinning/following with preserved viewport, evidence inspection, filter changes,
empty scope, stale responses, and failure feedback. These are test-only checks,
not real-source acceptance or production performance measurements.

To unblock, provide an accessible processor artifact and producing revision,
or restore access to the downloader's existing public source. Do not retrieve
or broaden unrelated production credentials. Then:

1. Produce/obtain the canonical CSV, recording processor revision, artifact ID,
   original source URL/notices, retrieval and generation timestamps, checksum,
   observed dates, game count, patches, and leagues.
2. Validate the consumer contract and record startup/memory/query measurements.
3. Commit snapshot and manifest together on this feature branch (the existing
   `data/` ignore rule must be narrowed when adding the real release files).
4. Run the independent implementation against the real snapshot, then complete
   isolated QA provisioning and verification before final approval.

## QA and Render decision

Read-only inspection confirmed Joseph's Workspace is accessible and currently
has no RiftAtlas/DPS service. No Render resources were created or changed.

The initial candidate is a **new** free Python web service named `dps-qa`,
explicitly linked to `feat/dps-standalone-service`, with one Uvicorn worker,
bundled immutable data, `/healthz`, and deployment only after checks pass.
Create it only after the application and real snapshot can start and the
resource measurements support the free instance. Use no production env groups,
credentials, databases, disks, or application dependencies. This gives a
separate QA service without touching existing services.

Render's [service previews](https://render.com/docs/service-previews) can run
on free web services. PR previews apply to PRs **against the service's linked
branch**: a QA service linked to this feature branch will preview child PRs
targeting this feature branch, not automatically this branch's PR against main.
Use the directly branch-linked QA service for the initial review. Consider
manual service previews on the new QA service for subsequent child branches.

Full [preview environments](https://render.com/docs/preview-environments)
require a Pro workspace plan or higher. They are unnecessary for this
single-service launch; no workspace upgrade is proposed or authorized here.

[Free service limits](https://render.com/docs/free), checked November 3, 2026:

- Web services sleep after 15 minutes idle; wakeup is about a minute plus app
  initialization. No always-on availability promise.
- The workspace shares 750 free instance hours per month. Existing free
  services also use that allowance; exhaustion suspends free services.
- Builds and bandwidth consume shared allowances and can incur overage charges.
  Check available allowance/spend controls before creating the service; disclose
  any unavoidable cost before proceeding. Do not alter existing workspace or
  service settings to make room.
- Runtime filesystem changes are ephemeral. Bundle the snapshot in the release;
  no database or paid disk is necessary for the proposed architecture.

QA publication, browser smoke verification, cold-start/restart checks,
two-user measurements, and any final production approval remain pending.
