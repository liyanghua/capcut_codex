# G-B 测量、质量快照与操作型审核工作台设计

> 状态：P0b 本机审核工作台已实现；G-B 真实回归、owner 复核和人工视口验收仍待执行
>
> 日期：2026-08-17
>
> 适用版本：`remix-reference-video 2.0.0-alpha.1` 到 `2.0.0-rc.1`
>
> 页面细节基线：`docs/review-workbench-page-design.md`
>
> 质量定义来源：`docs/superpowers/specs/2026-08-16-video-quality-online-feedback-generation-process-design.md`

## 1. 决策与目标

当前 Native Runner 已完成真实 cold/hot Gate 1-5、真实 TTS、FFmpeg 渲染和 production audit，但 G-B 仍为 `measured_pending_review`。阻塞不在媒体内核，而在三类发布证据：

1. `approvals_recorded`、缓存命中和人工审核耗时口径不完整；
2. 没有合法的五阶段 `phase6_score_snapshot.json`；
3. 审核内容偏工程化，运营无法快速判断是否通过、如何修改以及修改后的影响。

本设计把审核工作台前置为 G-B 必需能力，并将以下目标作为同一条发布主线：

- 修复 G-B cold/hot 测量口径；
- 生成可审计的生产质量、内容质量和过程评价快照；
- 提供本机单运营、可直接审批和受控修改的审核工作台；
- 用新的监督 cold/hot 运行采集可信审核时间；
- 形成 owner 可明确批准或拒绝的 G-B 复核包。

P0b 的业务工作台投影、关键产物抽屉、增量刷新和 hash-bound 修改预览已实现；创意质量升级在 [08-19 设计](2026-08-19-reference-remix-creative-quality-upgrade-design.md) 之上增加策略/脚本候选与分镜诊断，不新增审核事件类型。审核计时继续采用本文件定义的 `review.active_start`、`review.active_stop`、`review.heartbeat`、`review.pause`、`review.evidence_interaction` 与 `review.decision_accepted` 区间模型。

系统不得自行批准 G-B。普通 V2 production、共享生产缓存和归档继续保持锁定，直到 G-B owner 批准且后续监督运营试用通过。

## 2. 范围

### 2.1 首版包含

- 七个 Gate 的业务化审核视图；
- Gate 3/4/5 的完整图片、音频、视频证据；
- Gate 1/2 的结构化摘要、时间线、声明和变更对照；
- 页面内通过、驳回、要求修改；
- 修改 dry-run、影响预览、二次确认和 stale 传播；
- cold/hot 审批、缓存、机器时间、审核时间和返工统计；
- Track-B `phase6_score_snapshot.json` 五阶段生产质量投影；Track C `quality_scorecard.json` 在 G-B 通过后才启用；
- L0 硬门禁、L1 六维离线内容质量和 P 过程评价；
- G-B owner 复核包和明确决定；
- 静态 HTML/Markdown + CLI 故障降级路径。

### 2.2 首版不包含

- 多用户账号、远程部署、企业权限和协同审核；
- 页面直接修改 `pipeline_state.json`；
- 自动批准 Gate、G-B 或发布；
- 自动改写脚本、素材、声音或质量策略；
- L2 线上经营结果计算和投放自动化；
- 完整 Track C 经营看板；
- Playwright 视觉回归、浏览器录像或截图回归包。

## 3. 发布与比较口径

### 3.1 V2 前向基线

历史 V1 不具备同一冻结输入下可重复执行的 cold/hot 数据。G-B 使用版本化的 `v2_forward_baseline_v1` policy：

- 历史 V1 只标记为 `retrospective_baseline`；
- `measured_baseline_v0` 是后续 V2 前向回归基线；
- 不生成或推断伪造的 V1 可比指标；
- 后续比较必须冻结参考片、Brief、素材快照、TTS 设置和输出规格；
- cold 从空缓存开始，hot 只能复制声明的 cold 技术缓存；
- cold/hot 使用不同 `run_id`、审核包、决定记录和输出目录；
- 质量、效率和审批安全均不得相对当前已批准 V2 基线回退。

该 policy 必须进入 G-B owner 复核包并由 owner 明确批准。实现时 `Phase6Snapshot.build` 必须接受 `baseline_comparison` policy 对象；当 `require_v1_comparability=false` 且没有 V1 数据时，不能抛出“V1 comparability required”，而应按 15.2 生成 `not_evaluated` 结果。

### 3.2 G-B 必需证据

G-B 复核前必须具备：

- cold `machine_api_critical_path_seconds <= 780`；
- hot `machine_api_critical_path_seconds <= 480`；
- 五阶段生产质量分均不低于 88；
- `video_quality_score >= 88`，91 为目标值；
- canonical 七个 Gate 全部独立批准：`gate1`、`gate2`、`gate3_material_selection`、`gate3_evidence_closure`、`gate4_pre_generation`、`gate4_post_generation`、`gate5`；`gate3`/`gate4` 仅由子状态派生；
- 无审批复用、范围越界、未登记生产输入和越权归档；
- 新监督 cold/hot 的七个 canonical Gate 决定全部来自工作台；CLI 只用于工作台故障演练，该 run 不计入 G-B qualification；
- Gate 3 选材 `decision_seconds <= 300`；
- Gate 4 生成前 `decision_seconds <= 180`；
- 修订轮 `decision_seconds <= 120`；
- 其他 Gate 首轮记录实测，单次轻微超时不自动阻断；
- owner 明确记录 `approved` 或 `rejected`，并绑定 policy、package hash、snapshot hash、actor 和可信服务时间。

## 4. 质量模型

### 4.1 三个相互独立的制作期视角

工作台首版覆盖：

1. **L0 硬门禁**：合规授权、声明真实性、商品与 Offer 一致性、证据闭环、音画技术质量、生产可追溯性；
2. **L1 离线内容质量**：抓注意力、信息清晰度、卖点与人群匹配、说服与证据强度、节奏与观看体验、品牌与商品一致性；
3. **P 生成过程**：首次通过、缺陷逃逸、返工、机器时间、人工等待、运营触达和成本数据完整性。

L2 依赖真实投放后的观看、转化、退款和贡献利润。首版只保留 `evaluation_context_id`、`video_version_id` 和反馈入口，不预测、不伪造 L2，也不把 L2 接入作为本轮 G-B 阻塞项。

L0 必需输入包括落地页快照、结构化人群定义、素材授权和声明事实。任一缺失固定为 L0 `fail`，不得用 `not_scored` 跳过；`not_scored` 只适用于 L1 或 Track-B rubric 的观察证据不足。

### 4.2 Track C 与 L1 不混用

- `phase6_score_snapshot.json` 是 G-B 阶段的最小 Track-B 五阶段质量投影；
- `quality_scorecard.json` 是 G-B 通过后才启用的 Track-C 五阶段质量权威，不属于本轮 G-B 批准产物；
- `content_quality_profile.json` 是 L1 六维内容质量权威；
- `process_assessment.json` 是 P 过程评价权威；
- 候选匹配置信度、技术校验结果或线上指标不得替代上述任一分数；
- Gate 5 生产批准不自动表示 L1 合格；
- L1 结论不修改现有 Gate 批准。

### 4.3 Gate 到质量维度的映射

| Gate | 主要质量判断 |
| --- | --- |
| Gate 1 | 钩子、镜头功能、参考节奏识别 |
| Gate 2 | 人群、卖点、Offer、CTA、品牌语气、声明边界 |
| Gate 3 选材 | 授权、商品一致性、动作完整性、画面证明力 |
| Gate 3 证据 | 逐句声明真实性、证据闭环和 fallback |
| Gate 4 生成前 | 文案清晰度、信息密度、音色、语速、画面预算 |
| Gate 4 生成后 | 发音、停顿、字幕边界、句尾完整性和听感 |
| Gate 5 | 完整 L0 结论、L1 六维画像、生产批准和返工入口 |

每个质量项必须分别显示机器事实、运营判断、改进建议和修改影响。机器可以生成事实和候选建议，不能代替运营评分或批准。

### 4.4 评分产物

Track-B `phase6_score_snapshot.json` 每个阶段至少记录：

- `framework_stage_id`；
- `rubric_items[].earned_points`；
- `rubric_items[].max_points`；
- `rubric_items[].evidence_paths`；
- `rubric_items[].reason`；
- `stage_output_quality_score`；
- `measurement_status` 与 `approval_status`。

只有全部 rubric 项有当前证据时才计算阶段分。缺项写 `not_scored`，不得填目标分。G-B 前不生成或宣称 Track-C `quality_scorecard.json` 已激活。

`content_quality_profile.json` 每个 L1 维度至少记录：

- `rating`，取 1-5；
- `weight`；
- `observable_evidence`，包含路径和时间点；
- `issues`；
- `recommended_actions`；
- `reviewer_id` 与可信时间；
- `calibration_status`。

首版允许 owner 独立评分用于当前视频改版，但标记 `calibration_status=provisional`。用于跨视频排序或发布正式场景合格线前，必须完成双人独立评分、分歧复核和信度校准。

## 5. 系统架构

### 5.1 ReviewViewBuilder

职责：把当前 Gate 机器包和已登记产物转换为确定性业务视图。

输入：审核包、`pipeline_state.json` 当前投影、Gate 对应业务产物、最近一次有效决定。

输出：`gate_review_view.json`、静态 `review.html` 和 `snapshot.md`。

边界：只读；不决定 Gate，不写业务产物，不调用 LLM 生成临时事实。

### 5.2 Workbench API

职责：在 `127.0.0.1` 提供任务快照、媒体、决策和变更入口。

输入：任务根目录和启动时指定的本机 `actor`；请求体中的 actor 只作为显示字段，服务端必须覆盖为启动身份。

输出：JSON/SSE、Range 媒体流和结构化命令结果。

边界：不维护第二套状态；所有写操作委托给 Approval Service 或 Change Service。

### 5.3 DecisionService

职责：提交通过或驳回。

必需输入：`review_identity`、canonical `gate_id`、`review_package_hash`、`state_revision`、B0 原生 `scope_type`、`scope_ids`、`strategy`、`decision`、幂等键和可选备注。B0 `scope_type` 只允许 `artifact_set`、`fragment_set`、`script_settings`、`output_bundle`；工作台展示层的 material/content/evidence 名称必须在 adapter 中转换为这四类，不得写入未知 scope。UI `request_changes` 映射为 B0 的 `changes_requested`；UI `approve/reject` 映射为 `approved/rejected`。

行为：服务端重新读取当前审核包、重算哈希、验证 predecessor 和 revision，再调用现有 B0 Approval Service。

冲突：返回当前 revision、变化摘要和新审核页地址，不应用旧决定。

### 5.4 ChangeImpactAnalyzer

职责：对结构化修改请求做只读 dry-run。

输出至少包含：

- `earliest_affected_gate`；
- `stale_gates`；
- `artifacts_to_regenerate`；
- `media_actions`；
- `requires_tts`；
- `requires_render`；
- `estimated_machine_seconds`；
- `quality_dimensions_affected`；
- `business_explanation`；
- `recovery_path`。

`estimated_machine_seconds` 只能从相同 `policy_version`、runtime profile 和受影响 `execution_stage_id` 的成功 `stage_metrics.jsonl` 历史计算：优先使用最近 20 次的 P50，并同时展示 P90 与样本量；不足 3 个可比样本时写 `not_measured`，不得用目标 SLA 或人工常数伪装成实测估算。

服务端根据当前状态和固定影响规则计算，不信任浏览器提交的影响范围。

### 5.5 ChangeService

职责：在运营二次确认后执行受控修改事务。

输入：当前 review identity、结构化 change request、已展示影响预览哈希、actor 和幂等键。

行为：验证预览仍有效，在 staging 写入修改，校验成功后原子提升并传播 stale；事务提交后写 `change.applied`，由 Workbench Orchestrator 异步调用 `ProductionRunner.run(resume=true)` 从 DAG 中最早 ready/stale 节点恢复，并返回 `job_id`。修改事务失败时保留原批准产物；Runner 失败时保留已提交修改和 stale 状态，写入可重试恢复命令，不回滚已审计的修改事务。

### 5.6 MeasurementCollector

职责：记录可信审核和过程事件，生成 `process_assessment.json`。

事件统一使用 `TaskStorage.append_event` 生成的可信 `occurred_at`，canonical 名称至少包含：

- `review.opened`；
- `review.active_start`；
- `review.evidence_interaction`；
- `review.active_stop`；
- `review.heartbeat`；
- `review.pause`；
- `review.change_previewed`；
- `review.decision_submitted`；
- `review.decision_accepted`；
- `review.decision_conflicted`；
- `review.rework_completed`。

“首次证据交互”是同一 review session 中最早的 `review.evidence_interaction` 聚合结果，不另设 `review.evidence_first_interaction` 事件。

浏览器只能提交事件意图，不能提交任意秒数。

### 5.7 GBOwnerReviewBuilder

职责：从冻结证据生成 `g_b_owner_review_package.json`。

输入：baseline policy、cold/hot measurement、两侧 audit、质量快照、过程评价、工作台验收记录和所有输入哈希。

输出：阈值逐项结果、阻塞项、未测量项、建议和 owner 决定契约。

边界：只能生成待审包，不能写 owner 批准；owner 决定由独立的 `GBOwnerDecisionService` 记录。

## 6. 审核工作台交互

### 6.1 通用结构

首屏直接进入当前待审 Gate：

- 顶部：任务、七步进度、当前 Gate、预计与已用审核时间；
- 主区：当前 Gate 的核心视觉或听觉证据；
- 侧栏/移动端抽屉：L0/L1 影响、风险、修改建议和影响预览；
- 底部固定操作栏：通过、要求修改、驳回；
- 技术哈希和 JSON 只放在折叠附录。

修订轮默认只展示变化和未变化摘要，用户可切换完整证据。

### 6.2 证据深度

- Gate 1/2：结构化摘要、时间线、声明、叙事和变更对照；
- Gate 3：参考帧与候选并排、短代理、叠字标注和逐句证据；
- Gate 4：文案预算、音色试听、逐句播放、字幕联动和停顿风险；
- Gate 5：完整视频、边界跳转、L0、L1 和返工入口；
- G-B 页：测量、质量快照、阻塞项和 owner 决定。

Gate 4 生成前的音色试听只能读取冻结的非生产样本库，样本按 provider、speaker、model label 和文件 SHA-256 登记；不得使用当前候选文案提前调用真实 TTS。样本缺失时显示“试听不可用”，不生成临时生产语音。

### 6.3 修改指导卡

每个问题显示：

1. 观察到什么；
2. 为什么影响质量；
3. 一个推荐动作和最多两个备选动作；
4. 从哪个 Gate、哪个字段修改；
5. 修改会失效什么、重生成什么、预计多久；
6. 修改完成后如何验收。

AI 可以提出候选建议，但建议必须标记来源，且不能自行执行或批准。

## 7. 受控修改边界

首版允许：

- 文案、已批准声明范围、音色和语速；
- Gate 3 候选素材和已批准源范围内的宽范围；
- Gate 4 指定句重录；
- Gate 5 指定边界、画面或声音返工请求。

以下变化必须返回 Gate 2：删段、并段、重排结构、增加未经批准声明、改变人群/Offer/CTA 意图。

固定影响规则：

- 改切点或参考结构：Gate 1 及下游；
- 改人群、卖点、声明、结构或 CTA：Gate 2 及下游；
- 换素材、宽范围或叠字：受影响 Gate 3 子状态及下游；
- 同一批准文案重录：Gate 4 生成后和 Gate 5；
- 改文案、音色或语速：Gate 4 生成前及下游；新增声明返回 Gate 2；
- Gate 5 问题：按根因返回最早可修复 Gate。

变更到产物和状态的最小映射：

| change_type | 主要产物 | stale 状态 | Runner action |
| --- | --- | --- | --- |
| `copy` | `production_script_candidate`、`voice_preflight` | `gate4_pre_generation`、`gate4_post_generation`、`gate5` | 重新编译脚本并预检 |
| `claim_scope` | `content_baseline`、`mutation_plan` | Gate 2 及全部下游 | 返回 Gate 2 重新批准 |
| `voice` | `approved_production_script`、`voice/*`、timeline、SRT | Gate 4 生成前及下游 | 重新预检并 TTS |
| `material`/`range` | `fragment_plan`、material manifest、evidence matrix | 受影响 Gate 3 子状态及下游 | 重新物化、证据闭环 |
| `rerecord` | 指定 voice segment、duration report、timeline、SRT | Gate 4 生成后、Gate 5 | 指定句 TTS、重建时间轴 |
| `boundary` | proxy boundary、render reports、final validation | Gate 5 | 重新代理/渲染校验 |
| `structural` | `content_baseline`、`mutation_plan` | Gate 2 及全部下游 | 只生成 Gate 2 change request |

Gate 3 `request_omit`、`request_merge`、`request_restructure` 只记录请求，不直接执行结构变化。所有 aggregate Gate 状态由两个子状态重新计算。

## 8. 测量口径修复

### 8.1 审批

`approvals_recorded` 必须从整个 run 的有效决定记录统计，而不是只统计最后一次 resume 的新增决定。新决定记录必须直接写入 `run_id`；统计按 `decision_id` 去重，校验每条记录的 `run_id`、Gate、审核包哈希和 revision。迁移前的旧决定若缺少 `run_id`，只允许从承载它的 `pipeline_state.run_id` 派生，并在测量结果标记 `run_id_source=derived_legacy`；新记录不得使用派生路径。cold/hot 决定 ID 交集必须为空。

### 8.2 缓存

缓存至少按每个 execution stage 拆成：

- `snapshot_seeded`：是否复制经声明的 cold 快照；
- `lookup_hits` / `lookup_misses`：索引查询结果；
- `asset_records_reused`：复用的技术画像条目数；
- `stage_execution_skipped`：是否因完整缓存跳过阶段；
- `index_reuse_seconds_saved`：相对冻结基线的索引耗时差。

每个 stage 记录 `cache_source`、`lookup_hit_count`、`lookup_miss_count`、`reused_record_count`、`skipped`、`started_at`、`ended_at` 和 `evidence_paths`。汇总字段只能由这些 stage facts 计算。

不得用 `snapshot_seeded=true` 推断所有阶段 cache hit，也不得把阶段执行成功统一写成 miss。

### 8.3 时间

分别记录并按 session、Gate、stage 聚合：

- `machine_api_critical_path_seconds`；
- `human_wait_seconds`；
- `operator_touch_seconds`；
- `decision_seconds`；
- `rework_seconds`；
- `retry_network_seconds`；
- `gate_return_count`。

`decision_seconds = decision_accepted.occurred_at - first(evidence_interaction.occurred_at)`；`operator_touch_seconds` 是证据交互到决定提交之间的 active interaction 区间总和；`human_wait_seconds` 是审核包生成到首次证据交互的等待；`rework_seconds` 是结构化变更接受到下游重新达到当前 Gate 的机器与人工周期，不包含原始审核时间。页面失去连接、关闭或无心跳超过 60 秒时结束 session 并写 `paused`，恢复后创建新 session；未闭合事件写 `incomplete/not_measured`，不得估算。重试和 Gate 返回按 `occurred_at` 和 run_id 去重。

## 9. 产物与 API 契约

### 9.1 共同快照 envelope

以下产物均为 V2 immutable snapshot，必须包含共同字段：

```json
{
  "artifact_type": "...",
  "schema_id": "urn:capcut:remix-reference-video:artifact:...",
  "schema_version": "1.0.0",
  "contract_version": "2.0.0-alpha.1",
  "skill_version": "2.0.0-alpha.1",
  "snapshot_id": "uuid",
  "run_id": "...",
  "state_revision": 63,
  "input_hashes": {},
  "policy_id": "...",
  "policy_version": "...",
  "source_versions": {},
  "event_time": "trusted-service-time",
  "processed_at": "trusted-service-time",
  "idempotency_key": "...",
  "lifecycle_status": "ready|measured|provisional|incomplete|not_scored|not_measured|stale|building|ready_for_owner|approved|rejected|derived_review_only",
  "supersedes_snapshot_id": null
}
```

共同 `lifecycle_status` 只表示 artifact 生命周期，不表示质量测量、审批或过程效率是否完成。质量/过程类 artifact 必须另外提供 `measurement_status`，需要审批时提供 `approval_status`，涉及效率时提供 `efficiency_measurement_status`；三者不得互相推断，也不得用共同 `lifecycle_status` 代替。每个 `artifact_type` 的字段、类型、允许状态和完整 `schema_id` 必须在 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json` 注册。`phase6_score_snapshot`、`content_quality_profile`、`process_assessment`、`gate_review_view`、`g_b_owner_review_package` 和 `g_b_owner_decision` 必须登记到 canonical registry；历史快照不可覆盖，修订通过新 `snapshot_id` 和 `supersedes_snapshot_id` 产生。任一单元失败可以生成 `incomplete` 快照，但不得伪造其他单元的结果。

`g_b_frozen_input_snapshot.json` 是 G-B 输入根的必需产物，至少绑定唯一 `reference-*.mp4`、`project_brief.json`、`asset_profiles.json`、源素材清单、代码/runtime/TTS/FFmpeg 版本和各自 SHA-256。owner review package 必须包含该 snapshot 的 SHA-256，并绑定 cold/hot 的 `run_id` 与 task root。

### 9.2 质量与过程快照字段

`phase6_score_snapshot.json` 仅用于 G-B：包含五阶段 `rubric_items[]`、总分、机器关键路径、可测人工/返工/返回指标、cache stage facts、baseline comparison result、`g_b_thresholds_met` 和 `owner_g_b_approval_required=true`。每个 rubric item 至少有 `rubric_id`、`earned_points`、`max_points`、`evidence_paths` 和 `reason`；缺证据的阶段为 `not_scored`，不得填目标分。当 V1 comparability 不可用时，`rework_seconds`/`gate_return_count` 的 comparison 状态为 `not_evaluated`，不填零、不伪造 V1；`v2_forward_baseline_v1` 只比较已批准 V2 基线。`baseline_status` 固定取 `establishing|established|invalid`：首个合法 V2 cold/hot 配对为 `establishing`，后续冻结同一 policy 的配对才可成为 `established`，输入或 policy 漂移则为 `invalid`。`establishing` 时只比较适用硬门禁；`not_evaluated` 指标必须列入 `thresholds_not_evaluated`。`g_b_thresholds_met` 只由快照时已存在的机器事实和 policy 决定：policy 明确允许该项未评估时可为 true，同时写 `owner_acknowledgement_required=true`；owner 是否确认只在后续 owner decision projection 中判断，不回写 immutable snapshot。

`process_assessment.json` 另外记录 `first_pass_rate`、`defect_escape_rate`、`operator_touch_seconds`、`human_wait_seconds`、`rework_seconds`、`gate_return_count`、`cost_status`、`cost_inputs` 和各指标的 `measurement_status`。缺少来源写 `not_measured` 及原因。

`first_pass_rate = 首次提交即获当前 Gate 最终批准的任务数 / 首次提交任务总数`；`defect_escape_rate = 下游首次发现且根因可归责当前阶段的缺陷数 / 当前阶段最终批准产物数`。`cost_status=not_measured` 时不填零，`cost_inputs` 必须列出模型、TTS、渲染、人工、补素材和重试来源。

`content_quality_profile.json` 的 L1 `calibration_status=provisional` 只允许当前视频改版和人工复核，不允许跨视频排序、正式合格线或 G-B 通过结论。它在 G-B owner package 中仅作为 informational/advisory 输入；缺失或 provisional 不阻断 G-B，但不得被引用为 G-B 质量门禁依据。G-B 的五阶段质量门禁只读取 `phase6_score_snapshot` 中证据完整且非 `not_scored` 的 rubric 分数。

### 9.3 决策请求

```json
{
  "review_identity": {"session_id": "uuid"},
  "decision": "approved|rejected|changes_requested",
  "scope_type": "artifact_set|fragment_set|script_settings|output_bundle",
  "scope_ids": ["..."],
  "strategy": {},
  "note": "...",
  "review_package_hash": "sha256",
  "state_revision": 63,
  "idempotency_key": "uuid"
}
```

服务端从启动配置绑定 actor，不接受浏览器伪造 actor。浏览器只提交 opaque `session_id`，服务端从当前 session 派生完整 `review_identity`（run、task、gate、package hash、revision）；请求中的其他 identity 字段若存在必须与服务端投影完全一致。相同幂等键和相同 payload 返回原决定；相同幂等键但 payload 不同返回 `409 idempotency_conflict`。UI 的 `request_changes` 只在展示层使用，写入时统一为 `changes_requested`。

### 9.4 Change request

```json
{
  "change_type": "copy|claim_scope|voice|material|range|rerecord|boundary|structural",
  "scope_ids": ["fragment04", "line02"],
  "payload": "按 change_type 绑定的对象",
  "reason": "业务原因",
  "preview_hash": "sha256",
  "review_package_hash": "sha256",
  "state_revision": 63,
  "idempotency_key": "uuid"
}
```

允许字段白名单与验证约束：

- `copy`：Gate 4 candidate lines；声明新增或意图变化升级为 `structural` 返回 Gate 2；
- `claim_scope`：Gate 2 已批准 claim IDs 的子集；
- `voice`：批准的 provider/speaker/speed 范围；
- `material`：Gate 3 候选 ID、SHA 和 overlay decision；
- `range`：Gate 3 已批准 broad range 内的起止；
- `rerecord`：Gate 4 已批准文本的 fragment/line ID；
- `boundary`：Gate 5 boundary ID 和问题类型；
- `structural`：只能生成 Gate 2 change request，不直接执行。

`copy` 的 `text_by_id` 只能覆盖当前脚本已有行；新增声明、改变口播意图或改变片段数量必须改写为 `structural` 并返回 Gate 2。`voice.speed` 为倍速数值且必须落在已批准范围；`range` 的单位为秒，要求 `0 <= start_seconds < end_seconds` 且完全包含于 Gate 3 broad range；`overlay_decision` wire 值直接使用 Gate 3 后端枚举 `retain_source_text|crop|cover|replace|no_action`。UI 仅把它们显示为“保留源文字/裁切/遮盖/替换/无需处理”，不得提交 `keep` 等展示别名。每种 change type 都必须有对应 schema 文件和 registry 条目，preview 与 execute 共用同一 validator；预览 hash 由服务端对规范化 payload、当前 package hash 和 state revision 计算，浏览器不得自带影响范围或 stale 列表。hash 过期、revision 变化、字段越权或 payload 无法验证时返回 `409`，不执行。

### 9.5 Owner G-B decision

`g_b_owner_decision.json` 是独立 immutable artifact，字段至少包含：`decision=approved|rejected`、`package_sha256`、`policy_id/version`、`input_snapshot_sha256`、`measurement_snapshot_ids`、`actor`、`trusted_service_time`、`state_revision`、`idempotency_key`、`acknowledge_not_evaluated`、`rejection_reasons`、`recovery_actions` 和 `status`。写入入口为 `g-b-owner-approve`/`g-b-owner-reject` CLI 或对应本机 API；actor 必须与 owner 启动身份匹配，不能由页面 body 覆盖。只有 package status 为 `ready_for_owner` 且所有硬门禁满足时才允许 approved；rejected 必须保留原因和恢复动作。

owner review package 状态为 `building -> ready_for_owner -> approved|rejected|stale`。package 任何输入 hash、policy version、run_id 或 measurement snapshot 变化都使其 stale；stale package 不可提交决定。owner approved 只推进 G-B evidence state，不直接修改普通 V2 production lock；解锁仍需后续发布事务。

### 9.6 API path and media boundary

现有 `/tasks/{task_id}` 是内部任务投影；新 `/runs/{run_id}` 先通过权威 `run_id -> task_dir` registry 解析，再复用同一 allowlist。允许的 artifact ID 只包括当前 Gate 登记的 review sheet、approved evidence、jpg/png/mp4/mp3/srt/report 文件；禁止目录遍历、符号链接逃逸和任意路径。Range 不满足时返回 `416`，artifact 不在 allowlist 返回 `404`，revision/hash 冲突返回 `409`，SSE 断线后使用 `Last-Event-ID` 重拉快照，不在客户端重放状态机。

## 10. API 契约

首版本机端点：

- `GET /api/v1/runs/{run_id}`；
- `GET /api/v1/runs/{run_id}/events`；
- `GET /api/v1/runs/{run_id}/review`；
- `GET /api/v1/runs/{run_id}/review-session`；
- `GET /api/v1/runs/{run_id}/artifacts/{artifact_id}`，支持 ETag/Range；
- `GET /api/v1/runs/{run_id}/artifacts/{artifact_id}/thumbnail?t=`；
- `POST /api/v1/runs/{run_id}/gates/{gate_id}/decisions`；
- `POST /api/v1/runs/{run_id}/gates/{gate_id}/changes/preview`；
- `POST /api/v1/runs/{run_id}/gates/{gate_id}/changes`。
- `POST /api/v1/g-b/reviews/{package_sha256}/owner-decision`。

写请求必须带 opaque `session_id` 和幂等键；actor、run、task、package hash、revision 由服务端从 session 和当前权威快照绑定，浏览器提交的同名字段不得作为可信来源。API 仅绑定 `127.0.0.1`，路径使用 allowlist 和 containment 校验，不提供目录浏览或任意文件读取。

## 11. 错误与恢复

- revision/hash 冲突：拒绝写入，刷新当前快照并展示 diff；
- 影响预览过期：拒绝执行，重新 dry-run；
- 修改校验失败：丢弃 staging，保留当前批准产物和状态；
- TTS/渲染失败：保留有效上游，记录可重试恢复命令；
- 媒体缺失或路径逃逸：阻塞当前操作并登记安全错误；
- 工作台/API 不可用：允许静态快照 + CLI 完成故障恢复演练，但该 run 明确标记 `workbench_qualification=excluded`，不计入 G-B；
- 缺少 L0 必需输入（落地页快照、结构化人群定义、素材授权、声明事实）：对应 L0 检查固定为 `fail`，必须返回最早受影响 Gate；缺少 L1 或 Track-B rubric 观察证据才可标记 `not_scored`，两者不可互换；
- owner 复核包存在阻塞项：不显示可提交的 G-B approved 决定。

## 12. 验收

### 12.1 自动化契约验收

- 审批统计覆盖完整 run，resume 不重复；
- cold/hot 决定无交集；
- 缓存分类与阶段事实一致；
- 时间缺失不填零；
- 五阶段评分缺证据时拒绝计算；
- 七个 Gate 视图对同一输入确定性生成；
- 决策绑定 hash/revision/actor；
- 过期页面提交冲突；
- 影响预览与实际 stale 传播一致；
- L0、L1、Track C、P 和 L2 不互相覆盖；
- API 保持路径、媒体和本机边界。

### 12.2 人工浏览器验收

使用真实任务逐项检查：

- 六类状态：处理中、待确认、阻塞、失败、stale、完成；
- 七个 Gate 是否能在一屏形成有效决定；
- 桌面与 390px 手机布局；
- 图片、短代理、音频、字幕联动和最终视频；
- 通过、驳回、修改、影响预览和冲突刷新；
- 静态快照 + CLI 降级路径。

首版不要求 Playwright 视觉回归、浏览器录像或截图回归包。人工验收保存检查表、真实任务路径和未决问题。

### 12.3 监督 G-B 运行

- 创建新的 cold/hot run，不复用现有审批；
- 全部 Gate 从工作台决定；
- 采集可信审核事件和关键决策时长；
- 两侧 production audit 通过；
- 生成质量、内容和过程评价；
- 生成 owner G-B 复核包；
- owner 明确记录最终决定。

## 13. 实施与发布顺序

1. P0a：修复测量口径、baseline policy、评分契约和 review view model；
2. P0b：本机操作型工作台、媒体端点、决策、影响预览和变更事务；
3. P0c：新监督 cold/hot、人工浏览器验收和 owner G-B 复核；
4. G-B approved 后晋级 `2.0.0-rc.1`；
5. 执行小范围监督运营试用和异常恢复演练；
6. 试用通过后再单独批准普通 V2 production、共享缓存和归档；
7. 多用户、远程部署、L2 经营闭环和完整 Track C 看板后置。

## 14. 已确认决策

- 采用本地操作型工作台，不采用只读话术页或完整多用户平台；
- 页面可直接通过、驳回和要求修改，但不直接写状态；
- 修改前必须展示影响并二次确认；
- 七个 Gate 均可操作，Gate 3/4/5 优先完整证据；
- 工作台前置为 G-B 必需能力；
- 首版只绑定本机单运营身份；
- G-B 采用 V2 前向基线，V1 只作回溯背景；
- 首版质量范围是 L0 + L1 + P，L2 只留反馈入口；
- Gate 5 生产决定与离线质量决定分开；
- 浏览器使用人工验收，不把 Playwright 视觉回归作为阻塞项。

## 15. 规范化产物与运行契约

### 15.1 artifact registry

本设计新增或明确以下 artifact registry 条目；每项都使用 9.1 共同 envelope：

| artifact_type | schema_id suffix | required status |
| --- | --- | --- |
| `phase6_score_snapshot` | `urn:capcut:remix-reference-video:artifact:phase6-score-snapshot` / `schemas/phase6-score-snapshot.schema.json` | `measured|incomplete|provisional` |
| `quality_scorecard` | `urn:capcut:remix-reference-video:artifact:quality-scorecard` / `schemas/quality-scorecard.schema.json` | `measured|incomplete|not_scored` (Track C only, after G-B) |
| `content_quality_profile` | `urn:capcut:remix-reference-video:artifact:content-quality-profile` / `schemas/content-quality-profile.schema.json` | `provisional|measured|not_scored` |
| `process_assessment` | `urn:capcut:remix-reference-video:artifact:process-assessment` / `schemas/process-assessment.schema.json` | `measured|incomplete|not_measured` |
| `gate_review_view` | `urn:capcut:remix-reference-video:artifact:gate-review-view` / `schemas/gate-review-view.schema.json` | `ready|stale|incomplete` |
| `gate_review_sheet` | `urn:capcut:remix-reference-video:artifact:gate-review-sheet` / `schemas/gate-review-sheet.schema.json` | `derived_review_only` |
| `g_b_owner_review_package` | `urn:capcut:remix-reference-video:artifact:gb-owner-review-package` / `schemas/gb-owner-review-package.schema.json` | `building|ready_for_owner|approved|rejected|stale` |
| `g_b_owner_decision` | `urn:capcut:remix-reference-video:artifact:gb-owner-decision` / `schemas/gb-owner-decision.schema.json` | `approved|rejected` |
| `g_b_frozen_input_snapshot` | `urn:capcut:remix-reference-video:artifact:gb-frozen-input-snapshot` / `schemas/gb-frozen-input-snapshot.schema.json` | `frozen|stale` |
| `workbench_acceptance_record` | `urn:capcut:remix-reference-video:artifact:workbench-acceptance-record` / `schemas/workbench-acceptance-record.schema.json` | `measured|incomplete` |

`gate_review_view` 是 canonical JSON 展示模型；`gate_review_sheet` 是由 view 确定性生成的 HTML/Markdown 派生产物，二者不能互相替代。表中 schema 文件、字段、required 列表和 track activation 由 registry 原子登记；实现前必须同时提交这些 schema 文件，不能只创建 suffix 或在代码中隐含字段。所有 snapshot 必须有 `input_hashes`、`source_versions`、`policy_id/version`、时间、幂等键和 supersedes 关系。`measurement_status`、`approval_status`、`efficiency_measurement_status` 作为 artifact-specific 字段单独保留，不压缩进共同 `lifecycle_status`。现有 `g_b_pair_measurement`/`gb_measurement.json` 在 P0a 后标记为 `legacy_projection`，只读兼容当前配对；新 G-B 结论以 `phase6_score_snapshot.json` 与 `process_assessment.json` 为权威，不再向旧文件增加字段。

### 15.2 baseline comparison matrix

`phase6_score_snapshot.baseline_comparison` 必须按指标记录 `pass|fail|not_evaluated`、source snapshot、threshold、reason 和 owner acknowledgement：

| 指标 | 首次 V2 baseline | 后续 V2 run |
| --- | --- | --- |
| machine critical path | 与 780/480 秒硬门槛比较 | 与硬门槛和基线 P50 比较 |
| quality score | 与 88/91 比较 | 与 88/91 和基线比较 |
| rework/gate return | `not_evaluated`，policy 允许且 owner acknowledge | 与 `measured_baseline_v0` 比较 |
| approval reuse/scope/timeline | 必须 `pass` | 必须 `pass` |

`g_b_thresholds_met=true` 只表示所有适用硬门禁通过且所有 `not_evaluated` 项都被 policy 明确允许，不包含 owner 决定。复核包必须同时列出 `thresholds_not_evaluated` 和 `owner_acknowledgement_required`；owner 未确认时 package 仍为 `ready_for_owner` 而非 `approved`。owner decision projection 验证 acknowledgement 后才能批准，但不得回写 immutable score snapshot。L1 `content_quality_profile` 为 provisional 时只作改版指导，不影响该字段，也不能作为 G-B 质量通过依据。

### 15.3 review identity and actor binding

```json
{
  "run_id": "gb-hot-...",
  "task_dir": "work/2026-08-17-case/hot",
  "gate_id": "gate3_material_selection",
  "review_package_hash": "sha256",
  "state_revision": 42,
  "session_id": "uuid",
  "actor": "operator-a"
}
```

`review_identity` 由服务端从当前 session 生成；浏览器只能引用 opaque `session_id`，不能提交 task_dir、actor 或 package hash 作为可信来源。启动参数 `--actor` 与 `--role operator|owner` 写入 session；owner API 只接受 `role=owner` 的 session。

### 15.4 per-change payload shapes

`change_request.payload` 不允许任意对象：

- `copy`：`{"line_ids":["line02"],"text_by_id":{"line02":"..."}}`；
- `claim_scope`：`{"claim_ids_add":[],"claim_ids_remove":["claim03"]}`，只允许 Gate 2 已批准 claim IDs 子集；
- `voice`：`{"provider":"doubao-v3","speaker":"...","speed":1.0}`，speed 必须在已批准范围；
- `material`：`{"fragment_id":"fragment04","candidate_id":"...","source_sha256":"...","overlay_decision":"retain_source_text|crop|cover|replace|no_action"}`；
- `range`：`{"fragment_id":"fragment04","start_seconds":0.0,"end_seconds":2.8}`，必须为数字且 containment 于 Gate 3 broad range；
- `rerecord`：`{"fragment_ids":["fragment04"],"approved_text_sha256":"..."}`；
- `boundary`：`{"boundary_id":"b03","issue_type":"flash|black_frame|audio_gap|color_jump"}`；
- `structural`：`{"request_type":"omit|merge|restructure","reason":"...","affected_ids":["fragment04"]}`，只生成 Gate 2 request。

每个 payload 都必须通过 schema、源 SHA、时间单位、claim/fragment ID 和当前审核包校验；只读影响预览和实际变更共享同一 validator。

工作台动作到 B0 scope 的固定转换为：Gate 1/2 `artifact_set`；Gate 3 选材 `fragment_set`；Gate 3 证据 `artifact_set`；Gate 4 生成前 `script_settings`；Gate 4 生成后与 Gate 5 `output_bundle`。转换后才调用现有 ApprovalService，禁止新增自由 scope。

### 15.5 timing and cache event shapes

审核事件至少使用：

```json
{
  "event_id": "uuid",
  "event_type": "review.opened|review.active_start|review.evidence_interaction|review.active_stop|review.heartbeat|review.pause|review.change_previewed|review.decision_submitted|review.decision_accepted|review.decision_conflicted|review.rework_completed|command.started|command.awaiting_user|command.succeeded|command.failed",
  "session_id": "uuid",
  "run_id": "...",
  "gate_id": "...",
  "occurred_at": "trusted-service-time",
  "attempt_id": "...",
  "payload": {"evidence_id":"...", "active_interval_id":"...", "execution_stage_id":"..."}
}
```

`execution_stage_id` 不另造框架阶段枚举，必须取当前 `default_dag()` 的真实 command node ID，并同时记录该 node 的 `framework_stage_id` 投影。G-B 测量终点为 `build-gate5-package`，排除 `init` 和 Gate 5 后的 `archive-approved`。审核事件的 `event_id`、`sequence`、`occurred_at` 和 `state_revision` 由 `TaskStorage.append_event` 生成；每个 active interval 有唯一 `active_interval_id`，heartbeat 只能续接同一 interval，超过 60 秒自动写 pause。重复 `event_id` 幂等忽略。`rework_completed` 由 Runner 在受影响 Gate 重新生成审核包时写入，并携带 `affected_gate_id`、`new_review_package_hash`。

`stage_metrics.jsonl` 是节点耗时与 cache status 的唯一权威，`pipeline_events.jsonl` 只提供顺序、Gate 和审计事实。每个成功或 cache-hit attempt 必须记录 `execution_stage_id`、`attempt_id`、`status`、`wall_seconds` 和 `cache_status`；Gate 节点以 `command.awaiting_user` 结束不影响 metric 完整性。`machine_api_critical_path_seconds` 对 `default_dag()` 中从 `split-reference`/`index-assets` 到 `build-gate5-package` 的真实 command nodes 计算：每个 node 取最终成功 attempt 的 `wall_seconds`，按 `critical(node) = duration(node) + max(critical(dep))` 动态规划，终值为 `critical(build-gate5-package)`。并行分支只计较长依赖链，一个 framework stage 分布在多个 command node 时逐 node 计入。失败 attempt 不进入关键路径，耗时进入 `retry_network_seconds`；Gate 人工等待不在 metric duration 内。缺少成功 metric、DAG node 未登记或到终点的必需依赖不全时为 `incomplete/not_measured`，不得按 framework stage 折叠或从事件时间、日志文本推断。

每个 stage cache fact 至少使用 canonical `execution_stage_id`、`cache_source=empty|cloned_cold|hot_lookup|none`、hit/miss/reused/skipped 数量、开始/结束时间和 evidence path。`approvals_recorded` 只计 `approved|rejected|changes_requested` 的有效 decision record，按 decision_id 去重。

### 15.6 run registry and owner transaction

`workbench/run_registry.json` 是本机 API 的唯一 run 映射，条目包含 `run_id`、canonical `task_dir`、`execution_mode`、`g_b_frozen_input_snapshot_sha256`、创建时间、更新时间和状态。registry 更新采用锁文件 + 临时文件 fsync + rename；CLI/API 并发写入时按 registry revision 乐观并发控制，旧 revision 返回 `409` 后重读，不覆盖新条目。禁止 symlink、路径逃逸和重复 `run_id`；已有 task 但 registry 条目 stale 时 API 返回 `409 registry_stale`，不自动修复；task 移动/改名视为新 task，必须通过显式 repair 命令重绑定并留下审计事件；缺失条目返回 `404`，不从目录名推断。

owner 决定 payload：

```json
{
  "decision":"approved|rejected",
  "package_sha256":"sha256",
  "policy_id":"v2_forward_baseline_v1",
  "policy_version":"1.0.0",
  "input_snapshot_sha256":"sha256",
  "acknowledge_not_evaluated":["rework_seconds","gate_return_count"],
  "rejection_reasons":[],
  "recovery_actions":[],
  "idempotency_key":"uuid"
}
```

`g-b-owner-approve`/`g-b-owner-reject` 读取 `--role owner --actor` 启动身份，服务端生成可信时间和 decision ID。事务原子写入 `g_b_owner_decision.json`、owner review package 状态和审计事件；重复 payload 重放原结果，payload 冲突返回 `409`。该事务只更新 G-B evidence projection，不改变普通 production lock。

owner package 状态转换固定为 `building -> ready_for_owner -> approved|rejected|stale`。`approved` 仅当所有适用硬门禁为 `pass`、`thresholds_not_evaluated` 均有 owner acknowledge、输入和 snapshot hash 仍匹配时允许；`rejected` 必须包含至少一条 `rejection_reasons[]` 和 `recovery_actions[]`；`stale` 只能由输入 hash、policy version、run registry 或 measurement snapshot 变化触发。owner transaction 成功后只推进 G-B evidence projection，不直接改变普通 V2 production lock。
