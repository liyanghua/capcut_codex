# G-B 测量、质量快照与操作型审核工作台设计

> 状态：设计已确认，等待书面规格审查
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

系统不得自行批准 G-B。普通 V2 production、共享生产缓存和归档继续保持锁定，直到 G-B owner 批准且后续监督运营试用通过。

## 2. 范围

### 2.1 首版包含

- 七个 Gate 的业务化审核视图；
- Gate 3/4/5 的完整图片、音频、视频证据；
- Gate 1/2 的结构化摘要、时间线、声明和变更对照；
- 页面内通过、驳回、要求修改；
- 修改 dry-run、影响预览、二次确认和 stale 传播；
- cold/hot 审批、缓存、机器时间、审核时间和返工统计；
- Track C 五阶段生产质量快照；
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

该 policy 必须进入 G-B owner 复核包并由 owner 明确批准。

### 3.2 G-B 必需证据

G-B 复核前必须具备：

- cold `machine_api_critical_path_seconds <= 780`；
- hot `machine_api_critical_path_seconds <= 480`；
- 五阶段生产质量分均不低于 88；
- `video_quality_score >= 88`，91 为目标值；
- cold/hot Gate 1-5 全部独立批准；
- 无审批复用、范围越界、未登记生产输入和越权归档；
- 新监督 cold/hot 的七个 Gate 决定全部来自工作台；
- Gate 3 选材 `decision_seconds <= 300`；
- Gate 4 生成前 `decision_seconds <= 180`；
- 修订轮 `decision_seconds <= 120`；
- 其他 Gate 首轮记录实测，单次轻微超时不自动阻断；
- owner 明确记录 `approved` 或 `rejected`。

## 4. 质量模型

### 4.1 三个相互独立的制作期视角

工作台首版覆盖：

1. **L0 硬门禁**：合规授权、声明真实性、商品与 Offer 一致性、证据闭环、音画技术质量、生产可追溯性；
2. **L1 离线内容质量**：抓注意力、信息清晰度、卖点与人群匹配、说服与证据强度、节奏与观看体验、品牌与商品一致性；
3. **P 生成过程**：首次通过、缺陷逃逸、返工、机器时间、人工等待、运营触达和成本数据完整性。

L2 依赖真实投放后的观看、转化、退款和贡献利润。首版只保留 `evaluation_context_id`、`video_version_id` 和反馈入口，不预测、不伪造 L2，也不把 L2 接入作为本轮 G-B 阻塞项。

### 4.2 Track C 与 L1 不混用

- `quality_scorecard.json` 是 Track C 五阶段生产质量权威；
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

`quality_scorecard.json` 每个阶段至少记录：

- `framework_stage_id`；
- `rubric_items[].earned_points`；
- `rubric_items[].max_points`；
- `rubric_items[].evidence_paths`；
- `rubric_items[].reason`；
- `stage_output_quality_score`；
- `measurement_status` 与 `approval_status`。

只有全部 rubric 项有当前证据时才计算阶段分。缺项写 `not_scored`，不得填目标分。

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

输入：任务根目录和启动时指定的 `actor`。

输出：JSON/SSE、Range 媒体流和结构化命令结果。

边界：不维护第二套状态；所有写操作委托给 Approval Service 或 Change Service。

### 5.3 DecisionService

职责：提交通过或驳回。

必需输入：`run_id`、`gate_id`、`review_package_hash`、`state_revision`、`actor`、`decision`、幂等键和可选备注。

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

服务端根据当前状态和固定影响规则计算，不信任浏览器提交的影响范围。

### 5.5 ChangeService

职责：在运营二次确认后执行受控修改事务。

输入：当前 review identity、结构化 change request、已展示影响预览哈希、actor 和幂等键。

行为：验证预览仍有效，在 staging 写入修改，校验成功后原子提升并传播 stale；失败时保留原批准产物并记录恢复信息。

### 5.6 MeasurementCollector

职责：记录可信审核和过程事件，生成 `process_assessment.json`。

事件使用服务端时间，至少包含：

- `review.opened`；
- `review.evidence_first_interaction`；
- `review.change_previewed`；
- `review.decision_submitted`；
- `review.decision_accepted`；
- `review.decision_conflicted`；
- `review.rework_completed`。

浏览器只能提交事件意图，不能提交任意秒数。

### 5.7 GBOwnerReviewBuilder

职责：从冻结证据生成 `g_b_owner_review_package.json`。

输入：baseline policy、cold/hot measurement、两侧 audit、质量快照、过程评价、工作台验收记录和所有输入哈希。

输出：阈值逐项结果、阻塞项、未测量项、建议和 owner 决定契约。

边界：只能生成待审包，不能写 owner 批准。

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

## 8. 测量口径修复

### 8.1 审批

`approvals_recorded` 必须从整个 run 的有效决定记录统计，而不是只统计最后一次 resume 的新增决定。统计按 `decision_id` 去重，校验每条记录的 `run_id`、Gate、审核包哈希和 revision。cold/hot 决定 ID 交集必须为空。

### 8.2 缓存

缓存至少拆成：

- `snapshot_seeded`：是否复制经声明的 cold 快照；
- `lookup_hits` / `lookup_misses`：索引查询结果；
- `asset_records_reused`：复用的技术画像条目数；
- `stage_execution_skipped`：是否因完整缓存跳过阶段；
- `index_reuse_seconds_saved`：相对冻结基线的索引耗时差。

不得用 `snapshot_seeded=true` 推断所有阶段 cache hit，也不得把阶段执行成功统一写成 miss。

### 8.3 时间

分别记录：

- `machine_api_critical_path_seconds`；
- `human_wait_seconds`；
- `operator_touch_seconds`；
- `decision_seconds`；
- `rework_seconds`；
- `retry_network_seconds`；
- `gate_return_count`。

缺失时状态为 `not_measured` 并写原因。零只表示确实观测到零。

## 9. API 契约

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

写请求必须带 review identity、actor 和幂等键。API 仅绑定 `127.0.0.1`，路径使用 allowlist 和 containment 校验，不提供目录浏览或任意文件读取。

## 10. 错误与恢复

- revision/hash 冲突：拒绝写入，刷新当前快照并展示 diff；
- 影响预览过期：拒绝执行，重新 dry-run；
- 修改校验失败：丢弃 staging，保留当前批准产物和状态；
- TTS/渲染失败：保留有效上游，记录可重试恢复命令；
- 媒体缺失或路径逃逸：阻塞当前操作并登记安全错误；
- 工作台/API 不可用：使用当前哈希绑定的静态快照和 CLI；
- 质量证据缺失：标记 `not_scored` 或 L0 fail，不推断通过；
- owner 复核包存在阻塞项：不显示可提交的 G-B approved 决定。

## 11. 验收

### 11.1 自动化契约验收

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

### 11.2 人工浏览器验收

使用真实任务逐项检查：

- 六类状态：处理中、待确认、阻塞、失败、stale、完成；
- 七个 Gate 是否能在一屏形成有效决定；
- 桌面与 390px 手机布局；
- 图片、短代理、音频、字幕联动和最终视频；
- 通过、驳回、修改、影响预览和冲突刷新；
- 静态快照 + CLI 降级路径。

首版不要求 Playwright 视觉回归、浏览器录像或截图回归包。人工验收保存检查表、真实任务路径和未决问题。

### 11.3 监督 G-B 运行

- 创建新的 cold/hot run，不复用现有审批；
- 全部 Gate 从工作台决定；
- 采集可信审核事件和关键决策时长；
- 两侧 production audit 通过；
- 生成质量、内容和过程评价；
- 生成 owner G-B 复核包；
- owner 明确记录最终决定。

## 12. 实施与发布顺序

1. P0a：修复测量口径、baseline policy、评分契约和 review view model；
2. P0b：本机操作型工作台、媒体端点、决策、影响预览和变更事务；
3. P0c：新监督 cold/hot、人工浏览器验收和 owner G-B 复核；
4. G-B approved 后晋级 `2.0.0-rc.1`；
5. 执行小范围监督运营试用和异常恢复演练；
6. 试用通过后再单独批准普通 V2 production、共享缓存和归档；
7. 多用户、远程部署、L2 经营闭环和完整 Track C 看板后置。

## 13. 已确认决策

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
