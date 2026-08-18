(() => {
  const runId = document.body.dataset.runId;
  const state = { workspace: null, review: null, session: null, selected: null, media: null, preview: null, request: null, reloadPending: false };
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? "").replace(/[&<>\"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;"}[c]));
  const api = (path, options = {}) => fetch(`/api/v1/runs/${encodeURIComponent(runId)}${path}`, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options }).then(async (response) => {
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("json") ? await response.json() : await response.text();
    if (!response.ok) throw Object.assign(new Error(body?.detail?.message || body?.message || body || "请求失败"), { response, body });
    return body;
  });
  const toast = (message) => { $("#toast").textContent = message; $("#toast").classList.add("visible"); setTimeout(() => $("#toast").classList.remove("visible"), 2600); };
  const mediaUrl = (path) => `/api/v1/runs/${encodeURIComponent(runId)}/media/${path.split("/").map(encodeURIComponent).join("/")}`;
  const formatTime = (seconds) => { const value = Number(seconds); if (!Number.isFinite(value)) return "00:00"; return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(Math.floor(value % 60)).padStart(2, "0")}`; };
  const objectRows = (rows, type) => (rows || []).map((row) => {
    const id = row[`${type}_id`] || row.asset_id;
    const title = row.business_label || row.label || row.reason || "待确认";
    const meta = row.purpose || row.status || "";
    const ref = row.thumbnail_ref || row.media_ref;
    const thumb = ref && /\.(png|jpe?g|webp)$/i.test(ref) ? `<img class="object-thumb" alt="" src="${mediaUrl(ref)}">` : `<span class="object-thumb"></span>`;
    const status = { ready: "可审核", not_ready: "待补齐", unclassified: "未归类" }[row.status] || row.status || "可审核";
    return `<button type="button" class="object-card ${state.selected?.id === id ? "selected" : ""}" data-object-type="${esc(type)}" data-object-id="${esc(id)}">${thumb}<span><span class="object-name">${esc(title)}</span><span class="object-meta">${esc(meta)}</span><span class="object-status ${row.status === "not_ready" ? "not_ready" : ""}">${esc(status)}</span></span></button>`;
  }).join("");
  function renderRail() {
    const story = state.workspace.storyboard || {};
    $("#element-list").innerHTML = objectRows(story.elements, "element") || `<div class="empty-rail">暂无关键元素</div>`;
    $("#shot-list").innerHTML = objectRows(story.shots, "shot") || `<div class="empty-rail">暂无分镜</div>`;
    $("#audio-list").innerHTML = objectRows(story.audio, "audio") || `<div class="empty-rail">暂无音频</div>`;
    const unclassified = state.workspace.unclassified_assets || [];
    $("#unclassified-list").innerHTML = objectRows(unclassified, "asset") || `<div class="empty-rail">暂无未归类素材</div>`;
    $("#story-count").textContent = `${(story.shots || []).length} 段`;
    $("#unclassified-count").textContent = `${unclassified.length} 个`;
    document.querySelectorAll("[data-object-id]").forEach((button) => button.addEventListener("click", () => selectObject(button.dataset.objectType, button.dataset.objectId)));
  }
  function findObject(type, id) {
    const story = state.workspace.storyboard || {};
    if (type === "asset") return (state.workspace.unclassified_assets || []).find((row) => row.asset_id === id);
    return (story[`${type}s`] || []).find((row) => row[`${type}_id`] === id);
  }
  function selectObject(type, id) {
    const object = findObject(type, id); if (!object) return;
    state.selected = { type, id, object }; renderRail(); renderSelection();
  }
  function renderSelection() {
    const object = state.selected?.object;
    $("#selection-title").textContent = object?.business_label || object?.label || "选择一个分镜";
    $("#selection-purpose").textContent = object?.purpose || object?.reason || "从故事板选择对象查看审核内容";
    const ref = object?.media_ref || object?.thumbnail_ref || state.workspace.preview?.media_ref;
    renderPreview(ref);
    const timelineId = state.selected?.type === "audio" ? `timeline-voice-${state.selected.id.replace("audio-", "")}` : `timeline-${state.selected?.id}`;
    document.querySelectorAll(".timeline-segment").forEach((segment) => segment.classList.toggle("selected", segment.dataset.objectId === state.selected?.id || segment.dataset.objectId === timelineId));
  }
  function renderPreview(ref) {
    const holder = $("#preview-media"); $("#preview-empty").hidden = Boolean(ref); holder.innerHTML = "";
    if (!ref) return;
    const url = mediaUrl(ref); state.media = null;
    if (/\.mp4$/i.test(ref)) holder.innerHTML = `<video id="active-video" controls preload="metadata" src="${url}"></video>`;
    else if (/\.(mp3|wav|m4a)$/i.test(ref)) holder.innerHTML = `<audio id="active-video" controls preload="metadata" src="${url}"></audio>`;
    else if (/\.(png|jpe?g|webp)$/i.test(ref)) holder.innerHTML = `<img id="active-video" alt="审核预览" src="${url}">`;
    const media = $("#active-video"); if (media) { state.media = media; media.addEventListener("timeupdate", () => updatePlayhead(media.currentTime)); }
    $("#preview-caption").textContent = ref === state.workspace.preview?.media_ref ? "当前阶段主预览" : "已选对象预览";
  }
  function updatePlayhead(seconds) { $("#playhead-label").textContent = formatTime(seconds); }
  function renderTimeline() {
    const timeline = state.workspace.timeline || {}; $("#timeline-source").textContent = { planned_order: "计划顺序", approved_broad_range: "批准素材范围", measured_reconstruction_timeline: "真实语音时间线", final_tracks: "成片实测时间线" }[timeline.source] || timeline.source || "";
    $("#timeline-tracks").innerHTML = (timeline.tracks || []).map((track) => `<div class="timeline-track"><span class="track-label">${esc(track.kind)}</span><div class="track-lane">${(track.segments || []).map((segment) => `<button type="button" class="timeline-segment ${track.track_id}" data-object-id="${esc(segment.segment_id)}" data-start="${esc(segment.start_seconds)}" title="${esc(segment.label)}">${esc(segment.label || "片段")}</button>`).join("") || "<span class=\"empty-rail\">暂无</span>"}</div></div>`).join("");
    document.querySelectorAll(".timeline-segment").forEach((segment) => segment.addEventListener("click", () => { updatePlayhead(segment.dataset.start); if (state.media && Number.isFinite(Number(segment.dataset.start))) state.media.currentTime = Number(segment.dataset.start); const id = segment.dataset.objectId || ""; if (id.startsWith("timeline-shot-")) selectObject("shot", id.slice("timeline-".length)); else if (id.startsWith("timeline-voice-")) selectObject("audio", `audio-${id.slice("timeline-voice-".length)}`); else if (id.startsWith("timeline-subtitle-")) selectObject("shot", `shot-${id.slice("timeline-subtitle-".length)}`); }));
  }
  function renderAssistant() {
    const view = state.workspace; const decision = view.decision_context || {};
    $("#run-label").textContent = ` · ${view.summary.task} / ${view.summary.product}`; $("#task-label").textContent = `${view.summary.platform} · ${view.summary.current_stage}`; $("#business-stage").textContent = view.summary.business_stage; $("#assistant-stage").textContent = view.summary.business_stage; $("#progress-label").textContent = `${Math.round(Number(view.summary.progress || 0) * 100)}%`;
    $("#decision-question").textContent = decision.question || "等待审核内容"; $("#recommendation").textContent = decision.recommendation || ""; $("#next-action").textContent = decision.next_action || "";
    const evidenceLabels = { "recipe.json": "参考片拆解", "content_baseline.json": "内容基线", "mutation_plan.json": "变化范围", "shot_blueprint.json": "分镜方案", "matches.json": "素材匹配", "fragment_plan.json": "已选素材范围", "script_evidence_matrix.json": "口播证据闭环", "production_script_candidate.json": "生产文案", "voice_preflight.json": "声音预算检查", "voice/voice_manifest.json": "生成语音", "reconstruction_timeline.json": "真实剪辑时间线", "captions.srt": "字幕文件", "final_validation_report.json": "成片技术校验", "render_report.json": "渲染结果", "remix.mp4": "最终成片" };
    $("#evidence-list").innerHTML = (decision.evidence || []).map((item) => `<div class="evidence-row ${item.status === "missing" ? "missing" : ""}"><span>${esc(evidenceLabels[item.artifact] || "审核依据")}</span><strong>${item.status === "missing" ? "缺失" : "已具备"}</strong></div>`).join("") || `<div class="empty-rail">暂无</div>`;
    const risks = decision.risks || []; $("#risks").innerHTML = risks.map((risk) => `<div class="risk-row ${risk.blocking ? "blocking" : ""}">${esc(risk)}</div>`).join("") || `<div class="empty-rail">当前未发现阻塞</div>`;
    $("#stage-progress").innerHTML = (view.process?.stages || []).map((stage) => `<span class="stage-dot ${stage.status === "approved" ? "done" : stage.gate_ids?.includes(view.current_gate) ? "active" : ""}" title="${esc(stage.business_label)}"></span>`).join("");
    const approve = document.querySelector('[data-action="approve"]'); approve.disabled = decision.approval_eligibility !== true;
    $("#diagnostics-body").textContent = JSON.stringify({ run_id: view.run_id, state_revision: view.state_revision, package_revision: view.package_revision, current_gate: view.current_gate }, null, 2);
  }
  function openSession() { return api("/review-session", { method: "POST", body: JSON.stringify({ gate_id: state.workspace.current_gate }) }).then((session) => { state.session = session; }); }
  async function load() { state.workspace = await api("/workspace"); state.review = await api("/review"); await openSession(); renderAssistant(); renderRail(); renderTimeline(); const preview = state.workspace.preview?.media_ref; renderPreview(preview); $("#connection-status").textContent = "已连接"; if (state.workspace.current_gate === "gate5") { $("#selection-title").textContent = "最终成片"; $("#selection-purpose").textContent = "成片终审"; } else selectObject("shot", state.workspace.storyboard?.shots?.[0]?.shot_id); connectEvents(); }
  function connectEvents() { const events = new EventSource(`/api/v1/runs/${encodeURIComponent(runId)}/events`); events.onopen = () => { $("#connection-status").textContent = "已连接"; }; events.addEventListener("revision", async (event) => { try { const payload = JSON.parse(event.data); if (state.reloadPending || Number(payload.state_revision) <= Number(state.workspace.state_revision)) return; const current = await api("/workspace"); if (Number(current.state_revision) > Number(state.workspace.state_revision)) { state.reloadPending = true; location.reload(); } } catch (_) {} }); events.onerror = () => { $("#connection-status").textContent = "自动同步"; }; }
  async function decide(action) {
    if (action === "request_changes") { openChangeDialog(); return; }
    const note = $("#decision-note").value.trim(); if (action === "reject" && !note) { toast("驳回需要填写业务原因"); return; }
    const identity = state.session.review_identity;
    try { await api(`/gates/${state.workspace.current_gate}/decisions`, { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, decision: action, scope_ids: state.review?.impact_context?.decision_scope_ids || [state.workspace.current_gate], strategy: {}, note, review_package_hash: identity.review_package_hash, state_revision: identity.state_revision, idempotency_key: crypto.randomUUID() }) }); toast(action === "approve" ? "已通过" : "已驳回"); setTimeout(() => location.reload(), 500); } catch (error) { toast(error.message); if (error.response?.status === 409) setTimeout(() => location.reload(), 900); }
  }
  function openChangeDialog() { const options = state.review?.impact_context?.change_options || {}; const types = options.allowed_change_types || ["copy", "material", "voice", "structural"]; const labels = {boundary:"镜头衔接",copy:"文案",material:"素材",range:"素材取用范围",rerecord:"重新配音",voice:"音色或语速",structural:"结构"}; $("#change-dialog").classList.add("change-dialog"); $("#change-type").innerHTML = types.map((type) => `<option value="${esc(type)}">${esc(labels[type] || type)}</option>`).join(""); renderChangeTargets(); $("#change-dialog").showModal(); }
  function renderChangeTargets() { const options = state.review?.impact_context?.change_options || {}; const type = $("#change-type").value; const rows = type === "material" || type === "range" ? (options.fragments || []) : type === "copy" ? (options.lines || []) : type === "rerecord" ? (options.rerecord || []) : (options.structure_fragments || options.claims || [{ id: state.workspace.current_gate, label: state.workspace.current_gate }]); $("#change-target").innerHTML = rows.map((row) => `<option value="${esc(row.fragment_id || row.line_id || row.claim_id || row.id)}">${esc(row.label || row.text || row.fragment_id || row.line_id || row.claim_id || row.id)}</option>`).join(""); renderChangeExtra(type, rows[0] || {}); }
  function renderChangeExtra(type, row) { let extra = $("#change-extra"); if (!extra) { extra = document.createElement("div"); extra.id = "change-extra"; $("#change-target").insertAdjacentElement("afterend", extra); } const options = state.review?.impact_context?.change_options || {}; if (type === "copy") extra.innerHTML = `<label for="change-text">新文案</label><textarea id="change-text" rows="3">${esc(row.text || "")}</textarea>`; else if (type === "voice") extra.innerHTML = `<label for="voice-provider">服务</label><input id="voice-provider" value="${esc(options.voice?.current?.provider || "")}"><label for="voice-speaker">音色</label><input id="voice-speaker" value="${esc(options.voice?.current?.speaker || options.voice?.current?.voice || "")}"><label for="voice-speed">语速</label><input id="voice-speed" type="number" step="0.05" value="${esc(options.voice?.current?.speed || 1)}">`; else if (type === "range") extra.innerHTML = `<label for="range-start">开始秒数</label><input id="range-start" type="number" min="0" step="0.01" value="${esc(row.range?.start_seconds ?? 0)}"><label for="range-end">结束秒数</label><input id="range-end" type="number" min="0" step="0.01" value="${esc(row.range?.end_seconds ?? 1)}">`; else if (type === "material") { const candidates = row.candidates || []; extra.innerHTML = `<label for="material-candidate">候选素材</label><select id="material-candidate">${candidates.map((candidate) => `<option value="${esc(candidate.candidate_id)}" data-hash="${esc(candidate.source_sha256)}">${esc(candidate.label || candidate.candidate_id)}</option>`).join("")}</select><label for="overlay-decision">源文字处理</label><select id="overlay-decision"><option value="no_action">无需处理</option><option value="retain_source_text">保留源文字</option><option value="crop">裁切</option><option value="cover">遮盖</option><option value="replace">替换</option></select>`; } else if (type === "structural") extra.innerHTML = `<label for="structural-type">结构动作</label><select id="structural-type"><option value="omit">删段</option><option value="merge">并段</option><option value="restructure">重排</option></select>`; else extra.innerHTML = ""; }
  async function previewChange() { const reason = $("#change-reason").value.trim(); if (!reason) { toast("请填写业务原因"); return; } const type = $("#change-type").value; const target = $("#change-target").value; let payload = { target_id: target }; if (type === "copy") payload = { line_ids: [target], text_by_id: { [target]: $("#change-text")?.value.trim() || "" } }; if (type === "claim_scope") payload = { claim_ids_add: [target], claim_ids_remove: [] }; if (type === "voice") payload = { provider: $("#voice-provider")?.value.trim(), speaker: $("#voice-speaker")?.value.trim(), speed: Number($("#voice-speed")?.value) }; if (type === "range") payload = { fragment_id: target, start_seconds: Number($("#range-start")?.value), end_seconds: Number($("#range-end")?.value) }; if (type === "material") { const candidate = $("#material-candidate")?.selectedOptions[0]; payload = { fragment_id: target, candidate_id: candidate?.value, source_sha256: candidate?.dataset.hash, overlay_decision: $("#overlay-decision")?.value }; } if (type === "rerecord") { const rerecord = (state.review?.impact_context?.change_options?.rerecord || []).find((item) => item.fragment_id === target); payload = { fragment_ids: [target], approved_text_sha256: rerecord?.approved_text_sha256 }; } if (type === "boundary") payload = { boundary_id: target, issue_type: "trim" }; if (type === "structural") payload = { request_type: $("#structural-type")?.value, affected_ids: [target] }; state.request = { change_type: type, scope_ids: [target], payload, reason }; try { const result = await api(`/gates/${state.workspace.current_gate}/changes/preview`, { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, request: state.request }) }); state.preview = result; $("#impact-preview").hidden = false; $("#impact-preview").innerHTML = `<strong>将返回 ${esc(result.earliest_affected_gate || "上一阶段")}</strong><p>失效阶段：${esc((result.stale_gates || []).join("、") || "无")}</p><p>${esc(result.business_explanation || result.estimated_time || "影响预览已生成")}</p>`; $("[data-confirm]").disabled = false; } catch (error) { toast(error.message); } }
  async function confirmChange() { if (!state.preview || !state.request) return; try { const result = await api(`/gates/${state.workspace.current_gate}/changes`, { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, request: state.request, preview_hash: state.preview.preview_hash, idempotency_key: crypto.randomUUID() }) }); toast(`修改已提交 · ${result.job_id || "处理中"}`); $("#change-dialog").close(); } catch (error) { toast(error.message); } }
  $("#play-toggle").addEventListener("click", () => { if (!state.media || !state.media.play) return; if (state.media.paused) state.media.play(); else state.media.pause(); }); $("#diagnostics-toggle").addEventListener("click", () => { $("#diagnostics").open = !$("#diagnostics").open; }); document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.action))); $("[data-close]").addEventListener("click", () => $("#change-dialog").close()); $("[data-preview]").addEventListener("click", previewChange); $("[data-confirm]").addEventListener("click", confirmChange); $("#change-type").addEventListener("change", renderChangeTargets);
  load().catch((error) => { $("#connection-status").textContent = "需要刷新"; toast(error.message); });
})();
