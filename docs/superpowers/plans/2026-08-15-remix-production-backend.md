# 参考视频复刻生产后端 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已验证的人工五阶段路径固化为可重复、可审计、可缓存、可测量的 Track B 后端，并在 G-A 通过前保持不可启用。

**Architecture:** 在现有 Fast Path v0 的 runner、storage、contracts、asset index 和 CLI 上增量建设 Gate-aware orchestrator、事务性审批、完整 artifact validator、五阶段 adapter 和只读 FastAPI/SSE 投影。`pipeline_state.json` 是唯一权威，事件/指标/缓存都是派生或审计数据；所有生产产物经过 staging、校验和原子提升。

**Tech Stack:** Python 3.12+, stdlib、现有 `remix_reference_video` package、SQLite asset index、FastAPI/SSE（B0 API 读取层）、pytest/unittest、ffprobe/ffmpeg 外部工具。

**Governance:** 当前 `manifest.json` 的 `track_b=locked_until_g_a` 不得修改。G-A 通过前只能实现隔离 fixture、契约测试、设计和文档；不得启动真实 Track B 生产，不得把 `work/2026-08-15-tablemat-ga-replacement-pilot/` 作为 golden fixture，不得复用其审批。

---

## Chunk 1: B0 状态、审批、事务和执行器

### Execution Boundary

- **Pre-G-A work:** Task 0 (WP-A2 Evidence Harness), Task 6 (lock/fixture tests), static contract tests that do not activate Track B runtime, and documentation are allowed.
- **Post-G-A work:** Tasks 1–5 and 7–17 may not start, be committed, or be activated until `docs/g-a-assessment-2026-08-15.md` (or a newer owner-approved assessment) records `G-A=passed` for a clean pilot with current input hashes and no approval reuse.
- Task 18 is split: its documentation-only status synchronization may happen now; its G-B measurement harness and any runtime activation remain post-G-A/post-Track-B.
- The implementation worker must run a preflight that reads the manifest and the owner-approved G-A assessment before each post-G-A task. Missing, stale, or non-passed evidence exits without writing runtime state, cache directories, or production artifacts.

### Task 0: Implement WP-A2 G-A Evidence Harness (Pre-G-A)

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/ga_evidence.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Create: `.agents/skills/remix-reference-video/tests/test_ga_evidence.py`
- Create: `.agents/skills/remix-reference-video/tests/fixtures/ga_decision.json`
- Modify: `.agents/skills/remix-reference-video/references/fast-path-v0.md`
- Do not modify: `.agents/skills/remix-reference-video/manifest.json`
- Do not modify: existing pilot artifacts except an explicitly owner-designated new clean G-A pilot during actual evidence collection

- [ ] **Step 1: Write failing tests** for non-manual task rejection, task-relative artifact allowlist, symlink/path escape rejection, trusted generated timestamps, package hash/input revalidation, structured decision schema, Gate order/substate enforcement, no approval reuse, and write-free audit.
- [ ] **Step 2: Run focused tests and confirm RED** because the three commands do not exist.
- [x] **Step 3: Implement `ga-prepare-review`** to hash existing task artifacts and atomically create `gate_review_packages/<gate_id>.json`; it must not generate business/media artifacts.
- [x] **Step 4: Implement `ga-record-decision`** to validate a structured decision file, rehash package inputs, generate the approval timestamp internally, and atomically append a scoped decision/update Gate state.
- [x] **Step 5: Implement `ga-audit`** as a write-free check of package-before-approval ordering, input hashes, canonical Gate 3/4 substate order, structural-change restrictions, decision uniqueness, and final G-A readiness.
- [ ] **Step 6: Run focused and full tests**; verify manifest and existing pilot hashes are unchanged.
- [ ] **Step 7: Update operator documentation** with the exact clean-pilot loop and explicit prohibition on using WP-A2 for production.
- [ ] **Step 8: Commit** `feat: add pre-g-a evidence harness` when a Git repository is available.

### Task 1: 扩展权威状态与 Gate 子状态契约

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/contracts.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/storage.py`
- Test: `.agents/skills/remix-reference-video/tests/test_contracts.py`
- Test: `.agents/skills/remix-reference-video/tests/test_storage.py`

- [ ] **Step 1: Write failing contract tests** for `execution_mode`, `run_id`, monotonic `state_revision`, work status values, Gate 3/4 substate IDs, and `blocked` Gate state.
- [ ] **Step 2: Run the focused tests**.

Run: `PYTHONPATH=.agents/skills/remix-reference-video/src python -m unittest .agents/skills/remix-reference-video/tests/test_contracts.py .agents/skills/remix-reference-video/tests/test_storage.py`

Expected: FAIL because the new fields and substate validation are not implemented.

- [x] **Step 3: Implement minimal typed contract changes** without changing V1 schema behavior. Preserve V2 envelope fields and reject unknown/invalid Gate states.
- [x] **Step 4: Add migration-safe defaults** for existing alpha pilot read-only inspection: missing runtime fields remain explicit `null`/unsupported, never silently become `track-b-production`.
- [x] **Step 5: Run the focused tests again** and verify PASS.
- [x] **Step 6: Commit** `feat: define track b state and gate substate contracts`.

### Task 2: Implement transaction journal, atomic state writes, events, and metrics

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/transactions.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/storage.py`
- Test: `.agents/skills/remix-reference-video/tests/test_storage.py`
- Create: `.agents/skills/remix-reference-video/tests/test_transactions.py`

- [ ] **Step 1: Write failing tests** for prepared/committed transactions, state-before-event recovery, event-before-metrics recovery, orphan artifact cleanup, idempotent transaction replay, and revision conflict rejection.
- [ ] **Step 2: Run the focused tests** and confirm the failures describe missing reconciliation behavior.
- [x] **Step 3: Implement** `.transactions/<transaction_id>.json`, expected-revision checks, staging manifest, immutable versioned artifact references, atomic state replacement, idempotent event append, and reconciliation rules from the design spec.
- [x] **Step 4: Ensure metrics gaps become `measurement_status=partial`**, never zero seconds and never a Gate approval change.
- [x] **Step 5: Run tests with `-W error::ResourceWarning`**.

Run: `PYTHONPATH=.agents/skills/remix-reference-video/src python -W error::ResourceWarning -m unittest .agents/skills/remix-reference-video/tests/test_transactions.py .agents/skills/remix-reference-video/tests/test_storage.py`

Expected: PASS.

- [x] **Step 6: Commit** `feat: add recoverable task transactions and audit events`.

### Task 3: Add Approval Service and `approve-gate`

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/approvals.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/contracts.py`
- Create: `.agents/skills/remix-reference-video/tests/test_approvals.py`
- Test: `.agents/skills/remix-reference-video/tests/test_cli.py`

- [ ] **Step 1: Write failing tests** for trusted-server approval timestamps, review-package hash mismatch, stale revision, out-of-order timestamps, incomplete Gate 3/4 substate, cross-task approval rejection, and idempotent repeated approval.
- [x] **Step 2: Implement** `approve-gate --task-dir --gate --review-package-hash --decision-file --actor` as the only state-writing approval command. The decision file must validate against a schema with enumerated `decision`, `scope_type`, `scope_ids`, and strategy fields; free-form notes are advisory only and cannot encode approval policy. Actor identity is required and is recorded by the trusted service.
- [x] **Step 3: Implement the Gate 4 pre-generation transaction** that promotes the candidate plus TTS settings to immutable `approved_production_script.json` before setting `gate4_pre_generation=approved`.
- [x] **Step 4: Add structured exit codes** for invalid command, awaiting Gate, blocked policy, audit failure, and successful approval.
- [x] **Step 5: Run focused CLI and approval tests**.

Run: `PYTHONPATH=.agents/skills/remix-reference-video/src python -W error::ResourceWarning -m unittest .agents/skills/remix-reference-video/tests/test_approvals.py .agents/skills/remix-reference-video/tests/test_cli.py`

Expected: PASS.

- [x] **Step 6: Commit** `feat: add hash-bound gate approval service`.

### Task 4: Build the explicit DAG orchestrator

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/runner.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Create: `.agents/skills/remix-reference-video/tests/test_orchestrator.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_runner.py`

- [ ] **Step 1: Write failing tests** for Gate stop, exact next-node selection, parallel-safe read-only nodes, blocked/stale propagation, attempt IDs, and no self-approval.
- [x] **Step 2: Define adapter interface** with `required_inputs`, `required_gates`, `declared_outputs`, `cache_fingerprint`, and `execute`.
- [x] **Step 3: Implement DAG selection** for the normative sequence in the design spec, including Gate 3 and Gate 4 summaries.
- [x] **Step 4: Implement `run`, `stage`, `resume`, `status`, and `audit` through the orchestrator**, preserving Fast Path v0 fixture behavior.
- [x] **Step 5: Run all B0 tests**.

Run: `PYTHONPATH=.agents/skills/remix-reference-video/src python -W error::ResourceWarning -m unittest discover -s .agents/skills/remix-reference-video/tests -p 'test_*.py'`

Expected: Existing 75 tests remain green, plus the new B0 tests.

- [ ] **Step 6: Commit** `feat: add gate-aware production orchestrator`.

### Task 5: Implement complete artifact validation

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/artifact_validator.py`
- Modify: `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`
- Create: `.agents/skills/remix-reference-video/tests/test_artifact_validator.py`

- [ ] **Step 1: Write failing tests** for envelope/shape, artifact hash references, path allowlist, symlink escape, Gate 3 broad-range containment, timeline containment, and Gate 5 output bundle.
- [x] **Step 2: Implement validator results as structured data**; validators must not mutate state or approve a Gate.
- [x] **Step 3: Wire validation into staging promotion and `audit`**.
- [x] **Step 4: Run the focused validator and all regression tests**.
- [x] **Step 5: Commit** `feat: validate complete remix artifacts before promotion`.

### Task 6: Add B0 isolated fixture and prove no runtime activation before G-A (Pre-G-A)

**Files:**
- Create: `.agents/skills/remix-reference-video/tests/fixtures/track_b_plan.json`
- Create: `.agents/skills/remix-reference-video/tests/test_track_b_lock.py`
- Modify: `.agents/skills/remix-reference-video/references/fast-path-v0.md`
- Do not modify: `.agents/skills/remix-reference-video/manifest.json`

- [ ] **Step 1: Write failing lock tests** that reject `track-b-production` and real production plans while manifest tracks are locked, but permit isolated contract fixtures.
- [ ] **Step 2: Implement the lock guard** in the existing Fast Path v0 CLI/fixture path only; do not create Track B runtime modules, caches, or production state.
- [ ] **Step 3: Verify existing pilot `status/audit` remains read-only and still rejects `fast/resume`.
- [ ] **Step 4: Run the complete package suite** and record results in the implementation report.
- [ ] **Step 5: Commit** `test: enforce track b lock until clean g-a`.

## Chunk 2: B1 Reference Split and B4a Shared Asset Index

### Task 7: Define stage adapter manifests

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/__init__.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/reference_split.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/asset_index.py`
- Create: `.agents/skills/remix-reference-video/tests/test_stage_adapters.py`

- [x] **Step 1: Write failing adapter tests** for declared inputs, outputs, Gate 1 stop, implementation version, and cache fingerprint.
- [x] **Step 2: Implement declarative adapter manifests**; content execution remains outside the orchestrator and is connected in Task 8.
- [x] **Step 3: Run focused adapter tests** and commit `feat: define reference and index adapter manifests`.

### Task 8: Connect incremental technical asset indexing

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/asset_index.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Test: `.agents/skills/remix-reference-video/tests/test_asset_index.py`

- [x] **Step 1: Add tests** for cold index, warm cache hit, content hash change, unreadable media, probe timeout retry, and path escape.
- [x] **Step 2: Implement `index-assets` through the shared cache root** with explicit implementation-bound keys.
- [x] **Step 3: Ensure source files are never moved or modified.**
- [x] **Step 4: Run asset-index tests and the full package suite.**
- [x] **Step 5: Commit** `feat: connect shared incremental asset index`.

## Chunk 3: B2 Blueprint and B3 Controlled Mutation

### Task 9: Implement Blueprint and Gate 2 package adapters

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/blueprint.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/mutation.py`
- Create: `.agents/skills/remix-reference-video/tests/test_blueprint_mutation_adapters.py`

- [x] **Step 1: Write failing tests** for precheck versus authoritative coverage ownership, Gate 2 atomic baseline/mutation package, forbidden new claims, fallback lint, and timing lint.
- [x] **Step 2: Implement adapters** that produce drafts and review packages but never approve them or generate TTS.
- [x] **Step 3: Add stale propagation** when Brief, baseline, mutation, claim boundary, or fallback changes.
- [x] **Step 4: Run focused and full regression tests**; commit intentionally skipped per owner instruction.

### Task 10: Implement evidence-gated production script compilation

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/mutation.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/script_compile.py`
- Create: `.agents/skills/remix-reference-video/tests/test_script_compile.py`

- [x] **Step 1: Write failing tests** for missing evidence, approved fallback selection, forbidden claim strengthening, input hash recording, and candidate-only output.
- [x] **Step 2: Implement `build-production-script`** to consume only Gate 2 bundle, approved evidence matrix, and approved fallback.
- [x] **Step 3: Keep `approved_production_script.json` creation inside the Approval Service transaction; the compiler must never create it.**
- [x] **Step 4: Run focused and full regression tests**; commit intentionally skipped per owner instruction.

## Chunk 4: B4 Retrieval, Coverage, Matching, and Gate 3

### Task 11: Implement authoritative coverage and deterministic matching adapters

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/retrieval.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/asset_index.py`
- Create: `.agents/skills/remix-reference-video/tests/test_retrieval_adapters.py`

- [x] **Step 1: Write failing tests** for precheck/authoritative scope, qualification gates, semantic/action/product/scene scoring, perceptual duplicate suppression, global scheduling, and missing-material blocking.
- [x] **Step 2: Implement `build-coverage --scope authoritative` and `match-assets`** with deterministic scoring version in cache fingerprints.
- [x] **Step 3: Implement candidate review package with explicit overlay policy** (`retain_source_text`, `crop`, `cover`, `replace`, `no_action`) and approved broad ranges.
- [x] **Step 4: Run focused and full regression tests**; commit intentionally skipped per owner instruction.

### Task 12: Implement Gate 3 selection, evidence closure, and stale propagation

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/retrieval.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/gate3.py`
- Create: `.agents/skills/remix-reference-video/tests/test_gate3.py`

- [x] **Step 1: Write failing tests** for separate selection/evidence substates, current-hash approval binding, material range extension, source-content change, overlay change, and Gate 2 return for structural changes.
- [x] **Step 2: Implement** `build-material-selection-package`, `freeze-fragment-plan`, `validate-script-evidence`, and `summarize-gate3`.
- [x] **Step 3: Ensure both Gate 3 substates become stale on relevant material/overlay changes, while unrelated assets remain reusable.**
- [x] **Step 4: Run focused and full regression tests**; commit intentionally skipped per owner instruction.

## Chunk 5: B5 Reconstruction and Gate 4/5

### Task 13: Materialize broad ranges and generate voice idempotently

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/reconstruction.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/voice.py`
- Create: `.agents/skills/remix-reference-video/tests/test_reconstruction_adapters.py`
- Create: `.agents/skills/remix-reference-video/tests/test_voice.py`

- [x] **Step 1: Write failing tests** for source copy-only behavior, material manifest hashes, approved script-only TTS input, idempotency key, retry categories, timeout, rate limit, and incomplete audio rejection.
- [x] **Step 2: Implement `materialize-approved-broad`** as a copy/export operation bounded by the immutable fragment plan.
- [x] **Step 3: Implement `generate-voice`** with 60-second per-attempt timeout, three-attempt maximum, retryable error categories, capped backoff, and provider identity in the cache key.
- [x] **Step 4: Add `voice_preflight` between Gate 3 and Gate 4, binding video duration budgets and blocking TTS before generation when the estimate exceeds budget.
- [x] **Step 5: Run focused and full regression tests**; commit intentionally skipped per owner instruction.

### Task 14: Build timeline, captions, proxy and boundary validation

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/reconstruction.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/timeline.py`
- Create: `.agents/skills/remix-reference-video/tests/test_timeline.py`
- Create: `.agents/skills/remix-reference-video/tests/test_proxy_validation.py`

- [x] **Step 1: Write failing tests** for measured voice duration, subtitle non-overlap, broad-range containment, 1.00x speed, proxy profile selection, boundary frames, preflight-before-TTS ordering, and no formal render before Gate 4 post approval.
- [x] **Step 2: Implement `build-reconstruction-timeline`** using real TTS duration and only narrowing Gate 3 ranges.
- [x] **Step 3: Implement `render-proxy` and `validate-proxy-boundaries`** with default 540x960/30fps and explicit 720x1280/30fps override in the task config.
- [x] **Step 4: Run focused and full regression tests**; commit intentionally skipped per owner instruction.

### Task 15: Render final bundle and Gate 5 package

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/reconstruction.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/adapters/render.py`
- Create: `.agents/skills/remix-reference-video/tests/test_render_adapter.py`

- [x] **Step 1: Write failing tests** for Gate 4 summary prerequisites, final render inputs, stream/duration checks, SRT sidecar, output bundle hashes, Gate 5 awaiting-user status, and pilot archive prohibition.
- [x] **Step 2: Implement** `render-final` and `build-gate5-package`; do not self-approve Gate 5.
- [x] **Step 3: Implement ordinary-task `archive-approved` with a hard `manual-contract-only` refusal.**
- [x] **Step 4: Run focused render tests and full regression tests.**
- [x] **Step 5: Commit intentionally skipped per owner instruction.**

## Chunk 6: FastAPI/SSE, G-B evidence, and documentation synchronization

### Task 16: Add read-only FastAPI/SSE projection

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/api.py`
- Create: `.agents/skills/remix-reference-video/tests/test_api.py`
- Modify: `.agents/skills/remix-reference-video/pyproject.toml`

- [x] **Step 1: Write failing API tests** for redacted `ProgressView`, ETag/revision, artifact allowlist, SSE reconnect with `Last-Event-ID`, event deduplication, and no Gate-write endpoint.
- [x] **Step 2: Add FastAPI dependency only in the API runtime extra**; keep CLI and core package usable without the server.
- [x] **Step 3: Implement read-only task list/detail/artifact metadata and SSE revision notices.**
- [ ] **Step 4: Run API tests and verify the API reads state rather than maintaining a second state machine.**
- [ ] **Step 5: Commit** intentionally skipped per owner instruction after Step 4 is verified.

### Task 17: Implement G-B measurement and frozen-pair harness

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/measurement.py`
- Create: `.agents/skills/remix-reference-video/tests/test_measurement.py`
- Create: `.agents/skills/remix-reference-video/tests/fixtures/g_b_pair_plan.json`
- Modify: `docs/reference-video-remix-optimization-plan.md`

- [x] **Step 1: Write failing tests** for empty isolated cold caches, cloned hot-cache snapshots, controlled visual mutation, separate approval records, exclusion of human Gate waits, no cross-run cache reads, and V1 comparability failure.
- [x] **Step 2: Implement `phase6_score_snapshot.json` generation** using the authoritative per-stage V2 thresholds and total `>=88` / target `91`.
- [x] **Step 3: Record `machine_api_critical_path_seconds`, `human_wait_seconds`, `operator_touch_seconds`, `rework_seconds`, `gate_return_count`, and cache status separately.**
- [x] **Step 4: Run the isolated fixture tests; ordinary Track B production remains prohibited until G-B and supervised-operator approval.**
- [x] **Step 5: Commit intentionally skipped per owner instruction.**

### Task 18: Synchronize project documentation and release state

**Files:**
- Modify: `docs/reference-video-remix-optimization-plan.md`
- Modify: `docs/reference-video-remix-backend-first-technical-design.md`
- Modify: `AGENTS.md`
- Modify: `.agents/skills/remix-reference-video/SKILL.md`
- Modify: `.agents/skills/remix-reference-video/references/fast-path-v0.md`
- Do not modify: `.agents/skills/remix-reference-video/manifest.json`
- Do not modify: `work/2026-08-15-tablemat-ga-replacement-pilot/`

- [x] **Step 1: Record the replacement pilot as Gate 5-passed and retain the independent clean-harness G-A result**, including the three historical audit gaps and the fact that the replacement pilot remains in `work/` by contract.
- [x] **Step 2: Add the production-backend design as the normative Track B reference** and link the implementation plan.
- [x] **Step 3: Keep all docs consistent on `track_b=locked_until_g_a`, `track_c=locked_until_g_b`, no approval reuse, and no pilot archive.**
- [x] **Step 4: Update Fast Path docs** to distinguish tested v0 fixture behavior from the lock-protected native runner and incomplete production registry.
- [x] **Step 5: Run static validation, trigger smoke, package tests, and link/path checks.**

Run:

```bash
PYTHONPATH=.agents/skills/remix-reference-video/src python -W error::ResourceWarning -m unittest discover -s .agents/skills/remix-reference-video/tests -p 'test_*.py'
python3 .agents/skills/remix-reference-video/track_a_static_check.py
```

Expected: all package tests pass; static check reports valid; manifest remains alpha and Track B locked.

- [ ] **Step 6: Commit documentation synchronization** `docs: record production backend implementation boundary`.

## Final Verification Checklist

- [ ] `75/75` existing Fast Path tests remain green, with all new B0/B1–B5/API tests green.
- [ ] `status/audit` on the existing replacement pilot remains read-only and reports unsupported production execution rather than mutating it.
- [ ] No test or command writes to the pilot directory or changes its Gate decisions.
- [ ] Every Gate write is hash-bound, revision-checked, server-timestamped, and auditable.
- [ ] Gate 3 and Gate 4 substate transitions cannot be skipped.
- [ ] A crash at every transaction boundary reconciles deterministically.
- [ ] A repeated run reports cache hits without reusing approvals.
- [ ] Source content, overlay strategy, claim/fallback, TTS, timeline, and render changes invalidate exactly the affected downstream graph.
- [ ] G-B harness uses isolated cold/hot caches and separate approval records.
- [ ] FastAPI/SSE remains read-only and consumes the same state authority.
- [ ] `manifest.json` remains unchanged until owner-recorded G-A approval.
- [ ] No ordinary V2 production release or Backlot UI is claimed before G-B.
