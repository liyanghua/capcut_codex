# `remix-reference-video` 质量加固设计

## 1. 文档状态

- 状态：基础质量加固已实现并合并主干；历史 legacy run 不追溯启用，创作质量升级待后续实施
- 日期：2026-08-18
- 修订日期：2026-08-19
- 适用对象：V2 Track-B 新任务及隔离 `gb-pair` 验证
- 关联工作台设计：[业务视频工作台重构设计](2026-08-18-business-video-workbench-design.md)
- 后续升级设计：[参考视频复刻创作质量升级设计](2026-08-19-reference-remix-creative-quality-upgrade-design.md)

本文只定义 `remix-reference-video` 的生产质量加固，以及这些质量结果如何被审核工作台读取。它不引入 Agent，不改变 `pipeline_state.json` 的审批权威，不解除普通 V2 production lock，也不改变 V1 历史任务的创建时契约。本文中的新产物、字段和规则均属于 V2 契约，必须先通过 schema、registry、输入哈希和回归测试，再进入真实 `gb-pair`。

截至 2026-08-19，本文定义的叙事报告、图片布局报告、共享 contain 布局、DAG/失效闭包、工作台质量投影和增量刷新已实现并合并主干。该实现只对冻结基线携带 `narrative_contract_v1` 的新 V2 任务生效；`tablemat-mix-v2` 等旧冻结任务按 legacy DAG 续跑，其历史成片不能被表述为已经通过本文两个新质量节点。本文解决的是确定性底线，不包含多策略拆解、生成式脚本候选、前三秒/高光和局部 AI 增强，这些由后续升级设计定义。

## 2. 现状与问题

当前生产链已经具备参考拆解、Blueprint、Mutation、Retrieval、证据闭环、TTS、重建、渲染和 `production-audit`。质量问题集中在两个位置：

1. `production_script_candidate.json` 主要按证据矩阵逐段复制口播，缺少叙事角色、段间承接和收束检查。
2. `media_runtime.py` 与 `review_media.py` 对图片使用放大后裁切的策略，工作台预览和正式成片没有统一的完整画面布局契约。

结果是运营人员看到的脚本像卖点清单，图片画面可能溢出或裁掉源文字，工作台也无法解释具体是哪个生产节点造成问题。

## 3. 设计目标

- 保持参考片的镜头顺序、节奏和时长包络。
- 在 approved claims、approved evidence 和禁用声明边界内，形成可解释的连贯口播。
- 图片完整保留，不裁切源文字或水印；低清或可读性未知时在 TTS 前阻断。
- 在不增加人工 Gate 的前提下，把质量检查作为 Gate 3 到 Gate 4 之间的机器准入条件。
- 让工作台展示真实执行节点、质量报告、输入输出产物和处理建议。

## 4. 生产 DAG 调整

现有五阶段 Gate 不变，只增加 Gate 3 汇总后的受控执行节点：

```text
summarize-gate3
  ├─ build-narrative-coherence
  │    └─ build-production-script
  ├─ materialize-approved-broad
  │    └─ validate-visual-layout
  └─ voice-preflight
       (依赖 production script、material manifest、visual layout report)
```

节点规则：

- `build-narrative-coherence` 读取 Gate 2 内容基线、Mutation、参考蓝图和 Gate 3 证据闭环，生成 `narrative_coherence_report.json`。
- `build-production-script` 只有在叙事报告通过后，才生成带连贯性元数据的 `production_script_candidate.json`。
- `validate-visual-layout` 读取 Gate 3 批准宽范围、素材画像和已物化副本，生成 `visual_layout_report.json`。
- 任一报告为 `blocked`，不得进入 `voice-preflight`、TTS 或任何媒体渲染。
- 这两个节点不新增用户审批点；阻断时由当前 Gate 4 生成前审核包展示具体缺口和返回路径。

### 4.1 节点、产物和失效闭包

两个新节点必须同时出现在以下三处：

1. `default_dag()` 的节点和依赖关系；
2. Native registry 的 adapter、声明输入和声明输出；
3. `ChangeService` 的 `stale_stages`、`artifacts_to_regenerate` 和 recovery path。

失效规则固定为：

- 文案、声明范围或结构变化：使 `build-narrative-coherence`、`build-production-script` 及其下游失效；
- 素材或范围变化：使 `validate-visual-layout`、`build-narrative-coherence`、`build-production-script` 及其下游失效；
- 仅声音变化：不重新执行两个质量节点；
- 仅边界变化：不重新执行两个质量节点。

实现必须优先从 DAG 依赖计算下游失效闭包；若保留显式清单，必须由测试验证清单与 DAG 一致。

### 4.2 新 V2 artifact 契约

`narrative_coherence_report.json` 和 `visual_layout_report.json` 都必须包含：

```json
{
  "artifact_type": "...",
  "schema_id": "urn:capcut:remix-reference-video:artifact:...",
  "schema_version": "1.0.0",
  "contract_version": "2.0.0-alpha.1",
  "skill_version": "2.0.0-alpha.1",
  "implementation_version": "...",
  "lifecycle_status": "ready",
  "input_hashes": {},
  "status": "passed"
}
```

两个 schema 必须注册到 `schemas/v2-alpha.registry.schema.json`，声明 task-local path、Track-B activation 和非生产状态权威属性；runner 必须登记输出哈希，artifact validator 必须校验 envelope、输入哈希和 lifecycle。报告不能携带 Gate approval 字段，`lifecycle_status` 只允许 `ready|stale`（机器报告没有待审人，不得使用 `awaiting_user`）。

### 4.3 在飞 V2 任务的续跑规则

`narrative_contract_v1` 与两个新节点只作用于注册后新建的 V2 任务。已经开始的 V2 run（冻结快照早于 `narrative_contract_v1`）不得静默变轨：

- 冻结快照的 Gate 2 内容基线缺少 `narrative_role`/`required_actions` 字段时，该 run 默认按旧 DAG 续跑，质量节点视为未启用；
- 若要启用新节点，必须显式返回 Gate 2 重建内容基线并重新完成 Gate 2/3 确认，生成旧/新映射、输入哈希、失效 Gate 和重新确认清单；
- 两种方式都不得复用其他 run 的批准或共享生产缓存。

## 5. 脚本连贯性契约

### 5.1 输入边界

编排器只能使用：

- `content_baseline.json` 中已批准的 claims 和片段顺序；
- `mutation_plan.json` 中已批准的 fallback；
- `script_evidence_matrix.json` 中已闭环的证据和 `voice_text`；
- 参考片蓝图中的镜头意图和节奏信息。

不得从文件名、素材路径或未批准文本推断产品事实。

### 5.2 叙事元数据

每个片段生成以下确定性字段。字段由 Gate 2 Blueprint/Content Baseline 产生，不能在 Gate 3 或 Gate 4 临时猜测：

- `narrative_role`：开场情境、问题/需求、产品出现、功能证明、使用结果、收束等；
- `required_actions`：该片段必须完成的动作集合，例如 `show_context`、`show_problem`、`show_product`、`demonstrate_feature`、`show_result`、`close`；
- `continuity_before`：与前一段的关系，例如情境延续、问题转解决、功能转证据；
- `continuity_after`：对下一段的预期承接；
- `approved_claim_ids`、`evidence_row_ref`：事实边界绑定；
- `coherence_status`：`passed`、`blocked` 或 `manual_review`。

`narrative_role`、`required_actions` 和 `continuity_*` 的规则版本固定为 `narrative_contract_v1`。角色分配只读取参考蓝图的镜头意图、Content Baseline 的动作集合和 evidence closure 状态；缺少这些字段时为 `manual_review`，不默认判定通过。

承接文本只能使用版本化的 `continuity_lexicon_v1`：

| 关系 | 允许的中性连接语 | 禁止行为 |
| --- | --- | --- |
| 情境 → 问题 | `先看这个场景`、`先从这里开始` | 新增产品事实或效果承诺 |
| 问题 → 产品 | `这时候`、`所以看产品本身` | 把未批准 claim 写成结论 |
| 产品 → 证明 | `具体看这一点`、`再看实际使用` | 把画面推断成未闭环证据 |
| 证明 → 结果 | `从这个结果看`、`用起来之后` | 新增性能、承诺或对比 |
| 任意 → 收束 | `最后`、`整体来看` | 新增 CTA 声明或保证 |

结构重排、删段和片段并段仍必须返回 Gate 2。V2 文案请求的 `edit_intent` 只允许 `bridge|rewrite`；`merge` 只允许出现在结构修改的 `request_type` 中。历史 V1 请求继续按创建时契约处理，并由兼容层将缺失的 intent 归一为 `rewrite`，不得回写旧任务产物。

### 5.3 `narrative_coherence_report.json`

报告至少包含：

- 片段顺序和每段叙事角色；
- 每段的承接关系和使用的 claim/evidence；
- `opening_context`、`transition_coverage`、`claim_density`、`closing` 检查结果；
- 阻塞片段、业务解释和允许的处理方式。

报告还必须记录 `narrative_contract_version`、`continuity_lexicon_version` 和每个检查使用的输入哈希。

阻断条件：

- 开头没有情境或问题；
- 相邻片段连续为纯卖点，缺少动作、语境或结果连接；
- 结尾没有收束；
- 句子越过 approved claims、approved fallback 或禁用声明边界。

## 6. 图片布局与可读性契约

### 6.1 渲染规则

- 图片一律使用 `fit_mode=contain`，保留完整内容；不允许通过 `crop`、`cover` 或冻结尾帧补齐图片画面。
- 视频默认保持现有行为；仅当 `overlay_detected=true` 且已批准 overlay policy 要求不裁切时，视频也使用 `contain`。
- 带源文字/水印的素材强制 `crop_pixels=0`。
- 剩余画布使用版本化 `image_layout_policy_v1` 的中性背景色；背景色不是自由运行时输入，策略版本变化必须改变 stage fingerprint。
- `gate3_review_media`、正式渲染和工作台中央预览复用同一布局计算。

### 6.2 `visual_layout_report.json`

逐片段记录：

- 源媒体尺寸和目标画布尺寸；
- 实际缩放比例、内容矩形和画布位置；
- `crop_pixels`、源文字/水印策略；
- 文字区域可读性状态：`passed`、`blocked` 或 `manual_review`；
- 具体处理建议。

`visual_layout_policy_v1` 的确定性 rubric 为：

- `blocked`：`crop_pixels > 0`、源文字/水印素材未使用 `contain`、有效放大倍数超过 `2.0x`，或已知文字区域渲染高度低于 `18px`；
- `passed`：无裁切、有效放大倍数不超过 `2.0x`，且无源文字/水印或已知文字区域达到 `18px`；
- `manual_review`：检测到源文字/水印但没有可靠文字区域尺寸，或素材画像缺少足以判定的尺寸信息。

`overlay_detected=true` 且 `overlay_policy_required=true` 时，不得进入 `passed` 的裁切分支；必须为 `contain` 并满足上述可读性条件。低分辨率或文字区域无法验证时，不自动放大硬拉、不使用无关素材替代，工作台必须提示补充高分辨率图片/视频或更换已批准候选。

## 7. 工作台展示契约

工作台继续读取 `workbench_workspace_view`，新增只读派生投影：

- `process.execution[]`：节点状态、耗时、attempt、输入/输出产物和失败原因；
- `artifacts[]`：业务名称、阶段、预览引用、输入输出关系和诊断 hash；
- `quality_checks[]`：叙事连贯性、图片布局、声音预检、L0/L1/P 结果及其来源；
- `decision_context.next_action`：补素材、改文案、返回 Gate 2 或重新审核。

Gate 1/2 尚未形成自有素材选择时，左侧故事板显示参考镜头和“待生成/尚未进入该阶段”的明确状态，不使用“暂无”掩盖阶段门控；Gate 3 才显示批准宽范围和选材结果。

右侧仍展示完整五阶段，中央主预览保持固定，左侧选择只定位时间线和详情。SSE 收到更高 `state_revision` 后执行增量重渲染，不调用 `location.reload()`，并保留播放位置、选中对象和时间线定位。

修改入口保持结构化：

- 文案：`edit_intent=bridge|rewrite`；
- 素材：候选替换、宽范围和源文字处理；
- 结构：`request_type=omit|merge|restructure`，统一返回 Gate 2；
- 声音：音色、语速和重录。

所有修改继续经过 ChangeService 的影响预览和持久化 job，不能由前端直接写 artifact 或状态文件。

### 7.1 质量结果来源

工作台不得把不存在的字段映射成质量结论：

- L0 来源为 `final_validation_report.hard_gate_checks`；
- P 来源为 `render_report.production_audit` 或实际存在的 `production-audit` 报告；
- L1 只有在 Track-C 质量快照或 `quality_scorecard` 存在时展示；
- 缺少来源时统一返回 `status=not_available`、`source_artifact=null` 和业务说明，不修改 `final_validation_report.json` 伪造 L0/L1/P。

## 8. 失败处理

质量检查失败时只允许：

1. 补充指定片段的高质量图片或视频；
2. 在 approved claim/evidence 范围内修改文案或补承接；
3. 返回 Gate 2 做结构修改；
4. 重新审核已批准候选。

禁止自动变速、冻结尾帧、裁切源文字、水印或使用无关素材凑数。

## 9. 验收标准

- 同一参考结构生成的口播具有开场、承接、结果/收束，不再是卖点逐条罗列。
- 横图、竖图和带源文字图片均满足 `crop_pixels=0`，成片和工作台预览布局一致。
- 低清或可读性未知素材在 TTS 前阻断，并显示具体片段和补素材建议。
- 叙事报告或布局报告未通过时，不生成 TTS、代理或正式成片。
- 工作台可看到执行节点、报告、输入输出产物、阻塞原因和受控修改影响。
- 现有审批哈希、媒体 allowlist、Track-B 锁和 `gb-pair` 隔离测试保持通过。
