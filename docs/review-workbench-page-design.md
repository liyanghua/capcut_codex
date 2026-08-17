# 审核工作台页面设计

> 状态：设计方向已确认，详细契约待继续评审；审核工作台前置为 G-B 必需运营能力
> 编写日期：2026-08-16
> 目标：给一线运营一个"做决定"的界面，而不只是"看进度"的看板。

---

## 1. 定位与目标

### 1.1 问题

当前人审是端到端时长的绝对瓶颈（`work/2026-08-16-gb-v2-cold` 实测：机器关键路径 ~41s，墙钟 2h50m；其中 Gate 3 选材人工等待 29 分钟、Gate 4 生成前 20 分钟）。两个直接原因：

1. 交给审核人的材料是机器 JSON（`gate_review_packages/gateN.json` 是 `input_hashes`/`sha256`/`broad_ranges` 结构），人不可读，只能在聊天里等 agent 转述；
2. 视觉材料是无标注裸拼图（`gate3_review_contact_sheet.jpg` 只有选中帧，无参考帧对照、无叠字标注、无文案对应、无标签）。

### 1.2 定位

审核工作台 = **决策上下文与受控操作界面**，不是只看进度的看板，也不维护第二套审批状态：

| | 进度看板（已设计） | 审核工作台（本文） |
|---|---|---|
| 回答的问题 | 流程走到哪、卡在哪 | **这个 Gate 我要不要通过、为什么；需要怎么改、改了影响什么** |
| 核心内容 | 阶段轨道、状态、计数 | 单 Gate 决策视图：业务摘要 + 视觉/听觉证据 + 受控修改 + 影响预览 |
| 出口 | 知道状态 | 通过、驳回或带影响确认的结构化修改决定 |

审批权威不变：`pipeline_state.json` 仍是唯一权威。页面不直接写状态文件；通过、驳回和要求修改都调用现有 B0 Approval Service，绑定当前审核包哈希、`run_id`、`state_revision`、操作人和可信服务时间。页面负责把“判断所需的全部上下文”压缩到一屏，并在执行修改前展示最早受影响 Gate、下游失效范围、需重生成产物和预计耗时。

### 1.3 成功标准

- 每个 Gate 的"决策所需时间"有明显目标值（见第 8 节），Gate 3 选材从 29 分钟 → ≤5 分钟；
- 修订轮从"全量重看"变为"只看到变化"（diff 视图），≤2 分钟；
- 运营可以在同一页面直接通过、驳回或提出结构化修改，不再复制话术往返；
- 每个修改在提交前都有可解释的影响预览，结构变化不会被误当成局部修改；
- 页面打不开不阻塞生产（降级 `snapshot.md`）。

---

## 2. 设计原则

1. **一 Gate 一页一决策**：每个 Gate 恰好一个待决问题、一组预置选项和通过、驳回、要求修改三个明确出口。
2. **业务语言优先，工程证据折叠**：正文只有"看/听/选"；哈希、校验明细收进可展开的"技术附录"。
3. **确定性生成**：视图由 Python + ffmpeg 从已批准产物确定性生成，业务文本直接取自 `content_baseline` / `recipe` / 证据矩阵等已批准字段；渲染路径不引入 LLM 临时改写，保证可复现、可哈希。
4. **机器包是合同，人审页是界面**：审批绑定仍只针对机器包哈希；人审页是绑定机器包哈希的派生展示产物。
5. **可操作 + 单一权威**：页面只通过 B0 审批事务和结构化变更事务写入决定，不直接写 `pipeline_state.json`；SSE 只通知快照变化，前端重拉权威快照。
6. **移动端优先**：运营大概率用手机审，布局先保证 390px 宽度可用，再增强桌面。
7. **先看影响再修改**：任何修改先 dry-run，展示最早失效 Gate、下游重做范围、媒体/API 成本和预计耗时，再由运营二次确认。

---

## 3. 页面整体布局（单任务工作台）

```
┌──────────────────────────────────────────────────────────┐
│ 顶部横幅：任务名 · 七步业务阶段高亮 · 当前状态            │
│    [资料准备✓][参考片拆解✓][复刻方案✓][素材匹配●][…]      │
│    状态：待你确认 · Gate 3 选材确认 · 预计审核 5 分钟      │
├──────────────────────────────────────────────────────────┤
│ 决策区（主区，占 70%+ 高度）                               │
│  §4.1 现在到哪（一句话）                                   │
│  §4.2 业务影响（≤3 条）                                    │
│  §4.3 主证据区（随 Gate 切换，见第 5 节视图规格）           │
│  §4.4 只需确认（一个决策问题）                             │
│  §4.5 建议（系统推荐 + 一行理由）                           │
│  §4.6 决策操作（通过 / 驳回 / 要求修改）                   │
├──────────────────────────────────────────────────────────┤
│ 侧栏 / 折叠区                                             │
│  未处理风险（≤3 条，标注"不阻塞本次决策"）                 │
│  修订 diff（仅修订轮显示："自上次批准后只变了 X"）          │
│  修改影响（失效 Gate / 重生成项 / 预计耗时）               │
│  技术附录（哈希、校验明细，默认折叠）                      │
└──────────────────────────────────────────────────────────┘
```

### 3.1 顶部横幅与状态语言

沿用后端设计文档 §8.3 的状态词：`未开始 / 系统处理中 / 待你确认 / 已确认 / 阻塞 / 失败 / 需重新确认`。横幅只显示当前**决策点**（`gate_id` → 业务名 → 预计审核时长），不显示机器 stage 名词。

业务名映射（固定表）：

| gate_id | 业务名 | 决策问题 | 预计审核 |
|---|---|---|---|
| gate1 | 参考片拆解 | 镜头切分是否可接受 | 3 分钟 |
| gate2 | 复刻方案 | 内容基线与变更包是否批准（原子） | 5 分钟 |
| gate3_material_selection | 素材选配 | 每段配的素材画面是否可用 | 5 分钟 |
| gate3_evidence_closure | 证据闭环 | 每句口播是否都有对应画面证据 | 3 分钟 |
| gate4_pre_generation | 文案与声音 | 文案、音色、语速是否批准 | 3 分钟 |
| gate4_post_generation | 配音听审 | 逐句配音是否可用 | 5 分钟 |
| gate5 | 成片终审 | 预览是否通过 | 5 分钟 |

预计审核时长由后端写入（`review_meta.expected_minutes`），实测决策时长记入 `measurement`，形成"预计 vs 实测"反馈环。

---

## 4. 通用组件规格

### 4.1 决策摘要五段式

每个 Gate 视图固定渲染五段，文本由确定性生成器从已批准产物抽取：

- **现在到哪**：一句话（阶段业务名 + 下一步动作）。
- **业务影响**：≤3 条业务语言（如"批准后 11 段素材进入生产范围，精确裁点仍待配音实测后确定"）。不出现哈希/JSON/状态码。
- **只需确认**：一个决策问题（见 §3.1 表）。
- **建议**：系统推荐选项 + 一行理由（如"建议通过：11/11 段有合格候选，最差置信 0.79，叠字均按已批准政策保留"）。
- **决策操作**：通过、驳回、要求修改三个明确出口；要求修改进入结构化表单和影响预览，不依赖自由文本话术完成状态写入。

### 4.2 修订 diff 面板

仅 `需重新确认` 状态显示。对比当前审核包与最近一次该 Gate 的批准记录（`decisions[].input_hashes` + 产物字段 diff），输出两栏：

> **变了**：fragment07 宽范围 [403,451) → [420,468)；文案第 7 句"柔韧" → "铺开后更服帖"。
> **没变**：其余 10 段素材与范围、音色、语速、时长包络。

生成规则：逐字段 JSON diff + 允许的字段别名表；媒体文件以 sha256 判定"同/异"；无法定位到字段的变化显示产物名。目标：修订轮决策时间 ≤2 分钟。

### 4.3 对比帧组件（Gate 1/3 用）

- 布局：`参考帧 ‖ 选中素材帧` 左右并排，上方文字条 `fragment03 · 素材：桌垫65度.jpg · 范围 0.0–60.0s · 置信 0.93`；
- 叠字/水印：素材帧上按 `asset_profiles.overlay_bbox` 画红色框 + 角标"叠字：保留"；无 bbox 时显示"叠字存在（无位置标注）"黄标；
- 缺素材：红色占位卡（fragment + 缺失原因 + 建议动作），不渲染假画面；
- 底部一行横向缩略条可快速跳片段（fragment01…11），当前片段高亮。

### 4.4 音频组件（Gate 4 用）

- 逐句行：`① 餐桌要保护。 [▶ 1.6s]` 点按播放该句 `voice/segment-NN-fragmentNN.mp3`；
- 每行附：实测时长、估算时长、偏差（超 ±0.5s 标黄）、对应字幕文本；
- 顶部"全部连播"按钮（播 `final_voice.mp3`）+ 播放位置与字幕 cue 联动高亮；
- 听审五查清单（开头吞字/边界停顿/最长停顿/最紧字幕/结尾完整性）渲染为勾选行，仅辅助记忆，勾选状态不写回。

### 4.5 视频组件（Gate 5 用）

- 主播放器（`remix.mp4`，Range 流式）；
- 时间轴下方标记 N 个片段边界点，点按跳转到边界前后各 1 秒，边界两侧帧并排小图（来自 `proxy_boundary_report.json` 的 `boundary_frames`）；
- 校验摘要条：分辨率/帧率/流数/时长/字幕侧车，全部 ✅ 才显示"技术校验通过"。

### 4.6 风险清单

来源：审核包 `known_nonblocking_risks` / `blockers`（可重试与需用户区分）。渲染规则：

- `blockers` 且 `requires_user=true` → 红色阻塞卡，顶部置顶，写明恢复动作；
- `blockers` 且 `requires_user=false` → 黄色"系统将重试"卡；
- 非阻塞风险 → 灰条，固定标注"不阻塞本次决策"。

### 4.7 技术附录（默认折叠）

展开后显示：机器包 `input_hashes`、`state_revision`、校验明细、事件序列区间。仅供排查，不参与决策叙事。

### 4.8 受控修改与影响预览

首版允许运营直接提出以下受控修改：

- 文案、声明范围、音色和语速；
- Gate 3 候选素材选择及已批准源素材内的宽范围；
- Gate 4 生成后的指定句重录；
- Gate 5 指定边界、画面或声音问题的返工请求。

删段、并段、重排结构或增加未经批准声明只能生成返回 Gate 2 的结构性变更请求，不能作为局部修改执行。所有修改先生成不可执行的影响预览，至少包含：`earliest_affected_gate`、`stale_gates`、`artifacts_to_regenerate`、`media_actions`、`estimated_machine_seconds`、`requires_tts`、`requires_render` 和业务解释。运营二次确认后才写入结构化变更并触发 Runner。

---

## 5. 七个 Gate 视图规格

每个视图 = 五段式 + 该 Gate 的主证据区。数据来源均为现存产物，字段映射如下。

### 5.1 Gate 1 · 参考片拆解

- **主证据区**：横向时间线条（总时长 + 13 个 shot 色块，色块上标 shot 编号与时长）+ 下方关键帧缩略条（`video_clips/keyframes/shotNNN.jpg`）+ 可疑切点红三角（`gate1` 包 `candidate_cut_points_seconds`）。
- **数据**：`gate_review_packages/gate1.json`（`shot_count`、`candidate_cut_points_seconds`、`input_hashes`）、`recipe.json`、`review_contact_sheet.jpg`。
- **选项**：通过 / 修订切点（输入具体秒数）/ 打回重拆。

### 5.2 Gate 2 · 复刻方案

- **主证据区**：叙事结构表（钩子/卖点/证明/CTA 四行，每行片段数 + 时长预算）+ 变更清单红绿标注（保留=绿、替换=黄、删并=红，来自 `mutation_plan.json`）+ 醒目提示"本 Gate 为原子批准：内容基线与变更包一起生效"。
- **数据**：`content_baseline.json`（`claims`、`fragments[].narration`）、`mutation_plan.json`（`allowed_fallbacks`、变更项）。
- **选项**：通过（原子）/ 修订（指定变更项）/ 打回。

### 5.3 Gate 3 选材确认

- **主证据区**：逐片段"对比帧组件"（§4.3）+ 底部合计条"11/11 有合格候选 · 最差置信 0.79 · 缺素材 0"；整页附 `gate3_review_proxies/` 短代理视频（点按播放该段宽范围）。
- **数据**：`material_selection_candidate.json`（`selections[]`）、`gate3_review_frames/fragmentNN.jpg`、`gate3_review_proxies/fragmentNN.mp4`、`gate3_review_contact_sheet.jpg`、`matches.json`（`confidence`、`score_components`）。
- **选项**：通过 / 替换（指定 fragment + 源文件 + 秒范围）/ 打回 Gate 2（仅结构性问题，页面明确提示此选项会回 Gate 2）。

### 5.4 Gate 3 证据闭环

- **主证据区**：逐句行"口播文案 → 证据帧缩略图 → 动作完整性（✅/⚠️/❌）→ fallback 状态"，无证据句红色置顶。
- **数据**：`script_evidence_matrix.json`（`rows[].voice_text`、`evidence_window`、`closure_decision`、`fallback`）。
- **选项**：通过 / 修订 fallback（指定句）/ 打回 Gate 2（改口播意图）。

### 5.5 Gate 4 生成前

- **主证据区**：全文案（逐句可点选）+ 每句时长估算表（`voice_preflight.json`：字数、标点停顿、估算秒、画面预算、margin，margin<0.2s 标黄）+ 音色卡（音色名/语速 1.0x/试听按钮）。
- **数据**：`production_script_candidate.json`（`lines[]`）、`voice_preflight.json`（`fragments[]`）、`approved_production_script.json`（历史对照）。
- **选项**：通过 / 改文案（指定句）/ 改音色或语速 / 打回。

### 5.6 Gate 4 生成后

- **主证据区**：音频组件（§4.4）+ 字幕对照（`captions.srt` 每条 cue 与句行对齐高亮）+ 实测 vs 估算偏差总览 + 最长停顿标注。
- **数据**：`voice_manifest.json`（`segments[]`）、`reconstruction_timeline.json`（`fragments[].timeline_start/end_seconds`）、`captions.srt`。
- **选项**：通过 / 指定重录句（逐句选择后一键生成"重录 fragment04、09"话术）。

### 5.7 Gate 5 成片终审

- **主证据区**：视频组件（§4.5）+ 边界清单（每边界"时间点 + 两侧帧图 + 状态"）+ 交付包文件卡（remix.mp4 / captions.srt / 导入清单 / 校验报告）。
- **数据**：`remix.mp4`、`proxy_boundary_report.json`、`final_validation_report.json`、`render_report.json`、`jianying_import_manifest.json`。
- **选项**：通过 / 修订（指定边界或画面问题）/ 打回（指定 Gate）。

---

## 6. 决策与修改回路（首版可操作）

```
用户（手机浏览器）
  │ 打开工作台 → 看到当前 Gate 的决策视图
  │ 看完证据 → 通过 / 驳回 / 要求修改
  ▼
B0 Decision Service
  │ 通过/驳回：绑定机器包哈希 + run_id + state_revision + actor
  │ 要求修改：先调用 ChangeImpactAnalyzer 生成 dry-run
  ▼
影响预览
  │ 展示失效 Gate、重生成项、预计耗时和恢复路径
  │ 运营二次确认后提交结构化 change_request
  ▼
pipeline_state.json（唯一审批权威）
  │ SSE 通知变化
  ▼
工作台刷新 → 状态变为"已确认"或"需重新确认（diff 视图）"
```

边界约束：

- 页面不直接写状态文件，不维护第二份 Gate 状态；
- 所有决定必须经过 B0 Approval Service 或受控变更事务，绑定当前审核包和可信服务时间；
- 提交时 revision 或审核包哈希已变化则返回冲突，页面强制刷新并展示 diff，不得静默套用旧决定；
- 本机首版只绑定 `127.0.0.1`，操作人由启动参数指定；不在首版建设账号、多用户协作或远程权限后台；
- 静态 HTML/Markdown 快照和 CLI 决定命令保留为故障降级路径。

---

## 7. 数据契约增量

### 7.1 派生产物 `gate_review_sheet`

新增展示层产物（不进审批绑定）：

```json
{
  "artifact_type": "gate_review_sheet",
  "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-sheet",
  "schema_version": "1.0.0",
  "gate_id": "gate3_material_selection",
  "run_id": "…",
  "state_revision": 21,
  "bound_package_sha256": "…（gateN.json 机器包）",
  "bound_package_path": "gate_review_packages/gate3_material_selection.json",
  "generator_version": "review-sheet-v1",
  "path": "gate_review_packages/gate3_material_selection.review.html",
  "expected_review_minutes": 5,
  "vs_last_approval": { "changed": [], "unchanged": [] }
}
```

生成时机：每个 `build-gateN-package` 成功后追加 `build-gateN-sheet` 阶段（确定性、可缓存，约 +1–2s）。sheet 哈希登记进 `pipeline_state.artifacts`（`status: derived_review_only`）。

### 7.2 `ProgressView` 扩展

在只读投影中追加 `review_context`（仅当存在 `awaiting_user` 的 gate 时非空）：

```json
"review_context": {
  "gate_id": "gate3_material_selection",
  "business_name": "素材选配",
  "decision_question": "每段配的素材画面是否可用？",
  "expected_minutes": 5,
  "sheet_path": "gate_review_packages/gate3_material_selection.review.html",
  "available_actions": ["approve", "reject", "request_changes"],
  "change_form_schema": "gate3_material_selection-change-v1",
  "last_approval_diff": { "changed": [], "unchanged": [] }
}
```

### 7.3 媒体端点契约（补充现有 `artifacts/{id}` 一行）

- `GET /api/v1/runs/{run_id}/artifacts/{artifact_id}`：支持 `Range`（视频/音频流式播放）、`ETag`；
- `GET …/artifacts/{artifact_id}/thumbnail?t=12.4`：帧缩略图（jpeg）；
- 媒体 allowlist：`jpg/png/mp4/mp3/srt/html`，其余 404；路径脱敏、禁止目录浏览。

### 7.4 决策与影响分析端点

首版新增本机操作端点，内部调用现有 B0 服务，不允许浏览器构造任意状态 patch：

- `POST /api/v1/runs/{run_id}/gates/{gate_id}/decisions`：提交通过或驳回；
- `POST /api/v1/runs/{run_id}/gates/{gate_id}/changes/preview`：生成只读影响预览；
- `POST /api/v1/runs/{run_id}/gates/{gate_id}/changes`：二次确认后提交结构化变更；
- `GET /api/v1/runs/{run_id}/review-session`：读取当前审核会话和可信计时。

所有写请求必须携带 `review_package_hash`、`state_revision`、`actor` 和幂等键；服务端从当前任务重算并校验，不信任浏览器提交的影响范围。

### 7.5 审核计时契约

`MeasurementCollector` 使用服务端时间记录：审核页首次打开、首次证据交互、影响预览生成、决定提交、决定接受/冲突和返工完成。浏览器只发送事件意图，不能提交任意耗时数字。输出区分 `human_wait_seconds`、`operator_touch_seconds`、`decision_seconds`、`rework_seconds` 和 `machine_api_critical_path_seconds`，缺失时写 `not_measured` 及原因，不填零。

---

## 8. 验收标准

### 8.1 决策时长目标（写进 G-B 度量）

| Gate | 基线（08-16 冷跑实测人工等待） | 目标 |
|---|---|---|
| gate1 | ~3 分钟 | ≤3 分钟 |
| gate2 | ~2 分钟 | ≤5 分钟（含阅读结构表） |
| gate3 选材 | **29 分钟** | **≤5 分钟** |
| gate3 证据 | ~6 分钟 | ≤3 分钟 |
| gate4 生成前 | **20 分钟** | ≤3 分钟 |
| gate4 生成后 | ~2 分钟 | ≤5 分钟（逐句听） |
| gate5 | 未测 | ≤5 分钟 |
| 修订轮（任意） | 全量重看（10 分钟级） | ≤2 分钟（diff 视图） |

### 8.2 页面验收

- 人工走查六类状态（处理中/待确认/阻塞/失败/stale/完成）以及桌面与 390px 移动端；首版不把 Playwright 视觉回归作为阻塞项；
- 七个 Gate 视图各出一份真实任务快照，人工走查"是否一屏做出决定"；
- 页面不可用时 `snapshot.md` 降级可用，生产不被阻塞；
- sheet 生成确定性：同一机器包哈希两次生成结果字节一致。
- 通过、驳回和修改请求都必须绑定当前审核包哈希、revision 和 actor；过期页面提交返回冲突并强制刷新；
- 影响预览与实际 stale 传播一致，结构变化不得停留在 Gate 3/4 局部修改；
- 本机工作台不可用时，静态快照 + CLI 降级路径仍可完成审核；
- 用一轮新的监督 cold/hot 运行采集七个 Gate 的可信决策时间。

视觉验收记录人工检查表、任务快照路径和未决问题即可；不要求额外录制浏览器自动化视频或截图回归包。

### 8.3 G-B 前置验收边界

审核工作台不再等待 G-B 后实施，而是 G-B 的必需运营能力。G-B owner 复核前必须同时具备：

- 修正后的 cold/hot 测量口径和审批/缓存统计；
- 合法 `phase6_score_snapshot.json`，未实测项不得伪造分数；
- 七个 Gate 均可在工作台完成通过、驳回或要求修改；
- Gate 3/4/5 提供完整视觉、音频和视频证据，Gate 1/2 先提供结构化摘要；
- 新监督 cold/hot 运行全部决定来自工作台，Gate 3 选材 ≤5 分钟、Gate 4 生成前 ≤3 分钟、修订轮 ≤2 分钟；其他 Gate 首轮记录实测，不因单次轻微超时阻断；
- owner 对当前审核包明确批准 G-B，系统不得自批。

G-B 比较口径采用版本化的 V2 前向基线策略：历史 V1 只保留为 `retrospective_baseline`；`measured_baseline_v0` 作为后续 V2 冻结输入回归基线。G-B 不要求伪造无法复现的 V1 cold/hot 对照，但必须由 owner 明确批准该策略，并对后续 V2 的质量、效率和审批安全执行非回退检查。

### 8.4 首版质量范围

审核工作台以 `docs/superpowers/specs/2026-08-16-video-quality-online-feedback-generation-process-design.md` 为业务质量定义来源，首版覆盖：

- L0 硬门禁：合规授权、声明真实性、商品与 Offer 一致性、证据闭环、音画技术质量和生产可追溯性；
- L1 离线内容质量：抓注意力、信息清晰度、卖点与人群匹配、说服与证据强度、节奏与观看体验、品牌与商品一致性；
- P 生成过程：首次通过、缺陷逃逸、返工、机器时间、人工等待和运营触达。

L2 经营质量依赖真实投放后的观看、转化、退款和贡献利润数据。首版只保留 `evaluation_context_id`、`video_version_id` 和后续反馈入口，不在制作阶段预测或伪造 L2，也不把 L2 数据接入作为本轮 G-B 阻塞项。

---

## 9. 实施分期

| 期 | 内容 | 时机 | 收益 |
|---|---|---|---|
| P0a | 修复 G-B 测量口径，生成质量快照；确定性生成七个 Gate 的 review view model 和静态降级快照 | 现在 | 先修复发布证据，同时建立统一展示数据源 |
| P0b | 本机 FastAPI/SSE 操作型工作台；七 Gate 均可决策，Gate 3/4/5 完整证据，受控修改和影响预览 | G-B 前 | 直接解决决策质量与效率瓶颈 |
| P0c | 新监督 cold/hot 全流程，采集可信审核计时并形成 owner G-B 复核包 | P0b 后 | 用真实运营行为完成 G-B，而非只验证机器链路 |
| P1 | 小范围监督运营试用、异常恢复演练和 `2.0.0-rc.1` 发布准备 | G-B owner 批准后 | 为普通 V2 production 解锁提供运营证据 |
| P2 | 企业身份、多用户协作、远程部署和更完整 Track C 看板 | 监督试用后 | 扩大运营规模，不阻塞首版 |

---

## 10. 已确认决策与待细化项

已确认：

1. 以本文现有的一 Gate 一页、业务语言优先、证据可视化和修订 diff 为设计基线；
2. 首版工作台可以直接通过、驳回或要求修改，但只通过 B0 审批/变更事务写入；
3. 七个 Gate 都可操作，Gate 3/4/5 先达到完整证据深度，Gate 1/2 先做结构化摘要；
4. 审核工作台前置为 G-B 必需能力，并用新监督 cold/hot 验收关键决策时长；
5. 首版为 `127.0.0.1` 本机单运营模式，不建设账号和多人协作；
6. 采用“本地操作型工作台 + 静态快照降级”路线，不建设完整多用户平台。
7. G-B 采用 `measured_baseline_v0` 的 V2 前向回归口径，V1 仅作历史回溯背景；
8. 首版质量范围为 L0 + L1 + P，L2 只保留投放后反馈接口。

待继续细化：质量评分 rubric 和 owner 复核包、结构化 change request 字段、各 Gate 影响规则、错误恢复、测试矩阵和实施拆分。
