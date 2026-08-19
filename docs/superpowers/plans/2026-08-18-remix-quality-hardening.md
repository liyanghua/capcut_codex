# `remix-reference-video` Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent disconnected sell-point scripts and cropped/unreadable image shots while exposing the real quality checks and execution outputs in the existing review workbench.

**Architecture:** Add two deterministic Track-B production nodes between Gate 3 and Gate 4: one for narrative coherence and one for visual layout/readability. Both emit hash-bound V2 artifacts, block TTS/rendering when they fail, and feed a derived workbench projection. Keep Gate approvals, `pipeline_state.json`, production locks, `gb-pair`, V1 compatibility, and structured ChangeService modifications unchanged except for the explicitly defined contracts below.


> **Ledger note (2026-08-18):** the implementation slices were completed in one working session on a dirty tree (earlier uncommitted workspace rounds), so the per-slice `git commit` steps are intentionally left unchecked and should be committed together when the tree is clean.
**Tech Stack:** Python 3.11+, existing Native Runner/DAG, JSON Schema 2020-12, FFmpeg, FastAPI, vanilla JavaScript, HTML/CSS, `unittest`.

---

## Chunk 1: Contracts And Invalidation

### Task 1: Define V2 Quality Artifact Schemas

**Files:**
- Create: `.agents/skills/remix-reference-video/schemas/narrative-coherence-report.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/visual-layout-report.schema.json`
- Modify: `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/artifact_validator.py`
- Test: `.agents/skills/remix-reference-video/tests/test_artifact_contracts.py`

- [x] **Step 1: **Write failing schema tests**

  Assert both reports require `artifact_type`, `schema_id`, `schema_version`, `contract_version`, `skill_version`, `implementation_version`, `lifecycle_status`, `input_hashes`, `status`, and `report` payloads. Reject Gate approval fields recursively.

- [x] **Step 2: **Run the focused tests**

  Run: `PYTHONPATH=src python -m unittest tests.test_artifact_contracts -v`

  Expected: FAIL because the schemas and registry entries do not exist.

- [x] **Step 3: **Implement the schemas and registry entries**

  Register both artifacts as Track-B active task-local artifacts with `activation=after_g_a`, explicit schema paths, and `production_state_authority=false` where the artifact is derived. Add the two schema IDs to the registry discriminator list.

- [x] **Step 4: **Enforce envelope and input-hash validation**

  Reuse the existing validator rules for the five-field envelope, lifecycle values, task containment, SHA-256 input bindings, and recursive reserved approval-key rejection. Do not modify historical V1 artifact validation.

- [x] **Step 5: **Re-run the focused tests**

  Expected: PASS.

- [ ] **Step 6: Commit the contract slice**

  Run: `git add .agents/skills/remix-reference-video/schemas .agents/skills/remix-reference-video/src/remix_reference_video/artifact_validator.py .agents/skills/remix-reference-video/tests/test_artifact_contracts.py && git commit -m "feat: add quality hardening artifact contracts"`

### Task 2: Close Change Impact And Edit Contracts

**Files:**
- Modify: `.agents/skills/remix-reference-video/schemas/changes/copy.schema.json`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/review_view.py`
- Test: `.agents/skills/remix-reference-video/tests/test_change_service.py`
- Test: `.agents/skills/remix-reference-video/tests/test_orchestrator.py`

- [x] **Step 1: **Write failing contract tests**

  Assert copy changes accept only `edit_intent=bridge|rewrite`; reject `merge`. Assert structural changes keep `request_type=omit|merge|restructure` and always return Gate 2. Assert copy/claim/material/range/structural impact previews include the new quality nodes and their reports in stale stages and regeneration outputs.

- [x] **Step 2: **Run the focused tests**

  Run: `PYTHONPATH=src python -m unittest tests.test_change_service tests.test_orchestrator -v`

  Expected: FAIL because the schema and impact tables do not contain the new contract.

- [x] **Step 3: **Implement the edit-intent contract**

  Add `payload.edit_intent` to the V2 copy schema and service validation with enum `bridge|rewrite`. Remove `merge` from the copy UI/service path. Keep segment merging exclusively in the structural request schema and return `awaiting_gate2_revision` for it. Preserve V1 compatibility by normalizing a missing intent to `rewrite` only for tasks carrying the V1 contract.

- [x] **Step 4: **Implement deterministic invalidation closure**

  Add `build-narrative-coherence` and `validate-visual-layout` to all affected impact definitions. Prefer a helper that computes downstream node IDs from `default_dag()`; retain serialized stale lists only as audited output and fail tests when they diverge from the DAG.

- [x] **Step 5: **Re-run focused tests**

  Expected: PASS.

- [ ] **Step 6: Commit the contract slice**

  Run: `git add .agents/skills/remix-reference-video/schemas/changes/copy.schema.json .agents/skills/remix-reference-video/src/remix_reference_video/change_service.py .agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py .agents/skills/remix-reference-video/tests/test_change_service.py .agents/skills/remix-reference-video/tests/test_orchestrator.py && git commit -m "fix: bind quality nodes to change invalidation"`

## Chunk 2: Narrative Quality Node

### Task 3: Add Versioned Narrative Contract And Builder

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/narrative_coherence.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/blueprint.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/script_compile.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py`
- Test: `.agents/skills/remix-reference-video/tests/test_narrative_coherence.py`
- Test: `.agents/skills/remix-reference-video/tests/test_script_compile.py`

- [x] **Step 1: **Write failing deterministic narrative tests**

  Cover: valid ordered fragments with `narrative_role` and `required_actions`; missing role/action metadata producing `manual_review`; adjacent pure-claim fragments blocking; opening/closing requirements; forbidden/unapproved claim rejection; connector selection from `continuity_lexicon_v1`; and stable input hashes.

- [x] **Step 2: **Run the focused tests**

  Run: `PYTHONPATH=src python -m unittest tests.test_narrative_coherence tests.test_script_compile -v`

  Expected: FAIL because no narrative builder or metadata contract exists.

- [x] **Step 3: **Extend Blueprint/Content Baseline output**

  Require Gate 2 fragments to carry `narrative_role`, `required_actions`, and `narrative_contract_version="narrative_contract_v1"`. Validate the role/action enums and preserve the reference fragment order.

- [x] **Step 4: **Implement `NarrativeCoherenceBuilder.build()`**

  Read only the approved baseline, mutation fallbacks, reference blueprint, and closed evidence matrix. Assign transitions from the versioned lexicon, never add product facts, and return a complete `narrative_coherence_report` envelope with per-fragment checks, blockers, input hashes, and recovery actions.

- [x] **Step 5: **Gate script compilation on the report**

  Change `ProductionScriptCompiler.compile()` to require the current report hash and `status=passed`. Add `narrative_role`, `continuity_before`, `continuity_after`, and `coherence_status` to every production-script line. A blocked/manual report must prevent `production_script_candidate.json` from being produced.

- [x] **Step 6: **Register the native node**

  Add `build-narrative-coherence` after `summarize-gate3` and before `build-production-script`. Declare the report output and all baseline/mutation/blueprint/evidence inputs so the runner records fingerprints and hashes. Activation follows design §4.3: the node only runs when the frozen Gate 2 baseline carries `narrative_contract_v1`; in-flight V2 runs whose baseline lacks the metadata keep the old DAG unless they explicitly return to Gate 2.

- [x] **Step 7: **Re-run focused tests**

  Expected: PASS.

- [ ] **Step 8: Commit the narrative slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/narrative_coherence.py .agents/skills/remix-reference-video/src/remix_reference_video/adapters/blueprint.py .agents/skills/remix-reference-video/src/remix_reference_video/adapters/script_compile.py .agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py .agents/skills/remix-reference-video/tests/test_narrative_coherence.py .agents/skills/remix-reference-video/tests/test_script_compile.py && git commit -m "feat: add deterministic narrative coherence gate"`

## Chunk 3: Visual Layout And Readability Node

### Task 4: Implement Shared Image Layout Policy

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/media_layout.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/media_runtime.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/review_media.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py`
- Test: `.agents/skills/remix-reference-video/tests/test_media_layout.py`
- Test: `.agents/skills/remix-reference-video/tests/test_media_runtime.py`

- [x] **Step 1: **Write failing layout and rubric tests**

  Cover landscape, portrait, small, transparent, and overlay-marked images. Assert `contain`, `crop_pixels=0`, `max_upscale_factor=2.0`, `min_text_height_px=18`, and exact `passed|blocked|manual_review` outcomes. Assert the same layout calculation is used for Gate 3 review media and final rendering.

- [x] **Step 2: **Run the focused tests**

  Run: `PYTHONPATH=src python -m unittest tests.test_media_layout tests.test_media_runtime -v`

  Expected: FAIL because the renderer still hard-codes `scale=increase,crop` and review media still hard-codes `360x640`.

- [x] **Step 3: **Implement `image_layout_policy_v1`**

  Centralize source dimensions, target canvas, contain rectangle, effective scale, crop pixels, background fill, overlay policy, and readability status. Keep the policy version in the stage implementation fingerprint, not in `production_runtime_config.json`.

- [x] **Step 4: **Use the helper in all media paths**

  Replace image crop filters in `FFmpegRenderer` and `build_gate3_review_media`. Parameterize review dimensions from the same target profile used by production. Preserve existing video behavior unless the approved overlay policy requires no-crop containment.

- [x] **Step 5: **Register `validate-visual-layout`**

  Add the node after `materialize-approved-broad`, declare its report output and material/profile inputs, and make `voice-preflight` depend on the report with `status=passed`.

- [x] **Step 6: **Re-run focused tests**

  Expected: PASS.

- [ ] **Step 7: Commit the visual slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/media_layout.py .agents/skills/remix-reference-video/src/remix_reference_video/media_runtime.py .agents/skills/remix-reference-video/src/remix_reference_video/review_media.py .agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py .agents/skills/remix-reference-video/tests/test_media_layout.py .agents/skills/remix-reference-video/tests/test_media_runtime.py && git commit -m "fix: preserve complete image layout and readability"`

## Chunk 4: Workbench Quality Projection And Incremental Refresh

### Task 5: Project Execution, Quality Sources, And Early-Gate States

**Files:**
- Modify: `.agents/skills/remix-reference-video/schemas/workbench-workspace-view.schema.json`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/workspace_view.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.css`
- Test: `.agents/skills/remix-reference-video/tests/test_workspace_view.py`
- Test: `.agents/skills/remix-reference-video/tests/test_workbench_client.py`

- [x] **Step 1: **Write failing projection tests**

  Assert `process.execution[]` reads `pipeline_events.jsonl` and `stage_metrics.jsonl`; `artifacts[]` exposes approved reports and output links; `quality_checks[]` binds each result to a real source artifact; missing L1/P returns `not_available`; and Gate 1/2 storyboard rails show reference/pending states instead of an empty misleading state.

- [x] **Step 2: **Run focused projection tests**

  Run: `PYTHONPATH=src python -m unittest tests.test_workspace_view tests.test_workbench_client -v`

  Expected: FAIL because the projection schema and builder do not expose these fields.

- [x] **Step 3: **Extend the workspace schema and builder**

  Add typed `process.execution`, `artifacts`, and `quality_checks` fields. Map L0 from `final_validation_report.hard_gate_checks`, P from `render_report.production_audit` when present, and L1 only from a Track-C/quality-scorecard artifact. Never synthesize missing values.

- [x] **Step 4: **Add quality artifacts to Gate-specific allowlists**

  Expose each new report only from the Gate where it is valid, bind media references through the current workspace authorizer, and keep future artifacts hidden from Gate 1/2.

- [x] **Step 5: **Implement business rendering**

  Render execution nodes, report status, source artifact, blocking reason, and next action in the right rail or expandable diagnostics. Keep the central stage preview fixed and preserve current source-range timeline behavior.

- [x] **Step 6: **Re-run focused tests**

  Expected: PASS.

### Task 6: Replace Full Reload With Incremental Workspace Refresh

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.css`
- Test: `.agents/skills/remix-reference-video/tests/test_workbench_client.py`
- Test: `.agents/skills/remix-reference-video/tests/test_workbench_layout.py`

- [x] **Step 1: **Write failing client tests**

  Assert a higher `state_revision` fetches `/workspace` and re-renders affected sections without calling `location.reload()`. Preserve `state.media.currentTime`, `state.selected`, timeline selection, and open detail state.

- [x] **Step 2: **Run the focused client tests**

  Run: `node .agents/skills/remix-reference-video/tests/client_workbench_harness.js`

  Expected: FAIL because the current client reloads the page on every higher revision.

- [x] **Step 3: **Implement incremental re-rendering**

  Add a refresh function that snapshots playback/selection state, fetches `/workspace`, updates rail/timeline/stepper/stage content/diagnostics, restores the snapshot when the current media remains valid, and only resets media when the preview reference changes.

- [x] **Step 4: **Replace brittle layout assertions**

  Change `test_workbench_layout.py` from broad string checks to selector/property checks for the preview container, three-column overflow isolation, and narrow viewport scroll behavior.

- [x] **Step 5: **Re-run client and syntax checks**

  Run: `node --check .agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js && node .agents/skills/remix-reference-video/tests/client_workbench_harness.js`

  Expected: PASS.

## Chunk 5: Documentation, Regression, And Acceptance

### Task 7: Synchronize Plans And Run Full Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-08-18-remix-quality-hardening-design.md`
- Modify: `docs/superpowers/specs/2026-08-18-business-video-workbench-design.md`
- Modify: `docs/superpowers/plans/2026-08-18-business-video-workbench.md`
- Modify: `docs/review-workbench-workspace-acceptance-2026-08-18.md`
- Modify: `.agents/skills/remix-reference-video/README.md`
- Test: `.agents/skills/remix-reference-video/tests/`

- [x] **Step 1: **Update the workbench plan ledger**

  Record the already implemented Gate-specific media allowlist, rejected/blocked/stale approval predicate, `source_range` timebase, fixed-preview selection, and layout regression tests. Add the remaining execution/quality projection and incremental-refresh tasks as unchecked.

- [x] **Step 2: **Update artifact and output documentation**

  Add both quality reports, their Gate placement, V2 envelope, invalidation behavior, and the L0/L1/P source rules to the Skill README and workbench acceptance document.

- [x] **Step 3: **Run the full suite**

  Run: `PYTHONPATH=src python -m unittest discover -s tests -q`

  Expected: `Ran 274+ tests` with only documented optional skips and `OK`.

- [x] **Step 4: **Run static checks**

  Run: `node --check src/remix_reference_video/static/review_workbench.js && git diff --check && python -m compileall -q src`

  Expected: all commands exit 0.

- [ ] **Step 5: Run isolated `gb-pair` verification**

  Use a fresh pair directory and frozen inputs. Verify both sides stop at the new machine quality checks when blocked, proceed to TTS only when both reports pass, and never reuse approvals or shared production cache.

- [ ] **Step 6: Perform manual workbench acceptance**

  Check 1440px and 390px viewports, Gate 1/2 pending rails, Gate 3 source-range timeline, Gate 4 quality reports, Gate 5 actual quality sources, incremental refresh, and legacy rollback. Record evidence in `docs/review-workbench-workspace-acceptance-2026-08-18.md`.

- [ ] **Step 7: Commit the documentation and acceptance slice**

  Run: `git add docs .agents/skills/remix-reference-video/README.md .agents/skills/remix-reference-video/tests && git commit -m "docs: plan remix quality hardening and acceptance"`
