# 工作台项目初始化与 Stage 0 Implementation Plan

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator create and freeze a new `remix-reference-video` V2 project through the local workbench without a long prompt, then start its isolated cold side at Gate 1.

**Architecture:** Add a focused `project_initialization.py` service that owns draft persistence, local-path validation, Stage 0 staging, freeze, and project lifecycle. Keep frozen input separate from Track-B cold/hot runs. Extend the existing FastAPI workbench with project APIs and a macOS picker bridge, then add a small vanilla-JS project list, form, and Stage 0 confirmation surface. The creative DAG receives its Blueprint handoff only after the existing Gate 1 approval selects a decomposition.

**Tech Stack:** Python 3.14, FastAPI, stdlib `subprocess`/`osascript`, JSON Schema, existing `AssetIndexer`/`RunRegistry`/`gb-pair`, vanilla HTML/CSS/JavaScript, unittest and Node client harness.

---

## Chunk 1: Contracts and Safe Inputs

### Task 1: Register Stage 0 artifacts and validate project inputs

**Files:**
- Create: `.agents/skills/remix-reference-video/schemas/project-initialization-draft.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/stage0-report.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/material-evidence-annotations.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/material-evidence-requirements.schema.json`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/project_initialization.py`
- Modify: `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/artifact_validator.py`
- Test: `.agents/skills/remix-reference-video/tests/test_project_initialization.py`

- [ ] **Step 1: Write failing schema and validator tests**

  Cover strict five-field envelope, `production_state_authority=false`, no approval-shaped fields, draft claim de-duplication, NFC/whitespace normalization, stable claim IDs, absolute task-name validation, and rejecting relative/symlink/unreadable reference or asset root paths. Add audit/idempotency tests for replay/conflict, lifecycle state transitions, and two project IDs competing for one task name.

- [ ] **Step 2: Run the focused test module**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_initialization -q`
  Expected: FAIL because the artifacts and initialization service do not exist.

- [ ] **Step 3: Implement schemas and `ProjectInitializationStore`**

  Store drafts only under `<workspace>/workbench/projects/<project_id>/`. Use `draft_revision` optimistic concurrency, file locks, idempotency records and immutable audit JSONL; normalize `"无"` to `[]`; reject names outside `[a-z0-9][a-z0-9-]{0,63}`. Add a single containment helper for absolute path and no-symlink validation, plus atomic task-root reservation so two projects cannot create the same `work/YYYY-MM-DD-task/` target.

- [ ] **Step 4: Register and validate non-authoritative artifacts**

  Add draft/report/`material_evidence_requirements`/`material_evidence_annotations` to registry enum, `oneOf`, and `x-artifacts` with strict schema paths and `production_state_authority:false`. Add validator entry points which recursively reject approval-shaped fields from all four non-authoritative artifacts and bind every evidence annotation to an existing technical asset hash/source path.

- [ ] **Step 5: Run focused tests and static registry guard**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_initialization tests.test_artifact_contracts -q && .venv/bin/python track_a_static_check.py`
  Expected: PASS.

### Task 2: Version recursive frozen asset snapshots safely

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/gb_frozen_case.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/run_registry.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/path_contracts.py`
- Test: `.agents/skills/remix-reference-video/tests/test_gb_frozen_case.py`
- Test: `.agents/skills/remix-reference-video/tests/test_run_registry.py`

- [ ] **Step 1: Write failing tests for `relative_path_v1` snapshots**

  Require recursive relative POSIX keys, reject absolute paths, `.`/`..`, backslashes and any symlink path component; require legacy snapshots with no contract marker to preserve the existing direct-child rule.

- [ ] **Step 2: Run targeted tests**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_gb_frozen_case tests.test_run_registry -q`
  Expected: FAIL on the new nested-path cases.

- [ ] **Step 3: Implement the shared relative-path resolver**

  `resolve_asset_snapshot_path(asset_root, key, contract_version)` must return a regular file below root without following symlinks. Reuse it in `validate_frozen_input()` and `RunRegistry._validate_task()`; retain legacy behavior when `asset_snapshot_contract_version` is absent.

- [ ] **Step 4: Verify regression and commit chunk**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_gb_frozen_case tests.test_run_registry tests.test_project_initialization -q`
  Expected: PASS.

  Commit: `feat: add stage0 input contracts`

## Chunk 2: Stage 0 Service and Creative Handoff

### Task 3: Build transactional Stage 0 preflight and freeze

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/project_initialization.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/gb_frozen_case.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/runtime_resolver.py`
- Test: `.agents/skills/remix-reference-video/tests/test_project_initialization.py`
- Test: `.agents/skills/remix-reference-video/tests/test_runtime_resolver.py`

- [ ] **Step 1: Write failing service tests**

  Test Stage 0 creates only a private report plus `frozen-input` candidate files, copies exactly one reference, builds recursive technical `asset_profiles.json`, and never writes `pipeline_state.json`, Gate packages, TTS or derived media. Assert no product/semantic/action/score facts are invented and freeze converts normalized claim text into stable `{claim_id,text}` objects. Test cancellation, staging cleanup, frozen-root collisions, freeze rehash/input-changed, and same-key idempotence.

- [ ] **Step 2: Run the focused service tests**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_initialization -q`
  Expected: FAIL until the Stage 0 methods exist.

- [ ] **Step 3: Implement `run_stage0()` and `freeze()`**

  Scan into `<project>/.staging/<request_id>/`, invoke existing technical probing only for source facts, and atomically promote to a reserved `work/YYYY-MM-DD-<task>/frozen-input/`. Write canonical JSON Brief plus human YAML copy, including stable claim objects. Freeze validates current hashes, writes only the frozen snapshot and advances project lifecycle; it never creates a run. Technical profiles omit business fields rather than writing fabricated values.

- [ ] **Step 4: Add isolated cold launch adapter**

  Implement a server-owned `RuntimeResolver` that reads a fixed workspace configuration for the trusted Doubao client and Python executable without putting secrets or client paths in drafts/frozen inputs. Test configured, missing and invalid resolver states. `start_cold()` must return `runtime_unavailable` before creating any pair root when resolution fails; otherwise call `run_gb_pair()` with explicit frozen/cold/hot roots, `--creative-contract v1`, no decision directory, and no approval reuse. Return the cold run only after runner initialization and `RunRegistry.ensure_registered()` succeeds.

- [ ] **Step 5: Verify service behavior**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_initialization tests.test_runtime_resolver tests.test_gb_frozen_case tests.test_cli -q`
  Expected: PASS.

### Task 4: Materialize approved Gate 1 decomposition for Blueprint

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/decomposition_handoff.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_planning.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_preparation.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/approvals.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/stage_input_validator.py`
- Test: `.agents/skills/remix-reference-video/tests/test_decomposition_handoff.py`
- Test: `.agents/skills/remix-reference-video/tests/test_orchestrator.py`

- [ ] **Step 1: Write failing Gate 1 handoff tests**

  Require package binding to candidate-set/bundle hash and strategy metadata without a default selected ID. Use real `ApprovalService` to approve candidate #2, then assert only that decision record yields both handoffs. Cover unknown selection, state forgery, bundle drift, missing claims, stale closure, and native registry/DAG completeness.

- [ ] **Step 2: Run focused handoff tests**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_decomposition_handoff tests.test_orchestrator -q`
  Expected: FAIL because the node and dependencies are absent.

- [ ] **Step 3: Implement deterministic handoff production**

  Remove candidate-0 prebinding from the Gate 1 package while retaining bundle/strategy integrity. Make ApprovalService validate the submitted `selected_decomposition_id` against the current bundle and persist it only in the current approval decision. `materialize-approved-decomposition` reads only that decision, the current bundle, Brief and strategy registry; it emits registered current hash-bound StageInputs. Convert only approved decomposition facts plus frozen `approved_claims` to fragments, roles and actions; never infer claims or assets. Register the native adapter, StageInputValidator and ChangeService closure; make creative `build-coverage-precheck` depend on it and `compile-blueprint` consume only its handoff.

- [ ] **Step 4: Verify creative-DAG compatibility and commit chunk**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_decomposition_handoff tests.test_orchestrator tests.test_production_runtime -q`
  Expected: PASS.

  Commit: `feat: initialize creative projects safely`

## Chunk 3: Local APIs and Workbench UI

### Task 5: Add honest Gate 3 material evidence annotations

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/material_evidence.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/retrieval.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_planning.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/runner.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/workspace_view.py`
- Test: `.agents/skills/remix-reference-video/tests/test_material_evidence.py`
- Test: `.agents/skills/remix-reference-video/tests/test_retrieval.py`
- Test: `.agents/skills/remix-reference-video/tests/test_runner.py`

- [ ] **Step 1: Write failing annotation and retrieval tests**

  Assert `build-material-evidence-requirements` deterministically reports the evidence fields missing for every Gate 2 target and writes a previewable candidate list. A technical profile without a current annotation must yield `manual_classification_required`, pause the run at `collect-material-evidence`, and remain resumable without creating a Gate 3 package. Assert a schema-valid annotation with matching requirements/profile hash and source path/hash is the only way to expose product/semantic/action evidence to retrieval; mismatched hash, unreviewable evidence window, duplicate asset annotation, or annotation change fails closed/stales Gate 3.

- [ ] **Step 2: Run the evidence tests**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_material_evidence tests.test_retrieval -q`
  Expected: FAIL because annotations are not yet an input.

- [ ] **Step 3: Implement annotation merge without rewriting Stage 0 facts**

  `material_evidence.py` builds and validates `material_evidence_requirements.json`, then merges only a current `material_evidence_annotations.json` with technical profiles. Add `build-material-evidence-requirements` between Gate 2 lint and authoritative coverage in the creative DAG. A dedicated recoverable runner result records `active_stage=collect-material-evidence`, one replaceable `manual_classification_required` blocker and `next_actions=["submit_material_evidence"]`; it must not mark the stage permanently failed/blocked or advance downstream nodes. Retrieval uses the merged projection for qualification and package evidence, but preserves the original Stage 0 profile file unchanged. Register both artifacts in native planning and ChangeService stale closure; Gate 3 package records requirements/annotation hashes and explicit blocker labels.

- [ ] **Step 4: Verify the Stage 0-to-Gate 3 boundary**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_project_initialization tests.test_material_evidence tests.test_retrieval tests.test_runner -q`
  Expected: PASS, including no-fabrication, deterministic blocker, no premature Gate 3 package, and resume-from-requirements cases.

### Task 6: Expose localhost-only project APIs and macOS picker

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/api.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/project_initialization.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/material_evidence.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/local_session.py`
- Test: `.agents/skills/remix-reference-video/tests/test_api.py`
- Test: `.agents/skills/remix-reference-video/tests/test_project_initialization.py`

- [ ] **Step 1: Write failing API tests**

  Cover `GET /workbench`, `/workbench/projects/new`, and `/workbench/projects/{id}/stage0`; draft save/list/read, revision conflict, Stage 0 result, freeze, start-cold response, back navigation, and `POST /api/v1/projects/path-validation` status values (`valid`, `missing`, `not_readable`, `unsupported`, `symlink`, `scan_error`). Cover `POST /api/v1/runs/{run_id}/material-evidence`: current operator ownership, requirements/profile hash preconditions, idempotent replay/conflict, atomic annotation/audit writes, stale input rejection, and automatic durable resume from `build-material-evidence-requirements`. Test remote peer rejection, forged/missing Origin, missing/wrong/replayed nonce, fixed picker modes only, macOS picker unavailability, and manual path fallback.

- [ ] **Step 2: Run API tests**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_api tests.test_project_initialization -q`
  Expected: FAIL for the missing routes.

- [ ] **Step 3: Implement route layer and picker bridge**

  Keep `api.py` as routing only. `LocalSessionStore` issues a TTL-bound, one-use nonce ID in an HttpOnly/SameSite=Strict cookie and injects the nonce into each local project page meta tag; its guard checks actual loopback peer, fixed Host/Origin, cookie ID, nonce and replay. Every successful protected response returns `next_nonce`; the client replaces its token before the next request. Put `osascript` invocation in the initialization service with fixed scripts for video file and directory selection, `shell=False`, no caller-supplied command values, and structured unavailable/cancelled states. Route evidence submissions through a dedicated `MaterialEvidenceService`; after a successful atomic write it clears only the matching replaceable blocker, resets the requirements node and downstream stage cache/statuses, and invokes the existing registered production runner with `resume=True` until the next human Gate or another recoverable evidence pause.

- [ ] **Step 4: Add project-list and initialization page templates**

  Add the three routed templates, `project_initialization.js`, and `project_initialization.css`. Render all buttons with real behavior: native picker, nonce-protected blur-time manual path validation, claim add/remove, draft save, Stage 0 polling, validation errors, Brief confirmation and cold launch. No browser upload control is used as a path authority.

- [ ] **Step 5: Run API and client syntax verification**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_api tests.test_project_initialization -q && node --check src/remix_reference_video/static/project_initialization.js`
  Expected: PASS.

### Task 7: Wire navigation and protect existing run workbench

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/templates/review_workbench.html`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js`
- Create: `.agents/skills/remix-reference-video/tests/client_project_initialization_harness.js`
- Modify: `.agents/skills/remix-reference-video/tests/test_workbench_client.py`
- Test: `.agents/skills/remix-reference-video/tests/test_api.py`

- [ ] **Step 1: Write failing DOM contract tests**

  Assert every initialization action has a handler, the page uses only server-returned picker paths, blur-time validation renders structured errors, Stage 0 status preserves completed data on temporary API errors, and existing completed-run readonly fallback remains intact. For `collect-material-evidence`, assert the run workbench shows candidate thumbnails, per-target missing fields, product/semantic/action/overlay inputs and evidence frame/time-window controls; submission uses only the current requirements/profile hashes, explains validation failures, and preserves edits across temporary API errors.

- [ ] **Step 2: Run client tests**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_workbench_client tests.test_api -q`
  Expected: FAIL until the initialization harness/page is wired.

- [ ] **Step 3: Implement minimal navigation and client state**

  Add a “新建项目” route/link without changing run review APIs. On a successful cold launch, navigate only to the returned registered cold `run_id`; never construct a run URL from user task input. Extend the existing run projection only for the `collect-material-evidence` state and submit annotations through the protected API; do not render approve/reject controls until the real Gate 3 package exists.

- [ ] **Step 4: Verify full UI contract and commit chunk**

  Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_workbench_client tests.test_api tests.test_project_initialization -q && node --check src/remix_reference_video/static/review_workbench.js && node --check src/remix_reference_video/static/project_initialization.js`
  Expected: PASS.

  Commit: `feat: add workbench project initialization`

## Chunk 4: Documentation, Regression, and Manual Acceptance

### Task 8: Document startup workflow and prove regressions

**Files:**
- Modify: `.agents/skills/remix-reference-video/README.md`
- Modify: `AGENTS.md`
- Modify: `docs/review-workbench-manual-acceptance.md`
- Modify: `docs/superpowers/plans/2026-08-20-workbench-project-initialization.md`

- [ ] **Step 1: Update operator documentation**

  Describe project-list entry, Stage 0/freeze/cold split, macOS picker and manual fallback, no media before Gate 1, and the current `gb-pair` production lock.

- [ ] **Step 2: Execute complete automated verification**

  Run: `cd .agents/skills/remix-reference-video && PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q && node --check src/remix_reference_video/static/review_workbench.js && node --check src/remix_reference_video/static/project_initialization.js && .venv/bin/python -m compileall -q src && git diff --check`
  Expected: all commands exit 0.

- [ ] **Step 3: Perform manual operator acceptance**

  Verify at 1440px and 390px: save a draft; select a reference and source directory; use manual paths; view blocked and successful Stage 0; cancel scanning; exercise duplicate task-name, stale report/input-changed and runtime-unavailable states; confirm Brief; verify frozen input has no state file; launch cold and open its Gate 1 page. Record any issue without approving a Gate.

- [ ] **Step 4: Commit final documentation and acceptance evidence**

  Commit: `docs: document workbench project initialization`
