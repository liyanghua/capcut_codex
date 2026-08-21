(() => {
  "use strict";

  const state = {
    nonce: document.querySelector('meta[name="local-session-nonce"]')?.content || "",
    projectId: document.querySelector('meta[name="project-id"]')?.content || "",
    draft: null,
    report: null,
    requestQueue: Promise.resolve(),
  };

  const requestId = (prefix) => `${prefix}-${crypto.randomUUID()}`;
  const lines = (value) => value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);

  function protectedApi(path, payload) {
    const operation = async () => {
      const response = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-Local-Nonce": state.nonce},
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (body.next_nonce) {
        state.nonce = body.next_nonce;
        document.querySelector('meta[name="local-session-nonce"]').content = state.nonce;
      }
      if (!response.ok) throw new Error(body.message || body.detail?.message || "请求失败");
      return body;
    };
    state.requestQueue = state.requestQueue.then(operation, operation);
    return state.requestQueue;
  }

  function message(text, kind = "info") {
    const node = document.getElementById("form-message");
    if (!node) return;
    node.hidden = !text;
    node.textContent = text;
    node.dataset.kind = kind;
  }

  function setBusy(button, busy, label) {
    if (!button) return;
    if (busy) button.dataset.label = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? label : (button.dataset.label || button.textContent);
  }

  function formPayload() {
    const form = document.getElementById("project-form");
    const data = new FormData(form);
    return {
      reference_path: String(data.get("reference_path") || ""),
      asset_root: String(data.get("asset_root") || ""),
      product_name: String(data.get("product_name") || ""),
      task_name: String(data.get("task_name") || ""),
      platform: String(data.get("platform") || "抖音"),
      audience: String(data.get("audience") || ""),
      approved_claims: lines(String(data.get("approved_claims") || "")),
      forbidden_claims: lines(String(data.get("forbidden_claims") || "")),
      output: {aspect_ratio: "9:16", width: 1080, height: 1920, fps: 60},
      voice: {provider: "doubao", speaker: String(data.get("speaker") || ""), speed: 1.0},
    };
  }

  function fillDraft(draft) {
    const form = document.getElementById("project-form");
    if (!form || !draft) return;
    for (const name of ["reference_path", "asset_root", "product_name", "task_name", "platform", "audience"]) {
      if (form.elements[name]) form.elements[name].value = draft[name] || "";
    }
    form.elements.approved_claims.value = (draft.approved_claims || []).join("\n");
    form.elements.forbidden_claims.value = (draft.forbidden_claims || []).join("\n");
    form.elements.speaker.value = draft.voice?.speaker || "zh_female_gaolengyujie_uranus_bigtts";
    state.draft = draft;
  }

  async function validatePath(input, mode) {
    const status = document.getElementById(`${input.id}-status`);
    if (!input.value.trim()) {
      status.textContent = "请输入绝对路径";
      status.dataset.status = "missing";
      return false;
    }
    try {
      const result = await protectedApi("/api/v1/projects/path-validation", {mode, path: input.value.trim()});
      status.dataset.status = result.status;
      status.textContent = result.status === "valid" ? `已验证：${result.basename}` : result.detail;
      if (result.status === "valid") input.value = result.path;
      return result.status === "valid";
    } catch (error) {
      status.dataset.status = "scan_error";
      status.textContent = error.message;
      return false;
    }
  }

  async function saveDraft() {
    const payload = {
      ...formPayload(),
      project_id: state.projectId || undefined,
      expected_revision: state.draft?.draft_revision || (state.projectId ? 0 : undefined),
      request_id: requestId("draft"),
      idempotency_key: requestId("draft-key"),
    };
    const result = await protectedApi("/api/v1/projects/drafts", payload);
    state.draft = result.draft;
    state.projectId = result.draft.project_id;
    document.querySelector('meta[name="project-id"]').content = state.projectId;
    history.replaceState({}, "", result.project_url);
    document.getElementById("project-status").textContent = "草稿已保存";
    return result.draft;
  }

  function showStage0(report) {
    state.report = report;
    const section = document.getElementById("stage0-result");
    section.hidden = false;
    const ready = report.status === "ready";
    document.getElementById("stage0-summary").textContent = ready ? "输入检查完成，可确认 Brief 并冻结。" : "存在需要处理的输入问题。";
    const summary = report.asset_summary || {};
    document.getElementById("stage0-facts").innerHTML = [
      ["素材总数", summary.supported_files ?? 0], ["图片", summary.images ?? 0],
      ["视频", summary.videos ?? 0], ["风险", (report.risks || []).length],
    ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
    document.getElementById("freeze-project").hidden = !ready;
    document.getElementById("project-status").textContent = ready ? "Stage 0 待确认" : "Stage 0 阻断";
  }

  function setFrozenState(locked) {
    const save = document.getElementById("save-draft");
    const stage0 = document.getElementById("run-stage0");
    if (save) save.disabled = locked;
    if (stage0) stage0.disabled = locked;
  }

  async function loadProject() {
    if (!state.projectId) return;
    const response = await fetch(`/api/v1/projects/${encodeURIComponent(state.projectId)}`, {credentials: "same-origin"});
    if (!response.ok) throw new Error("无法读取项目");
    const result = await response.json();
    fillDraft(result.draft);
    if (result.stage0_report) showStage0(result.stage0_report);
    if (result.project_state?.lifecycle_status === "frozen_waiting_gate1") {
      setFrozenState(true);
      document.getElementById("freeze-project").hidden = true;
      document.getElementById("start-cold").hidden = false;
      document.getElementById("project-status").textContent = "等待启动 Gate 1";
    }
  }

  async function initializeForm() {
    const reference = document.getElementById("reference-path");
    const assets = document.getElementById("asset-root");
    reference.addEventListener("blur", () => validatePath(reference, "reference_video"));
    assets.addEventListener("blur", () => validatePath(assets, "asset_directory"));
    document.querySelectorAll("[data-picker]").forEach((button) => button.addEventListener("click", async () => {
      const mode = button.dataset.picker;
      setBusy(button, true, "选择中...");
      try {
        const result = await protectedApi("/api/v1/projects/path-picker", {mode});
        if (result.status === "selected") {
          const input = mode === "reference_video" ? reference : assets;
          input.value = result.path;
          await validatePath(input, mode);
        } else if (result.status !== "cancelled") {
          message(result.detail || "原生选择器不可用，请手动输入路径", "warning");
        }
      } catch (error) { message(error.message, "error"); }
      finally { setBusy(button, false); }
    }));

    document.getElementById("save-draft").addEventListener("click", async (event) => {
      setBusy(event.currentTarget, true, "保存中...");
      try { await saveDraft(); message("草稿已保存。", "success"); }
      catch (error) { message(error.message, "error"); }
      finally { setBusy(event.currentTarget, false); }
    });
    document.getElementById("run-stage0").addEventListener("click", async (event) => {
      setBusy(event.currentTarget, true, "正在检查素材...");
      try {
        await saveDraft();
        const result = await protectedApi(`/api/v1/projects/${encodeURIComponent(state.projectId)}/stage0`, {request_id: requestId("stage0"), idempotency_key: requestId("stage0-key")});
        showStage0(result.stage0_report);
        message(result.stage0_report.status === "ready" ? "Stage 0 已完成，尚未生成任何媒体。" : "Stage 0 发现阻断项。", result.stage0_report.status === "ready" ? "success" : "warning");
      } catch (error) { message(error.message, "error"); }
      finally { setBusy(event.currentTarget, false); }
    });
    document.getElementById("freeze-project").addEventListener("click", async (event) => {
      setBusy(event.currentTarget, true, "冻结中...");
      try {
        await protectedApi(`/api/v1/projects/${encodeURIComponent(state.projectId)}/freeze`, {draft_revision: state.draft.draft_revision, report_sha256: state.report.report_sha256, request_id: requestId("freeze"), idempotency_key: requestId("freeze-key")});
        event.currentTarget.hidden = true;
        setFrozenState(true);
        document.getElementById("start-cold").hidden = false;
        document.getElementById("project-status").textContent = "等待启动 Gate 1";
        message("冻结输入已生成，尚未启动生产运行。", "success");
      } catch (error) { message(error.message, "error"); }
      finally { setBusy(event.currentTarget, false); }
    });
    document.getElementById("start-cold").addEventListener("click", async (event) => {
      setBusy(event.currentTarget, true, "正在启动 Gate 1...");
      try {
        const result = await protectedApi(`/api/v1/projects/${encodeURIComponent(state.projectId)}/start-cold`, {request_id: requestId("cold"), idempotency_key: requestId("cold-key")});
        if (result.run_url) location.assign(result.run_url);
        else message(result.project?.detail || "运行环境未就绪", "warning");
      } catch (error) { message(error.message, "error"); }
      finally { setBusy(event.currentTarget, false); }
    });
    await loadProject();
  }

  async function initializeList() {
    const response = await fetch("/api/v1/projects", {credentials: "same-origin"});
    const projects = response.ok ? await response.json() : [];
    const list = document.getElementById("project-list");
    if (!projects.length) {
      list.innerHTML = '<div class="empty-state"><strong>还没有项目</strong><span>创建项目后，从 Stage 0 开始检查输入。</span></div>';
      return;
    }
    list.innerHTML = projects.map((project) => `<a class="project-row" href="/workbench/projects/${encodeURIComponent(project.project_id)}/stage0"><div><strong>${escapeHtml(project.product_name)}</strong><span>${escapeHtml(project.task_name)}</span></div><div><span>${escapeHtml(project.platform)}</span><span>草稿 r${project.draft_revision}</span></div></a>`).join("");
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[character]);
  }

  const page = document.body.dataset.page;
  if (page === "project-initialization") initializeForm().catch((error) => message(error.message, "error"));
  if (page === "project-list") initializeList();
})();
