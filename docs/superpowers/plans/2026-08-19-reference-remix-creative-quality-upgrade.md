# Reference Remix Creative Quality Upgrade Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the reference-video remix pipeline from "auditable generation" to "objective-driven, strategy-comparable, quality-evaluable, locally reworkable" per `docs/superpowers/specs/2026-08-19-reference-remix-creative-quality-upgrade-design.md`, without weakening Gate approvals, `pipeline_state.json` authority, `gb-pair` isolation, or the ordinary V2 production lock.

**Architecture:** Add a creative contract layer on top of the implemented hardening DAG: versioned decomposition strategies selected at Gate 1, a `creative_objective.json` plus remix-strategy candidates atomically approved at Gate 2, generative script candidates validated and selected before Gate 4 pre-generation, shot-level and final content diagnostics around Gate 5, an optional on-demand shot enhancement path that returns through Gate 3, and a workbench "key artifacts" projection. Everything is hash-bound, candidate artifacts never carry approval, and legacy runs never switch DAGs silently.

**Review rulings adopted (2026-08-19, owner-confirmed):**

1. **Timing model:** keep the implemented interval model (`review.active_start/active_stop/heartbeat/pause/evidence_interaction`; `decision_seconds = decision_accepted - evidence_first_interaction`). Section 11.2 of the 08-19 design is amended to reference this model; the tick-based event names (`review.session_started`, `review.visibility_changed`, `review.activity`, `review.active_tick`) are NOT implemented. G-B decision-time thresholds (300/180/120 s) stay bound to the implemented口径.
2. **Compatibility marker:** single capability marker `creative_contract_version="creative_contract_v1"` written into `g_b_frozen_input_snapshot.json` at Stage 0 freeze for new creative runs. DAG selection matrix below; no per-feature markers.
3. **Candidate switching:** new change type `script_candidate_select` (scope `script_settings`); it re-materializes `production_script_candidate.json` + `voice_preflight.json` and rebuilds the Gate 4 pre-generation package.
4. **G-B scope:** supervised G-B qualification runs use the hardened `default_dag()` (with `build-narrative-coherence`/`validate-visual-layout`) and do NOT enable P1–P3 creative nodes. The 08-17 G-B evidence checklist stays unchanged. P1–P3 are validated in isolated new tasks plus the §15 `baseline_v1` comparison.

**DAG selection matrix (final):**

| `g_b_frozen_input_snapshot.json` | `pipeline_state.production_dag_version` | DAG |
| --- | --- | --- |
| no `creative_contract_version`, Gate 2 baseline lacks `narrative_contract_v1` | `LEGACY_DAG_VERSION` | `legacy_dag()` (pre-hardening) |
| no `creative_contract_version`, Gate 2 baseline carries `narrative_contract_v1` | `HARDENED_DAG_VERSION` | `default_dag()` (hardened; G-B qualification DAG) |
| `creative_contract_version="creative_contract_v1"` | `CREATIVE_DAG_VERSION` | `creative_dag()` (hardened + creative nodes) |

**Tech Stack:** Python 3.11+, existing Native Runner/DAG, JSON Schema 2020-12, FFmpeg, FastAPI, vanilla JavaScript, `unittest`.

**Sequencing:** P0a-contracts → P0a-docs → P0b → P1 → P2 → P3a → P3b → P4 baseline comparison → P5 outline. P0b does not depend on generative models and may proceed in parallel with P1 contract work. P3b may only start after P3a supervision evidence shows a repeatable, fixable shot problem class.

---

## Phase 0a: Contract Foundation

### Task 1: Register The Eight New Creative Artifacts

**Files:**
- Create: `.agents/skills/remix-reference-video/schemas/decomposition-bundle.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/creative-objective.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/remix-strategy-candidates.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/script-candidates.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/script-candidate-validation-report.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/shot-quality-report.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/enhancement-plan.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/final-content-diagnostic-report.schema.json`
- Modify: `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/artifact_validator.py`
- Test: `.agents/skills/remix-reference-video/tests/test_creative_contracts.py`

- [x] **Step 1: Write failing registry/schema tests**

  For each artifact: five-field envelope, task-local path, `lifecycle_status` in the design-allowed set (`ready|stale` for machine reports; candidates are input artifacts, never `awaiting_user`), `input_hashes` required, recursive rejection of `approval`/`gate_status`/`decision` reserved keys. Candidate artifacts (`decomposition_bundle`, `remix_strategy_candidates`, `script_candidates`) must not be validatable as approval-carrying.

- [x] **Step 2: Run focused tests**

  Run: `PYTHONPATH=src python -m unittest tests.test_creative_contracts -v`

  Expected: FAIL because registry entries and schemas do not exist.

- [x] **Step 3: Implement schemas and registry entries**

  Register all eight artifacts with `track=B` (Track-C-only fields stay out), explicit `schema_path`, `production_state_authority=false` for machine diagnostics and candidates, and discriminator `oneOf` entries. Fix per design §12.1 producer/execution-point/authoritative-input/gate columns in the schema descriptions.

- [x] **Step 4: Enforce lifecycle and reserved-key validation**

  Extend `artifact_validator.py` with the per-type `lifecycle_status` allowlists and the reserved approval-key rejection for the new types. Do not modify V1 validation paths.

- [x] **Step 5: Re-run focused tests**

  Expected: PASS.

- [x] **Step 6: Commit the contract slice**

  Run: `git add .agents/skills/remix-reference-video/schemas .agents/skills/remix-reference-video/src/remix_reference_video/artifact_validator.py .agents/skills/remix-reference-video/tests/test_creative_contracts.py && git commit -m "feat: register creative quality upgrade artifact contracts"`

### Task 2: Add The Capability Marker And Third DAG

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/gb_frozen_case.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/runner.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Test: `.agents/skills/remix-reference-video/tests/test_dag_selection.py`

- [x] **Step 1: Write failing DAG-selection tests**

  Cover the full three-way matrix: legacy snapshot → `legacy_dag()`; hardened snapshot (narrative contract, no creative marker) → `default_dag()`; snapshot with `creative_contract_version=creative_contract_v1` → `creative_dag()`. Assert `production_dag_version` is written to `pipeline_state.json` at init and never silently changed mid-run.

- [x] **Step 2: Run focused tests**

  Expected: FAIL because only two DAGs exist.

- [x] **Step 3: Add `CREATIVE_DAG_VERSION` and `creative_dag()`**

  Add `CREATIVE_DAG_VERSION` and a `creative_dag()` placeholder equal to `default_dag()` for now (nodes land in P1/P2/P3a; keep the selection machinery stable). Extend `dag_for_task()` to read the frozen snapshot marker first, then fall back to the existing `production_dag_version`/`narrative_contract_version` logic.

- [x] **Step 4: Write the marker at Stage 0 freeze**

  In `gb_frozen_case.py`, when a new run is frozen for the creative upgrade, the Stage 0 freeze helper writes `creative_contract_version="creative_contract_v1"` into `g_b_frozen_input_snapshot.json`; the marker participates in the snapshot SHA-256. `gb-pair --creative-contract v1` only verifies that the immutable frozen snapshot already carries the marker and must never add or rewrite it. Absence of the flag keeps the hardened qualification path.

- [ ] **Step 5: Route invalidation through the selected DAG**

  Replace remaining direct `default_dag()` consumers in `change_service.py`/`native_registry.py`/`critical_path.py` with the task-selected DAG so impact previews and critical-path computation follow whichever DAG the task actually runs.

- [x] **Step 6: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 7: Commit the DAG slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py .agents/skills/remix-reference-video/src/remix_reference_video/gb_frozen_case.py .agents/skills/remix-reference-video/src/remix_reference_video/runner.py .agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py .agents/skills/remix-reference-video/src/remix_reference_video/change_service.py .agents/skills/remix-reference-video/src/remix_reference_video/critical_path.py .agents/skills/remix-reference-video/tests/test_dag_selection.py && git commit -m "feat: add creative contract marker and DAG selection"`

### Task 3: Gate Package Binding Contracts

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/approvals.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py`
- Test: `.agents/skills/remix-reference-video/tests/test_gate_package_bindings.py`

- [ ] **Step 1: Write failing binding tests**

  Assert: Gate 1 decision `strategy` carries exactly one `selected_decomposition_id` that exists in the bound `decomposition_bundle.json` (reject unknown/multiple IDs); Gate 2 decision `strategy` carries exactly one `selected_remix_strategy_id` present in `remix_strategy_candidates.json`; Gate 4 pre-generation decision `strategy` carries `selected_script_candidate_id` whose candidate is `passed` in `script_candidate_validation_report.json`, plus the existing `tts_settings` speed check. Reject approval when any bound hash is stale.

- [ ] **Step 2: Run focused tests**

  Expected: FAIL because the strategies are not validated.

- [ ] **Step 3: Implement strategy validation in ApprovalService**

  Add per-Gate strategy validators gated on the creative contract marker (hardened/legacy runs keep today's strategy shapes). Verify the selected ID against the bound candidate artifact and its package hash before writing the decision. Keep the Gate 4 pre-generation approved-script promotion transaction unchanged otherwise.

- [ ] **Step 4: Extend package builders**

  In `native_completion.py`, extend `build-gate1-package`, `lint-gate2-package`, and `build-gate4-pre-package` to include the new bound artifacts in `input_hashes` and the machine-proposed default selection (P1/P2 fill the actual producers; P0a keeps them absent and skips binding for non-creative runs).

- [ ] **Step 5: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 6: Commit the binding slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/approvals.py .agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py .agents/skills/remix-reference-video/tests/test_gate_package_bindings.py && git commit -m "feat: bind decomposition, remix strategy and script candidate to Gate packages"`

### Task 4: New Change Type `script_candidate_select`

**Files:**
- Create: `.agents/skills/remix-reference-video/schemas/changes/script-candidate-select.schema.json`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js`
- Test: `.agents/skills/remix-reference-video/tests/test_change_service.py`

- [x] **Step 1: Write failing change tests**

  Assert the type accepts only `{script_candidate_id, script_candidates_sha256}` payloads; requires Gate 4 pre-generation as the earliest affected gate; impact = re-materialize `production_script_candidate.json` + `voice_preflight.json` + rebuild Gate 4 pre package (`gate4_pre_generation`/`gate4_post_generation`/`gate5` stale); rejects IDs that are not `passed` or not bound to the current package.

- [x] **Step 2: Run focused tests**

  Expected: FAIL because the schema and impact table do not exist.

- [x] **Step 3: Implement validation and impact rules**

  Add the schema to `_SCHEMA_NAMES`, the validator branch, and `_IMPACTS` entry. Scope maps to B0 `script_settings`; server re-validates the candidate's `passed` status from `script_candidate_validation_report.json` and recomputes the preview hash.

- [ ] **Step 4: Expose in the Gate 4 pre-generation UI**

  Add a candidate-switch action in the review sheet Gate 4 pre-generation view that opens the standard change preview; no direct artifact writes.

- [x] **Step 5: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 6: Commit the change slice**

  Run: `git add .agents/skills/remix-reference-video/schemas/changes/script-candidate-select.schema.json .agents/skills/remix-reference-video/src/remix_reference_video/change_service.py .agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js .agents/skills/remix-reference-video/tests/test_change_service.py && git commit -m "feat: add script candidate selection change type"`

### Task 5: Stage North-Star Measurement Contract

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/stage_north_star.py`
- Test: `.agents/skills/remix-reference-video/tests/test_stage_north_star.py`

- [x] **Step 1: Write failing measurement tests**

  Per design §11.2: first-round package = first package bound to the current input hash with `awaiting_user`; every `changes_requested|rejected` regeneration is a rework round. Assert deduplication by the table's metric keys, `not_measured` for missing sources (never zero), required-action observations sourced only from `shot_quality_report.shots[].action_results[]`, and that candidate counts never enter any denominator.

- [x] **Step 2: Run focused tests**

  Expected: FAIL because no builder exists.

- [x] **Step 3: Implement `StageNorthStarBuilder`**

  Compute Gate 1 first-pass structure rate, weighted creative-objective coverage, script first-pass business rate, shot-intent completion rate, and the workbench effective decision time from the implemented interval-model events (`review.evidence_interaction` → `review.decision_accepted` per package revision). Do not implement L1-pass-rate or profit north-stars (they read Track C artifacts later).

- [x] **Step 4: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 5: Commit the measurement slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/stage_north_star.py .agents/skills/remix-reference-video/tests/test_stage_north_star.py && git commit -m "feat: add stage north-star measurement contract"`

---

## Phase 0b: Workbench Key Artifacts Projection

### Task 6: Project Stage Artifacts, Versions, Lineage, Evaluation, Impact

**Files:**
- Modify: `.agents/skills/remix-reference-video/schemas/workbench-workspace-view.schema.json`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/workspace_view.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.css`
- Test: `.agents/skills/remix-reference-video/tests/test_workspace_view.py`
- Test: `.agents/skills/remix-reference-video/tests/test_workbench_client.py`

- [ ] **Step 1: Write failing projection tests**

  Assert `stage_artifacts[]` is organized by the five business stages; `artifact_versions[]` exposes candidate-vs-approved versions with strategy IDs and diff summaries only when candidate artifacts exist; `lineage_edges[]` chains objective → strategy → script → shot → material → timeline → final video; `evaluation_summary` carries north-star/constraint/evidence-source/`not_measured` reasons; `change_impact` mirrors ChangeService previews. Missing artifacts must yield explicit "旧契约未生成" states, never fabricated data.

- [ ] **Step 2: Run focused tests**

  Expected: FAIL because the projection fields do not exist.

- [ ] **Step 3: Extend the workspace schema and builder**

  Add the five typed projection sections to the workspace schema; build them deterministically from `pipeline_state.json`, review packages, and registered artifacts, bound to `state_revision` and package revision.

- [ ] **Step 4: Implement the stage key-artifacts card and detail drawer**

  Right-rail stage cards gain a "关键产物" region; the drawer compares candidates, shows evidence, locates the central preview/timeline, and offers structured change entry. Raw JSON/paths/hashes stay in the diagnostics foldout. No placeholder capabilities.

- [ ] **Step 5: Re-run focused and client tests**

  Run: `PYTHONPATH=src python -m unittest tests.test_workspace_view -v && node .agents/skills/remix-reference-video/tests/client_workbench_harness.js`

  Expected: PASS.

- [ ] **Step 6: Commit the workbench slice**

  Run: `git add .agents/skills/remix-reference-video/schemas/workbench-workspace-view.schema.json .agents/skills/remix-reference-video/src/remix_reference_video/workspace_view.py .agents/skills/remix-reference-video/src/remix_reference_video/static .agents/skills/remix-reference-video/tests/test_workspace_view.py .agents/skills/remix-reference-video/tests/test_workbench_client.py && git commit -m "feat: project key artifacts, versions and lineage into workbench"`

---

## Phase 1: Strategy Layer

### Task 7: Multi-Strategy Decomposition And Gate 1 Selection

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/decomposition.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_preparation.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Test: `.agents/skills/remix-reference-video/tests/test_decomposition.py`

- [ ] **Step 1: Write failing decomposition tests**

  Cover the four versioned strategies (`structure_semantic_v1`, `rhythm_visual_v1`, `evidence_action_v1`, `hybrid_commerce_v1`); 1–3 candidates with default `hybrid_commerce_v1`; candidate references to `recipe.json` physical shot IDs without redefining boundaries; semantic segments, hooks, rhythm peaks, suspect cuts, low-confidence items, and structured inter-candidate diffs; low-confidence threshold read from `decomposition_policy_v1`.

- [ ] **Step 2: Run focused tests**

  Expected: FAIL because no decomposition adapter exists.

- [ ] **Step 3: Restructure the Gate 1 DAG nodes**

  In `creative_dag()`: `split-reference` loses its `stop_gate` (recipe + physical facts only); new `build-decomposition-candidates` depends on `split-reference`; new `build-gate1-package` depends on it and carries `stop_gate=gate1`. The Gate 1 package binds `recipe.json` + `decomposition_bundle.json` + machine-proposed `selected_decomposition_id`.

- [ ] **Step 4: Implement the four decomposition strategies**

  Each strategy is a deterministic adapter with its own implementation version, input hashes, and candidate output. Keep physical facts in `recipe.json`; never mutate it.

- [ ] **Step 5: Extend invalidation closure**

  Decomposition-switch changes stale Gate 1 and all downstream; recipe changes stale everything downstream; record both in `change_service.py` impact rules for creative runs.

- [ ] **Step 6: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 7: Commit the decomposition slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/adapters/decomposition.py .agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py .agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py .agents/skills/remix-reference-video/src/remix_reference_video/native_preparation.py .agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py .agents/skills/remix-reference-video/src/remix_reference_video/change_service.py .agents/skills/remix-reference-video/tests/test_decomposition.py && git commit -m "feat: add multi-strategy decomposition with Gate 1 selection"`

### Task 8: Creative Objective And Remix Strategy Candidates At Gate 2

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/blueprint.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/mutation.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_preparation.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Test: `.agents/skills/remix-reference-video/tests/test_creative_objective.py`
- Test: `.agents/skills/remix-reference-video/tests/test_remix_strategies.py`

- [ ] **Step 1: Write failing objective/strategy tests**

  Assert `creative_objective.json` reads only the frozen Brief (`approved_claims[]`/`forbidden_claims[]`, audience, platform, target) and the Gate 1 decision; enforces normalized non-negative weights summing to `1.0`; supports `product_appearance_target_seconds` plus an explicit approved exception field; rejects identity-field overrides. Assert `remix_strategy_candidates.json` contains ≤3 candidates from the fixed strategy set with coverage/feasibility/deviation estimates computed from `coverage_precheck.json`.

- [ ] **Step 2: Run focused tests**

  Expected: FAIL because the producers do not emit these artifacts.

- [ ] **Step 3: Implement Blueprint `creative_objective` production**

  Generate after Gate 1 approval, before the Gate 2 package. Also emit per-fragment `visual_intent` into `content_baseline.json` (producer fixed here; downstream script lines and shot diagnostics consume it).

- [ ] **Step 4: Implement Controlled Mutation remix candidates**

  Generate the ≤3 strategy candidates with retain/replace/compress/expand/reorder/fallback sections and coverage-precheck-based estimates; the machine-proposed `selected_remix_strategy_id` defaults to `balanced_remix_v1`.

- [ ] **Step 5: Bind the Gate 2 atomic package**

  `lint-gate2-package` binds `creative_objective.json`, `remix_strategy_candidates.json`, `content_baseline.json`, `mutation_plan.json`, `coverage_precheck.json`, and `selected_remix_strategy_id`. Document the coverage-precheck binding as display-completeness: regenerating the precheck re-stales the Gate 2 package; approval authority remains the objective+baseline+mutation+strategy set.

- [ ] **Step 6: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 7: Commit the Gate 2 slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/adapters/blueprint.py .agents/skills/remix-reference-video/src/remix_reference_video/adapters/mutation.py .agents/skills/remix-reference-video/src/remix_reference_video/native_preparation.py .agents/skills/remix-reference-video/src/remix_reference_video/change_service.py .agents/skills/remix-reference-video/tests/test_creative_objective.py .agents/skills/remix-reference-video/tests/test_remix_strategies.py && git commit -m "feat: add creative objective and remix strategy candidates at Gate 2"`

---

## Phase 2: Script Layer

### Task 9: Generative Script Candidates With Machine Gates

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/script_candidates.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/script_candidate_generator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py`
- Test: `.agents/skills/remix-reference-video/tests/test_script_candidates.py`

- [ ] **Step 1: Write failing candidate-generation tests**

  Cover: generation only runs when `narrative_coherence_report.status != blocked`; 2–3 candidates with creative hypotheses ("问题解决"/"演示证明"/"场景收益"); per-candidate fields from design §8.2 including `objective_id`, `narrative_role`, `required_actions`, claim/evidence refs, expected visuals, duration estimates, continuity, first-3-seconds/product/proof/result/CTA completion, risks, and provider/model/prompt-version/seed/input-hash records; provider registry allows a deterministic `stub` provider for tests and requires explicit production provider config (no silent default).

- [ ] **Step 2: Run focused tests**

  Expected: FAIL because no candidate generator exists.

- [ ] **Step 3: Insert the creative DAG nodes**

  `creative_dag()`: `summarize-gate3 → build-narrative-coherence → generate-script-candidates → validate-script-candidates → select-script-candidate → build-production-script → voice-preflight → build-gate4-pre-package`. `materialize-approved-broad → validate-visual-layout` stays parallel; `voice-preflight` keeps both upstream dependencies.

- [ ] **Step 4: Implement the generator with governance**

  `ScriptCandidateGenerator` protocol: fixed provider/model/prompt-template-version/seed/params; candidates are hash-immutable once emitted; failures keep upstream artifacts and return recoverable states; re-running reproduces inputs/configuration/audit chain (byte-identical text only promised for the stub provider).

- [ ] **Step 5: Implement `validate-script-candidates`**

  Per-candidate re-execution of design §8.3 gates (100% claim/evidence closure, no forbidden claims, hook function, product-appearance target with approved exception, no ≥2 consecutive pure-claim segments, required roles present, continuity known, budget fit, all `required` objectives covered). Failed candidates stay in the list with elimination reasons but are excluded from selection.

- [ ] **Step 6: Implement `select-script-candidate`**

  `script_candidate_rank_v1`: required-goal coverage desc → weighted coverage desc → minimal budget margin desc → `script_candidate_id` lexicographic tiebreak. Re-materializes `production_script_candidate.json` (with per-line `objective_id`/`script_line_id`/`narrative_role`/`required_actions`/`evidence_row_ref`/`visual_intent`) and `voice_preflight.json` on every selection.

- [ ] **Step 7: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 8: Commit the script-layer slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/adapters/script_candidates.py .agents/skills/remix-reference-video/src/remix_reference_video/script_candidate_generator.py .agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py .agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py .agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py .agents/skills/remix-reference-video/tests/test_script_candidates.py && git commit -m "feat: add validated generative script candidates before Gate 4"`

---

## Phase 3a: Shot And Final Content Diagnostics

### Task 10: Shot Quality Report And Gate 5 Diagnostic

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/shot_quality.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/final_diagnostic.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Test: `.agents/skills/remix-reference-video/tests/test_shot_quality.py`
- Test: `.agents/skills/remix-reference-video/tests/test_final_diagnostic.py`

- [ ] **Step 1: Write failing diagnostic tests**

  Assert `validate-shot-quality` runs after proxy generation and before boundary validation/final render; per-shot checks from design §9.1 with deterministic `blocked` (identity error, missing evidence/action, cropped text, timeline overflow, incomplete required action) vs `manual_review` (subjective continuity/highlight/aesthetic); `manual_review` items must be carried into Gate 5 and never shown as `passed`; high-light candidates record target/expected role/time range/issue/suggested actions.

- [ ] **Step 2: Run focused tests**

  Expected: FAIL because no diagnostic adapters exist.

- [ ] **Step 3: Insert nodes and implement `validate-shot-quality`**

  `creative_dag()`: `render-proxy → validate-shot-quality → validate-proxy-boundaries → render-final → build-final-content-diagnostic → build-gate5-package`. Implement the shot rubric reading approved script, material manifest, exact timeline, proxy frames, narrative and layout reports.

- [ ] **Step 4: Implement `build-final-content-diagnostic`**

  Aggregate shot results into `final_content_diagnostic_report.json` (first-3-seconds, script-visual coherence, product/scene consistency, persuasion/evidence, rhythm/highlights, objective coverage, L0 citations). `blocked` only from deterministic derivable problems; subjective dimensions stay `manual_review`; lifecycle `ready|stale`. Gate 5 package displays items and sources without inventing Track C L1 claims.

- [ ] **Step 5: Extend invalidation and recovery**

  Script edits stale Gate 4 pre and downstream; material/range edits stale both Gate 3 sub-states and downstream; exact-cut adjustments inside approved broad ranges stale timeline/proxy/reports/downstream; diagnostics failures return `earliest_recovery_gate` (Gate 2 / Gate 3 sub-state / Gate 4) per design §13.

- [ ] **Step 6: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 7: Commit the diagnostics slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/adapters/shot_quality.py .agents/skills/remix-reference-video/src/remix_reference_video/adapters/final_diagnostic.py .agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py .agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py .agents/skills/remix-reference-video/src/remix_reference_video/native_completion.py .agents/skills/remix-reference-video/src/remix_reference_video/change_service.py .agents/skills/remix-reference-video/tests/test_shot_quality.py .agents/skills/remix-reference-video/tests/test_final_diagnostic.py && git commit -m "feat: add shot-level and final content diagnostics"`

---

## Phase 3b: Optional AI Shot Enhancement

### Task 11: On-Demand `propose-shot-enhancement`

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/enhancement.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/enhancement_provider.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/change_service.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py`
- Test: `.agents/skills/remix-reference-video/tests/test_enhancement.py`

- [ ] **Step 1: Write failing enhancement tests**

  Assert the node is not part of any default DAG and only runs for an operator-initiated shot rework; `enhancement_plan.json` status `ready|failed`; provider output lands in an isolated candidate directory and never overwrites user or approved copies; candidates bind source shot/objective/material/provider/model/prompt-version/input-output hashes; adopting a candidate returns to `gate3_material_selection` and stales `gate3_evidence_closure`, Gate 4 and Gate 5 (structure/claim changes additionally return Gate 2); failures keep the approved material and current Gate state.

- [ ] **Step 2: Run focused tests**

  Expected: FAIL because no enhancement adapter exists.

- [ ] **Step 3: Implement the on-demand node and provider protocol**

  Provider adapters are registered like TTS (explicit config, no silent default, stub provider for tests). Candidate adoption is manual: the operator submits it through the Gate 3 material-selection review; first version never auto-adopts.

- [ ] **Step 4: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 5: Commit the enhancement slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/adapters/enhancement.py .agents/skills/remix-reference-video/src/remix_reference_video/enhancement_provider.py .agents/skills/remix-reference-video/src/remix_reference_video/change_service.py .agents/skills/remix-reference-video/src/remix_reference_video/native_registry.py .agents/skills/remix-reference-video/tests/test_enhancement.py && git commit -m "feat: add optional shot enhancement with Gate 3 re-review"`

> **Gate:** P3b may only start after P3a supervision samples demonstrate a repeatable, fixable shot problem class. If that evidence does not exist, keep P3b deferred and record the reason.

---

## Phase 4: Baseline v0/v1 Comparison And Acceptance

### Task 12: Register `baseline_v0` And Build The Comparison Harness

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/creative_baseline.py`
- Create: `docs/superpowers/blind-eval-template.md`
- Test: `.agents/skills/remix-reference-video/tests/test_creative_baseline.py`

- [ ] **Step 1: Write failing comparison tests**

  Assert `baseline_v0` registration binds cold run `gb-cold-1786890259` of `work/2026-08-16-tablemat-mix-v2/` with its `g_b_frozen_input_snapshot` SHA-256 and `video_version_id`; the comparison fixes reference/Brief/asset-pool hashes, claim scope, audience, platform, voice settings and output specs; allowed deltas are exactly the design §15 creative/making choices; AI enhancement is forced off for the first comparison; each side gets its own `evaluation_context_id` linked by one `comparison_id`; pass requires both L0 pass, all v1 required objectives and claim evidence pass, v1 first-3-seconds and script coherence strictly above v0, visual consistency/highlights/viewing experience not below v0, and no unapproved facts/material/enhancements.

- [ ] **Step 2: Run focused tests**

  Expected: FAIL because no comparison module exists.

- [ ] **Step 3: Implement `CreativeBaselineComparison`**

  Register baseline_v0, compute comparison inputs/hashes, freeze the blind-eval rubric (`low|ordinary|high` with evidence timestamps), and evaluate the §15 pass criteria. Effective decision time and rework rounds are recorded but observational only. v0 scores are direct human observations of the final video (v0 has no narrative/first-3-seconds machine reports); record that asymmetry in the comparison.

- [ ] **Step 4: Re-run focused tests**

  Expected: PASS.

- [ ] **Step 5: Commit the comparison slice**

  Run: `git add .agents/skills/remix-reference-video/src/remix_reference_video/creative_baseline.py docs/superpowers/blind-eval-template.md .agents/skills/remix-reference-video/tests/test_creative_baseline.py && git commit -m "feat: add baseline v0/v1 creative comparison harness"`

### Task 13: Execute The `baseline_v1` Run And Record The Result

- [ ] **Step 1: Create a new frozen run**

  New cold run reusing the same `g_b_frozen_input_snapshot` with `--creative-contract v1`; never reuse decisions or the shared production cache from `tablemat-mix-v2`.

- [ ] **Step 2: Run Gate 1–5 on the creative DAG**

  All seven canonical Gate decisions from the workbench; stop at each Gate; no AI enhancement; record decision time and rework rounds observationally.

- [ ] **Step 3: Owner blind evaluation**

  Owner scores v0/v1 with the frozen rubric (`low|ordinary|high` + issues + evidence timestamps); compute the §15 pass criteria with `CreativeBaselineComparison`.

- [ ] **Step 4: Record the result**

  Write the comparison result, evidence paths, policy versions and the owner decision into the run directory and link it from the comparison ledger; never rewrite the v0 task artifacts.

---

## Phase 5: Documentation, Governance Sync, And Track C Outline

### Task 14: Synchronize Documents And Verifications

**Files:**
- Modify: `docs/superpowers/specs/2026-08-19-reference-remix-creative-quality-upgrade-design.md`
- Modify: `docs/superpowers/specs/2026-08-17-gb-review-workbench-quality-design.md`
- Modify: `docs/superpowers/specs/2026-08-18-remix-quality-hardening-design.md`
- Modify: `docs/superpowers/specs/2026-08-18-business-video-workbench-design.md`
- Modify: `AGENTS.md`
- Modify: `.agents/skills/remix-reference-video/README.md`

- [ ] **Step 1: Amend the 08-19 design per review rulings**

  Rewrite §11.2 to reference the implemented interval-model events and drop the tick-based event names; replace the §12 compatibility wording with the single `creative_contract_version` marker and the three-way DAG matrix; state the G-B scope ruling (hardened DAG, no P1–P3); document coverage-precheck display-completeness binding; add the product-appearance exception field and the `visual_intent` producer (Blueprint); note the v0 blind-eval evidence asymmetry.

- [ ] **Step 2: Update the 08-17 workbench design status**

  Mark its P0b as implemented, cross-reference the 08-18/08-19 docs, and reconcile its event contract wording with the implemented interval model (no new events introduced by the creative design).

- [ ] **Step 3: Sync AGENTS.md**

  Record `tablemat-mix-v2` as the latest completed pair and its `baseline_v0` role; describe the creative contract marker, the three DAG generations, the new core artifacts, and that supervised G-B keeps the hardened DAG until owner G-B review passes.

- [ ] **Step 4: Update the Skill README**

  Document the new task-start path for creative runs (`--creative-contract v1`), the new artifacts and Gate bindings, the `script_candidate_select` change type, and the enhancement re-review path.

- [ ] **Step 5: Run the full suite and static checks**

  Run: `PYTHONPATH=src python -m unittest discover -s tests -q && node --check src/remix_reference_video/static/review_workbench.js && git diff --check && python -m compileall -q src`

  Expected: all commands exit 0.

- [ ] **Step 6: Isolated `gb-pair` regression**

  Re-run an isolated hardened-DAG pair to confirm G-B measurement contracts (critical path end `build-gate5-package`, approvals, cache facts) are unaffected by the creative additions; confirm the creative DAG never activates without the marker.

- [ ] **Step 7: Manual workbench acceptance**

  1440px and 390px walkthrough: stage key-artifact cards, candidate comparison drawer, lineage, evaluation summary, Gate 1 strategy selection, Gate 2 objective/strategy review, Gate 4 candidate switch preview, Gate 5 diagnostic carry-over, and the "旧契约未生成" state on a legacy task. Record evidence and open issues.

- [ ] **Step 8: Commit the documentation slice**

  Run: `git add docs AGENTS.md .agents/skills/remix-reference-video/README.md && git commit -m "docs: sync creative quality upgrade design and governance"`

### Task 15: Track C Calibration Outline (post-G-B, plan-only)

- [ ] **Step 1: Freeze the L1 policy from supervised samples**

  After G-B owner approval and supervised ops trial, calibrate the six-dimension L1 rubric, anchors, dual-rater reliability, and `content_quality_policy` v1 per the 08-16 design §14.2; until then L1 stays `review_required`/provisional and never gates G-B.

- [ ] **Step 2: Access real L2 feedback**

  Execute the 08-16 §16 data-access validation (source inventory, `creative_id ↔ video_version_id` mapping carrier, per-source fallbacks) before any online snapshot; never predict or fabricate L2 in the workbench.

- [ ] **Step 3: Wire the remaining north-stars**

  Connect L1-pass-rate and profit north-stars to Track C immutable snapshots only after L1 policy and L2 access exist; keep `not_measured` until then.

---

## Acceptance Gate

- All eight new artifacts registered, validated, and never approval-carrying; candidate artifacts immutable once in a review package.
- Gate 1 selects one decomposition; Gate 2 atomically approves objective + remix strategy + baseline + mutation; Gate 4 pre-generation approves one validated script candidate.
- No TTS/render when narrative/layout reports are blocked; machine script gates fail closed.
- New runs no longer emit consecutive same-structure sell-point scripts, and every shot binds objective/script/action/evidence.
- Shot and final diagnostics show first-3-seconds, coherence, consistency, highlights with evidence paths; `manual_review` never silently renders as `passed`.
- AI enhancement never overwrites source/approved copies and always re-enters Gate 3 review.
- `baseline_v1` comparison per §15 executed, blind-evaluated, repeatable, and recorded; decision time and rework rounds observational only.
- Supervised G-B evidence thresholds (300/180/120 s decision times, 780/480 s critical paths, five-stage quality ≥88) computed on the hardened DAG with the implemented interval-model口径.
- Ordinary V2 production lock, shared production cache, and first-line publishing remain locked until G-B owner approval and the supervised ops trial pass.
