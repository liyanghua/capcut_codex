# Native Runner CLI And G-B Pair Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the real Native Runner through the supported `remixctl` production CLI, complete one isolated real G-B cold/hot validation pair, and synchronize the backend status/design documents with measured evidence.

**Architecture:** Keep `pipeline_state.json` as the only approval authority. Add a CLI-only factory that resolves an explicit `production_runtime_config.json`, builds the existing real Native Registry, and preserves the Track B manifest lock for ordinary production. A dedicated `gb-pair` command is the only isolated exception: it requires `g_b_frozen_input_snapshot.json`, separate cold/hot task roots, fresh package-hash/revision-bound approvals for every Gate, and never enables ordinary V2 production or archive. The cache transfer is a verified copy of the cold run's declared SQLite index only; no decisions, task artifacts, absolute source-root references, or output files are copied. Record machine, human, cache, retry, and gate metrics as evidence rather than inferring readiness from a single Gate 5 result.

**Tech Stack:** Python 3.12+, `remixctl`, Native Registry/ProductionRunner, SQLite asset cache, FFmpeg/ffprobe, Doubao V3 TTS, unittest, Markdown.

---

## Chunk 1: CLI Integration

### Task 1: Define the supported production CLI contract

**Files:**
- Modify: `.agents/skills/remix-reference-video/tests/test_cli.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Test: `.agents/skills/remix-reference-video/tests/test_cli.py`

- [ ] Write failing tests proving the production runner factory loads the real registry from an explicit `production_runtime_config.json`, rejects missing/symlink/escaped paths and secrets in output without writing task state, and preserves the existing legacy reference-only fixture path.
- [ ] Run the focused CLI test and confirm it fails because `_production_runner` only registers the reference split adapter.
- [ ] Implement the smallest factory/config resolver for `reference_path`, `asset_root`, `brief_path`, `asset_profiles_path`, `cache_path`, `doubao_client_script`, optional `python_executable`, and `archive_root`; paths resolve relative to the config file, reject symlinks/escapes, and never serialize credential values.
- [ ] Keep `track_b=locked_until_g_a` and `v2_production_enabled=false` as release guards. Add only an explicit `gb-pair` command that requires `g_b_frozen_input_snapshot.json`, `execution_mode=track-b-production`, `pilot_policy.archive_allowed=false`, and a task-local no-archive policy; arbitrary `run/resume/stage` flags must still reject while locked.
- [ ] Add exact top-level aliases `production-run`, `production-resume`, `production-stage`, `production-status`, and `production-audit` with `--runtime-config`; retain existing commands and test both forms.
- [ ] Run the focused CLI tests and the Track B lock tests.

## Chunk 2: Real G-B Cold/Hot Pair

### Task 2: Add an executable frozen-pair command and evidence output

**Files:**
- Modify: `.agents/skills/remix-reference-video/tests/test_gb_frozen_case.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/gb_frozen_case.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Create: `work/<date>-gb-frozen-pair/gb_measurement.json`

- [ ] Write a failing test requiring immutable reference/Brief/profile/all source asset/code/runtime hashes, separate cold and hot task roots, separate approval records bound to each package revision, cache hit accounting, and machine/human/operator/rework timing fields.
- [ ] Run the focused G-B test and confirm the evidence shape is incomplete.
- [ ] Implement a bounded pair runner that snapshots and verifies reference/Brief/profile/asset/code/Python/dependency/FFmpeg/ffprobe/Doubao model inputs, clones only the completed cold SQLite cache into the hot run, verifies the cache key has no absolute source-root dependency, and never copies task artifacts or approvals.
- [ ] Capture fresh owner approvals for every stop Gate in each run; each record must bind the current package SHA, run ID, state revision, and trusted timestamp. Record approval timestamps, retries, rework, and Gate returns without reusing a decision key.
- [ ] Run the real frozen input through the CLI path with actual FFmpeg, ffprobe, and Doubao TTS, preserving the current Gate sequence and package validation; if a prerequisite is unavailable, write `not_measured` with a reason rather than substituting a fixture.
- [ ] Record per-stage and aggregate monotonic machine/API critical path, trusted human wait, operator touch, rework, retry/network, and Gate-return durations; each metric has `status`, `seconds`, `started_at`, `ended_at`, and `reason` when not measured.
- [ ] Require two valid Gate 5 bundles, cold miss/hot hit evidence, media contract checks, timeline containment, and distinct output hashes before any G-B pass claim; keep V1 comparability explicitly `not_measured` unless a real V1 baseline is run.
- [ ] Record a failure-injection retry that proves no failed cold output or approval pollutes the hot cache.
- [ ] Run the pair test and inspect the evidence artifact before declaring G-B status.

## Chunk 3: Documentation Synchronization

### Task 3: Update the design and implementation status documents

**Files:**
- Modify: `docs/reference-video-remix-backend-first-technical-design.md`
- Modify: `docs/remix-production-backend-implementation-status.md`
- Modify: `docs/reference-video-remix-optimization-plan.md`
- Modify: `AGENTS.md`
- Modify: `.agents/skills/remix-reference-video/SKILL.md`
- Modify: `.agents/skills/remix-reference-video/manifest.json`

- [ ] Record that the independent G-A assessment passed, while ordinary V2 production remains locked pending G-B and supervised operations.
- [ ] Document the supported CLI entry points, exact configuration flags, and the isolated G-B pair command/marker requirements.
- [ ] Link the measured cold/hot evidence artifact and explicitly distinguish fixture results from real-media results.
- [ ] List remaining release blockers: API route integration if still skipped, Backlot UI, supervised operator trial, manifest release update, and any unmet cold/hot thresholds.
- [ ] Do not claim the one-hour target or ordinary V2 release until the measured evidence meets the documented thresholds.

## Chunk 4: Verification

### Task 4: Run focused and full verification

**Files:**
- No production file changes expected.

- [ ] Run focused CLI, lock, G-B, security/transaction, media contract, dependency-prerequisite, and API tests.
- [ ] Run the complete unittest suite and Track A static checks.
- [ ] Run `remixctl` help/status/audit smoke commands against the frozen pair.
- [ ] Review the final diff and state/document consistency before reporting completion.
