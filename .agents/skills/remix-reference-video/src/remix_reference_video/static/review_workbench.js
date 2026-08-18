(() => {
  const runId = document.body.dataset.runId;
  const state = { view: null, session: null, preview: null, request: null, activeIntervalId: null, eventSource: null };
  const labels = { copy: "文案", claim_scope: "声明范围", voice: "音色或语速", material: "素材", range: "素材范围", rerecord: "指定句重录", boundary: "成片边界", structural: "结构调整" };
  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value).replace(/[&<>"]/g, (character) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[character]));
  const api = (path, options = {}) => fetch(`/api/v1/runs/${encodeURIComponent(runId)}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options,
  }).then(async (response) => {
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("json") ? await response.json() : await response.text();
    if (!response.ok) throw Object.assign(new Error(body.message || body.detail?.message || "请求失败"), { response, body });
    return body;
  });
  const toast = (message) => { $("#toast").textContent = message; $("#toast").classList.add("visible"); setTimeout(() => $("#toast").classList.remove("visible"), 2600); };
  const eventIntent = (eventType, payload = {}) => state.session && api("/review-session/events", { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, event_type: eventType, payload }) }).catch(() => {});
  const mediaUrl = (path) => `/api/v1/runs/${encodeURIComponent(runId)}/media/${path.split("/").map(encodeURIComponent).join("/")}`;
  const mediaPreview = (path) => {
    if (/\.mp4$/i.test(path)) return `<video controls preload="metadata" src="${mediaUrl(path)}"></video>`;
    if (/\.(mp3|wav|m4a)$/i.test(path)) return `<audio controls preload="metadata" src="${mediaUrl(path)}"></audio>`;
    if (/\.(jpg|jpeg|png|webp)$/i.test(path)) return `<img loading="lazy" alt="证据预览" src="${mediaUrl(path)}">`;
    return "";
  };
  function connectEvents() {
    if (state.eventSource) state.eventSource.close();
    state.eventSource = new EventSource(`/api/v1/runs/${encodeURIComponent(runId)}/events`);
    state.eventSource.addEventListener("revision", (event) => {
      let payload;
      try { payload = JSON.parse(event.data); } catch { return; }
      if (Number(payload.state_revision) > Number(state.view.state_revision)) location.reload();
    });
    state.eventSource.onerror = () => { $("#connection-status").textContent = "等待刷新"; };
  }
  function startActive() {
    state.activeIntervalId = crypto.randomUUID();
    eventIntent("review.active_start", { active_interval_id: state.activeIntervalId });
  }
  function stopActive() {
    if (!state.activeIntervalId) return;
    eventIntent("review.active_stop", { active_interval_id: state.activeIntervalId });
    state.activeIntervalId = null;
  }

  async function loadReview() {
    state.view = await api("/review");
    state.session = await api("/review-session", { method: "POST", body: JSON.stringify({ gate_id: state.view.gate_id }) });
    render();
    $("#connection-status").textContent = "已连接";
    startActive();
    connectEvents();
  }

  function render() {
    const view = state.view;
    $("#run-label").textContent = ` · ${runId}`;
    $("#gate-name").textContent = view.review_meta.business_name;
    $("#decision-question").textContent = view.review_meta.decision_question;
    $("#current-step").textContent = view.business_summary.current_step;
    $("#recommendation").textContent = view.business_summary.recommendation.reason;
    $("#business-impacts").innerHTML = view.business_summary.business_impacts.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    $("#risks").innerHTML = view.risks.map((risk) => `<p class="${risk.blocking ? "blocking" : ""}">${escapeHtml(risk.message)}</p>`).join("");
    $("#evidence-list").innerHTML = view.evidence.map((item) => {
      const available = item.status === "available";
      const preview = available ? mediaPreview(item.path) : "";
      const link = available ? `<a target="_blank" href="${mediaUrl(item.path)}">打开证据</a>` : "";
      return `<article class="evidence-row" data-evidence-id="${escapeHtml(item.evidence_id)}"><div><strong>${escapeHtml(item.evidence_id)}</strong><small>${available ? "可用" : "缺失"}</small></div>${preview}${link}</article>`;
    }).join("");
    document.querySelectorAll(".evidence-row").forEach((row) => row.addEventListener("click", () => eventIntent("review.evidence_interaction", { evidence_id: row.dataset.evidenceId })));
    const types = view.impact_context.change_options.allowed_change_types || [];
    $("#change-type").innerHTML = types.map((type) => `<option value="${type}">${labels[type]}</option>`).join("");
    renderChangeFields();
  }

  async function decide(action) {
    if (action === "request_changes") { $("#change-dialog").showModal(); return; }
    const identity = state.session.review_identity;
    try {
      await api(`/gates/${state.view.gate_id}/decisions`, { method: "POST", body: JSON.stringify({
        session_id: state.session.session_id, decision: action,
        scope_ids: state.view.impact_context.decision_scope_ids, strategy: {}, note: $("#decision-note").value,
        review_package_hash: identity.review_package_hash, state_revision: identity.state_revision,
        idempotency_key: crypto.randomUUID(),
      }) });
      toast(action === "approve" ? "已通过" : "已驳回");
      setTimeout(() => location.reload(), 500);
    } catch (error) { toast(error.message); if (error.response?.status === 409) setTimeout(() => location.reload(), 900); }
  }

  function optionRows(rows, valueKey, labelFn, extra = () => "") {
    return (rows || []).map((row) => `<option value="${escapeHtml(row[valueKey])}" ${extra(row)}>${escapeHtml(labelFn(row))}</option>`).join("");
  }

  function renderChangeFields() {
    const type = $("#change-type").value;
    const options = state.view?.impact_context.change_options || {};
    const fragmentOptions = optionRows(options.fragments, "fragment_id", (row) => row.fragment_id);
    const fields = {
      copy: `<label for="change-target">文案行</label><select id="change-target">${optionRows(options.lines, "line_id", (row) => `${row.line_id} · ${row.text}`)}</select><label for="change-text">修改后文案</label><textarea id="change-text" rows="3" required></textarea>`,
      claim_scope: `<label for="change-target">声明</label><select id="change-target">${optionRows(options.claims, "claim_id", (row) => row.label)}</select><label for="claim-action">处理方式</label><select id="claim-action"><option value="remove">移出当前范围</option><option value="add">加入当前范围</option></select>`,
      voice: `<label for="voice-provider">服务</label><input id="voice-provider" value="${escapeHtml(options.voice?.current?.provider || "")}"><label for="voice-speaker">音色</label><input id="voice-speaker" value="${escapeHtml(options.voice?.current?.speaker || options.voice?.current?.voice || "")}"><label for="voice-speed">语速</label><input id="voice-speed" type="number" min="0.1" step="0.05" value="${options.voice?.current?.speed || options.voice?.current?.speed_ratio || 1}">`,
      material: `<label for="change-fragment">片段</label><select id="change-fragment">${fragmentOptions}</select><label for="material-candidate">候选素材</label><select id="material-candidate"></select><label for="overlay-decision">源文字处理</label><select id="overlay-decision">${optionRows(options.overlay_options, "value", (row) => row.label)}</select>`,
      range: `<label for="change-fragment">片段</label><select id="change-fragment">${fragmentOptions}</select><div class="field-pair"><div><label for="range-start">起点（秒）</label><input id="range-start" type="number" min="0" step="0.01"></div><div><label for="range-end">终点（秒）</label><input id="range-end" type="number" min="0.01" step="0.01"></div></div>`,
      rerecord: `<label for="change-target">重录片段</label><select id="change-target">${optionRows(options.rerecord, "fragment_id", (row) => `${row.fragment_id} · ${row.text}`, (row) => `data-hash="${row.approved_text_sha256}"`)}</select>`,
      boundary: `<label for="change-target">边界</label><select id="change-target">${optionRows(options.boundaries, "boundary_id", (row) => `${row.boundary_id} · ${row.boundary_seconds ?? "-"}s`)}</select><label for="boundary-issue">问题</label><select id="boundary-issue"><option value="flash">闪帧</option><option value="black_frame">黑帧</option><option value="audio_gap">声音断点</option><option value="color_jump">色彩跳变</option></select>`,
      structural: `<label for="change-target">影响片段</label><select id="change-target">${optionRows(options.structure_fragments || options.fragments, "fragment_id", (row) => row.label || row.fragment_id)}</select><label for="structural-type">结构动作</label><select id="structural-type"><option value="omit">删段</option><option value="merge">并段</option><option value="restructure">重排</option></select>`,
    };
    $("#change-fields").innerHTML = fields[type] || "";
    $("#change-fragment")?.addEventListener("change", syncFragmentFields);
    syncFragmentFields();
    state.preview = null; state.request = null; $("[data-confirm]").disabled = true; $("#impact-preview").hidden = true;
  }

  function syncFragmentFields() {
    const fragmentId = $("#change-fragment")?.value;
    if (!fragmentId) return;
    const fragment = (state.view.impact_context.change_options.fragments || []).find((item) => item.fragment_id === fragmentId);
    if ($("#material-candidate")) $("#material-candidate").innerHTML = optionRows(fragment?.candidates, "candidate_id", (row) => row.label, (row) => `data-hash="${row.source_sha256}"`);
    if ($("#range-start")) $("#range-start").value = fragment?.range?.start_seconds ?? "";
    if ($("#range-end")) $("#range-end").value = fragment?.range?.end_seconds ?? "";
  }

  function parseChange() {
    const type = $("#change-type").value;
    const reason = $("#change-reason").value.trim();
    let scopeIds = [], payload = {};
    if (type === "copy") { const id = $("#change-target").value; scopeIds = [id]; payload = { line_ids: [id], text_by_id: { [id]: $("#change-text").value.trim() } }; }
    if (type === "claim_scope") { const id = $("#change-target").value; scopeIds = [id]; const add = $("#claim-action").value === "add"; payload = { claim_ids_add: add ? [id] : [], claim_ids_remove: add ? [] : [id] }; }
    if (type === "voice") payload = { provider: $("#voice-provider").value, speaker: $("#voice-speaker").value, speed: Number($("#voice-speed").value) };
    if (type === "material") { const id = $("#change-fragment").value; const selected = $("#material-candidate").selectedOptions[0]; scopeIds = [id]; payload = { fragment_id: id, candidate_id: selected.value, source_sha256: selected.dataset.hash, overlay_decision: $("#overlay-decision").value }; }
    if (type === "range") { const id = $("#change-fragment").value; scopeIds = [id]; payload = { fragment_id: id, start_seconds: Number($("#range-start").value), end_seconds: Number($("#range-end").value) }; }
    if (type === "rerecord") { const selected = $("#change-target").selectedOptions[0]; scopeIds = [selected.value]; payload = { fragment_ids: [selected.value], approved_text_sha256: selected.dataset.hash }; }
    if (type === "boundary") { const id = $("#change-target").value; scopeIds = [id]; payload = { boundary_id: id, issue_type: $("#boundary-issue").value }; }
    if (type === "structural") { const id = $("#change-target").value; scopeIds = [id]; payload = { request_type: $("#structural-type").value, reason, affected_ids: [id] }; }
    return { change_type: type, scope_ids: scopeIds, payload, reason };
  }

  async function previewChange() {
    try {
      state.request = parseChange();
      state.preview = await api(`/gates/${state.view.gate_id}/changes/preview`, { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, request: state.request }) });
      const impact = $("#impact-preview");
      impact.hidden = false;
      impact.innerHTML = `<strong>将返回 ${escapeHtml(state.preview.earliest_affected_gate)}</strong><p>失效阶段：${state.preview.stale_gates.map(escapeHtml).join("、")}</p><p>${escapeHtml(state.preview.business_explanation)}</p>`;
      $("[data-confirm]").disabled = false;
    } catch (error) { toast(error.message); }
  }

  async function confirmChange() {
    if (!state.preview || !state.request) return;
    try {
      const result = await api(`/gates/${state.view.gate_id}/changes`, { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, request: state.request, preview_hash: state.preview.preview_hash, idempotency_key: crypto.randomUUID() }) });
      toast(`修改已提交 · ${result.job_id}`); $("#change-dialog").close();
    } catch (error) { toast(error.message); }
  }

  document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.action)));
  $("[data-close]").addEventListener("click", () => $("#change-dialog").close());
  $("[data-preview]").addEventListener("click", previewChange);
  $("[data-confirm]").addEventListener("click", confirmChange);
  $("#change-type").addEventListener("change", renderChangeFields);
  setInterval(() => eventIntent("review.heartbeat", state.activeIntervalId ? { active_interval_id: state.activeIntervalId } : {}), 30000);
  addEventListener("visibilitychange", () => document.hidden ? stopActive() : startActive());
  addEventListener("pagehide", stopActive);
  loadReview().catch((error) => { $("#connection-status").textContent = "需刷新"; toast(error.message); });
})();
