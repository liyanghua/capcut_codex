#!/usr/bin/env node
// Client-contract harness for review_workbench.js.
// Runs the workspace client against fixture JSON in a minimal DOM stub and
// asserts the revised product contract: fixed stage-main preview, media-rich
// storyboard cards, complete five-stage stepper, visual static timeline,
// selection highlighting/detail without replacing the center media.
"use strict";

const fs = require("fs");
const path = require("path");

const fixturesDir = process.env.WORKBENCH_FIXTURES;
const jsPath = process.env.WORKBENCH_JS;
if (!fixturesDir || !jsPath) { console.error("WORKBENCH_FIXTURES and WORKBENCH_JS are required"); process.exit(2); }
const readFixture = (name) => JSON.parse(fs.readFileSync(path.join(fixturesDir, name), "utf-8"));
const workspace = readFixture("workspace.json");
const review = readFixture("review.json");
const session = readFixture("session.json");
const workspacePath = path.join(fixturesDir, "workspace2.json");
const hasSecondWorkspace = fs.existsSync(workspacePath);
const workspace2 = hasSecondWorkspace ? JSON.parse(fs.readFileSync(workspacePath, "utf-8")) : null;
const staleReview = process.env.WORKBENCH_REVIEW_STALE === "1";
const legacyDom = process.env.WORKBENCH_LEGACY_DOM === "1";

const failures = [];
const assert = (condition, message) => { if (!condition) failures.push(message); };
const assertContains = (haystack, needle, message) => assert(String(haystack || "").includes(needle), `${message} (missing "${needle}")`);

const elements = new Map();
function elementFor(selector) {
  if (!elements.has(selector)) {
    const listeners = {};
    elements.set(selector, {
      selector,
      innerHTML: "", textContent: "", value: "", disabled: false, hidden: false, open: false,
      paused: true, currentTime: 0, dataset: {}, style: {},
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
      setAttribute() {}, getAttribute() { return null; },
      insertAdjacentElement() {}, scrollIntoView() {}, showModal() {}, close() {},
      play() { this.paused = false; return Promise.resolve(); }, pause() { this.paused = true; },
    });
  }
  return elements.get(selector);
}

global.document = {
  body: { dataset: { runId: "harness-run" } },
  querySelector: (selector) => legacyDom && ["#material-evidence-card", "#material-evidence-editor"].includes(selector) ? null : elementFor(selector),
  querySelectorAll: () => [],
  addEventListener: () => {},
};
global.window = global;
global.CSS = { escape: (value) => String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&") };
global.EventSource = class {
  constructor() { this.onopen = null; this.onerror = null; this.listeners = {}; global.__lastEventSource = this; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
};
global.__reloadCalls = 0;
global.location = { reload: () => { global.__reloadCalls += 1; } };

const jsonResponse = (payload, options = {}) => ({
  ok: options.ok !== false,
  status: options.status || 200,
  headers: { get: () => "application/json" },
  json: async () => payload,
  text: async () => JSON.stringify(payload),
});
let workspaceCalls = 0;
global.fetch = async (url) => {
  if (String(url).endsWith("/workspace")) {
    workspaceCalls += 1;
    return jsonResponse(workspaceCalls === 1 || !workspace2 ? workspace : workspace2);
  }
  if (String(url).endsWith("/review")) {
    if (staleReview) return jsonResponse({ detail: { message: "review package revision is stale" } }, { ok: false, status: 409 });
    return jsonResponse(review);
  }
  if (String(url).endsWith("/review-session")) return jsonResponse(session);
  throw new Error(`unexpected fetch: ${url}`);
};

const clientSource = fs.readFileSync(jsPath, "utf-8");
eval(clientSource);

(async () => {
  const deadline = Date.now() + 8000;
  while (!window.__workbench?.state?.workspace && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  const hook = window.__workbench;
  assert(Boolean(hook), "window.__workbench hook was not exposed");
  assert(Boolean(hook?.state?.workspace), "client did not load the workspace projection");
  if (!hook?.state?.workspace) { console.error(failures.join("\n")); process.exit(1); }

  const stage = hook.state.workspace;
  const previewMedia = elementFor("#preview-media");
  const centerBefore = previewMedia.innerHTML;

  if (staleReview) {
    assert(elementFor("#business-stage").textContent !== "", "stale review package still renders the workspace");
    assert(elementFor("#connection-status").textContent.includes("只读"), "stale review package reports read-only mode");
    for (const action of ["approve", "request_changes", "reject"]) {
      assert(elementFor(`[data-action="${action}"]`).disabled === true, `stale review package disables ${action}`);
    }
  }

  // 1. Fixed stage-main preview renders on load and is never replaced.
  const previewRef = stage.preview?.media_ref;
  if (previewRef) {
    assertContains(centerBefore, previewRef.split("/").pop(), "center preview renders the stage main media");
  } else {
    assert(elementFor("#preview-empty").hidden === false, "empty preview state must be visible when media is absent");
  }

  // 2. Storyboard cards are media-rich and truthful.
  const shotList = elementFor("#shot-list").innerHTML;
  assertContains(shotList, "object-card", "shot cards render");
  if (stage.preview?.mode === "final") {
    const withImage = (shotList.match(/object-thumb" alt/g) || []).length;
    assert(withImage > 0, "at least one shot card renders a real thumbnail image");
  }
  const missingThumbCount = (stage.storyboard?.shots || []).filter((row) => !row.thumbnail_ref).length;
  const placeholderCount = (shotList.match(/thumb-placeholder/g) || []).length;
  assert(placeholderCount === missingThumbCount, `every shot without a thumbnail shows an explicit placeholder (${placeholderCount} vs ${missingThumbCount})`);

  // 3. Shot selection never replaces the center media and opens read-only detail.
  const shotId = stage.storyboard?.shots?.[0]?.shot_id;
  if (shotId) {
    hook.selectObject("shot", shotId);
    assert(previewMedia.innerHTML === centerBefore, "shot selection must not replace the center stage preview");
    assert(elementFor("#object-detail").hidden === false, "shot selection opens the read-only detail");
    assertContains(elementFor("#detail-fields").innerHTML, "用途", "detail shows business fields");
    assertContains(elementFor("#shot-list").innerHTML, "selected", "selected shot card is highlighted");
  }

  // 4. Audio selection works (regression: the former audios-key bug) and shows details.
  const audioId = stage.storyboard?.audio?.[0]?.audio_id;
  if (audioId) {
    hook.selectObject("audio", audioId);
    assert(elementFor("#object-detail").hidden === false, "audio selection opens the read-only detail");
    assertContains(elementFor("#detail-fields").innerHTML, "实测时长", "audio detail shows measured duration");
    assert(previewMedia.innerHTML === centerBefore, "audio selection must not replace the center stage preview");
  }

  // 5. Element selection links fragments and stays read-only.
  const elementId = stage.storyboard?.elements?.[0]?.element_id;
  if (elementId) {
    hook.selectObject("element", elementId);
    assertContains(elementFor("#detail-fields").innerHTML, "关联片段", "element detail shows related fragments");
    assert(previewMedia.innerHTML === centerBefore, "element selection must not replace the center stage preview");
  }

  // 6. Unknown objects fail closed without side effects.
  hook.selectObject("shot", "shot-does-not-exist");
  assert(previewMedia.innerHTML === centerBefore, "unknown selection leaves the center stage preview intact");

  // 7. Timeline is proportional and visual.
  const timelineHtml = elementFor("#timeline-tracks").innerHTML;
  assertContains(timelineHtml, "timeline-segment", "timeline segments render");
  assertContains(timelineHtml, "left:", "timeline segments are time-proportional");
  assertContains(timelineHtml, "width:", "timeline segments carry proportional widths");
  assertContains(timelineHtml, "data-object-id=", "timeline segments link to storyboard objects");
  assert(elementFor("#timeline-ruler").innerHTML.includes("ruler-tick"), "timeline ruler renders ticks");

  // 8. Playhead moves and formats.
  hook.updatePlayhead(2.5);
  assert(elementFor("#playhead-label").textContent === "00:02", "playhead label formats seconds");
  if (Number(stage.timeline?.total_duration_seconds) > 0) {
    assert(elementFor("#timeline-playhead").hidden === false, "playhead marker becomes visible");
    assert(elementFor("#timeline-playhead").style.left.length > 0, "playhead marker position is set");
  }

  // 9. Complete five-stage stepper with substeps for the current stage.
  const stepper = elementFor("#stage-stepper").innerHTML;
  for (const label of ["参考拆解", "复刻方案", "素材与证据", "文案与声音", "成片终审"]) {
    assertContains(stepper, label, "stepper shows all five business stages");
  }
  assertContains(stepper, "substep", "current stage shows Gate substeps");
  assertContains(stepper, "stage-step", "stepper stages render");
  assert((stepper.match(/class="stage-detail"/g) || []).length === (stage.process?.stages || []).length, "all business stages expose their substeps");
  assert(!stepper.includes('class="stage-detail" hidden'), "business stage details are visible by default");

  // 10. Stage content for Gate 4/5 renders in business language.
  const stageContent = elementFor("#stage-content").innerHTML;
  const contentCardHidden = elementFor("#stage-content-card").hidden;
  if (stage.current_gate === "gate5") {
    assert(contentCardHidden === false, "Gate 5 stage content card is visible");
    assertContains(stageContent, "质量与交付", "Gate 5 renders quality and delivery content");
  } else if (String(stage.current_gate).startsWith("gate4")) {
    assert(contentCardHidden === false, "Gate 4 stage content card is visible");
    assertContains(stageContent, "生产文案", "Gate 4 renders the production script");
    assertContains(stageContent, "声音预算检查", "Gate 4 renders the voice preflight");
  }

  // 11. Quality checks render only for the current gate and bind real sources.
  const qualityCardHidden = elementFor("#quality-card").hidden;
  const qualityHtml = elementFor("#quality-checks").innerHTML;
  const scoped = (stage.quality_checks || []).filter((row) => (row.gate_scope || []).includes(stage.current_gate));
  assert(qualityCardHidden === (scoped.length === 0), "quality card visibility matches the gate scope");
  if (scoped.length) {
    assertContains(qualityHtml, "quality-row", "quality checks render rows");
    const unavailable = (stage.quality_checks || []).filter((row) => row.status === "not_available");
    if (unavailable.length) assertContains(qualityHtml, "暂无来源", "missing quality sources render an explicit not_available label");
  }

  // 12. Gate 1/2 rails explain pending stages instead of an empty misleading state.
  const sectionStates = stage.storyboard?.section_states || {};
  if (sectionStates.elements === "pending_gate2") {
    assertContains(elementFor("#element-list").innerHTML, "尚未进入该阶段", "Gate 1 elements rail shows a pending-stage hint");
  }
  if (sectionStates.audio === "pending_gate3") {
    assertContains(elementFor("#audio-list").innerHTML, "尚未进入该阶段", "early gates show a pending hint for audio");
  }

  // 13. Diagnostics carry execution nodes and business artifacts.
  const diagnostics = elementFor("#diagnostics-body").textContent;
  assertContains(diagnostics, "execution", "diagnostics include execution nodes");
  assertContains(diagnostics, "artifacts", "diagnostics include business artifacts");

  // 14. Higher state_revision re-renders without location.reload and keeps selection/detail.
  if (hasSecondWorkspace && !staleReview) {
    const shotId = stage.storyboard?.shots?.[0]?.shot_id;
    if (shotId) hook.selectObject("shot", shotId);
    const questionBefore = elementFor("#decision-question").textContent;
    const eventSource = global.__lastEventSource;
    assert(Boolean(eventSource), "EventSource instance is registered");
    if (eventSource?.listeners?.revision) {
      eventSource.listeners.revision({ data: JSON.stringify({ state_revision: 999999 }) });
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline && elementFor("#decision-question").textContent === questionBefore) {
        await new Promise((resolve) => setTimeout(resolve, 10));
      }
      assert(global.__reloadCalls === 0, "revision refresh must not call location.reload");
      assert(elementFor("#decision-question").textContent !== questionBefore, "revision refresh re-renders the decision question");
      assert(elementFor("#decision-question").textContent.includes("刷新"), "revision refresh uses the newer workspace payload");
      if (shotId) {
        assertContains(elementFor("#shot-list").innerHTML, "selected", "selection survives the incremental refresh");
        assert(elementFor("#object-detail").hidden === false, "detail panel survives the incremental refresh");
      }
    }
  }

  if (failures.length) { console.error(failures.join("\n")); process.exit(1); }
  console.log(`client contract OK (gate=${stage.current_gate})`);
  process.exit(0);
})().catch((error) => { console.error(error); process.exit(1); });
