#!/usr/bin/env node
"use strict";

const fs = require("fs");
const scriptPath = process.env.PROJECT_INITIALIZATION_JS;
if (!scriptPath) process.exit(2);

const failures = [];
const assert = (condition, message) => { if (!condition) failures.push(message); };
const elements = new Map();
function node(id, extra = {}) {
  const listeners = {};
  const value = {
    id, value: "", textContent: "", innerHTML: "", hidden: false, disabled: false,
    dataset: {}, content: "", elements: {},
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
    async dispatch(type) { for (const fn of listeners[type] || []) await fn({currentTarget: value}); },
    ...extra,
  };
  elements.set(`#${id}`, value);
  return value;
}

const metaNonce = node("meta-nonce", {content: "nonce-1"});
const metaProject = node("meta-project", {content: ""});
const reference = node("reference-path");
const assets = node("asset-root");
node("reference-path-status"); node("asset-root-status"); node("form-message", {hidden: true});
node("project-status"); node("stage0-result", {hidden: true}); node("stage0-summary"); node("stage0-facts");
const save = node("save-draft", {textContent: "保存草稿"});
node("run-stage0", {textContent: "开始 Stage 0 预检"});
node("freeze-project", {textContent: "确认 Brief 并冻结"});
node("start-cold", {textContent: "启动 Gate 1", hidden: true});
const form = node("project-form");
for (const [name, value] of Object.entries({
  reference_path: "", asset_root: "", product_name: "透明桌垫", task_name: "tablemat-new",
  platform: "抖音", audience: "精致白领", approved_claims: "防水防油",
  forbidden_claims: "", speaker: "zh_female_gaolengyujie_uranus_bigtts", speed: "1.0",
})) form.elements[name] = {value};

const referencePicker = node("reference-picker", {dataset: {picker: "reference_video"}, textContent: "选择文件"});
const assetPicker = node("asset-picker", {dataset: {picker: "asset_directory"}, textContent: "选择目录"});

global.document = {
  body: {dataset: {page: "project-initialization"}},
  getElementById(id) { return elements.get(`#${id}`) || null; },
  querySelector(selector) {
    if (selector === 'meta[name="local-session-nonce"]') return metaNonce;
    if (selector === 'meta[name="project-id"]') return metaProject;
    return elements.get(selector) || null;
  },
  querySelectorAll(selector) { return selector === "[data-picker]" ? [referencePicker, assetPicker] : []; },
};
global.FormData = class {
  constructor(source) { this.source = source; }
  get(name) { return this.source.elements[name]?.value ?? null; }
};
global.history = {last: null, replaceState(_state, _title, url) { this.last = url; }};
global.location = {assign() {}};

const calls = [];
let nonceCounter = 1;
const response = (body) => ({ok: true, json: async () => body});
global.fetch = async (url, options = {}) => {
  const payload = options.body ? JSON.parse(options.body) : null;
  calls.push({url: String(url), payload, nonce: options.headers?.["X-Local-Nonce"]});
  const next = `nonce-${++nonceCounter}`;
  if (String(url).endsWith("/path-picker")) {
    const path = payload.mode === "reference_video" ? "/tmp/reference.mp4" : "/tmp/source";
    return response({status: "selected", mode: payload.mode, path, next_nonce: next});
  }
  if (String(url).endsWith("/path-validation")) {
    return response({status: "valid", mode: payload.mode, path: payload.path, basename: payload.path.split("/").pop(), next_nonce: next});
  }
  if (String(url).endsWith("/drafts")) {
    return response({draft: {...payload, project_id: "project-1", draft_revision: 1}, project_url: "/workbench/projects/project-1/stage0", next_nonce: next});
  }
  throw new Error(`unexpected fetch ${url}`);
};

eval(fs.readFileSync(scriptPath, "utf8"));

(async () => {
  await referencePicker.dispatch("click");
  assert(reference.value === "/tmp/reference.mp4", "reference picker must write the server-returned path");
  assert(elements.get("#reference-path-status").textContent.includes("reference.mp4"), "reference validation status must render");
  await assetPicker.dispatch("click");
  assert(assets.value === "/tmp/source", "directory picker must write the server-returned path");
  assert(calls.filter((call) => call.url.endsWith("/path-picker")).length === 2, "both native picker buttons must call the picker API");
  for (let index = 1; index < calls.length; index += 1) {
    assert(calls[index].nonce !== calls[index - 1].nonce, "protected requests must rotate the nonce");
  }
  form.elements.reference_path.value = reference.value;
  form.elements.asset_root.value = assets.value;
  await save.dispatch("click");
  assert(history.last === "/workbench/projects/project-1/stage0", "draft save must move to the stable project URL");
  assert(metaProject.content === "project-1", "draft save must retain the server project id");
  if (failures.length) { console.error(failures.join("\n")); process.exit(1); }
  console.log("project initialization client contract OK");
})().catch((error) => { console.error(error); process.exit(1); });
