# G-B Measurement And Quality Snapshot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce audit-safe G-B measurement, process assessment, and five-stage quality snapshots from complete run evidence without fabricating V1 metrics or changing the production lock.

**Architecture:** `pipeline_state.json` remains the only approval authority. Pure collectors read state, `stage_metrics.jsonl`, `pipeline_events.jsonl`, the frozen input snapshot, an explicit rubric input, and a versioned baseline policy. Canonical snapshots are stored under `measurements/<snapshot_id>/`; a replaceable `measurements/latest.json` pointer contains only paths and hashes, so superseding never overwrites history. `gb_measurement.json` remains byte-for-byte unchanged as a legacy projection.

**Tech Stack:** Python 3.12+, `unittest`, `jsonschema` Draft 2020-12 validation, existing `TaskStorage`, `default_dag()`, and argparse CLI.

**Spec:** `docs/superpowers/specs/2026-08-17-gb-review-workbench-quality-design.md`

---

## Chunk 1: Contracts And Run Evidence

### Task 1: Add Full Snapshot Schema Validation

**Files:**
- Modify: `.agents/skills/remix-reference-video/pyproject.toml`
- Create: `.agents/skills/remix-reference-video/schemas/phase6-score-snapshot.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/process-assessment.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/inputs/phase6-rubric-input.schema.json`
- Create: `.agents/skills/remix-reference-video/schemas/inputs/gb-baseline-policy.schema.json`
- Modify: `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/snapshot_schema_validator.py`
- Create: `.agents/skills/remix-reference-video/tests/test_snapshot_schema_validator.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_artifact_validator.py`
- Modify: `.agents/skills/remix-reference-video/track_a_static_check.py`

`jsonschema>=4.23,<5` becomes a core dependency. The generic `ArtifactValidator` keeps its current envelope behavior; the new `SnapshotSchemaValidator` is used only for the new full Track-B shapes, so Track A and the production lock are not weakened. Rubric and policy schemas are CLI input contracts under `x-input-contracts`, not task artifacts or approval authorities.

- [ ] **Step 1: Write failing schema tests**

Assert a score with `measurement_status=not_scored` cannot contain a numeric total. Assert the registry contains complete `schema_id`, `schema_path`, path template, format, track, and activation for both output artifacts; assert input schemas are under `x-input-contracts`, not `artifact_type.enum`.

- [ ] **Step 2: Verify RED**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_snapshot_schema_validator.py' -v
```

Expected: FAIL because the module and schemas do not exist.

- [ ] **Step 3: Implement minimal full-shape validation**

Use `jsonschema.Draft202012Validator`. Resolve schema paths only under the Skill `schemas/` directory, reject symlinks, return deterministic JSON-pointer errors, and leave existing artifact validation unchanged.

- [ ] **Step 4: Verify GREEN and Track A compatibility**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_snapshot_schema_validator.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_artifact_validator.py' -v
python3 track_a_static_check.py
```

Expected: PASS.

- [ ] **Step 5: Commit the contract slice**

```bash
git add .agents/skills/remix-reference-video/pyproject.toml .agents/skills/remix-reference-video/schemas .agents/skills/remix-reference-video/src/remix_reference_video/snapshot_schema_validator.py .agents/skills/remix-reference-video/tests/test_snapshot_schema_validator.py .agents/skills/remix-reference-video/tests/test_artifact_validator.py .agents/skills/remix-reference-video/track_a_static_check.py
git commit -m "feat: define G-B snapshot schemas"
```

### Task 2: Bind New Approval Records To Their Run

**Files:**
- Modify: `.agents/skills/remix-reference-video/tests/test_approvals.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/approvals.py`

- [ ] **Step 1: Write a failing run-binding test**

Assert that an accepted Gate decision contains the current `pipeline_state.run_id` and idempotent replay returns the same run-bound record.

- [ ] **Step 2: Verify RED**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_approvals.py' -v
```

Expected: FAIL with missing `run_id`.

- [ ] **Step 3: Write `run_id` from current state**

Add it only after package run/revision/hash validation. Never read it from the decision file.

- [ ] **Step 4: Verify GREEN and commit**

Run the same command, then:

```bash
git add .agents/skills/remix-reference-video/src/remix_reference_video/approvals.py .agents/skills/remix-reference-video/tests/test_approvals.py
git commit -m "feat: bind gate decisions to run ids"
```

### Task 3: Preserve Cache Facts At Metric Production Time

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/runner.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/asset_index.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_runner.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_asset_index_adapter.py`

Every completed command metric must include `execution_stage_id`, `attempt_id`, `status`, `wall_seconds`, `cache_status`, and `cache_source`. Optional producer facts are `lookup_hit_count`, `lookup_miss_count`, `reused_record_count`, `skipped`, and `evidence_paths`. Cold and hot orchestration supplies `cache_source=empty|cloned_cold|hot_lookup|none`; the asset index supplies actual hit/miss/reuse counts. Unknown facts remain absent and are later reported `not_measured`, not zero.

- [ ] **Step 1: Write failing producer tests**

Assert successful and cache-hit metrics preserve attempt identity and allowed cache facts from adapter output. Assert failed metrics include `failure_category=network_api|execution|validation|unknown`; only `network_api` contributes to retry network time.

- [ ] **Step 2: Verify RED**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_runner.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_asset_index_adapter.py' -v
```

Expected: FAIL because metric rows currently drop adapter cache facts and failure category.

- [ ] **Step 3: Implement a metric allowlist**

Copy only declared cache fields from execution results. Do not write arbitrary adapter output into metrics. Keep transaction rows without `execution_stage_id` unchanged for backward compatibility.

- [ ] **Step 4: Verify GREEN and commit**

Run the same tests, then:

```bash
git add .agents/skills/remix-reference-video/src/remix_reference_video/runner.py .agents/skills/remix-reference-video/src/remix_reference_video/adapters/asset_index.py .agents/skills/remix-reference-video/tests/test_runner.py .agents/skills/remix-reference-video/tests/test_asset_index_adapter.py
git commit -m "feat: record stage cache measurement facts"
```

## Chunk 2: Deterministic Measurement And Scoring

### Task 4: Calculate The Real Production DAG Critical Path

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/critical_path.py`
- Create: `.agents/skills/remix-reference-video/tests/test_critical_path.py`

The required subgraph has 24 command nodes: every `default_dag()` node from roots `split-reference` and `index-assets` through terminal `build-gate5-package`, excluding `init` and `archive-approved`. Rows without `execution_stage_id` are ignored. For each node, the last successful/cache-hit attempt by JSONL record order is authoritative. Formula: `critical(node) = duration(node) + max(critical(dep))`.

- [ ] **Step 1: Write failing tests using the actual 24 node IDs**

Cover the complete subgraph, retry selection, cache hits, ignored transaction rows, duplicate attempt ID rejection, parallel roots/branches, archive exclusion, and missing node => `not_measured`.

- [ ] **Step 2: Verify RED**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_critical_path.py' -v
```

Expected: import failure.

- [ ] **Step 3: Implement `CriticalPathCollector.collect(metrics)`**

Return `measurement_status`, `seconds`, `node_durations`, `critical_path_nodes`, `missing_stage_ids`, and `evidence_path`. Sum only failed metrics explicitly classified `network_api` into `retry_network_seconds`; old unclassified failures make that independent metric `not_measured`.

- [ ] **Step 4: Verify GREEN and commit**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_critical_path.py' -v
git add src/remix_reference_video/critical_path.py tests/test_critical_path.py
git commit -m "feat: measure production DAG critical path"
```

### Task 5: Build Full Process And Cache Assessments

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/process_assessment.py`
- Create: `.agents/skills/remix-reference-video/tests/test_process_assessment.py`

- [ ] **Step 1: Write failing full-run tests**

Use a hot-run fixture with nine valid approvals, including repeated Gate 3 decisions. Assert all valid decisions are counted after ID dedupe, while the latest valid decision per Gate remains a separate current approval projection. Assert legacy run-ID derivation, cross-run rejection, first-pass numerator/denominator and sample size, `not_measured` defect/timing/cost fields, Gate return counting from events, and per-stage cache facts with missing values reported `not_measured`.

- [ ] **Step 2: Verify RED**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_process_assessment.py' -v
```

Expected: import failure.

- [ ] **Step 3: Implement pure collectors**

API:

```python
ProcessAssessmentBuilder.build(
    *, state, events, metrics, run_id, execution_mode, source_paths
) -> dict[str, object]
```

Required outputs include approvals, current canonical approval projection, `first_pass_rate`, `defect_escape_rate`, machine/human/touch/decision/rework/retry metrics, `gate_return_count`, `cost_status`, `cost_inputs`, cache stage facts, measurement statuses, and evidence paths. No missing metric is written as zero.

- [ ] **Step 4: Verify schema and behavior GREEN**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_process_assessment.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_snapshot_schema_validator.py' -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/remix_reference_video/process_assessment.py tests/test_process_assessment.py
git commit -m "feat: build G-B process assessments"
```

### Task 6: Validate Baseline Policy And Comparison Provenance

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/baseline_policy.py`
- Create: `.agents/skills/remix-reference-video/tests/test_baseline_policy.py`

Policy input shape includes `policy_id`, `policy_version`, `require_v1_comparability`, `allowed_not_evaluated_metrics`, cold/hot limits, stage/video thresholds, frozen input SHA-256, optional approved V2 baseline snapshot IDs/hashes, and no caller-supplied baseline status. Status is derived as `establishing` (no approved V2 baseline and valid frozen input/policy), `established` (declared baseline snapshots validate and match), or `invalid` (any hash, policy, run-role, or frozen-input mismatch).

- [ ] **Step 1: Write failing policy tests**

Test missing V1 allowed/forbidden, policy drift, frozen-input drift, unapproved baseline rejection, source snapshot hash mismatch, and derived statuses.

- [ ] **Step 2: Verify RED**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_baseline_policy.py' -v
```

- [ ] **Step 3: Implement `BaselinePolicy.from_mapping()` and comparisons**

Do not trust a supplied `baseline_status`. Each comparison records `pass|fail|not_evaluated`, threshold, source snapshot, reason, and whether owner acknowledgement is required.

- [ ] **Step 4: Verify GREEN and commit**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_baseline_policy.py' -v
git add src/remix_reference_video/baseline_policy.py tests/test_baseline_policy.py
git commit -m "feat: validate G-B baseline policy"
```

### Task 7: Generate Evidence-Bound Five-Stage Snapshots

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/measurement.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_measurement.py`

- [ ] **Step 1: Write failing rubric tests**

Require exactly five canonical framework stages in order. Every rubric row requires `rubric_id`, numeric earned/max points, non-empty evidence paths, and reason. Missing evidence produces `measurement_status=not_scored`, `video_quality_score=null`, and no threshold pass. Complete evidence calculates each `stage_output_quality_score` and the video mean. Add a compatibility test proving the old raw `stage_scores` interface is accepted only through an explicit `retrospective_baseline` adapter and can never produce a measured G-B pass.

- [ ] **Step 2: Verify RED**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_measurement.py' -v
```

Expected: current ungrounded score API accepts invalid measured data.

- [ ] **Step 3: Implement `Phase6Snapshot.build()`**

Signature:

```python
build(
    *, run_id, state_revision, framework_stages, process_assessment,
    baseline_result, input_hashes, lifecycle_status="measured",
    supersedes_snapshot_id=None,
) -> dict[str, object]
```

Bind all evidence and source hashes. `g_b_thresholds_met` excludes owner acknowledgement and is false for `not_scored` stages.

- [ ] **Step 4: Verify GREEN and commit**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_measurement.py' -v
git add src/remix_reference_video/measurement.py tests/test_measurement.py
git commit -m "feat: build evidence-bound Phase 6 snapshots"
```

## Chunk 3: Read-Only CLI And Real-Pair Proof

### Task 8: Add Versioned Snapshot Storage And CLI

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/snapshot_store.py`
- Create: `.agents/skills/remix-reference-video/tests/test_snapshot_store.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_cli.py`
- Modify: `.agents/skills/remix-reference-video/README.md`

Command:

```text
remixctl gb-build-snapshots --task-dir <task> --rubric-input <file> --baseline-policy <file> --json
```

The frozen snapshot has no run ID; validate its content hash and bind generated output independently to authoritative `pipeline_state.run_id`. Write `measurements/<snapshot_id>/phase6_score_snapshot.json` and `process_assessment.json`, then atomically replace `measurements/latest.json` with paths and hashes. Existing snapshot directories are never overwritten.

- [ ] **Step 1: Write failing store and CLI tests**

Assert state/media/manifest hashes remain unchanged, versioned snapshots are immutable, identical idempotency input returns the prior snapshot, changed input creates a new directory with `supersedes_snapshot_id`, and failed promotion leaves the old latest pointer intact.

- [ ] **Step 2: Verify RED**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_snapshot_store.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_cli.py' -v
```

Expected: import/parser failure.

- [ ] **Step 3: Implement staging, schema validation, fsync, and promotion**

The command never calls a media adapter, ApprovalService, archive code, or production unlock path.

- [ ] **Step 4: Verify GREEN and lock protection**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_snapshot_store.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_cli.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_track_b_lock.py' -v
```

- [ ] **Step 5: Commit**

```bash
git add src/remix_reference_video/snapshot_store.py src/remix_reference_video/cli.py tests/test_snapshot_store.py tests/test_cli.py README.md
git commit -m "feat: add read-only G-B snapshot command"
```

### Task 9: Preserve Legacy Pair Measurement Byte-For-Byte

**Files:**
- Modify: `.agents/skills/remix-reference-video/tests/test_gb_frozen_case.py`
- Modify only if required: `.agents/skills/remix-reference-video/src/remix_reference_video/gb_frozen_case.py`

- [ ] **Step 1: Add a regression test**

Call existing `write_pair_measurement()`, save bytes, run the new snapshot command against both sides, and assert `gb_measurement.json` bytes are unchanged. Also assert its existing artifact type and fields remain accepted as the legacy projection.

- [ ] **Step 2: Verify**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_gb_frozen_case.py' -v
```

- [ ] **Step 3: Keep the legacy writer isolated and commit**

```bash
git add tests/test_gb_frozen_case.py src/remix_reference_video/gb_frozen_case.py
git commit -m "test: preserve legacy G-B measurement projection"
```

### Task 10: Full Regression And Existing Pair Dry Run

**Files:**
- Create with `apply_patch`: `work/2026-08-16-gb-pair-real-2/measurement_inputs/phase6-rubric-input.not-scored.json`
- Create with `apply_patch`: `work/2026-08-16-gb-pair-real-2/measurement_inputs/gb-baseline-policy.json`

The rubric file contains all five stage IDs with `measurement_status=not_scored`, empty rubric arrays, and explicit missing-evidence reasons. The policy uses `v2_forward_baseline_v1`, `require_v1_comparability=false`, cold/hot 780/480 limits, score minimum 88, target 91, and the actual frozen snapshot SHA-256.

- [ ] **Step 1: Run the complete Skill suite**

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests pass; platform-dependent tests may remain explicitly skipped.

- [ ] **Step 2: Run Track A**

```bash
cd .agents/skills/remix-reference-video
python3 track_a_static_check.py
```

Expected: PASS.

- [ ] **Step 3: Capture pre-run authoritative hashes**

```bash
shasum -a 256 work/2026-08-16-gb-pair-real-2/gb_measurement.json work/2026-08-16-gb-pair-real-2/cold/pipeline_state.json work/2026-08-16-gb-pair-real-2/hot/pipeline_state.json work/2026-08-16-gb-pair-real-2/cold/remix.mp4 work/2026-08-16-gb-pair-real-2/hot/remix.mp4
```

- [ ] **Step 4: Build honest incomplete snapshots without media generation**

```bash
PYTHONPATH=.agents/skills/remix-reference-video/src python3 -m remix_reference_video.cli gb-build-snapshots --task-dir work/2026-08-16-gb-pair-real-2/cold --rubric-input work/2026-08-16-gb-pair-real-2/measurement_inputs/phase6-rubric-input.not-scored.json --baseline-policy work/2026-08-16-gb-pair-real-2/measurement_inputs/gb-baseline-policy.json --json
PYTHONPATH=.agents/skills/remix-reference-video/src python3 -m remix_reference_video.cli gb-build-snapshots --task-dir work/2026-08-16-gb-pair-real-2/hot --rubric-input work/2026-08-16-gb-pair-real-2/measurement_inputs/phase6-rubric-input.not-scored.json --baseline-policy work/2026-08-16-gb-pair-real-2/measurement_inputs/gb-baseline-policy.json --json
```

Expected: both commands return `measurement_status=not_scored`, measured approval/machine facts, explicit missing quality evidence, and snapshot paths; no TTS/FFmpeg invocation.

- [ ] **Step 5: Re-run hashes and record the P0a handoff**

Expected: every authoritative state/media/legacy measurement hash is unchanged. Record snapshot paths, measured facts, missing owner rubric evidence, and confirmation that ordinary V2 production remains locked.
