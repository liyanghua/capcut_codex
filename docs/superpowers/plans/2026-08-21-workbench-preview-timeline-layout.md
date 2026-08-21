# Workbench Preview Timeline Layout Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the central stage preview from crossing its CSS Grid row and covering the review timeline while keeping the final video fully visible and the mobile layout usable.

**Architecture:** Keep the existing three-column workbench and DOM order. Make the desktop preview row `minmax(280px,1fr)`, constrain the preview box to that row, and explicitly reset the grid and preview sizing at the 820px mobile breakpoint. Preserve all media `contain` behavior and business interactions.

**Tech Stack:** Static HTML/CSS, Python `unittest` selector-contract tests, in-app browser DOM measurements.

**Spec:** `docs/superpowers/specs/2026-08-21-workbench-preview-timeline-layout-design.md`

---

## Chunk 1: Layout Contract And Fix

### Task 1: Encode the non-overlap layout contract

**Files:**
- Modify: `.agents/skills/remix-reference-video/tests/test_workbench_layout.py`

- [x] **Step 1: Write failing desktop layout assertions**

Extend `test_three_column_shell_and_main_stage_can_shrink_without_overflow` and `test_preview_uses_container_bounds_instead_of_fixed_video_height` to require:

```python
self.assertEqual(main_stage.get("grid-template-rows"), "auto minmax(280px,1fr) auto auto auto auto")
self.assertEqual(main_stage.get("gap"), "10px")
preview = _find_rule(rules, ".preview-stage")
self.assertEqual(preview.get("height"), "100%")
self.assertEqual(preview.get("min-height"), "0")
self.assertEqual(preview.get("max-height"), "100%")
self.assertNotIn("56vh", TEMPLATE)
```

- [x] **Step 2: Write failing mobile reset assertions**

Parse the `max-width:820px` block with `_rules()` and assert the concrete contract on the correct selectors:

```python
mobile_rules = _rules(body)
mobile_main = _find_rule(mobile_rules, ".main-stage")
self.assertEqual(mobile_main.get("grid-template-rows"), "auto")
self.assertEqual(mobile_main.get("height"), "auto")
self.assertEqual(mobile_main.get("overflow"), "visible")
mobile_preview = _find_rule(mobile_rules, ".preview-stage")
self.assertEqual(mobile_preview.get("height"), "min(70vh,640px)")
self.assertEqual(mobile_preview.get("min-height"), "280px")
self.assertEqual(mobile_preview.get("max-height"), "640px")
self.assertEqual(mobile_preview.get("aspect-ratio"), "9/16")
self.assertEqual(mobile_preview.get("width"), "auto")
self.assertEqual(mobile_preview.get("max-width"), "100%")
self.assertEqual(mobile_preview.get("justify-self"), "center")
```

Also preserve media rendering with selector-scoped template assertions:

```python
self.assertEqual(video.get("aspect-ratio"), "9/16")
self.assertEqual(video.get("object-fit"), "contain")
image = _find_rule(template_rules, ".preview-stage img")
self.assertEqual(image.get("height"), "auto")
self.assertEqual(image.get("object-fit"), "contain")
```

- [x] **Step 3: Run the layout tests and verify RED**

Run:

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src .venv/bin/python -m unittest tests.test_workbench_layout -q
```

Expected: FAIL because the desktop grid still uses `minmax(280px,1fr)` with only five declared rows plus an overflowing inline `56vh` preview, and the mobile breakpoint does not reset preview sizing.

### Task 2: Implement the constrained preview layout

**Files:**
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.css`
- Modify: `.agents/skills/remix-reference-video/src/remix_reference_video/templates/review_workbench.html`
- Test: `.agents/skills/remix-reference-video/tests/test_workbench_layout.py`

- [x] **Step 1: Update the desktop grid and preview box**

Change the central grid row list and replace only the preview's three sizing declarations. Preserve every other existing `.preview-stage` declaration, including `display:flex`, alignment, `max-width:100%`, background, border radius, `overflow:hidden`, and `position:relative`:

```css
.main-stage {
  grid-template-rows: auto minmax(280px,1fr) auto auto auto auto;
  gap: 10px;
}
.preview-stage {
  height: 100%;
  min-height: 0;
  max-height: 100%;
}
```

Keep existing `overflow-y:auto`, `overflow-x:hidden`, `position:relative`, and media `object-fit:contain` declarations.

- [x] **Step 2: Add explicit mobile resets**

In the existing `@media (max-width:820px)` block set:

```css
.main-stage { grid-template-rows:auto; height:auto; overflow:visible; }
.preview-stage {
  height:min(70vh,640px);
  min-height:280px;
  max-height:640px;
  aspect-ratio:9/16;
  width:auto;
  max-width:100%;
  justify-self:center;
}
```

- [x] **Step 3: Remove only the conflicting inline container height**

Delete the template's inline `.preview-stage{height:clamp(280px,56vh,620px);min-height:280px}` declaration. Preserve the inline video and image rules unchanged, including video `aspect-ratio:9/16`, image `height:auto`, and `object-fit:contain`.

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src .venv/bin/python -m unittest tests.test_workbench_layout tests.test_workbench_client -q
node --check src/remix_reference_video/static/review_workbench.js
```

Expected: PASS.

- [x] **Step 5: Run the complete Skill regression**

Run:

```bash
cd .agents/skills/remix-reference-video
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m compileall -q src
git diff --check
```

Expected: all tests PASS and all checks exit 0.

- [x] **Step 6: Restart and perform browser measurements**

Restart `workbench-serve` with `WORKBENCH_UI_MODE=workspace`. Open run `gb-cold-1787280937` and verify the spec state matrix at 1280×720, 1440×900, 1280×640, 821×720, 820×720, and 390×844. Do not submit any Gate decision.

At each applicable viewport measure real bounding rectangles and computed styles. Assert:

- desktop preview height is at least `280px`;
- `preview.bottom + 10 <= timeline.top` after scrolling the central column to the timeline;
- at 1280×640 `.main-stage.scrollHeight > .main-stage.clientHeight`, the central column scrolls, and the timeline becomes visible after scrolling;
- video/image bounds stay within `#preview-stage` and retain the expected 9:16/contain presentation;
- the right rail does not intersect the central preview or timeline;
- at 390×844, `.timeline-canvas.scrollWidth > .timeline-canvas.clientWidth`; set a positive `scrollLeft` and confirm it advances while `document.documentElement.scrollWidth <= innerWidth`.

- [x] **Step 7: Commit the implementation**

```bash
git add \
  .agents/skills/remix-reference-video/tests/test_workbench_layout.py \
  .agents/skills/remix-reference-video/src/remix_reference_video/static/review_workbench.css \
  .agents/skills/remix-reference-video/src/remix_reference_video/templates/review_workbench.html \
  docs/superpowers/plans/2026-08-21-workbench-preview-timeline-layout.md
git commit -m "fix: prevent workbench preview timeline overlap"
```
