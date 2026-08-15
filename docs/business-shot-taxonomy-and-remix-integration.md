# 业务镜头分类、标签字典与爆款参考复刻集成方案

## 1. 文档目标

本文从业务视角定义一套可复用的镜头分类体系，并说明它如何与当前参考视频复刻流程协作，用于：

- 统一业务、内容、拍摄、素材运营和算法对镜头的理解；
- 将爆款参考视频从“若干切镜”提升为可复用的业务结构；
- 让 Blueprint 能基于参考结构、Brief 和素材覆盖生成目标方案；
- 让 Retrieval 能按业务含义、证据要求和镜头语言匹配或替换自有素材；
- 在缺素材时准确说明缺什么、为什么缺，以及应该补拍、补传、生成还是调整结构；
- 提升参考视频复刻的速度、稳定性、可审核性和最终效果。

本文只定义业务镜头分类及其在复刻系统中的使用方式，不包含账号发布频率、内容排期或发布配比统计。

### 1.1 当前能力边界

本文同时包含“现在可人工落地的业务模型”和“未来 Track B 执行器的目标接口”，两者不能混为已实现能力：

| 状态 | 当前口径 |
|---|---|
| 现在可做 | 人工维护标签/模板/素材时间段表；在唯一 `manual-contract-only` V2 pilot 中按现有产物手工投影并逐 Gate 审核；运行 Track A envelope/registry 静态护栏 |
| 当前没有 | 自动业务 beat 识别、通用模板匹配、素材时间段建档执行器、完整产物 shape validator、普通 V2 生产发布能力 |
| Track B 目标 | 将稳定后的三层表固化为可缓存、可增量重算的索引、覆盖和匹配执行器 |

本文本身通过业务评审，不代表 G-A、G-B 或生产发布质量已经通过，也不授权创建 registry 之外的新 V2 任务产物。

## 2. 核心结论

镜头分类不能只做成一张混合标签表。推荐采用三层模型：

```text
标签字典 Tag Dictionary
  定义标准概念及其边界
            ↓
业务镜头模板库 Business Beat Template Library
  定义一种业务表达如何成立
            ↓
素材时间段目录 Asset Segment Catalog
  记录具体素材的哪个时间段实际满足了什么
```

三层使用同一套稳定的 `tag_id` 和 `template_id`，但职责不同：

| 层级 | 回答的问题 | 是否绑定具体素材 |
|---|---|---|
| 标签字典 | “防油、钩子、擦拭、检测报告分别是什么意思？” | 否 |
| 业务镜头模板库 | “防油证明镜头怎样拍、哪些画面必须出现才算成立？” | 否 |
| 素材时间段目录 | “`oil-test-01.mp4` 的 2.4–6.8 秒是否完整展示了倒油、擦拭和结果？” | 是 |

## 3. 统一颗粒度

业务分类的核心颗粒度应是 `business_beat`，不是单个技术切镜。

| 对象 | 定义 | 系统职责 |
|---|---|---|
| `shot` | 参考视频两个技术切点之间的画面 | 参考片切镜、节奏、构图和关键帧事实 |
| `business_beat` | 能独立完成一个叙事职责、说服任务或证据任务的最小业务表达单元 | 业务镜头分类和模板匹配的核心颗粒度 |
| `fragment` | 新视频时间轴上的一个视觉剪辑单元 | Blueprint 与 Reconstruction 的执行颗粒度 |
| `asset_segment` | 自有素材中语义连续、可独立检索使用的源时间窗 | 素材索引、匹配和替换的颗粒度 |

它们不是一一对应关系：

```text
1 个 business_beat
  可以包含 1–N 个参考 shot
  可以生成 1–N 个目标 fragment
  可以由 1–N 个 asset_segment 共同支撑
```

例如“防油污、一擦即净”通常不是一个单帧或单镜头概念，而是：

```text
污渍出现 → 连续擦拭 → 干净结果
```

该业务 beat 可以横跨多个参考 shot，也可能由一个完整连续的自有素材时间段承载。

### 3.1 业务分组与执行主键

`business_beat` 是业务分类和完整性判断的分组键，`fragment_id` 仍是现有 V2 的执行主键。Blueprint 必须在 Gate 2 前把每个目标 beat 确定性编译为有序 fragments；Gate 2 只展示并原子批准编译结果、规则版本和输入哈希：

```yaml
beat_id: target_beat03
template_id: tablemat.proof.oil_wipe
template_version: 1.0.0
fragment_ids: [fragment05, fragment06, fragment07]

fragments:
  - fragment_id: fragment05
    beat_id: target_beat03
    phase: precondition
    action_group_id: oil_wipe_group01
  - fragment_id: fragment06
    beat_id: target_beat03
    phase: action
    action_group_id: oil_wipe_group01
  - fragment_id: fragment07
    beat_id: target_beat03
    phase: result
    action_group_id: oil_wipe_group01
```

每个 fragment 还应携带 `template_id/template_version`、`source_shot_ids`、`span_group_id` 和自己的证据/媒体要求。Retrieval 为每个 fragment 生成候选与 Gate 3 宽范围；beat、`action_group_id` 和 `span_group_id` 只负责检查组合是否完整、顺序是否正确和是否需要同源连续。Reconstruction 继续按 `fragment_id` 消费生产素材、配音、字幕和精确时间轴。

如果一个业务 beat 需要三段不同素材，就编译为三个 fragments；不能让一个抽象 beat 直接绕过 `fragment_plan.json` 成为第二套生产主键。

## 4. 第一层：标签字典

### 4.1 定位

标签字典是全局、受控、带版本的标准词汇表。参考片、Blueprint、业务镜头模板和自有素材必须尽量使用同一套机器 ID，避免依赖自由文本或文件名进行模糊理解。

标签只表达语义概念，不表达任务批准。例如词典可以存在 `benefit.oil_resistance`，但这不表示某个产品已经获准宣称“防油”。声明授权必须来自当前任务 Brief 的 `approved_claim_ids`。

### 4.2 标签、声明与证明规则的边界

建议通过命名空间先区分概念角色，再在维度内建立父子标签：

| 命名空间 | 表达什么 | 能否由画面直接观察 |
|---|---|---|
| `narrative.*`、`hook.*`、`audience.*` | 创作意图、叙事职责和目标人群 | 否 |
| `scene.*`、`object.*`、`state.*`、`action.*`、`result.*`、`shot.*` | 实际可见场景、物体、前置状态、动作、结果和镜头语言 | 是，必须关联证据帧/时间窗 |
| `problem.*`、`benefit.*`、`feature.*` | 业务语义概念 | 不一定；不能只凭概念标签认定事实成立 |
| `proof_method.*`、`evidence_carrier.*` | 证明方法或信息载体 | 可以观察“采用了什么形式”，不自动代表证明有效 |
| `risk.*` | 水印、遮挡、跳切、第三方品牌等风险 | 视具体风险而定 |

`claim_id` 不属于标签批准状态。建议由独立声明表维护其允许文案、对应 `benefit_tag_ids`、适用产品和所需证明规则；当前任务只通过 `project_brief.yaml.approved_claim_ids` 授权声明。业务镜头模板引用证明规则，素材目录只记录潜在证据能力，`script_evidence_matrix.json` 才在 Gate 3 将“当前 claim + 当前已选素材时间窗”闭环。

### 4.3 配套的声明注册表

声明注册表不属于三层镜头分类模型，但它是解析 `approved_claim_ids` 的必要治理输入：

```text
claim_registry_id, claim_registry_version, content_hash,
claim_id, claim_revision_hash, product_id_or_category,
allowed_wording, prohibited_wording, benefit_tag_ids,
required_proof_rule_ids, limitations, channel_or_region_scope,
status, owner, reviewer
```

声明注册表只定义“某个 claim 是什么、在什么条件下可用”；当前 Brief 选择哪些 `claim_id`，才形成任务授权。任务必须把 registry version/hash 和所选 claim revision hashes 纳入 Gate 2 输入哈希。claim 文案、适用产品、限制或 proof 映射变化时，Gate 2 与下游变为 `stale`。

在当前 alpha 中，它应作为受控的外部业务/合规输入被引用并固定哈希，不自创 registry 之外的新任务审批产物。未来若将其正式纳入 V2 机器产物，需先更新 canonical registry 与 artifact contract。

### 4.4 推荐标签维度

| 层级 | 维度 | 示例 | 主要用途 |
|---|---|---|---|
| 策略层 | `funnel_stage` | 种草、需求激发、选择决策 | 标记镜头适用的业务阶段，不做发布频率统计 |
| 策略层 | `narrative_role` | hook、痛点、产品揭示、证明、顾虑处理、payoff、CTA | 参考结构和 Blueprint |
| 策略层 | `hook_mechanism` | 结果前置、强动作、反差、危险提示、权威背书 | 前三秒设计 |
| 策略层 | `persuasion_job` | 痛点、信任状、顾虑、利益强化 | 判断镜头的说服任务 |
| 意图层 | `target_audience` | 家庭用户、学生、母婴家庭、个体店主 | Brief 与 Blueprint，不作为画面事实 |
| 可见层 | `visible_person_role` | 成年女性、学生、父母、儿童 | 素材观察和人物连续性 |
| 场景层 | `room`、`support_object`、`occasion` | 餐厅、餐桌、乔迁、学习 | 场景理解与匹配 |
| 语义层 | `problem_concept` | 易刮漆、油污渗透、密封发霉、卷边 | 痛点和钩子匹配 |
| 语义层 | `benefit_concept` | 防油、防刮、耐黄变、易清洁 | 卖点语义匹配 |
| 语义层 | `feature_attribute` | 透明、服帖、材质、尺寸适配 | 产品属性匹配 |
| 证据层 | `state`、`action`、`action_phase`、`result` | 油污前置、擦拭；前置、过程、结果 | 时间窗检索和动作完整性 |
| 证据层 | `evidence_carrier` | 检测报告、包装信息、实验画面、人物口述 | 记录承载形式；证明强度另行审核 |
| 证据层 | `test_method` | 刮擦、泡水、高温、清洗 | 证明方式匹配 |
| 表现层 | `content_style` | UGC 测评、实验演示、对比、生活方式 | 风格替换和生成 |
| 表现层 | `shot_grammar` | 景别、角度、构图、运镜、主体位置 | 视觉评分和生成提示 |

`target_audience` 和 `visible_person_role` 必须分开。例如“目标用户是母婴妈妈”属于创作意图，不能因为画面出现一位成年女性就自动推断成立。

### 4.5 标签词典字段

建议每个标签至少包含：

```yaml
taxonomy_version: 1.0.0
tag_id: action.wipe
dimension_id: action
parent_tag_id: action.clean
name_zh: 擦拭
aliases: [擦, 抹]
definition: 人或工具在物体表面进行连续清洁移动
include_when: 能看到接触表面并产生擦拭位移
exclude_when: 只有擦布静态出现或动作被完全遮挡
applies_to: [brief, reference_beat, blueprint_beat, asset_segment]
observability: temporal_video
applicable_media_types: [video]
default_match_role: hard_eligibility
status: active
```

关键规则：

- `tag_id` 稳定且不复用，展示名称变化不修改 ID；
- 自由文本只作补充说明，不能代替标准标签；
- 模型发现的新词先进入候选状态，不能自动成为启用标签；
- 定义、父子关系或证明规则变化时，应使受影响的语义索引、覆盖、匹配和下游状态失效；
- 文件路径、时间范围、置信度、审核状态、版权和 Gate 决定不属于标签字典字段。

`benefit.*` 等业务概念标签应标记为 `intent_only` 或 `derived`，不能配置成单凭一帧即可观察。`proof_rule` 由业务镜头模板引用，不应塞进普通标签实例并让它反向授权声明。

## 5. 第二层：业务镜头模板库

### 5.1 定位

业务团队现有的“镜头名称、镜头类型、核心卖点、必拍说明、营销杠杆”等表格，应升级为业务镜头模板库。

一行不再只是一个名称，而是定义：

> 一种业务表达承担什么职责、需要哪些画面、采用什么证据机制、满足什么条件才算成功，以及允许如何替换或生成。

### 5.2 现有业务表字段改造

| 现有字段 | 建议字段 | 调整说明 |
|---|---|---|
| 镜头名称 | `template_name` | 另加稳定的 `template_id` 和版本 |
| 镜头类型 | `execution_type` | 工艺动作、卖点展示、场景氛围等；另加 `narrative_roles` |
| 关联核心卖点 | 拆为 `benefit_tag_ids` 与 `evidence_mechanisms` | “效果展示、对比”不是卖点，而是证明方式 |
| 必拍说明 | `capture_brief` + 结构化要求 | 可读说明保留，同时拆出 `must_show`、动作顺序、镜头语言 |
| 营销杠杆 | `marketing_lever_tag_ids` | 实用功能、颜值、健康环保等标准标签 |
| 流量分层 | `applicable_funnel_stages` | 只标记适用阶段，不保存 70/20/10，也不统计发布频率 |

### 5.3 镜头模板字段

建议模板包含：

```yaml
template_id: tablemat.proof.oil_wipe
template_version: 1.0.0
template_name: 防油污演示
status: active

applicable_product_categories: [table_mat]
execution_type: selling_point_demo
narrative_roles: [proof]
applicable_funnel_stages: [demand_activation, choice_decision]

marketing_lever_tag_ids: [lever.practical_function]
benefit_tag_ids: [benefit.oil_resistance, benefit.easy_clean]
evidence_mechanisms: [proof_method.direct_demonstration]

structure_type: continuous_action
required_media_types: [video]
allowed_origin_types: [live_action]
hard_required_tag_ids:
  - state.oil_visible
  - action.wipe
  - result.surface_clean
preferred_tag_ids: [shot.close_up, angle.oblique]
forbidden_tag_ids: [risk.hidden_jump_cut]

required_phases: [precondition, action, result]
same_source_required: true
continuous_required: true
must_show:
  - 污渍与产品表面同时可见
  - 擦拭动作连续
  - 擦拭后的结果清楚可见
proof_rule: 中间不得通过跳切隐藏测试过程或结果

shot_grammar:
  shot_size: close_up
  angle: top_or_oblique
  product_visibility: high

duration_envelope_seconds: [2.0, 6.0]
generation_policy:
  ai_for_claim_evidence: forbidden
fallback_template_ids: []

fragment_blueprint:
  - slot_id: precondition
    order: 10
    phase: precondition
    count_policy: fixed_one
    action_group_key: oil_wipe
    duration_weight: 0.25
  - slot_id: action
    order: 20
    phase: action
    count_policy: fixed_one
    action_group_key: oil_wipe
    duration_weight: 0.50
  - slot_id: result
    order: 30
    phase: result
    count_policy: fixed_one
    action_group_key: oil_wipe
    duration_weight: 0.25
```

### 5.4 Beat 到 Fragment 的编译规则

模板的 `fragment_blueprint[]` 必须为每个执行槽定义稳定 `slot_id`、顺序、phase、数量策略、分组规则、媒体/证据要求和计划时长分配。建议只允许以下数量策略：

- `fixed_one`：固定一个 fragment；
- `per_required_item`：每个已排序的 `required_item_id` 一个 fragment；
- `bounded_montage`：Gate 2 草案显式保存 `selected_count`，并满足模板 `min_count/max_count`；编译器不得自行随机取数。

编译顺序固定为 `target_beat.order → fragment_slot.order → expansion_item_id`。再按该顺序分配 `fragment01`、`fragment02`……；同一输入 snapshot、同一 `selected_count` 和同一编译器版本必须得到相同 IDs。可变 montage 出现并列候选时，按稳定 `required_item_id` 排序，不能受文件扫描顺序影响。

计划时长先按模板 `duration_weight` 在 beat 的 Gate 2 时长包络中确定 nominal duration，再按累计帧边界量化；它只服务 Blueprint 和粗覆盖，不是 Gate 4 后的最终时间轴。真实 TTS 后仍由 `reconstruction_timeline.json` 在 Gate 3 宽范围内确定精确裁点。

### 5.5 模板结构类型

| `structure_type` | 说明 | 示例 |
|---|---|---|
| `atomic_visual` | 单个稳定画面即可成立 | 包边、透亮、包装展示 |
| `continuous_action` | 需要连续动作过程 | 铺设、擦拭、按压回弹 |
| `comparison_pair` | 需要前后或 A/B 对照 | 耐刮前后、PVC 与 TPU 对比 |
| `montage_group` | 多个画面共同完成表达 | 工厂、生产、质检、发货 |
| `document_evidence` | 由证书、报告、包装或条款承载 | 质检卡、保障说明 |

模板的 `duration_envelope` 是粗可用范围，不等于最终成片时长，也不要求候选素材与参考镜头等长。

## 6. 第三层：素材时间段目录

### 6.1 定位与粒度

素材目录的核心粒度是：

> 一行等于一个源文件中语义连续、可以独立匹配使用的时间窗；图片一张一行。

一条 20 秒视频可能包含倒油、擦拭和结果三个时间段。系统可以保存三个阶段行，也可以额外保存一个覆盖完整证明动作的组合时间窗。

### 6.2 字段建议

| 字段组 | 核心字段 |
|---|---|
| 身份与溯源 | `segment_id`、`asset_id`、产品、批次、源路径、SHA、媒体类型、来源类型 |
| 时间范围 | 起止秒、起止帧、时长、关键帧、前后可扩展余量 |
| 客观画面 | 产品、可见部位、人物、场景、动作、结果、景别、角度、构图和光线 |
| 推荐用途 | 可承担的叙事职责和业务模板，仅作为推荐而非画面事实 |
| 动作结构 | 前置、过程、结果、动作完整性、连续动作组 |
| 素材证据候选 | 可支持的利益概念、证据类型、强度、时间窗、证明限制和反证风险；不等同于任务声明授权 |
| 技术质量 | 可解码性、分辨率、帧率、清晰度、曝光、抖动、遮挡、竖屏裁切能力 |
| 生产风险 | OCR、内嵌文字、品牌、水印、第三方产品和安全裁切区 |
| 授权信息 | 商业使用、肖像、渠道、地区、期限和授权凭证引用 |
| 标签审计 | 标签来源、词典版本、置信度、证据帧、人工覆盖和审核状态 |

每个标签实例至少应记录：

```text
tag_id + taxonomy_version + source + confidence
+ evidence_frame_or_window + human_override + review_status
```

### 6.3 示例

```yaml
segment_id: seg-oil-wipe-003
asset_id: tablemat-shoot01-007
source_path: assets/tablemat/shoot01/oil-test-01.mp4
source_sha256: sha256...
media_type: video
origin_type: live_action
source_start_seconds: 2.4
source_end_seconds: 6.8

observed_tag_ids:
  - scene.dining_table
  - state.oil_visible
  - action.wipe
  - result.surface_clean

intended_role_tag_ids:
  - narrative.proof
  - narrative.hook

matched_template_ids:
  - tablemat.proof.oil_wipe

action:
  completeness: complete
  precondition_visible: true
  result_visible: true

evidence_assessments:
  - supported_concept_tag_id: benefit.easy_clean
    evidence_type: direct_demonstration
    evidence_start_seconds: 2.7
    evidence_end_seconds: 6.5
    strength: strong
    limitations: 仅能证明该次画面中的擦拭结果，不自动证明所有污渍或长期性能
    catalog_review_status: reviewed

technical_status: pass
rights_status: owned_commercial
review_status: reviewed
```

必须区分：

```text
画面实际出现什么 observed
≠ 用户希望它表达什么 intended
≠ 素材目录认为它可能支持什么 evidence assessment
≠ 当前任务最终获准说什么 approved claim
```

素材目录中的证据评估只回答“这段画面具备什么潜在证明能力”。只有当前任务 Brief 已批准对应声明，并且 Gate 3 的逐句证据闭环确认该时间窗足以支撑具体说法后，素材才能成为该任务的声明证据。素材目录的 `reviewed` 不能替代 Brief 授权、Gate 3 决定或 `pipeline_state.json` 审批。

### 6.4 图片边界

图片可以承载产品外观、包装、证书、细节和静态结果，但不能证明擦拭、铺开、弯折、耐刮等连续动作。图片应标记：

```yaml
action_completeness: static_only
```

图片在最终视频中停留多久属于 Reconstruction 的编辑时间，不是图片素材自身的源时长。

## 7. 爆款参考结构的组织方式

### 7.1 不只拆 Shot，还要组织 Beat

参考视频先按技术切点生成 `shot`，再将相邻 shot 归并为业务 beat。每个 beat 至少记录：

```yaml
beat_id: reference_beat01
source_shot_ids: [shot_001, shot_002]
narrative_role: hook
hook_mechanism: result_first
persuasion_job: problem_activation
template_id: tablemat.proof.oil_wipe
message: 油污能够快速擦净
promise: 桌面日常更容易打理
payoff_beat_ids: [reference_beat03]
reference_start_seconds: 0.0
reference_end_seconds: 2.8
```

归并时遵循以下规则：

- 技术切镜不必然产生新 beat；连续完成同一说服任务的多个 shot 应归为一个 beat；
- 叙事职责、核心信息、证明对象或行动阶段发生实质变化时，开始新 beat；
- 连续动作证明不能只因切镜被拆成互不相关的标签，应保留前置、过程、结果及连续性关系；
- 一个 shot 内如果存在明确的业务语义边界，可以按时间窗映射到两个 beat，但必须保留源时间范围；
- 钩子的承诺必须通过 `payoff_beat_ids` 指向后续兑现或证据，不能只记录“开头吸睛”。

`shot` 和时间点属于 `recipe.json` 的参考事实；`business_beat`、模板映射和叙事判断属于可审核的派生解释。Gate 1 后不得为了加入业务分类而回写或改变 `recipe.json`，派生结构必须引用其哈希和 `source_shot_ids`。

前三秒必须单独记录：

- 钩子起止时间；
- 注意力机制；
- 第一条信息或承诺；
- 关键视觉动作；
- 该承诺在后续哪个 beat 被证明或兑现。

### 7.2 推荐参考结构字段

完整参考片可以组织为：

```yaml
video_archetype: problem_solution_demo
first_3s:
  beat_ids: [reference_beat01]
  hook_mechanism: strong_action
  promise: 一擦恢复干净
  payoff_beat_ids: [reference_beat03]

beats:
  - beat_id: reference_beat01
    narrative_role: hook
    structural_priority: must_keep
    template_id: tablemat.proof.oil_wipe
  - beat_id: reference_beat02
    narrative_role: product_reveal
    structural_priority: replaceable
    template_id: tablemat.product.reveal
  - beat_id: reference_beat03
    narrative_role: proof
    structural_priority: must_keep
    template_id: tablemat.proof.oil_wipe
  - beat_id: reference_beat04
    narrative_role: cta
    structural_priority: optional
```

`structural_priority` 建议使用：

- `must_keep`：结构价值高，缺素材时优先补拍或补传，不能静默删除；
- `replaceable`：职责必须保留，但可以更换业务模板或表现方式；
- `optional`：删除后不破坏核心承诺和证明链。

业务 beat 分析发生在 Gate 1 客观拆解完成之后、Gate 2 Blueprint 编译期间。当前 V2 不新增独立 `reference_beats.json`；可先作为 `shot_blueprint.json` / `content_baseline.json` 的可追溯分析字段或人工审核附件表达，引用 `recipe.json` 哈希。若未来需要独立机器产物，必须先更新 canonical registry、artifact contract 和 Track A 静态检查，不能直接在 pilot 中自创权威文件。

## 8. 从参考结构生成 Blueprint

Blueprint 的三类输入职责必须分开：

| 输入 | 提供什么 | 不提供什么 |
|---|---|---|
| 参考视频的 Gate 1 事实与 Blueprint 派生分析 | Gate 1 提供 shot/音轨/节奏事实；Blueprint 据此分析视频类型、钩子、业务 beat 和证明方式 | 不授权自有产品声明，不回写 `recipe.json`，不锁定最终时长 |
| 项目 Brief | 产品、受众、内容目标、已批准和禁用声明、必须展示项 | 不证明某条素材实际存在对应画面 |
| 自有素材目录 | 当前证据强度、动作完整性和生产就绪度 | 不自动成为 Blueprint 的创意上限 |

推荐编译顺序：

```text
参考 recipe + Brief
→ 参考 business beats 和目标结构草案
→ 草案中的 beat/template 需求
→ 查询素材时间段目录生成 coverage_precheck
→ 标记 covered / partial / missing / unknown
→ 形成带缺口处置的 content_baseline 候选
→ Gate 2 批准内容基线与 Controlled Mutation 规则
```

Blueprint 应先保留符合 Brief、具有价值的参考结构；素材覆盖只决定生产就绪度。关键 beat 缺素材时应优先选择：

```text
补传现有素材
→ 补拍
→ 在明确允许时生成非证据型 AI 素材
→ 使用 Gate 2 批准的 fallback 模板或弱化说法
→ 用户批准后重构或删除结构
```

不得因为当前素材库缺口，自动把高价值结构删掉；也不得用无关素材填洞。

### 8.1 Blueprint 质量与生产就绪度分开

Blueprint 不能只用一个总分评价。至少要保存两个正交结果：

| 结果 | 评价内容 | 素材不足的影响 |
|---|---|---|
| `blueprint_quality` | 视频类型与受众适配、前三秒钩子、叙事完整性、承诺与兑现、卖点证明链、节拍必要性 | 不直接扣成“结构差” |
| `production_readiness` | 索引完整度、硬需求覆盖、动作和证据完整性、粗时长可行性、技术/授权风险、缺口处置 | 可以是 blocked 或 needs_material |

因此一个合理状态可以是：

```text
blueprint_quality_status = pass
production_readiness = blocked_by_missing_material
```

这表示结构值得做，但当前尚未具备生产条件。系统应保留结构并输出补拍/补传清单，而不是为了提高“覆盖率”自动降低 Blueprint 质量。

### 8.2 素材覆盖的计算口径

覆盖不能按标签数量简单计算。`action.wipe`、`state.oil_visible`、`result.surface_clean` 虽然是三个标签，但在“防油污演示”里共同构成一个完整证明组；缺少其中一步，应报告一个证明组缺口，而不是制造三个彼此独立的业务缺口。

每个模板先把要求组织成需求组：

```yaml
requirement_groups:
  - group_id: product_identity
    rule: any_of
    alternatives:
      - [product.tablemat_visible]

  - group_id: oil_wipe_proof_chain
    rule: all_of_in_order
    requirements:
      - state.oil_visible
      - action.wipe
      - result.surface_clean
    continuity: same_source_and_contiguous

preferred_match_tags:
  - shot.close_up
  - angle.oblique
```

只有 `requirement_groups` 参与覆盖判断；`preferred_match_tags` 只用于候选排序，不能被统计成缺素材。覆盖先逐 fragment/phase 判定，再聚合到 beat/action group。

单个 fragment/phase 使用三态：

- `unknown`：相关索引范围未完成、文件不可读、关键标签未审核或置信度不足；
- `missing`：相关索引范围完整，但不存在通过全部硬资格的候选；
- `covered`：至少存在一个通过语义、媒体类型、技术、授权和粗时长硬资格的候选。

需求组按固定优先级聚合，保证四态互斥：

| 状态 | 判定 |
|---|---|
| `unknown` | 任一必需 fragment/phase 为 `unknown`；先补全索引，不能推断真实缺口 |
| `missing` | 不含 `unknown`，且任一必需 fragment/phase 为 `missing` |
| `partial` | 所有必需 fragment/phase 都各自 `covered`，但不存在一组候选可同时满足同源、顺序、连续性、证据强度、重复限制或其他组约束 |
| `covered` | 所有必需 fragment/phase 都 `covered`，且至少存在一组候选可同时满足全部组约束 |

聚合优先级固定为 `unknown → missing → partial → covered`。例如“结果画面被手遮挡且没有其他合格结果候选”，在索引充分时结果 phase 为 `missing`，整个组也为 `missing`；只有前置、动作、结果各自都有候选，但它们无法组成合法连续证明时才是 `partial`。

全片不应只输出一个百分比，而应同时输出：

```text
must_keep_blockers
covered_weight_ratio
partial_weight_ratio
missing_weight_ratio
unknown_weight_ratio
index_completeness
gap_resolution_by_beat
```

权重落在“业务 beat × 硬需求组”，而不是每个标签。每个需求组只计一次，组内多少标签都不改变分母。可按 `must_keep > replaceable > optional` 和需求重要性配置权重；四种状态分别保留，不把 `partial` 主观折算成 0.5，也不把 `unknown` 当作 `missing`。四类权重占总必需权重的比例之和为 100%，并单独列出所有 `must_keep` 阻塞项。

预判中的 `covered` 只表示“目录中存在至少一种可行组合”，不表示已锁定候选，也不处理所有跨片重复与最终排程冲突；因此可以称为 `candidate_covered`。Gate 2 后的权威覆盖需加入固定 Brief、baseline、模板、素材快照、授权与全局排程约束；Gate 3 仍必须逐 fragment 审核候选、宽范围和整片组合。百分比只用于概览，能否生产由硬门禁与人工 Gate 决定。

Gate 2 前的 `coverage_precheck.json` 基于结构草案和当前素材索引，只负责暴露缺口；Gate 2 后的 `coverage_report.json` 按已批准基线、固定素材快照和完整资格规则重算，才是 Gate 3 的权威覆盖。两次可以复用同一素材索引和分析缓存，重算的是“当前需求对当前素材的覆盖关系”，不是把原始素材重新理解两遍。

## 9. 素材索引结构

### 9.1 索引阶段做什么

素材索引应从原始文件生成两类信息：

1. 跨任务可复用的技术事实，例如 SHA、时长、分辨率、场景切点、低清采样帧、OCR、感知哈希和通用画面描述；
2. 可定位到时间窗的语义实例，例如产品、场景、动作、动作阶段、结果、镜头语言和风险标签。

文件名和文件夹名只能作为线索，最终标签必须有实际画面或人工说明依据。

### 9.2 对 Blueprint 友好的最低完成标准

在生成覆盖预判前，素材索引至少应能够回答：

- 素材是否可读，扫描是否完整；
- 某个产品、场景或业务模板是否存在候选；
- 动作发生在哪个粗时间窗，是否包含前置、过程和结果；
- 可用范围在 `1.00x` 下是否大致足够；
- 是否存在竖屏裁切、叠字、水印、第三方品牌和主体遮挡风险；
- 当前结论是 `covered`、`partial`、`missing`，还是因为索引不充分而 `unknown`。

`unknown` 不能误报为 `missing`。索引不完整时，覆盖预判必须显式标记为降级结果。

### 9.3 不在索引阶段完成的事项

- 不批准具体素材；
- 不确定 Gate 3 宽范围；
- 不根据最终配音确定精确裁点；
- 不把用户对素材用途的描述当成最终视觉事实；
- 不直接生成生产目录中的素材副本。

### 9.4 索引更新与任务快照

全局素材目录可以增量更新，但三层基础数据和配套声明输入都必须使用不可变 revision：

```text
taxonomy_id + taxonomy_version + content_hash
claim_registry_id + claim_registry_version + selected_claim_revision_hashes
template_library_id + template_version + selected_template_revision_hashes
asset_catalog_id + catalog_revision + asset_snapshot_hash
```

任务至少固定本次使用的这些 revision/hash，以及扫描文件数、成功数、失败数和未审核数。任何已发布 revision 都不能原地改定义；修订应创建新版本，并保留 `superseded_by` 和迁移关系。

失效范围建议如下：

| 变化 | 最早失效位置 | 可复用内容 |
|---|---|---|
| 标签语义、claim 映射、模板硬要求或 proof rule 变化 | Gate 2 与下游 `stale` | `recipe.json` 客观事实、未变化媒体技术缓存 |
| 素材源 SHA、时间窗观察、授权或技术资格变化 | 相关 coverage、Gate 3 与下游 `stale` | Gate 2 先保留；若新覆盖要求改结构，再请求返回 Gate 2 |
| 全局目录新增素材，但任务继续固定旧 snapshot | 任务不重算、不失效 | 全部任务产物与决定 |
| 任务显式升级到新素材 snapshot | coverage、Gate 3 与下游 `stale` | Gate 2 先保留；当前 alpha 不以局部 hash 例外复用旧 Gate 3 批准 |
| 展示名或别名变化且语义未变 | 不使业务 Gate 失效 | 全部语义和技术缓存 |

不需要重做未变化文件的解码、哈希和通用视觉分析；但任何旧报告若引用的快照哈希不再是当前选择，都必须标为 `stale`，不能继续当作当前证据。

## 10. 匹配与替换逻辑

匹配的对象不是“参考 shot 与整个素材文件”，而是先由 beat 编译要求，再逐 fragment 执行：

```text
Blueprint business beat 的模板和证据需求
→ 有序 target fragments / action groups
↔ 每个 fragment 的 asset_segment 候选时间窗
→ 在 beat/action group 层校验候选组合完整性
```

匹配顺序建议固定为：

1. **产品与声明资格**：产品兼容，声明已由 Brief 批准；
2. **模板硬条件**：媒体类型、必需标签、禁止语义和来源类型满足；
3. **证据与动作完整性**：前置、过程和结果满足证明规则；
4. **技术与时长可用性**：可解码、可裁切、`1.00x` 下范围大致足够；
5. **视觉相似度**：景别、角度、构图、颜色、亮度和参考节奏；
6. **全片连续性**：人物、空间、来源、动作组、重复和相邻画面关系。

硬条件不合格的候选不能被视觉相似度救回。

### 10.1 替换规则

替换时应区分必须保持和允许变化的部分：

```text
必须保持：narrative_role、业务承诺、已批准 claim、proof_rule
优先保持：structure_type、动作阶段、产品可见度、镜头职责
允许受控变化：场景、人物、景别、角度、颜色、具体动作表现
```

当没有完全一致的模板候选时：

- 同模板不同镜头语言：可以作为正常替换候选；
- 同叙事职责但不同模板：只能命中 Controlled Mutation 已批准的 fallback；
- 缺少关键证据或动作结果：标记缺素材，不能靠画面相似度补位；
- 需要删 beat、并 beat 或改变承诺：返回 Gate 2。

### 10.2 时长处理

候选素材不需要等于参考片段时长，也不需要等于新视频总时长。候选只需在 `1.00x` 下提供完整业务表达和足够宽的可用范围。

Gate 3 只批准宽范围；真实配音后，Reconstruction 才在批准范围内确定精确裁点。最终视频可以比参考片短或长，前提是完整实施批准的 Blueprint。

## 11. 与现有五阶段流程的接入

下表是三层模型应接入五阶段的目标职责，不表示当前 V2 已具备相应自动执行器：

| 阶段 | 如何使用三层模型 |
|---|---|
| Performance-proven Video | 只将参考片拆成客观 shot，保存切点、关键帧、音轨、转写和节奏事实；不批准业务解释 |
| Blueprint | Gate 1 后把相邻 reference shots 解释为业务 beats，识别视频类型/钩子/模板；结合 Brief 和覆盖预判编译有序 target fragments、结构优先级和缺口处置 |
| Controlled Mutation | 定义哪些模板必须保留、可替换模板、允许 fallback 和禁止变化 |
| Retrieval | 将每个 target fragment 与 asset segments 匹配，并在 beat/action group 层检查完整性，完成资格、证据、评分、排程和 Gate 3 审核 |
| Reconstruction | 只消费 Gate 3 批准的素材宽范围和 Gate 4 批准脚本，不重新选择模板或素材 |

推荐的数据流：

```text
标签字典 + 业务镜头模板库
             ↓
参考视频 → Gate 1 客观 shot 拆解
             ↓
Blueprint：Brief + shots → reference beat 分析 → target beats/templates
             ↓
Blueprint（Gate 2 前）：target beats → 有序 fragments / action groups
             ↓
Gate 2：批准 content baseline + mutation plan 及其输入哈希
             ↓
素材文件 → asset segments + 标签实例
             ↓
fragment requirements ↔ asset segments
             ↓
beat/action group 组合校验 → coverage → matches → Gate 3 宽范围
             ↓
证据矩阵 → 批准脚本 → Reconstruction
```

## 12. 建议的数据载体与现有产物映射

三层基础数据可以使用数据库、在线表格或版本化文件管理，但导入当前任务时应投影到既有产物，避免创建互相冲突的生产权威。

| 基础数据 | 建议对象 | 当前任务中的投影 |
|---|---|---|
| 标签字典 | `tag_dictionary` | snapshot/version/hash 与标准 `tag_id` 引用；当前为人工业务输入，不是新任务审批产物 |
| 声明注册表（配套治理输入） | `claim_registry` | registry/version/hash、所选 claim revision hashes 和 `project_brief.yaml.approved_claim_ids`；不属于镜头分类三层，也不是 Gate 审批替代品 |
| 业务镜头模板库 | `business_beat_templates` | snapshot/version/hash 及 `shot_blueprint.json`、`content_baseline.json` 的模板/fragment 需求 |
| 素材时间段目录 | `asset_segment_catalog` | snapshot/hash 与当前任务的 `asset_profiles.json` 投影 |
| 参考业务结构 | `reference_beats` 概念视图 | 引用 `recipe.json` 哈希和 `source_shot_ids` 的非权威派生分析；目标选择投影到 `shot_blueprint.json`，不得回写 Gate 1 事实 |
| 目标业务结构 | `blueprint_beats` | `shot_blueprint.json`、`content_baseline.json` |
| 匹配结果 | 任务级候选 | `coverage_precheck.json`、`coverage_report.json`、`matches.json` |
| 批准素材范围 | Gate 3 决定 | `fragment_plan.json` |

基础素材目录不是新的审批权威。审批仍只记录在 `pipeline_state.json.decisions[]`；任务级匹配和生产只使用当前 Brief、固定的标签/模板/目录 snapshot 和有效输入哈希。素材目录的证据审核、模板的启用状态、Brief 的 claim 授权和 Gate 决定是四件不同的事。

## 13. 自有素材提供规范

推荐的上传组织如下：

```text
assets/<product>/<batch>/
  asset_submission.yaml
  raw/
    hook/
    product-reveal/
    action-proof/
    product-detail/
    lifestyle/
    claim-evidence/
    cta/
```

这些子目录只是帮助人快速浏览和提供“推荐用途”线索，不是标签真值，也不是必须把所有类别都凑齐。一个素材可支持多个业务职责时只保留一份原文件，在 `asset_submission.yaml` 中写多个 intended role，避免重复复制。系统仍需看实际画面并按时间窗建档。

用户最少提供：

- 产品 ID 或产品名称、素材批次和原始视频/图片；
- 每个文件的一句话画面说明；
- 希望表达的用途、卖点或业务模板，可多选；
- 素材来源、商业使用和肖像授权状态；
- 已知限制，例如不可露脸、不得展示某品牌、限定渠道或期限。

为了提高后续匹配效果，视频应尽量保留原始画质、原速、原始连续动作和动作前后余量；不要提前加速、冻结、烧录字幕或过度裁切。证明类动作优先保留“前置状态 → 完整动作 → 结果状态”。图片优先提供无水印、高分辨率、主体完整且便于 9:16 裁切的版本。

`asset_submission.yaml` 只承载用户意图和来源声明。系统自动生成 SHA、技术参数、时间窗、关键帧、OCR、客观标签和风险；人工再确认产品身份、证据能力、授权与最终 Gate 3 宽范围。

## 14. 业务表落地建议

第一版不需要让业务人员填写所有机器字段。建议分工如下：

### 14.1 业务人员维护

- 镜头名称与业务目的；
- 适用产品和适用营销阶段；
- 叙事职责、营销杠杆和核心卖点；
- 必拍说明、必须出现的画面和不可接受的表达；
- 是否允许 AI 生成、是否必须实拍或文档证据；
- 可接受的 fallback 模板。

### 14.2 系统自动补充

- 标准标签 ID 映射；
- 素材 SHA、技术参数和时间窗；
- 动作阶段、关键帧、OCR、构图和质量风险；
- 模板候选、匹配分数和覆盖状态；
- 缺素材和补拍建议。

### 14.3 人工必须审核

- 产品身份是否正确；
- 卖点是否获准声明；
- 动作是否完整，画面是否足以证明声明；
- 测试过程是否存在误导；
- 品牌、水印、人物肖像和商业授权风险；
- Gate 3 的最终素材与宽范围。

### 14.4 第一版三张核心表与一张配套表

业务侧先维护必要字段，机器字段由系统导入时补齐。建议第一版表头如下：

**表 A：标签字典**

```text
taxonomy_version, tag_id, dimension_id, parent_tag_id,
name_zh, aliases, definition, include_when, exclude_when,
applies_to, observability, default_match_role, status, owner
```

**表 B：业务镜头模板**

```text
template_id, template_version, template_name, product_category,
narrative_roles, funnel_stages, benefit_tag_ids, execution_type,
structure_type, required_media_types, hard_requirement_groups,
preferred_tag_ids, forbidden_tag_ids, must_show, proof_rule,
duration_min_seconds, duration_max_seconds, generation_policy,
fallback_template_ids, fragment_blueprint, compilation_policy,
status, owner
```

**表 C：素材时间段目录**

```text
segment_id, asset_id, product_id, batch_id, source_path, source_sha256,
media_type, source_start_seconds, source_end_seconds,
observed_tag_instances, intended_role_tag_ids, action_group_id,
action_phase, action_completeness, evidence_assessments,
technical_status, crop_9x16_status, overlay_risks, rights_status,
catalog_review_status, reviewer
```

**配套表 D：声明注册表**

```text
claim_registry_id, claim_registry_version, content_hash,
claim_id, claim_revision_hash,
product_id_or_category, allowed_wording, prohibited_wording,
benefit_tag_ids, required_proof_rule_ids, limitations,
channel_or_region_scope, status, owner, reviewer
```

表 D 不改变“三层镜头分类”定义，只解决 claim 授权和证明要求的稳定映射。它通常由业务、法务/合规或证据负责人维护，而不是由素材运营维护。

多值字段应保存稳定 ID 数组或规范化子表，不用逗号自由文本承担机器语义。对业务人员可提供中文下拉选择，导出时转换成 ID。

### 14.5 旧业务表迁移规则

现有表不能通过一次字段改名直接变成模板库。建议执行：

1. 给每条旧记录保留 `legacy_row_id`、`source_table`、原始字段和值，确保可追溯和回滚；
2. 把“选题/内容/形式”等复合值拆成叙事职责、业务概念、证明方式、动作和镜头语言候选；
3. 生成稳定 `template_id` 和 tag 映射建议，同时输出 unmapped、冲突和重复候选；
4. 先生成 dry-run 迁移报告，不直接写入 `active` 词典或模板；
5. 业务负责人确认定义，证据/合规负责人确认 claim 与 proof 边界，再发布 v1 revision；
6. 无法映射的值保持 `candidate` 或 `review_required`，不得被模型自动启用；
7. 重复模板通过 `superseded_by` 合并，旧 ID 不复用、不删除审计关系。

ID 使用业务可读、发布后不可变的命名，例如 `tablemat.proof.oil_wipe`；首次迁移由规则生成候选 ID，人工确认后冻结。发生同名碰撞时附加稳定语义限定词，不能按运行次数追加随机序号。旧行一对多时，每个拆分模板拥有独立 ID 并共同引用同一 `legacy_row_id`；多对一时，目标模板记录全部 legacy row 引用。

每次 dry-run 至少输出：

```text
migration_run_id
source_table + source_snapshot_hash
legacy_row_id → proposed_tag_ids / proposed_template_ids / proposed_revisions
split_or_merge_relations
unmapped_values + conflicts + duplicate_candidates
reviewer_decisions
output_content_hash
```

`migration_run_id + source_snapshot_hash + mapping_rules_version` 是幂等键：相同输入重跑必须得到相同 proposed IDs 和 output hash。只有冲突清零、所有 `review_required` 有决定、引用 ID 均存在且输出 hash 被业务负责人确认后，才可发布新 revision；任务随后显式 pin 发布后的 taxonomy/template/claim hashes，不能引用未提交的 dry-run 草案。

典型拆分示例：

| 旧表内容 | 标签字典 | 业务模板 |
|---|---|---|
| 内容形式=种草；标签=痛点；形式=刮到桌面油漆 | `funnel_stage=seeding`、`narrative_role=problem`、`problem.surface_paint_damage` | `tablemat.problem.scratch_risk`，要求同时展示裸桌/受损风险或经批准的风险表达 |
| 内容=环保；形式=检测报告 | `benefit.environmental_safety`、`evidence_carrier.test_report` | `tablemat.trust.test_report`，模板只规定报告展示方式；具体 claim 仍需 Brief 授权 |
| 核心卖点=防油；形式=倒油+擦拭 | `benefit.oil_resistance`、`action.pour_oil`、`action.wipe`、`result.surface_clean` | `tablemat.proof.oil_wipe`，要求前置/动作/结果完整连续 |

## 15. 端到端示例

以参考片前三秒“倒油后一擦即净”为例：

1. **参考事实**：Gate 1 将 0.0–2.8 秒切成 `shot_001`、`shot_002`，保存切点、关键帧和音轨到 `recipe.json`。
2. **业务解释**：Blueprint 把两段 shot 归为 `reference_beat01`，标记 `hook + result_first + tablemat.proof.oil_wipe`，并记录承诺在后续 proof beat 兑现。
3. **目标结构**：Brief 允许“易清洁”但不允许绝对化说法。Blueprint 保留钩子职责，把目标 beat 编译成 `fragment01=油污前置`、`fragment02=擦拭动作`、`fragment03=干净结果`，三者同属一个 action group。
4. **覆盖预判**：素材目录发现同一源文件的前置和擦拭时间窗，但唯一结果画面被手遮挡，因而结果 fragment 没有硬资格候选，该证明组为 `missing`；Blueprint 质量仍可通过，生产就绪度被阻塞并输出补拍结果镜头。如果三个阶段各有候选但无法满足同源/连续性，才记为 `partial`。
5. **补素材后重算**：新素材被增量建档，权威 coverage 找到满足同源、顺序、授权、技术和粗时长要求的组合。
6. **匹配与批准**：Retrieval 逐 fragment 排候选，在 action group 层确认完整性；Gate 3 批准每段来源、SHA、叠字决定和宽范围。
7. **证据与生成**：`script_evidence_matrix.json` 将“油渍轻轻一擦就干净”映射到批准时间窗；Gate 4 批准脚本并完成真实 TTS 后，Reconstruction 才在宽范围内确定精确裁点。

这个例子体现了核心平衡：好结构先保留，缺口明确阻塞生产；素材补齐前不拿无关画面凑，也不悄悄删除钩子或弱化证明链。

## 16. 首期 MVP 与验收标准

首期不建议一次建立全品类、全场景词库。更可控的 MVP 是：

- 选择 1 个产品类目和 1 条完整参考视频；
- 建立约 10–20 个高频受控标签、3–5 个业务镜头模板；
- 对一批真实视频/图片建立时间段目录，至少包含完整、部分、缺失和未知四类样本；
- 人工完成一次 `shot → beat → fragments → asset segments → coverage → Gate 3` 映射；
- 对一份人工 fixture 执行 `fragment_plan → material_manifest → reconstruction_timeline` 投影检查：三份产物保持相同 `fragment_id`，精确裁点只在 Gate 3 宽范围内收窄，beat/template 只作追溯，Reconstruction 不回查目录重新选择素材；
- 使用当前 `manual-contract-only` 边界验证业务口径，不宣称已有 Track B 自动执行能力。

这套体系达到可用状态时，应满足：

- 同一业务概念在参考片、Blueprint、模板和素材中使用稳定 ID；
- 每个参考业务 beat 可追溯到一个或多个原始 shot；
- 每个目标 beat 都有叙事职责、模板、结构优先级和证据要求；
- 每个候选素材都定位到具体时间窗，而不是只标整个文件；
- 连续动作能区分前置、过程和结果，并检查完整性；
- 素材不足时能输出具体缺口，而不是笼统报告“匹配度低”；
- 模板硬条件、证据资格和视觉相似度分开计算；
- Blueprint 质量与素材生产就绪度分开评价；
- 覆盖按业务需求组计算，不把同一证明链的多个标签重复算成多个缺口；
- 高价值结构不会因当前素材不足被自动删除；
- Gate 3 宽范围与 Reconstruction 精确裁点保持分离；
- 至少一个拒绝用例能证明：视觉很像但 claim/动作/授权不合格的素材不会入选；
- 同一输入和相同 revision/hash 能得到稳定的 beat-to-fragment 与覆盖结论；
- 业务人员不需要理解底层 FFmpeg、哈希或时间轴即可维护镜头模板。

## 17. 当前实施边界

当前 V2 仍处于 `2.0.0-alpha.1`、`manual-contract-only` 阶段。本文定义的是业务分类与未来 Track B 执行器应消费的数据模型，不表示当前仓库已经具备自动业务 beat 识别、模板匹配或素材时间段建档执行器。

第一阶段可以先以人工维护的标签词典、业务镜头模板表和素材时间段表配合现有 Gate 流程验证口径；确认业务分类稳定后，再将其固化为可缓存、可增量重算的机器契约和执行器。
