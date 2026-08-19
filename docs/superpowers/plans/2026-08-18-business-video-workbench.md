# Business Video Workbench Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the engineering-oriented Gate evidence page with a business-facing single-run workspace containing a storyboard, media preview, review timeline, unclassified assets, and a five-stage decision assistant.

**Architecture:** Add a deterministic `WorkbenchWorkspaceBuilder` projection over existing canonical artifacts and expose it through a read-only workspace API. Keep `/review`, decision, change, approval, production-lock, and media boundaries unchanged. Render the new projection with the existing vanilla HTML/CSS/JS client and retain a legacy layout selected by `WORKBENCH_UI_MODE`.

**2026-08-18 operator revision:** The first workspace implementation is not product-accepted. The former selection model that replaced the center preview is superseded. The next pass must keep a fixed stage-main preview, render media-rich read-only storyboard cards, show the complete five-stage process, and turn the three text lanes into a visual static review timeline.

**Tech Stack:** Python 3.11+, FastAPI, JSON Schema, vanilla JavaScript, HTML, CSS, unittest.

---

## Chunk 1: Business Projection And API

### Task 1: Add Workspace Contract And Deterministic Projection

**Files:**
- Create: `.agents/skills/remix-reference-video/schemas/workbench-workspace-view.schema.json`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/workspace_view.py`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/workspace_media.py`
- Create: `.agents/skills/remix-reference-video/tests/test_workspace_view.py`
- Modify: `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`

- [x] Write failing schema and builder tests for the envelope, five business stages, stable element/shot/audio IDs, unclassified assets, Gate-specific timeline fallback, missing-artifact explanations, and byte-identical repeated builds.
- [x] Require and test top-bar task/product/platform/current-stage/progress/connection metadata; storyboard card label/thumbnail/purpose/status; explicit unclassified reason and replacement eligibility; and decision-assistant question/recommendation/evidence/risks/next action.
- [x] Add Gate 1 reference video/shot order/duration, Gate 2 approved claim/forbidden claim/structure, and Gate 3 reference-vs-source selection, source-text treatment, evidence coverage, and exact missing-object disclosures.
- [x] Add explicit fixtures for Gate 4 production script, voice preflight, generated voice and subtitle boundaries; add Gate 5 L0/L1/P summaries, production-audit, subtitles, render report, and delivery files. Missing files must produce business `not_ready` states, never fabricated values.
- [x] Run `PYTHONPATH=src <venv-python> -m unittest tests.test_workspace_view -v`; expect import/schema failures.
- [x] Register `workbench_workspace_view` as a derived review artifact without adding it to production state authority.
- [x] Implement `WorkbenchWorkspaceBuilder.build(gate_id)` using only canonical artifacts and deterministic fallbacks; never infer product claims from filenames.
- [x] Implement one `WorkspaceMediaAuthorizer` shared by the projection and `/media`: authorize only paths emitted by the current workspace/review projection, reject path escape, symlink, wrong run, stale package revision, and files absent from the current projection.
- [x] Re-run the focused tests; expect PASS.

### Task 2: Expose Workspace API And Legacy Toggle

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/api.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/review_view.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/workbench_decision.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_api.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_workbench_decision.py`

- [x] Write failing tests for `GET /api/v1/runs/{run_id}/workspace`, ETag/304, stale package rejection, registry containment, shared media authorization, and unchanged decision/change endpoints.
- [x] Write failing tests proving `WORKBENCH_UI_MODE=legacy|workspace` selects the page template and invalid values fail closed to legacy.
- [x] Define one blocking predicate in the business review projection: approval is allowed only when no current review risk has `blocking=true`. Return the result in `decision_context` and reuse it in `WorkbenchDecisionService`.
- [x] Write negative tests proving the decision service rejects approval while the shared predicate is false and rejects a rejection without a non-empty business reason; prove change requests require target object, supported type, and non-empty reason at HTTP and service boundaries.
- [x] Run focused API/CLI tests; expect missing route and toggle failures.
- [x] Add the workspace endpoint using `WorkbenchWorkspaceBuilder` and bind its ETag to the deterministic workspace snapshot. Route all media requests through the shared workspace/review authorizer.
- [x] Add a server-start UI mode resolved once from the CLI/environment; do not accept arbitrary remote mode changes.
- [x] Re-run focused tests; expect PASS.

## Chunk 2: Business Workspace UI

### Task 3: Build Storyboard, Preview, Timeline, And Decision Assistant

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/templates/review_workbench.html`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/templates/review_workbench_legacy.html`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.js`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.css`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench_legacy.js`
- Create: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench_legacy.css`
- Modify: `.agents/skills/remix-reference-video/tests/test_api.py`

- [x] Write failing page-contract tests for `storyboard-panel`, `unclassified-assets`, `preview-stage`, `review-timeline`, `decision-assistant`, five business stages, diagnostics disclosure, and retained approve/change/reject controls. Prove legacy mode loads separate immutable legacy JS/CSS and still renders its original DOM.
- [x] Write failing client-contract tests for loading `/workspace` and `/review`, stable entity selection, preview/timeline synchronization, play/pause and playhead seek, change initiation from a selected shot/timeline segment, media rendering, structured change targeting, and revision-only reload behavior.
- [x] Write failing interaction tests proving blocked approval is disabled/rejected, rejection requires a reason, and change confirmation requires selected object/type/reason plus a current impact preview.
- [x] Run focused API tests and `node --check`; expect contract failures.
- [x] Build the responsive shell: light business rails, dark 9:16 media preview, bottom three-track timeline, and fixed decision actions.
- [x] Render elements, shots, audio, and unclassified assets from the workspace projection without displaying raw paths or hashes.
- [x] Render Gate 4 script/voice/preflight/boundaries and Gate 5 L0/L1/P, production-audit, subtitles, render report, and delivery links in business language.
- [x] Synchronize entity selection across storyboard, preview, and timeline; use existing change preview/apply APIs and show earliest affected stage, stale stages, render impact, estimated time, current risks, and explanation before confirmation.
- [x] Supersede the previous synchronization behavior: entity selection must retain the stage-main preview, seek/highlight the related timeline location, and expose only read-only object detail.
- [x] Freeze the current client into separate legacy HTML/JS/CSS assets; preserve actor/revision/package binding in both modes.
- [x] Re-run focused tests and JavaScript syntax checks; expect PASS.

## Chunk 3: Regression And Manual Acceptance

### Task 4: Verify Compatibility, Responsive States, And Rollback

**Files:**
- Modify: `docs/review-workbench-manual-acceptance.md`
- Create: `docs/review-workbench-workspace-acceptance-2026-08-18.md`
- Modify: `.agents/skills/remix-reference-video/README.md`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/api.py`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/cli.py`
- Modify: `.agents/skills/remix-reference-video/tests/test_api.py`
- Test: `.agents/skills/remix-reference-video/tests/`

- [ ] Add manual checks for desktop 1440px and narrow 390px layouts, loading/awaiting/blocked/missing/conflict/completed states, and all five business stages with Gate 3/4 substeps.
- [x] Document `WORKBENCH_UI_MODE`, workspace URL, legacy rollback, and the read-only timeline boundary. Unset defaults to `legacy` during implementation.
- [x] Run the full Skill suite; expect all tests PASS.
- [x] Run Track A, Python compile, JavaScript syntax, and `git diff --check`; expect PASS.
- [ ] Start the localhost workbench from the isolated worktree and manually verify a registered run loads without repeated refresh.
- [ ] Verify the two-click criterion: from a storyboard object, preview/timeline/change request is reachable in at most two interactions.
- [ ] Execute and record both 1440px and 390px viewport checks in `docs/review-workbench-workspace-acceptance-2026-08-18.md`, including observed pass/fail evidence for layout, text fit, preview, timeline, decision controls, and legacy rollback.
- [ ] After both viewport records pass, write a failing API/CLI test for an unset mode defaulting to `workspace`, change the default, and retain explicit `WORKBENCH_UI_MODE=legacy` rollback.
- [ ] Confirm the legacy mode loads the prior page and no production artifact, approval, cache, or lock changes during read-only inspection.
- [ ] Commit the completed workspace implementation.

## Chunk 4: Operator Feedback Revision

### Task 5: Media-Rich Storyboard And Fixed Stage Preview

- [x] Add failing projection tests for element/shot thumbnail refs, media type, fragment relationships, explicit missing-preview states, and authorization of existing `gate3_review_frames/fragmentNN.jpg` files.
- [x] Add failing projection tests for per-Gate main preview resolution: Gate 1/2 reference video, Gate 3/4 existing `proxy.mp4` with explicit reference fallback, Gate 5 `remix.mp4`, and a business empty state when every candidate is absent.
- [x] Resolve `preview.media_ref` from canonical facts (`recipe.reference_video.path`, `proxy.mp4`, `remix.mp4`) instead of non-existent keys, and extend the media allowlist accordingly.
- [x] Project real review frames for approved elements and production shots without creating media or inferring claims from filenames.
- [x] Replace flat text cards with grouped, read-only media cards showing thumbnail, type, business label, relationship and status; keep add/replace actions in the existing structured change flow.
- [x] Keep the center bound to `workspace.preview.media_ref`; storyboard selection may highlight, seek and open read-only detail but must never replace the main media.

### Task 6: Complete Process And Static Review Timeline

- [x] Render all five business stages as a vertical stepper; completed stages are read-only and expandable, the current stage is expanded and actionable, future stages are locked.
- [x] Enrich timeline segments with real start/end/duration, object relationship and available thumbnail refs.
- [x] Render a ruler, playhead, proportional picture clips with thumbnails, proportional voice blocks, and readable subtitle blocks. Do not fabricate waveforms and do not add drag/edit/write behavior.
- [x] Add client-contract tests for fixed preview behavior, all-stage visibility, proportional track data, timeline seeking and unchanged approval/change bindings.
- [x] Add client-contract tests for element/shot/audio selection: highlight, timeline seek, read-only detail, and no center media replacement for every storyboard card type.

### Task 7: Repeat Product Acceptance

- [x] Mark the first desktop acceptance as changes requested and keep unset `WORKBENCH_UI_MODE` defaulting to `legacy`.
- [x] Re-run full Skill tests, Track A, JavaScript syntax and diff checks.
- [ ] Repeat desktop and `390px` manual acceptance against the revised product criteria before changing the default UI mode.
