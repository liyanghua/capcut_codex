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
  const mediaKind = { video: "视频", image: "图片", audio: "音频" };
  const statusLabel = { ready: "可审核", not_ready: "待补齐", unclassified: "未归类", 预算: "待生成" };
  const isImageRef = (ref) => Boolean(ref) && /\.(png|jpe?g|webp)$/i.test(String(ref));
  const isVideoRef = (ref) => Boolean(ref) && /\.(mp4|mov|m4v|webm)$/i.test(String(ref));
  const isAudioRef = (ref) => Boolean(ref) && /\.(mp3|wav|m4a|aac)$/i.test(String(ref));

  function objectThumb(ref) {
    if (isImageRef(ref)) return `<img class="object-thumb" alt="" loading="lazy" src="${mediaUrl(ref)}">`;
    return `<span class="object-thumb thumb-placeholder"><span>暂无预览</span></span>`;
  }
  const objectRows = (rows, type) => (rows || []).map((row) => {
    const id = row[`${type}_id`] || row.asset_id;
    const title = row.business_label || row.label || row.reason || "待确认";
    const meta = row.purpose || "";
    const kind = row.media_type ? mediaKind[row.media_type] || row.media_type : "";
    const related = type === "element" && (row.related_fragment_ids || []).length ? `关联 ${row.related_fragment_ids.length} 段` : "";
    const status = statusLabel[row.status] || row.status || "可审核";
    return `<button type="button" class="object-card ${state.selected?.id === id ? "selected" : ""}" data-object-type="${esc(type)}" data-object-id="${esc(id)}">${objectThumb(row.thumbnail_ref || row.media_ref)}<span class="object-text"><span class="object-name">${esc(title)}</span><span class="object-meta">${esc(meta)}</span><span class="object-sub">${kind ? `<span class="type-chip">${esc(kind)}</span>` : ""}${related ? `<span class="object-rel">${esc(related)}</span>` : ""}<span class="object-status ${row.status === "not_ready" ? "not_ready" : ""}">${esc(status)}</span></span></span></button>`;
  }).join("");

  function pendingHint(state, label, note) {
    if (state === "pending_gate2" || state === "pending_gate3") return `<div class="empty-rail">尚未进入该阶段（${note}）</div>`;
    return `<div class="empty-rail">暂无${label}</div>`;
  }

  function renderRail() {
    const story = state.workspace.storyboard || {};
    const sectionStates = story.section_states || {};
    $("#element-list").innerHTML = objectRows(story.elements, "element") || pendingHint(sectionStates.elements, "关键元素", "待 Gate 2 确认后展示");
    $("#shot-list").innerHTML = objectRows(story.shots, "shot") || pendingHint(sectionStates.shots, "分镜", "待生成");
    $("#audio-list").innerHTML = objectRows(story.audio, "audio") || pendingHint(sectionStates.audio, "音频", "待 Gate 3 证据闭环后展示");
    const unclassified = state.workspace.unclassified_assets || [];
    $("#unclassified-list").innerHTML = objectRows(unclassified, "asset") || `<div class="empty-rail">暂无未归类素材</div>`;
    $("#story-count").textContent = `${(story.shots || []).length} 段`;
    $("#unclassified-count").textContent = `${unclassified.length} 个`;
    document.querySelectorAll("[data-object-id]").forEach((button) => button.addEventListener("click", () => selectObject(button.dataset.objectType, button.dataset.objectId)));
  }

  function findObject(type, id) {
    const story = state.workspace.storyboard || {};
    if (type === "asset") return (state.workspace.unclassified_assets || []).find((row) => row.asset_id === id);
    if (type === "element") return (story.elements || []).find((row) => row.element_id === id);
    if (type === "shot") return (story.shots || []).find((row) => row.shot_id === id);
    if (type === "audio") return (story.audio || []).find((row) => row.audio_id === id);
    return undefined;
  }

  function timelineTargetFor(type, id, object) {
    if (type === "shot") return `timeline-shot-${id.replace("shot-", "")}`;
    if (type === "audio") return `timeline-voice-${id.replace("audio-", "")}`;
    if (type === "element") { const first = (object?.related_shot_ids || [])[0]; return first ? `timeline-shot-${first.replace("shot-", "")}` : null; }
    return null;
  }

  function highlightTimeline(targetId) {
    document.querySelectorAll(".timeline-segment").forEach((segment) => segment.classList.toggle("selected", Boolean(targetId) && segment.dataset.objectId === targetId));
    if (!targetId) return;
    const segment = document.querySelector(`.timeline-segment[data-object-id="${CSS.escape(targetId)}"]`);
    if (segment) segment.scrollIntoView({ block: "nearest", inline: "center" });
  }

  function seekCenterTo(targetId) {
    if (state.workspace?.timeline?.timebase === "source_range") return;
    const segment = document.querySelector(`.timeline-segment[data-object-id="${CSS.escape(targetId)}"]`);
    if (!segment) return;
    const start = Number(segment.dataset.start);
    if (Number.isFinite(start)) {
      if (state.media) state.media.currentTime = start;
      updatePlayhead(start);
    }
  }

  function selectObject(type, id, options = {}) {
    const object = findObject(type, id); if (!object) return;
    state.selected = { type, id, object };
    renderRail();
    renderDetail(object);
    const target = timelineTargetFor(type, id, object);
    highlightTimeline(target);
    if (options.seek !== false) seekCenterTo(target);
  }

  function mediaElement(mediaRef) {
    if (isVideoRef(mediaRef)) return `<video id="detail-media-el" controls preload="metadata" src="${mediaUrl(mediaRef)}"></video>`;
    if (isAudioRef(mediaRef)) return `<audio id="detail-media-el" controls preload="metadata" src="${mediaUrl(mediaRef)}"></audio>`;
    if (isImageRef(mediaRef)) return `<img id="detail-media-el" alt="对象预览" src="${mediaUrl(mediaRef)}">`;
    return "";
  }

  function renderDetail(object) {
    $("#object-detail").hidden = false;
    $("#detail-heading").textContent = object.business_label || object.label || "对象详情";
    const mediaRef = object.media_ref || (isImageRef(object.thumbnail_ref) ? object.thumbnail_ref : null);
    $("#detail-media").innerHTML = mediaRef ? mediaElement(mediaRef) : `<div class="empty-state">暂无可用媒体</div>`;
    const fields = [
      ["用途", object.purpose || "—"],
      ["状态", statusLabel[object.status] || object.status || "—"],
      ["媒体类型", object.media_type ? mediaKind[object.media_type] || object.media_type : "待确认"],
    ];
    if (object.related_fragment_ids?.length) fields.push(["关联片段", object.related_fragment_ids.join("、")]);
    if (object.fragment_id) fields.push(["生产片段", object.fragment_id]);
    if (object.claim_ids?.length) fields.push(["关联卖点", object.claim_ids.join("、")]);
    if (Number.isFinite(Number(object.measured_duration_seconds))) fields.push(["实测时长", `${object.measured_duration_seconds} 秒`]);
    if (Number.isFinite(Number(object.start_seconds)) && Number.isFinite(Number(object.end_seconds))) fields.push(["参考时段", `${object.start_seconds}s – ${object.end_seconds}s`]);
    fields.push(["关联对象", object.reason ? "未归类素材，不参与生产" : "故事板对象"]);
    $("#detail-fields").innerHTML = fields.map(([label, value]) => `<div class="detail-row"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("");
  }

  function updatePlayhead(seconds) {
    const total = Number(state.workspace?.timeline?.total_duration_seconds) || 0;
    const playhead = $("#timeline-playhead");
    if (total > 0) {
      const pct = Math.min(100, Math.max(0, (Number(seconds || 0) / total) * 100));
      playhead.hidden = false;
      playhead.style.left = `${pct}%`;
    } else {
      playhead.hidden = true;
    }
    $("#playhead-label").textContent = formatTime(seconds);
  }

  function renderPreview(ref) {
    const holder = $("#preview-media");
    $("#preview-empty").hidden = Boolean(ref);
    if (!ref) $("#preview-empty").textContent = state.workspace.preview?.empty_reason || "当前阶段尚无可播放媒体";
    holder.innerHTML = "";
    if (!ref) { state.media = null; return; }
    const url = mediaUrl(ref);
    if (isVideoRef(ref)) holder.innerHTML = `<video id="active-video" controls preload="metadata" src="${url}"></video>`;
    else if (isAudioRef(ref)) holder.innerHTML = `<audio id="active-video" controls preload="metadata" src="${url}"></audio>`;
    else if (isImageRef(ref)) holder.innerHTML = `<img id="active-video" alt="阶段主预览" src="${url}">`;
    const media = $("#active-video");
    if (media) { state.media = media; media.addEventListener("timeupdate", () => updatePlayhead(media.currentTime)); }
    const modeLabel = { reference: "参考视频", proxy: "审核代理", final: "最终成片", empty: "暂无主媒体" }[state.workspace.preview?.mode] || "";
    $("#preview-caption").textContent = `当前阶段主预览${modeLabel ? ` · ${modeLabel}` : ""}${state.workspace.preview?.status === "not_ready" ? " · 待补齐" : ""}`;
  }

  function renderTimeline() {
    const timeline = state.workspace.timeline || {};
    const sourceRange = timeline.timebase === "source_range";
    const pictureSegments = (timeline.tracks || []).find((track) => track.track_id === "picture")?.segments || [];
    const total = sourceRange ? Math.max(1, pictureSegments.length) : (Number(timeline.total_duration_seconds) || 10);
    const scale = (value) => Math.min(100, Math.max(0, (Number(value) / total) * 100));
    $("#timeline-source").textContent = { planned_order: "计划顺序", approved_broad_range: "素材范围（按顺序）", measured_reconstruction_timeline: "真实语音时间线", final_tracks: "成片实测时间线" }[timeline.source] || timeline.source || "";
    const tickCount = Math.max(4, Math.min(12, Math.round(total / 2)));
    let ruler = "";
    for (let index = 0; index <= tickCount; index += 1) {
      const time = (total / tickCount) * index;
      const label = sourceRange ? `素材 ${Math.min(pictureSegments.length, Math.round(time) + 1)}` : formatTime(time);
      ruler += `<span class="ruler-tick" style="left:${scale(time)}%"><span class="ruler-line"></span>${label}</span>`;
    }
    $("#timeline-ruler").innerHTML = ruler;
    $("#timeline-tracks").innerHTML = (timeline.tracks || []).map((track) => {
      const lane = (track.segments || []).map((segment, segmentIndex) => {
        const start = sourceRange ? segmentIndex : Number(segment.start_seconds) || 0;
        const width = sourceRange ? scale(1) : Math.max(1.5, scale(Number(segment.duration_seconds) || 1));
        const left = scale(start);
        const thumb = isImageRef(segment.thumbnail_ref) ? `<img class="segment-thumb" alt="" loading="lazy" src="${mediaUrl(segment.thumbnail_ref)}">` : "";
        const showText = track.track_id === "subtitles" || track.track_id === "voice";
        const sourceLabel = sourceRange && Number.isFinite(Number(segment.start_seconds)) && Number.isFinite(Number(segment.end_seconds)) ? ` · 素材 ${formatTime(segment.start_seconds)}-${formatTime(segment.end_seconds)}` : "";
        const dataStart = sourceRange ? "" : (segment.start_seconds ?? 0);
        const dataEnd = sourceRange ? "" : (segment.end_seconds ?? segment.start_seconds ?? 0);
        return `<button type="button" class="timeline-segment ${track.track_id} ${thumb ? "with-thumb" : ""}" data-object-id="${esc(segment.related_object_id)}" data-segment-id="${esc(segment.segment_id)}" data-start="${esc(dataStart)}" data-end="${esc(dataEnd)}" style="left:${left}%;width:${width}%" title="${esc(segment.label)}${sourceLabel}">${thumb}<span class="segment-text">${showText ? esc(segment.label) : ""}</span></button>`;
      }).join("") || `<span class="empty-rail">暂无</span>`;
      return `<div class="timeline-track"><span class="track-label">${esc(track.kind)}</span><div class="track-lane">${lane}</div></div>`;
    }).join("");
    document.querySelectorAll(".timeline-segment").forEach((segment) => segment.addEventListener("click", () => {
      const start = Number(segment.dataset.start);
      if (!sourceRange && Number.isFinite(start)) {
        if (state.media) state.media.currentTime = start;
        updatePlayhead(start);
      }
      const objectId = segment.dataset.objectId || "";
      if (objectId.startsWith("audio-")) selectObject("audio", objectId, { seek: false });
      else if (objectId.startsWith("shot-")) selectObject("shot", objectId, { seek: false });
    }));
  }

  const substepLabels = { gate1: "镜头拆解", gate2: "内容基线", gate3_material_selection: "选材确认", gate3_evidence_closure: "证据闭环", gate4_pre_generation: "生成前批准", gate4_post_generation: "生成后听审", gate5: "成片终审" };
  const substepStatus = { approved: "已通过", awaiting_user: "待确认", not_ready: "未开始", stale: "需重新确认", rejected: "已驳回", blocked: "阻塞" };
  const stageStatus = { approved: "已完成", awaiting_user: "待确认", not_ready: "未开始", stale: "需重新确认", rejected: "已驳回", blocked: "阻塞" };
  const _RISK_STAGE_STATUSES = new Set(["stale", "rejected", "blocked"]);

  function renderStepper() {
    const stages = state.workspace.process?.stages || [];
    const currentLabel = state.workspace.process?.current_stage;
    $("#stage-stepper").innerHTML = stages.map((stage, index) => {
      const isCurrent = stage.business_label === currentLabel;
      const cls = stage.status === "approved" ? "done" : _RISK_STAGE_STATUSES.has(stage.status) ? "blocked" : isCurrent ? "current" : "future";
      const label = stageStatus[stage.status] || "需确认";
      const subs = (stage.substeps || []).map((sub) => `<span class="substep ${sub.status}">${esc(substepLabels[sub.gate_id] || sub.gate_id)} · ${esc(substepStatus[sub.status] || sub.status)}</span>`).join("");
      return `<li class="stage-step ${cls}" data-open="${isCurrent ? "1" : "0"}">
        <button type="button" class="stage-toggle" aria-expanded="${isCurrent ? "true" : "false"}"><span class="stage-index">${index + 1}</span><span class="stage-info"><span class="stage-label">${esc(stage.business_label)}</span><span class="stage-status">${esc(label)}</span></span></button>
        <div class="stage-detail" ${isCurrent ? "" : "hidden"}>${subs || `<span class="empty-rail">暂无子步骤</span>`}</div>
      </li>`;
    }).join("");
    document.querySelectorAll(".stage-toggle").forEach((button) => button.addEventListener("click", () => {
      const step = button.closest(".stage-step");
      if (step.classList.contains("future")) return;
      const detail = step.querySelector(".stage-detail");
      detail.hidden = !detail.hidden;
      button.setAttribute("aria-expanded", String(!detail.hidden));
    }));
  }

  function renderStageContent() {
    const gate = state.workspace.current_gate;
    const decision = state.workspace.decision_context || {};
    const parts = [];
    if (gate.startsWith("gate4")) {
      const script = decision.script_details;
      if (script) {
        const lines = (script.lines || []).map((line) => `<div class="script-line"><span class="line-id">${esc(line.fragment_id)}</span><span>${esc(line.text)}</span></div>`).join("");
        parts.push(`<div class="content-group"><h4>生产文案${script.approved ? " · 已批准" : " · 候选"}</h4>${lines || `<span class="empty-rail">暂无文案</span>`}</div>`);
        if (script.voice) parts.push(`<div class="content-group"><h4>音色与语速</h4><div class="voice-facts"><span>服务：${esc(script.voice.provider || "待确认")}</span><span>音色：${esc(script.voice.speaker || "待确认")}</span><span>语速：${esc(script.voice.speed ?? "待确认")}</span></div></div>`);
      }
      const preflight = decision.voice_preflight_details;
      if (preflight) {
        const rows = (preflight.fragments || []).map((row) => `<div class="preflight-row ${row.preflight_status === "passed" ? "passed" : "blocked"}"><span>${esc(row.fragment_id)}</span><span>估算 ${esc(row.voice_duration_estimate_seconds ?? "—")}s / 预算 ${esc(row.visual_duration_budget_seconds ?? "—")}s</span><span>${row.preflight_status === "passed" ? "通过" : "超预算"}</span></div>`).join("");
        parts.push(`<div class="content-group"><h4>声音预算检查 · ${esc(preflight.preflight_status || "待确认")}${(preflight.blocked_fragment_ids || []).length ? ` · 阻塞 ${preflight.blocked_fragment_ids.length} 段` : ""}</h4>${rows || `<span class="empty-rail">暂无预检结果</span>`}</div>`);
      }
      if (decision.subtitle_boundary_results) parts.push(`<div class="content-group"><h4>字幕边界听审</h4><span>状态：${esc(decision.subtitle_boundary_results.status || "可用")}</span></div>`);
      if (decision.generated_voice) parts.push(`<div class="content-group"><h4>生成语音</h4><span>状态：${esc(decision.generated_voice.status || "可用")}</span></div>`);
    }
    if (gate === "gate5") {
      const quality = decision.quality || {};
      const rows = [
        ["L0 技术校验", quality.l0],
        ["L1 内容校验", quality.l1],
        ["P 生产审计", quality.p ?? quality.production_audit],
      ].map(([label, value]) => `<div class="quality-row"><span>${label}</span><span>${value ? esc(typeof value === "object" ? (value.status || value.result || JSON.stringify(value)) : value) : "暂无结果（待生成）"}</span></div>`).join("");
      const deliveries = (quality.delivery_files || []).map((file) => `<span class="type-chip">${esc(file)}</span>`).join("") || `<span class="empty-rail">暂无交付文件</span>`;
      parts.push(`<div class="content-group"><h4>质量与交付</h4>${rows}<div class="delivery-files"><span class="eyebrow">交付文件</span>${deliveries}</div></div>`);
    }
    $("#stage-content").innerHTML = parts.join("");
    $("#stage-content-card").hidden = parts.length === 0;
  }

  function renderQualityChecks() {
    const gate = state.workspace.current_gate;
    const checks = (state.workspace.quality_checks || []).filter((row) => (row.gate_scope || []).includes(gate));
    $("#quality-card").hidden = checks.length === 0;
    const labels = { passed: "通过", blocked: "阻断", manual_review: "需人工确认", not_available: "暂无来源" };
    const classes = { passed: "ok", blocked: "bad", manual_review: "warn", not_available: "muted" };
    $("#quality-checks").innerHTML = checks.map((row) => {
      const detail = row.status === "blocked" && (row.detail?.blocked_fragment_ids || []).length ? ` · 阻塞片段 ${row.detail.blocked_fragment_ids.join("、")}` : "";
      const source = row.source_artifact ? ` · 来源 ${esc(row.source_artifact)}` : "";
      return `<div class="quality-row"><span>${esc(row.business_label)}</span><span class="quality-status ${classes[row.status] || ""}">${esc(labels[row.status] || row.status)}${esc(detail)}${source}</span></div>`;
    }).join("") || `<div class="empty-rail">当前阶段暂无质量检查</div>`;
  }

  function renderAssistant() {
    const view = state.workspace;
    const decision = view.decision_context || {};
    $("#run-label").textContent = ` · ${view.summary.task} / ${view.summary.product}`;
    $("#task-label").textContent = `${view.summary.platform} · ${view.summary.current_stage}`;
    $("#business-stage").textContent = view.summary.business_stage;
    $("#assistant-stage").textContent = view.summary.business_stage;
    $("#substep-label").textContent = substepLabels[view.current_gate] || "";
    $("#progress-label").textContent = `${Math.round(Number(view.summary.progress || 0) * 100)}%`;
    $("#preview-title").textContent = view.current_gate === "gate5" ? "最终成片" : `${view.summary.business_stage}主预览`;
    $("#decision-question").textContent = decision.question || "等待审核内容";
    $("#recommendation").textContent = decision.recommendation || "";
    $("#next-action").textContent = decision.next_action || "";
    const evidenceLabels = { "recipe.json": "参考片拆解", "content_baseline.json": "内容基线", "mutation_plan.json": "变化范围", "shot_blueprint.json": "分镜方案", "matches.json": "素材匹配", "fragment_plan.json": "已选素材范围", "script_evidence_matrix.json": "口播证据闭环", "production_script_candidate.json": "生产文案", "voice_preflight.json": "声音预算检查", "voice/voice_manifest.json": "生成语音", "reconstruction_timeline.json": "真实剪辑时间线", "captions.srt": "字幕文件", "final_validation_report.json": "成片技术校验", "render_report.json": "渲染结果", "remix.mp4": "最终成片" };
    $("#evidence-list").innerHTML = (decision.evidence || []).map((item) => `<div class="evidence-row ${item.status === "missing" ? "missing" : ""}"><span>${esc(evidenceLabels[item.artifact] || "审核依据")}</span><strong>${item.status === "missing" ? "缺失" : "已具备"}</strong></div>`).join("") || `<div class="empty-rail">暂无</div>`;
    const risks = decision.risks || [];
    $("#risks").innerHTML = risks.map((risk) => `<div class="risk-row ${risk.blocking ? "blocking" : ""}">${esc(risk)}</div>`).join("") || `<div class="empty-rail">当前未发现阻塞</div>`;
    renderStepper();
    renderStageContent();
    renderQualityChecks();
    const approve = document.querySelector('[data-action="approve"]');
    approve.disabled = decision.approval_eligibility !== true;
    $("#diagnostics-body").textContent = JSON.stringify({ run_id: view.run_id, state_revision: view.state_revision, package_revision: view.package_revision, current_gate: view.current_gate, preview_mode: view.preview?.mode, execution: view.process?.execution || [], artifacts: view.artifacts || [] }, null, 2);
  }

  function openSession() { return api("/review-session", { method: "POST", body: JSON.stringify({ gate_id: state.workspace.current_gate }) }).then((session) => { state.session = session; }); }

  async function load() {
    state.workspace = await api("/workspace");
    state.review = await api("/review");
    await openSession();
    renderAssistant();
    renderRail();
    renderTimeline();
    renderPreview(state.workspace.preview?.media_ref);
    $("#connection-status").textContent = "已连接";
    connectEvents();
  }

  async function refreshWorkspace(current) {
    if (state.reloadPending) return;
    state.reloadPending = true;
    const previousPreviewRef = state.workspace?.preview?.media_ref;
    const paused = state.media ? state.media.paused !== false : true;
    const currentTime = state.media ? Number(state.media.currentTime) || 0 : 0;
    const selected = state.selected ? { type: state.selected.type, id: state.selected.id } : null;
    const detailOpen = $("#object-detail").hidden === false;
    state.workspace = current;
    state.review = await api("/review");
    renderAssistant();
    renderRail();
    renderTimeline();
    if (current?.preview?.media_ref !== previousPreviewRef) {
      renderPreview(current?.preview?.media_ref);
    } else if (state.media && Number.isFinite(currentTime)) {
      state.media.currentTime = currentTime;
      if (!paused && typeof state.media.play === "function") state.media.play().catch(() => {});
    }
    if (selected) {
      const object = findObject(selected.type, selected.id);
      if (object) {
        state.selected = { type: selected.type, id: selected.id, object };
        renderRail();
        renderDetail(object);
        highlightTimeline(timelineTargetFor(selected.type, selected.id, object));
      } else {
        state.selected = null;
        renderRail();
      }
    }
    $("#object-detail").hidden = !detailOpen;
    updatePlayhead(currentTime);
    state.reloadPending = false;
  }

  function connectEvents() {
    const events = new EventSource(`/api/v1/runs/${encodeURIComponent(runId)}/events`);
    events.onopen = () => { $("#connection-status").textContent = "已连接"; };
    events.addEventListener("revision", async (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (state.reloadPending || Number(payload.state_revision) <= Number(state.workspace.state_revision)) return;
        const current = await api("/workspace");
        if (Number(current.state_revision) > Number(state.workspace.state_revision)) await refreshWorkspace(current);
      } catch (_) {}
    });
    events.onerror = () => { $("#connection-status").textContent = "自动同步"; };
  }

  async function decide(action) {
    if (action === "request_changes") { openChangeDialog(); return; }
    const note = $("#decision-note").value.trim(); if (action === "reject" && !note) { toast("驳回需要填写业务原因"); return; }
    const identity = state.session.review_identity;
    try {
      await api(`/gates/${state.workspace.current_gate}/decisions`, { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, decision: action, scope_ids: state.review?.impact_context?.decision_scope_ids || [state.workspace.current_gate], strategy: {}, note, review_package_hash: identity.review_package_hash, state_revision: identity.state_revision, idempotency_key: crypto.randomUUID() }) });
      toast(action === "approve" ? "已通过" : "已驳回");
      const current = await api("/workspace");
      await refreshWorkspace(current);
      await openSession();
    } catch (error) {
      toast(error.message);
      if (error.response?.status === 409) {
        const current = await api("/workspace");
        await refreshWorkspace(current);
        await openSession();
      }
    }
  }

  function openChangeDialog() {
    const options = state.review?.impact_context?.change_options || {};
    const types = options.allowed_change_types || ["copy", "material", "voice", "structural"];
    const labels = { boundary: "镜头衔接", copy: "文案", material: "素材", range: "素材取用范围", rerecord: "重新配音", voice: "音色或语速", structural: "结构" };
    $("#change-dialog").classList.add("change-dialog");
    $("#change-type").innerHTML = types.map((type) => `<option value="${esc(type)}">${esc(labels[type] || type)}</option>`).join("");
    renderChangeTargets();
    $("#change-dialog").showModal();
  }

  function renderChangeTargets() {
    const options = state.review?.impact_context?.change_options || {};
    const type = $("#change-type").value;
    const rows = type === "material" || type === "range" ? (options.fragments || []) : type === "copy" ? (options.lines || []) : type === "rerecord" ? (options.rerecord || []) : (options.structure_fragments || options.claims || [{ id: state.workspace.current_gate, label: state.workspace.current_gate }]);
    $("#change-target").innerHTML = rows.map((row) => `<option value="${esc(row.fragment_id || row.line_id || row.claim_id || row.id)}">${esc(row.label || row.text || row.fragment_id || row.line_id || row.claim_id || row.id)}</option>`).join("");
    renderChangeExtra(type, rows[0] || {});
  }

  function renderChangeExtra(type, row) {
    let extra = $("#change-extra");
    if (!extra) { extra = document.createElement("div"); extra.id = "change-extra"; $("#change-target").insertAdjacentElement("afterend", extra); }
    const options = state.review?.impact_context?.change_options || {};
    if (type === "copy") extra.innerHTML = `<label for="change-text">新文案</label><textarea id="change-text" rows="3">${esc(row.text || "")}</textarea><label for="copy-edit-intent">修改意图</label><select id="copy-edit-intent"><option value="rewrite">改写这句</option><option value="bridge">补衔接不新增事实</option></select>`;
    else if (type === "voice") extra.innerHTML = `<label for="voice-provider">服务</label><input id="voice-provider" value="${esc(options.voice?.current?.provider || "")}"><label for="voice-speaker">音色</label><input id="voice-speaker" value="${esc(options.voice?.current?.speaker || options.voice?.current?.voice || "")}"><label for="voice-speed">语速</label><input id="voice-speed" type="number" step="0.05" value="${esc(options.voice?.current?.speed || 1)}">`;
    else if (type === "range") extra.innerHTML = `<label for="range-start">开始秒数</label><input id="range-start" type="number" min="0" step="0.01" value="${esc(row.range?.start_seconds ?? 0)}"><label for="range-end">结束秒数</label><input id="range-end" type="number" min="0" step="0.01" value="${esc(row.range?.end_seconds ?? 1)}">`;
    else if (type === "material") { const candidates = row.candidates || []; extra.innerHTML = `<label for="material-candidate">候选素材</label><select id="material-candidate">${candidates.map((candidate) => `<option value="${esc(candidate.candidate_id)}" data-hash="${esc(candidate.source_sha256)}">${esc(candidate.label || candidate.candidate_id)}</option>`).join("")}</select><label for="overlay-decision">源文字处理</label><select id="overlay-decision"><option value="no_action">无需处理</option><option value="retain_source_text">保留源文字</option><option value="crop">裁切</option><option value="cover">遮盖</option><option value="replace">替换</option></select>`; }
    else if (type === "structural") extra.innerHTML = `<label for="structural-type">结构动作</label><select id="structural-type"><option value="omit">删段</option><option value="merge">并段</option><option value="restructure">重排</option></select>`;
    else extra.innerHTML = "";
  }

  async function previewChange() {
    const reason = $("#change-reason").value.trim(); if (!reason) { toast("请填写业务原因"); return; }
    const type = $("#change-type").value; const target = $("#change-target").value;
    let payload = { target_id: target };
    if (type === "copy") payload = { line_ids: [target], text_by_id: { [target]: $("#change-text")?.value.trim() || "" }, edit_intent: $("#copy-edit-intent")?.value || "rewrite" };
    if (type === "claim_scope") payload = { claim_ids_add: [target], claim_ids_remove: [] };
    if (type === "voice") payload = { provider: $("#voice-provider")?.value.trim(), speaker: $("#voice-speaker")?.value.trim(), speed: Number($("#voice-speed")?.value) };
    if (type === "range") payload = { fragment_id: target, start_seconds: Number($("#range-start")?.value), end_seconds: Number($("#range-end")?.value) };
    if (type === "material") { const candidate = $("#material-candidate")?.selectedOptions[0]; payload = { fragment_id: target, candidate_id: candidate?.value, source_sha256: candidate?.dataset.hash, overlay_decision: $("#overlay-decision")?.value }; }
    if (type === "rerecord") { const rerecord = (state.review?.impact_context?.change_options?.rerecord || []).find((item) => item.fragment_id === target); payload = { fragment_ids: [target], approved_text_sha256: rerecord?.approved_text_sha256 }; }
    if (type === "boundary") payload = { boundary_id: target, issue_type: "trim" };
    if (type === "structural") payload = { request_type: $("#structural-type")?.value, affected_ids: [target] };
    state.request = { change_type: type, scope_ids: [target], payload, reason };
    try {
      const result = await api(`/gates/${state.workspace.current_gate}/changes/preview`, { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, request: state.request }) });
      state.preview = result;
      $("#impact-preview").hidden = false;
      $("#impact-preview").innerHTML = `<strong>将返回 ${esc(result.earliest_affected_gate || "上一阶段")}</strong><p>失效阶段：${esc((result.stale_gates || []).join("、") || "无")}</p><p>${esc(result.business_explanation || result.impact_explanation || "")}</p>`;
      document.querySelector('[data-confirm]').disabled = false;
    } catch (error) { toast(error.message); }
  }

  async function confirmChange() {
    if (!state.preview || !state.request) return;
    try {
      const result = await api(`/gates/${state.workspace.current_gate}/changes`, { method: "POST", body: JSON.stringify({ session_id: state.session.session_id, request: state.request, preview_hash: state.preview.preview_hash, idempotency_key: crypto.randomUUID() }) });
      toast(`修改已提交 · ${result.job_id || "处理中"}`);
      $("#change-dialog").close();
    } catch (error) { toast(error.message); }
  }

  $("#play-toggle").addEventListener("click", () => { if (!state.media || !state.media.play) return; if (state.media.paused) state.media.play(); else state.media.pause(); });
  $("#diagnostics-toggle").addEventListener("click", () => { $("#diagnostics").open = !$("#diagnostics").open; });
  $("#detail-close").addEventListener("click", () => { $("#object-detail").hidden = true; state.selected = null; renderRail(); });
  document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.action)));
  $("[data-close]").addEventListener("click", () => $("#change-dialog").close());
  $("[data-preview]").addEventListener("click", previewChange);
  $("[data-confirm]").addEventListener("click", confirmChange);
  $("#change-type").addEventListener("change", renderChangeTargets);
  window.__workbench = { state, selectObject, renderDetail, updatePlayhead, refreshWorkspace, mediaUrl };
  load().catch((error) => { $("#connection-status").textContent = "需要刷新"; toast(error.message); });
})();
