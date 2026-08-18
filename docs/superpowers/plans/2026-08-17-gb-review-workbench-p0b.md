# G-B Review Workbench P0b Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a localhost-only, auditable seven-Gate review workbench where an operator can approve, reject, request a change, see exactly what the change invalidates, and apply the confirmed request without bypassing `pipeline_state.json` or the production lock.

**Architecture:** Deterministic view builders read current Gate packages and task artifacts into a canonical `gate_review_view` and derived HTML/Markdown. Write actions use actor-bound review sessions and delegate decisions to `ApprovalService`; changes share one validator between dry-run and commit, write immutable change-request artifacts, and propagate stale state through `TransactionManager`. `create_app()` exposes the same services on `127.0.0.1`; it does not own a second Gate state machine.

**Tech Stack:** Python 3.12, stdlib HTML/JSON, Draft 2020-12 schemas, existing `TaskStorage`/`ApprovalService`/`TransactionManager`, optional FastAPI/Uvicorn, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-17-gb-review-workbench-quality-design.md`

---

## Chunk 1: Canonical Review And Change Contracts

### Task 1: Register Review And Change Schemas

**Files:**
- Create: `.agents/skills/remix-reference-video/schemas/gate-review-view.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/gate-review-sheet.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/changes/*.schema.json`
- Modify: `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`
- Modify: `.agents/skills/remix-reference-video/tests/test_snapshot_schema_validator.py`

- [ ] Write failing tests proving `gate_review_view` requires current run/gate/package/revision/business summary/actions/evidence/risk/impact metadata and that each of eight change types has a registered schema.
- [ ] From `.agents/skills/remix-reference-video`, run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_snapshot_schema_validator.py' -v`; expect schema/registry failures.
- [ ] Add full schemas. Change inputs live under `x-input-contracts`; only view/sheet enter the artifact enum. Preserve Track A filtering and production locks.
- [ ] Re-run the focused test and `python3 track_a_static_check.py`; expect PASS.
- [ ] Commit the contract slice.

### Task 2: Build Deterministic Seven-Gate Views And Static Fallback

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/review_view.py`
- Create: `.agents/skills/remix-reference-video/tests/test_review_view.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Modify: `.agents/skills/remix-reference-video/README.md`

- [ ] Write failing fixtures for all seven canonical Gates, revision diff, missing evidence, stale state, and byte-identical repeated HTML/Markdown output. Prove a production package build registers the derived view/sheet paths and hashes in the same state revision that makes the package await review.
- [ ] From `.agents/skills/remix-reference-video`, run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_review_view.py' -v`; expect import failure.
- [ ] Implement `ReviewViewBuilder.build(gate_id)` and `write_snapshot(gate_id)`. Use fixed business metadata and artifact allowlists; never infer claims or write approval state. Integrate generation into the package-build completion transaction so current views are registered without a second revision that would stale the package; legacy CLI generation remains explicitly unregistered recovery output.
- [ ] Add `workbench-build-review --task-dir --gate --json` as the static/CLI recovery path.
- [ ] Verify focused tests and commit.

## Chunk 2: Trusted Decisions And Change Transactions

### Task 3: Add Actor-Bound Review Sessions And Timing Events

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/review_session.py`
- Create: `.agents/skills/remix-reference-video/tests/test_review_session.py`

- [ ] Write failing tests for opaque session IDs, startup actor binding, current run/gate/package/revision identity, trusted event timestamps, 60-second heartbeat expiry, and cross-run/session rejection.
- [ ] From `.agents/skills/remix-reference-video`, run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_review_session.py' -v`; expect import failure.
- [ ] Implement immutable session files under `workbench/sessions/` and append only canonical review event intents through `TaskStorage.append_event`.
- [ ] Verify tests and commit.

### Task 3a: Measure Canonical Review Events From Trusted Time

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/process_assessment.py`
- Create: `.agents/skills/remix-reference-video/tests/test_process_assessment.py`

- [ ] Write failing event-to-assessment tests using only server `occurred_at`: package-ready to first evidence interaction is human wait; active start/heartbeat/stop intervals clipped to the window from first evidence interaction through decision submission are operator touch; first evidence to accepted decision is decision time; applied change to `review.rework_completed` is rework time; returns are counted once. Client `seconds`/`at_seconds` payloads must be ignored.
- [ ] From `.agents/skills/remix-reference-video`, run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_process_assessment.py' -v`; expect timing failures.
- [ ] Implement timestamp parsing, session/gate grouping, interval closure, event ID dedupe, and explicit `not_measured` reasons for missing boundaries.
- [ ] Verify focused tests and commit.

### Task 4: Adapt Workbench Decisions To ApprovalService

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/workbench_decision.py`
- Create: `.agents/skills/remix-reference-video/tests/test_workbench_decision.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`

- [ ] Write failing tests for approve/reject/request-changes mappings, B0 scope mapping, startup actor override, stale hash/revision conflict payloads, idempotency replay/conflict, and event ordering.
- [ ] From `.agents/skills/remix-reference-video`, run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_workbench_decision.py' -v`; expect import failure.
- [ ] Implement a thin service that validates the session/current package, records `review.decision_submitted`, calls `ApprovalService`, then records accepted/conflicted. It must not directly patch state.
- [ ] Add a CLI fallback `workbench-decide` using the same service.
- [ ] Verify tests and commit.

### Task 4a: Register Frozen Runs Before Change Jobs

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/run_registry.py`
- Create: `.agents/skills/remix-reference-video/tests/test_run_registry.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`

- [ ] Write failing tests for atomic revisioned registration, duplicate run rejection, path/symlink containment, frozen-input hash drift, stale mapping conflicts, explicit audited repair, and restart reads.
- [ ] From `.agents/skills/remix-reference-video`, run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_run_registry.py' -v`; expect import failure.
- [ ] Implement `workbench-register-run` and `workbench-repair-run`. Neither command infers a run from directory names; each requires an explicit task path, validates authoritative state plus frozen snapshot, and appends a registry audit record.
- [ ] Integrate explicit registration into `gb-pair` setup for newly created sides only; existing unregistered runs require the command and are never silently repaired.
- [ ] Verify focused tests and commit.

### Task 5: Preview And Apply Structured Changes

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Create: `.agents/skills/remix-reference-video/tests/test_change_service.py`

- [ ] Write failing tests for all eight payload shapes, fixed earliest-Gate/stale/artifact/media mappings, containment of range edits, claim and line allowlists, preview hashing, P50/P90 only with at least three comparable samples, stale preview rejection, actor/session/run binding, idempotency conflict, concurrent revision conflict, staging rollback, and `review.change_previewed`/`change.applied` ordering.
- [ ] From `.agents/skills/remix-reference-video`, run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_change_service.py' -v`; expect import failure.
- [ ] Implement `ChangeImpactAnalyzer.preview()` and `ChangeService.apply()`. Preview and apply share the same validator. Apply atomically promotes an immutable request plus the appropriate validated `stage_inputs/` override, marks only prescribed Gates/stages stale, recalculates Gate 3/4 aggregates, appends `change.applied`, and creates a durable job. Structural changes only create the Gate 2 request and never execute a local structural patch.
- [ ] Add `WorkbenchOrchestrator.resume_job(job_id)` with an explicit frozen `gb-pair` run-registry guard. It may invoke `ProductionRunner.run(resume=True)` only for a registered cold/hot task whose frozen-input hash still matches. Ordinary production, shared cache, archive, and manifest lock are never changed. On success it writes `review.rework_completed`; on failure it preserves the audited request/stale state and writes a retry command.
- [ ] Implement change materialization before resume: copy/voice edits produce validated candidate or stage-input revisions; material/range edits revise the unapproved selection candidate and rebuild the Gate 3 package; rerecord resumes at voice generation; boundary resumes at proxy/render review; claim/structural requests return to Gate 2. Approved immutable artifacts are retained and superseded by newly generated versions after the required Gate.
- [ ] Dispatch the durable job immediately after the change transaction through a bounded local worker; a process restart can resume the same pending job idempotently. Add an end-to-end fixture proving `submit change -> persisted job -> guarded resume -> affected package regenerated -> review.rework_completed -> awaiting_user`, including a restart between job creation and resume.
- [ ] Verify no approved broad-range artifact is overwritten, preview runs no adapter, ordinary Track-B tasks cannot resume, and the manifest/lock/shared cache hashes remain unchanged.
- [ ] Verify focused tests and commit.

## Chunk 3: Local API, Media, And Operational Proof

### Task 6: Add Run Registry And Local Workbench API

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/api.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_api.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/templates/review_workbench.html`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.css`

- [ ] Write failing tests for review/session endpoints, decision/change endpoints, a review-event intent endpoint, ETag, byte ranges including 416, media allowlist/containment/symlink rejection, SSE resume, and an HTML workbench route containing working approve/reject/request-change controls.
- [ ] From `.agents/skills/remix-reference-video`, run `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_api.py' -v`; expect route/helper failures.
- [ ] Implement `/api/v1/runs/...` endpoints over the pre-existing registry. Add `POST /api/v1/runs/{run_id}/review-session/events` accepting only canonical event intents. Add `/workbench/runs/{run_id}` with a real client that loads the current review, plays allowlisted media, emits opened/active/evidence/heartbeat/pause intents, submits decisions, opens a structured change form, displays the server-computed impact, requires confirmation, and refreshes authoritative state on SSE/conflict. Server actor and role are constructor/CLI inputs; request actor is ignored/rejected as authority. Keep existing `/tasks` API compatible.
- [ ] Add `workbench-serve --workspace-root --actor --host 127.0.0.1 --port` and reject non-loopback hosts.
- [ ] Verify tests and commit.

### Task 7: Complete P0b Regression And Real-Task Static Proof

**Files:**
- Create: `docs/review-workbench-manual-acceptance.md`
- Update: `.agents/skills/remix-reference-video/README.md`

- [ ] Run the full Skill suite and Track A static check.
- [ ] Generate static snapshots from a real frozen task without invoking TTS/FFmpeg or mutating state/media; record pre/post hashes.
- [ ] Manually inspect the generated HTML/Markdown and interactive page source/data flow. Browser screenshot automation remains excluded per user direction, but the page controls and API calls must be exercised through service/API tests.
- [ ] Document localhost startup, CLI fallback, six state cases, seven Gate checks, conflict recovery, and remaining P0c supervised-run requirements.
- [ ] Commit and request final code review.
