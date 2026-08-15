# Fast Path v0 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a single-task, Gate-aware, resumable executor that measures real stage time, reuses unchanged work, and pre-indexes the local asset library without changing the existing V2 approval contract.

**Architecture:** A standard-library Python package lives inside the existing Skill. `remixctl` reads a declarative argv plan, validates all paths and executables, executes one stage at a time, appends durable events/metrics, and stops whenever the business state is awaiting user approval. A separate SQLite index caches technical facts for reusable assets. The current `manual-contract-only` pilot is read-only to this executor.

**Tech Stack:** Python 3.12+, stdlib `argparse/json/sqlite3/subprocess/hashlib/fcntl`, FFmpeg/FFprobe, `unittest`, uv.

**Implementation status (2026-08-15):** Completed and hardened as an experimental executor. Fast Path tests are `75/75`; historical regressions are `59/59`. Gate/hash invalidation, task-root symlink rejection, implementation-bound cache keys, retryable probe timeouts and stricter audit checks are covered. Track B, V2 production, FastAPI and SSE remain disabled. The replacement pilot still fails read-only Fast Path audit (`unsupported execution_mode`, missing `state_revision` and zero events); this v0 result does not prove real five-stage production speed.

The confirmed production-backend design and implementation plan are `docs/superpowers/specs/2026-08-15-remix-production-backend-design.md` and `docs/superpowers/plans/2026-08-15-remix-production-backend.md`. Until a clean owner-approved G-A, only isolated fixtures, lock tests and documentation may change; no Track B runtime or production cache may be activated.

---

## Chunk 1: State, Events, Cache, and Runner

### Task 1: Define the Fast Path contracts

**Files:**
- Create: `.agents/skills/remix-reference-video/pyproject.toml`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/__init__.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/contracts.py`
- Test: `.agents/skills/remix-reference-video/tests/test_contracts.py`

- [x] Write failing tests for plan parsing, stable input fingerprints, rejected shell strings, path escape, and unsupported execution modes.
- [x] Run tests and confirm failures are caused by missing production modules.
- [x] Implement immutable plan/stage/result dataclasses and validation.
- [x] Run tests and confirm they pass.

### Task 2: Implement durable state, events, and metrics

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/storage.py`
- Test: `.agents/skills/remix-reference-video/tests/test_storage.py`

- [x] Write failing tests for atomic JSON writes, monotonic `state_revision`, locked JSONL append, and reconciliation after an event gap.
- [x] Run tests and confirm expected failures.
- [x] Implement task-local locks, staging writes, state updates, `pipeline_events.jsonl`, and `stage_metrics.jsonl` writers.
- [x] Run tests and confirm they pass.

### Task 3: Implement Gate-aware execution and cache hits

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/runner.py`
- Test: `.agents/skills/remix-reference-video/tests/test_runner.py`
- Test fixture: `.agents/skills/remix-reference-video/tests/fixtures/mock_stage.py`

- [x] Write failing tests for successful execution, Gate stop, resume, cache hit, failed command, timeout, missing output, and refusal to mutate `manual-contract-only`.
- [x] Run tests and confirm expected failures.
- [x] Implement argv-only subprocess execution, prerequisite Gate checks, post-stage Gate stops, fingerprints, output hash validation, and task-local cache records.
- [x] Run tests and confirm they pass.

## Chunk 2: Shared Asset Index

### Task 4: Implement incremental technical indexing

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/asset_index.py`
- Test: `.agents/skills/remix-reference-video/tests/test_asset_index.py`

- [x] Write failing tests for recursive discovery, supported media filtering, SHA deduplication, changed-file invalidation, unreadable media, and warm cache hits.
- [x] Run tests and confirm expected failures.
- [x] Implement SQLite schema, FFprobe adapter, incremental scan, content/file separation, and index summary metrics.
- [x] Run tests and confirm they pass.

## Chunk 3: CLI and Vertical Verification

### Task 5: Implement `remixctl`

**Files:**
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Create: `.agents/skills/remix-reference-video/scripts/remixctl.py`
- Test: `.agents/skills/remix-reference-video/tests/test_cli.py`

- [x] Write failing tests for `status`, `audit`, `index-assets`, `fast`, `resume`, JSON output, and stable exit codes.
- [x] Run tests and confirm expected failures.
- [x] Implement CLI commands and human-readable summaries.
- [x] Run tests and confirm they pass.

### Task 6: Add fixture and operator documentation

**Files:**
- Create: `.agents/skills/remix-reference-video/tests/fixtures/fast_path_plan.json`
- Create: `.agents/skills/remix-reference-video/references/fast-path-v0.md`
- Modify: `.agents/skills/remix-reference-video/SKILL.md`

- [x] Add an isolated plan fixture that stops at a Gate, resumes after explicit approval, then produces a cache hit.
- [x] Document standard-task limits, command examples, artifact locations, exit codes, and the production lock.
- [x] Add only a concise reference from `SKILL.md`; do not enable Track B in the manifest.

### Task 7: Verify end to end

- [x] Generate `uv.lock` without adding runtime dependencies.
- [x] Run the full new unittest suite.
- [x] Run existing Track A, matcher, Gate 4, timeline, and Gate 5 tests.
- [x] Run fixture `fast → awaiting_user → resume → success → cache_hit`.
- [x] Run cold and warm indexing against `assets/` and record elapsed time and counts.
- [x] Run read-only `status/audit` against `work/2026-08-13-tablemat-pilot/` and verify no file hashes change.
- [x] Record measured results in `.agents/skills/remix-reference-video/references/fast-path-v0.md`.

## Acceptance Criteria

- One command executes all currently eligible stages and stops at the first required Gate.
- `resume` never reruns a valid cached stage and never crosses an unapproved Gate.
- Current alpha.1 pilot is not modified by `status/audit` and is rejected by `fast/resume`.
- Every stage attempt writes actual elapsed time; unknown human wait remains unknown instead of zero.
- Warm asset indexing reports cache hits and avoids FFprobe for unchanged files.
- No shell evaluation, path escape, plaintext credential output, or unregistered source mutation is possible.
- Fast Path v0 is explicitly experimental and does not mark Track B or V2 production as enabled.
