# 参考视频复刻创作质量升级设计

## 1. 文档状态

- 状态：设计基线，待用户书面复核
- 日期：2026-08-19
- 适用对象：`remix-reference-video` V2 新任务、审核工作台和后续监督运营试用
- 前置设计：[业务视频工作台重构设计](2026-08-18-business-video-workbench-design.md)
- 质量基础：[质量加固设计](2026-08-18-remix-quality-hardening-design.md)
- 评价口径：[视频质量、线上反馈与生成过程业务评价体系](2026-08-16-video-quality-online-feedback-generation-process-design.md)

本文定义参考视频复刻从“可审计地生成成片”升级为“以创作目标牵引、可比较策略、可评价质量、可局部重做”的下一阶段能力。它不引入开放式 Agent 对话，不改变 `pipeline_state.json` 的审批权威，不解除普通 V2 production lock，也不允许生成模型绕过声明、素材证据或现有 Gate。

## 2. 当前任务复盘与事实边界

`tablemat-mix-v2` 已完成 Stage 0、隔离 cold/hot Gate 1–5、真实 TTS、字幕、正式渲染和最终技术校验：

- cold：`gb-cold-1786890259`，成片 10.20 秒；
- hot：`gb-hot-1786938266`，成片 9.96 秒；
- 两侧成片均为 1080×1920、60fps，含 H.264 视频轨和 AAC 音轨；
- 两侧 Gate 1–5 均已独立批准，成片、字幕、渲染报告和最终校验报告均已登记；
- `gb_measurement.json` 状态仍为 `measured_pending_review`，V1 可比性和 owner G-B 阈值复核尚未完成。

这次任务证明了生产链可以按契约执行，不等于内容质量已经达标。cold 批准口播实际为四句同构卖点：

1. 透明桌垫，极简透明。
2. 透明桌垫，防水。
3. 透明桌垫，防油。
4. 透明桌垫，进口冰晶粒。

该任务的 Gate 2 冻结基线早于 `narrative_contract_v1`，按在飞兼容规则走 legacy DAG，没有生成 `narrative_coherence_report.json` 和 `visual_layout_report.json`。因此后续已经合并的叙事与布局加固不能反向证明这两条历史成片已获得相同质量提升。历史成片只作为 `baseline_v0` 保留，不原地重写、不复用批准；验证新能力时必须以相同冻结输入新建任务版本。

## 3. 需要解决的问题

### 3.1 工作台看见阶段，但看不懂阶段成果

当前工作台已投影 `process.execution[]`、`artifacts[]` 和 `quality_checks[]`，但关键产物主要停留在诊断信息或文件名层。运营无法在右侧阶段内直接回答：

- 这个阶段采用了什么策略；
- 产生了哪些候选，为什么选当前版本；
- 当前产物服务哪个创作目标；
- 哪个问题应该改哪个产物，修改后影响什么。

### 3.2 拆解和复刻均只有单一路径

现有拆解偏向镜头边界和参考事实，复刻偏向按参考顺序生成 Blueprint。它们缺少显式策略选择，也没有保留候选比较和策略版本，难以适应“结构还原”“节奏模仿”“商品证据优先”或“受素材约束重组”等不同任务。

### 3.3 脚本只有事实约束，缺少创作目标

证据矩阵解决“能不能说”，尚未充分解决“为什么这样说、先说什么、如何承接、看完做什么”。脚本、分镜和成片之间也没有共享的目标标识，导致脚本容易退化为卖点列表，后续镜头只完成素材填槽。

### 3.4 成片缺少内容级闭环

现有 L0 技术校验可以发现流、时长、时间轴和硬规则问题，但一致性、连贯性、前三秒、高光密度、镜头功能完成度和局部 AI 增强尚未成为正式产物与失效契约。

## 4. 总体目标与边界

### 4.1 目标

- 用一个冻结的创作目标贯穿拆解、复刻策略、脚本、分镜、素材、成片和评价。
- 同一参考片可以执行不同的版本化拆解策略，并保留可比较产物。
- 同一拆解结果可以形成不同复刻策略，并在 Gate 2 原子选择。
- 脚本从“证据句编译”升级为“受事实边界约束的目标驱动创作”。
- 成片可定位到分镜级问题，允许受控局部重做或 AI 增强，而不是每次只能整片返工。
- 工作台可直接查看关键产物、候选差异、评价结果、修改方法和影响范围。

### 4.2 非目标

- 不建设开放式 Agent 聊天或自由提示词执行器。
- 不在浏览器内直接调用 shell、TTS 或视频生成 provider。
- 不建设完整多轨剪辑器，不开放拖拽改写 canonical timeline。
- 不由 AI 生成或推断新的产品事实、卖点、Offer 或声明授权。
- 不以离线评分预测或冒充线上转化、利润和因果增量。
- 不自动把一次投放结果提升为默认生成策略。

## 5. 目标驱动的数据主线

`creative_objective.json` 由 Blueprint 在 Gate 1 批准后、Gate 2 审核包生成前创建。生产者只能读取 Stage 0 冻结 `project_brief.json` 的 `approved_claims[]`、`forbidden_claims[]`、受众、平台和目标字段，以及 Gate 1 已批准的拆解结果；输入必须绑定该 Brief 和 Gate 1 decision scope 的哈希，不得从参考片或素材文字推断产品事实。Brief 中的 `approved_claims[]` 表示用户在 Stage 0 授权进入方案设计的声明边界；Gate 2 再批准本次实际使用的 claim、顺序和证据要求，两者是单向收窄关系，不循环引用。目标文件声明 `objective_contract_version=creative_objective_v1`，是 Gate 2 的候选内容目标，不是审批权威，也不替代 Brief。至少包含：

- `objective_id` 和 `objective_version`；
- 平台、受众、产品和视频时长包络；
- 唯一核心传播信息；
- 期望观看后动作；
- 前三秒创作假设；
- 必须出现的已批准 claim、证据要求和禁用声明引用；
- 商品最晚出现时间目标；
- CTA 要求或明确的 `not_required`；
- 当前目标集合。每个目标包含 `required` 和非负 `weight`；同一文件内全部 weight 必须归一化为 `1.0`。

Gate 2 审核包必须同时绑定 `creative_objective.json`、`remix_strategy_candidates.json`、`content_baseline.json`、`mutation_plan.json` 和 `coverage_precheck.json` 的哈希，以及当前 `selected_remix_strategy_id`。只有 Gate 2 对该原子包批准后，`creative_objective.json` 才成为下游输入。`coverage_precheck.json` 只表示 Gate 2 前非权威可实现性预判；权威 `coverage_report.json` 仍在 Gate 2 通过后按批准目标和策略重算。

所有下游候选与最终产物必须引用同一个 `objective_id`：

```text
recipe -> decomposition_bundle -> Gate 1 selected_decomposition_id
  -> creative_objective / remix_strategy_candidates
  -> Gate 2 selected_remix_strategy_id
  -> script_candidates / production_script_candidate
  -> fragment_plan / reconstruction_timeline
  -> shot_quality_report / final_content_diagnostic_report
  -> video_version_id
```

变更按以下边界处理：

| 变化 | 恢复方式 |
| --- | --- |
| 参考视频、产品身份、目标平台、受众、素材根/素材池身份或画幅/分辨率/fps 发生变化 | Stage 0 身份事实变化，必须从新冻结快照创建新 run，不允许 ChangeService 在位改写 |
| 参考切点、语义段或选中拆解策略变化 | 返回 Gate 1，使 Gate 1 及全部下游 stale |
| 同一受众和声明边界内的核心信息选择、期望动作、目标权重、商品出现目标或 CTA 变化 | 返回 Gate 2，使 Gate 2 及全部下游 stale |
| `approved_claims[]`/`forbidden_claims[]` 或时长包络变化，但产品、平台、受众和素材池不变 | 创建版本化 Brief revision 和新冻结输入快照，保留旧版本；Gate 2 及下游重新生成和批准，不复用旧决定 |
| 已批准目标内的脚本表达变化 | 按现有 copy change 返回 Gate 4 生成前 |
| provider、音色、语速或发音设置变化 | 返回 Gate 4 生成前，重新执行 voice preflight、TTS、听审和下游；不重新执行拆解、复刻或脚本事实校验 |

`creative_objective.json` 不能修改或覆盖 Stage 0 的产品、平台、受众和输出身份字段，只能引用其哈希并在冻结边界内做 Gate 2 选择。

## 6. 多策略拆解

### 6.1 策略集合

首版只提供四种版本化策略，不允许任务运行时任意发明策略名称：

| 策略 ID | 主要回答 | 核心产出 |
| --- | --- | --- |
| `structure_semantic_v1` | 参考片在讲什么、每段承担什么叙事功能 | 叙事段、镜头功能、信息顺序、开场与收束 |
| `rhythm_visual_v1` | 参考片如何抓注意力并维持节奏 | 切点、运动、景别、视觉变化、节奏峰值 |
| `evidence_action_v1` | 哪些画面在证明商品与动作 | 商品出现、功能演示、结果证据、声明风险 |
| `hybrid_commerce_v1` | 如何综合结构、节奏和商品证据 | 三类信号的统一拆解，作为抖音电商默认策略 |

每次运行可生成 1–3 个候选策略结果；默认生成 `hybrid_commerce_v1`，仅在用户要求比较或任一策略结果包含低置信度段时增加候选。Gate 1 审核包绑定 `recipe.json`、`decomposition_bundle.json`、当前 `selected_decomposition_id`、package hash 和 `state_revision`。批准决定把选中 ID 和 bundle hash 写入 `pipeline_state.json` 的当前 Gate 1 decision scope，不新增 Gate。候选文件自身不携带 approval 字段。

### 6.2 拆解产物

新增 `decomposition_bundle.json`，包含：

- 1–3 个候选的稳定 `decomposition_id`、策略 ID、实现版本和输入哈希；
- 对 `recipe.json` 物理镜头 ID/边界的引用，以及候选自己的语义段边界；
- 每段叙事功能、动作、商品可见性和证据角色；
- 钩子区间、节奏峰值和高光候选；
- 可疑切点、低置信度项和人工修订；
- 候选间的结构化差异。

`recipe.json` 继续是物理边界和参考流的唯一事实层，不因策略选择被改写。`decomposition_bundle.json` 不复制或重新定义物理边界，只引用 recipe shot ID；策略解释和语义结论进入候选，避免把推断混入客观事实。下游始终从 Gate 1 decision 读取选中 ID，并校验其 bundle hash 与当前批准一致。

## 7. 多策略复刻

### 7.1 策略集合

| 策略 ID | 优先目标 | 适用条件 | 主要风险 |
| --- | --- | --- | --- |
| `structure_fidelity_v1` | 保持参考结构与节奏 | 自有素材覆盖充分 | 可能复制参考片弱点 |
| `conversion_adaptation_v1` | 强化前三秒、商品证据和 CTA | 目标明确且证据充分 | 与参考结构偏差更大 |
| `asset_constrained_v1` | 在现有素材能力内形成完整叙事 | 素材明显受限 | 创意上限受素材制约 |
| `balanced_remix_v1` | 平衡结构还原、转化和素材可实现性 | 默认生产场景 | 单一维度不一定最优 |

Gate 2 前由 Controlled Mutation 生成 `remix_strategy_candidates.json`，最多包含三个候选。每个候选必须说明保留、替换、压缩、扩展、重排和 fallback，并基于非权威 `coverage_precheck.json` 计算目标覆盖、素材可实现性与参考偏差。Gate 2 原子批准目标、候选文件、内容基线、Mutation、覆盖预判和唯一 `selected_remix_strategy_id`；选中 ID 和候选文件 hash 写入当前 Gate 2 decision scope。Gate 2 通过后，权威 coverage 只读取该 decision 选中的候选。

### 7.2 失效规则

- 切换拆解策略：Gate 1 及全部下游失效；
- 切换复刻策略：Gate 2 及全部下游失效；
- 修改策略内部文字但不改变选中策略、结构或声明：按实际受影响对象返回最早 Gate；
- 未选候选只供比较，不进入素材匹配、脚本、TTS 或渲染。

## 8. 脚本与分镜升级

### 8.1 脚本生成边界

脚本生成器只能读取：

- `creative_objective.json`；
- Gate 2 已批准内容基线、复刻策略和 Mutation；
- Gate 3 已闭环的 claim/evidence；
- 已批准分镜功能、时长预算和禁用声明。

它可以改写表达和承接，但不能新增产品事实。任何生成模型都必须记录 provider、model、prompt template version、生成参数、输入哈希和确定性校验结果；支持 seed 时必须冻结 seed。候选一经进入审核包即按输出哈希不可变，复现指能够重建相同输入、配置和审计链，不承诺外部非确定性 provider 每次生成 byte-identical 文本。生成失败时保留上游产物并返回可恢复状态。

### 8.2 候选与选择

脚本节点按以下顺序接入现有 Gate 3 到 Gate 4 DAG：

```text
summarize-gate3
  -> build-narrative-coherence
  -> generate-script-candidates
  -> validate-script-candidates
  -> select-script-candidate
  -> build-production-script
  -> voice-preflight
  -> Gate 4 pre-generation package
```

`build-narrative-coherence` 继续产生确定性的角色、承接、证据和禁用声明底线。`generate-script-candidates` 只在该报告不为 `blocked` 时生成 2–3 个有明确创作假设的候选，例如“问题解决”“演示证明”“场景收益”。`script_candidates.json` 中每个候选必须包含：

- `script_candidate_id`、创作假设和目标覆盖；
- 逐句文本、`objective_id`、`narrative_role` 和 `required_actions`；
- claim/evidence 引用、预期画面、语音时长估算；
- `continuity_before`、`continuity_after`；
- 前三秒、商品出现、证明、结果和 CTA 的完成情况；
- 风险、未覆盖目标和候选间差异；
- provider、model、prompt template version 和生成输入哈希。

`validate-script-candidates` 逐候选重新执行 §8.3 的声明、证据、禁用声明、承接、目标覆盖和预算检查，生成 `script_candidate_validation_report.json`。失败候选保留在列表中并记录淘汰原因，但不得进入选择集合。`select-script-candidate` 只从 `passed` 候选中选择，采用版本化 `script_candidate_rank_v1`：依次按 required 目标覆盖数降序、加权目标覆盖率降序、最小画面预算余量降序，最后按 `script_candidate_id` 字典序升序打破平局。运营也可在 Gate 4 批准前提交另一个 `passed` 候选；每次选择都重新物化现有 `production_script_candidate.json` 和 `voice_preflight.json`，并重建 Gate 4 生成前审核包。

`production_script_candidate.json` 仍是唯一待批准生产脚本，不新增 `approved_script_storyboard.json`，也不让 `script_candidates.json` 成为审批权威。

Gate 4 生成前审核包绑定 `script_candidates.json`、候选验证报告、选中 ID/哈希、`production_script_candidate.json`、`voice_preflight.json`、package hash 和 `state_revision`。批准后仍只生成现有 `approved_production_script.json`；它保存批准文本、声音设置和对当前 `pipeline_state.json` decision scope/package hash 的不可独立生效快照，审批有效性始终只由 `pipeline_state.json` 判断。TTS 不读取候选文件。

### 8.3 脚本机器门禁

以下任一项失败时不得 TTS：

- 声明证据不是 100% 闭环，或命中禁用声明；
- 首段没有钩子功能，或商品出现晚于目标且无批准例外；
- 连续两个以上片段只罗列卖点、没有情境、动作、证据或结果推进；
- 缺少开场、推进、证明和收束中的必需角色；
- 句间承接未知，或口播预计时长超过画面预算；
- 任一 `required=true` 创作目标没有脚本行和预期画面覆盖。

机器门禁不替代人工判断。通过只表示候选满足结构与证据底线，Gate 4 仍需运营判断表达是否自然、有吸引力且符合受众。

### 8.4 脚本到分镜

`production_script_candidate.json` 的每一行同时携带 `objective_id`、`script_line_id`、`narrative_role`、`required_actions`、`evidence_row_ref` 和 `visual_intent`。`approved_production_script.json` 原样保留这些已批准引用，`reconstruction_timeline.json` 再把它们投影到真实语音时间。一个镜头没有明确目标或动作时不得仅因“有素材”进入生产。

## 9. 成片一致性、高光与局部 AI 增强

### 9.1 分镜级质量

Gate 4 生成后听审批准后，流程按“生成审核代理 → `validate-shot-quality` → 代理/边界检查 → 正式渲染”执行。该节点读取批准脚本、material manifest、精确时间线、审核代理帧、叙事报告和布局报告，生成非 L1 权威的生产诊断 `shot_quality_report.json`，逐镜检查：

- 商品身份、颜色、形态和品牌一致性；
- 场景、人物、光线和构图连续性；
- 动作开始、过程和结果是否完整；
- 画面是否完成对应脚本目标和证据角色；
- 源文字、水印、字幕和主体是否可读且不冲突；
- 相邻镜头是否重复、突跳或语义断裂；
- 前三秒是否具备视觉变化、商品信号和钩子信息；
- 高光候选是否达到当前策略要求。

报告状态为 `passed|manual_review|blocked`。确定性的商品身份错误、证据/动作缺失、文字被裁切、时间线越界或 required action 未完成为 `blocked`，不得正式渲染；主观连续性、高光强度或审美问题为 `manual_review`，不增加新 Gate、不阻断正式渲染，但必须携带到 Gate 5 供最终人工判断，不能静默显示为 passed。修改脚本使 Gate 4 生成前及下游失效；替换素材或范围使 Gate 3 material selection、Gate 3 evidence closure 及全部下游失效；仅调整批准宽范围内精确裁点时使 timeline、代理、该报告和下游失效。

### 9.2 高光片段

高光不是单纯的高运动片段，而是同时满足“目标重要、视觉清楚、信息有增量、与前后片段形成推进”的片段。每个高光候选记录：

- 对应目标和预期业务作用；
- 起止时间与来源；
- 当前问题和建议动作；
- 可执行操作：保留、替换、重新裁点、重新生成或局部增强。

### 9.3 AI 增强边界

AI 增强只作为分镜级受控操作：

- 生成新素材版本，禁止覆盖用户原素材或已批准副本；
- 必须绑定原分镜、目标、输入素材、provider/model、prompt version 和输入输出哈希；
- 不得改变商品事实、可见声明、品牌标识或证据含义；
- 新输出重新进入素材资格、Gate 3 material selection、Gate 3 evidence closure、布局和连续性检查；
- 采用增强候选固定返回 `gate3_material_selection`，并使 `gate3_evidence_closure`、Gate 4 和 Gate 5 全部 stale；如果还改变声明或结构，则继续返回 Gate 2；
- 首版不自动采用增强结果，只生成候选并由 Gate 3 material selection 选择。

`propose-shot-enhancement` 不是默认 DAG 节点，只在运营对指定分镜发起“重新生成/局部增强”修改后运行。它读取当前分镜诊断、批准素材和明确的修改意图，生成 `enhancement_plan.json`；provider adapter 生成的候选写入隔离 candidate 目录。计划状态为 `ready|failed`，不阻塞未发起增强的正常生产。候选失败时保留原批准素材和当前 Gate 状态，不得自动替换。

### 9.4 成片级质量

正式渲染与 `final_validation_report.json` 完成后、Gate 5 审核包生成前，新增 `build-final-content-diagnostic` 节点，生成 `final_content_diagnostic_report.json`，聚合分镜结果并独立展示：

- 前三秒完成度；
- 脚本与视觉连贯性；
- 商品与场景一致性；
- 说服与证据强度；
- 节奏、高光和观看体验；
- 目标覆盖率；
- L0 技术与合规结果引用。

该报告是生产诊断，不是 Track C `content_quality_profile`、L1 评价快照或 L2 经营结论。它使用 `ready|stale` 生命周期，状态为 `passed|manual_review|blocked`：只有从现有 L0、证据或分镜确定性阻断项派生的问题可以为 `blocked`；主观内容维度只能为 `manual_review`。Gate 5 包展示它的分项和来源，但官方 L1 仍只有在独立 evaluation context、policy version、证据和 reviewer 完整时由 Track C 创建不可变快照。

## 10. 工作台关键产物设计

右侧五阶段步骤条保持不变，每个阶段新增业务化“关键产物”区域：

| 阶段 | 必须可见的关键产物 |
| --- | --- |
| 参考拆解 | 拆解策略、镜头/语义段、钩子与高光、候选差异、可疑切点 |
| 复刻方案 | 创作目标、复刻策略候选、目标覆盖、结构变化、素材可实现性 |
| 素材与证据 | 分镜意图、候选素材、证据关系、缺口、增强候选 |
| 文案与声音 | 脚本候选、逐句目标与证据、连贯性、声音预算、批准版本 |
| 成片终审 | 成片、分镜质量、前三秒、高光、L0/L1/P 和交付文件 |

工作台投影增加：

- `stage_artifacts[]`：阶段、业务名称、状态、摘要、缩略图和预览引用；
- `artifact_versions[]`：候选与批准版本、策略 ID 和差异摘要；
- `lineage_edges[]`：目标到成片的输入输出关系；
- `evaluation_summary`：阶段北极星、约束指标、证据来源和未测量原因；
- `change_impact`：修改对象、最早返回阶段、失效产物、是否重做媒体和预计影响。

交互规则：

- 点击阶段产物打开业务详情抽屉，不把原始 JSON 作为默认正文；
- 详情内可比较候选、查看证据、定位中央成片/时间线并发起结构化修改；
- 中央区域继续固定显示阶段主媒体，左侧或右侧选择不能替换它；
- 缺少新契约产物的历史任务显示“旧契约未生成”，不得推断或伪造；
- hash、schema、绝对路径和原始事件只进入诊断信息。

## 11. 分阶段评价体系

### 11.1 共同规则

- 每个过程只定义一个阶段北极星，其余指标作为约束和诊断。
- 阶段北极星衡量该过程是否完成职责，不替代最终业务北极星。
- 缺少真实测量时使用 `not_measured`，不得填零或用候选置信度代替。
- Gate 1 拆解结果绑定 recipe/bundle hash、策略版本和 `run_id`；Gate 2 之后的结果再绑定 `objective_id`、artifact hash、policy version 和 `video_version_id`。

### 11.2 指标定义

| 过程 | 阶段北极星 | 定义 | 计量主键 | 主要约束指标 |
| --- | --- | --- | --- | --- |
| 拆解 | Gate 1 首轮结构通过率 | 首个有效 Gate 1 审核包即批准的 run 数 / 已完成 Gate 1 首轮审核的 run 数 | `run_id + gate1 + first_package_revision` | 关键镜头漏检率、边界修订量、策略低置信度率 |
| 复刻方案 | 加权创作目标覆盖率 | 已满足目标权重 / 全部目标权重 | `objective_id + objective_hash + gate2_decision_id` | 素材可实现率、证据可实现率、参考结构偏差 |
| 脚本 | 脚本首轮业务通过率 | 首个有效 Gate 4 生成前审核包即批准的 run 数 / 已完成该首轮审核的 run 数 | `run_id + gate4_pre_generation + first_package_revision` | 证据闭环率、连贯性、前三秒、预算超限率 |
| 分镜与素材 | 分镜意图完成率 | `shot_quality_report` 中全部 required actions 为 passed 的分镜数 / 已批准生产分镜数 | `video_version_id + shot_id + shot_report_hash` | 缺素材率、动作完整率、重复率、一致性缺陷 |
| 成片 | L1 内容质量合格率 | 通过当前 L1 policy 的视频版本数 / 已完成离线评价版本数 | `video_version_id + evaluation_context_id + policy_version + snapshot_id` | L0 100% 通过、前三秒、高光、连贯性、一致性 |
| 工作台 | 有效决策时间 | 从打开当前审核包到有效决定的活跃时长 | `review_session_id + package_revision` | 缺陷逃逸率、修改成功率、返工轮数、冲突率 |
| 线上经营 | 每千次曝光贡献利润 | 现有质量体系 §7.2 冻结口径 | `evaluation_context_id + attribution_window + evaluation_snapshot_id` | 3 秒留存、完播、点击、支付、退款和证据等级 |

计量契约固定如下：

- Gate 首轮通过率和返工轮次按表中 Gate package 主键去重；其他指标严格使用各自行的计量主键，候选数量不进入任何 run/video 分母。首个绑定当前输入哈希且状态为 `awaiting_user` 的 package 是“首轮”，任何 `changes_requested|rejected` 后生成的新 revision 都是返工轮。
- 目标权重来自 Gate 2 已批准的 `creative_objective.json`，必须非负且总和为 `1.0`；`required=true` 目标未满足时覆盖率仍可计算，但机器门禁失败。
- required action 的观察来源固定为 `shot_quality_report.shots[].action_results[]`，每项必须引用审核代理帧或时间范围；缺证据为 `not_measured`，不能计为 passed。
- 工作台增加 `review.session_started`、`review.visibility_changed`、`review.activity`、`review.active_tick` 和 `review.decision_submitted` 事件。客户端每 10 秒最多发送一个 `active_tick`，且只在页面可见、最近 30 秒发生过键盘/鼠标/触控输入、没有 workbench API 请求 pending 时发送；提交决定时再发送一个 `0..10` 秒的 final partial tick。服务端按 session+连续 sequence 去重并累加 tick 的 `delta_seconds`。有效决策时间是当前 package revision 从 session start 到有效 decision 之间的 tick 总秒数；网络等待、后台和空闲不会产生 tick。sequence 有缺口、缺 session/decision 边界或 final partial tick 时为 `not_measured`；完整序列的零秒值才是合法测量结果。
- 首版不设置未经校准的阶段通过率阈值；指标先作为监督运营测量。任何后续阈值都必须进入版本化 policy 并保留历史计算结果。

## 12. 状态、审批与兼容

- 现有 Gate 1–5 和两个 Gate 3/4 子状态保持不变。
- Gate 1 选择拆解策略，Gate 2 原子选择复刻策略与内容基线，Gate 4 生成前选择脚本候选。
- `pipeline_state.json` 仍是唯一审批权威；候选自身不能携带或替代 Gate approval。
- 新 V2 产物使用五字段 envelope、registry 注册、输入哈希和 `ready|stale` 生命周期。
- 所有新产物先定义 JSON Schema、注册到 canonical registry，并由 artifact validator 校验；DAG 节点、Native adapter、Gate package、ChangeService 失效闭包和工作台投影必须同步登记。
- 已冻结且缺少 `creative_objective_v1` 的 V1/V2 历史任务只能按原 DAG 续跑。首版不提供在位迁移；要使用本设计能力必须从同一冻结输入快照创建新的 run 和 `video_version_id`，不得通过返回某个 Gate 给旧 run 静默变轨。
- cold/hot 不复用候选选择、人工决定或审批；技术 cache 仍遵守现有 G-B 边界。
- 普通 V2 production lock、共享生产缓存和一线发布条件保持不变。

### 12.1 新产物与执行契约

| 产物 | 生产者与执行点 | 权威输入 | Gate/消费者 | 阻断与失效 |
| --- | --- | --- | --- | --- |
| `decomposition_bundle.json` | Gate 1 包生成前的 decomposition adapters | `recipe.json`、参考帧 | Gate 1 package；Blueprint | 无合格候选阻断 Gate 1；recipe 或策略配置变化使其及全部下游 stale |
| `creative_objective.json` | Gate 1 后 Blueprint | frozen Brief 的 `approved_claims[]`/`forbidden_claims[]`、Gate 1 decision | Gate 2 原子 package；策略、脚本、评价 | 缺 required 目标阻断 Gate 2；目标变化使 Gate 2 及下游 stale |
| `remix_strategy_candidates.json` | Gate 2 前 Controlled Mutation | 目标、选中拆解、`coverage_precheck.json` | Gate 2 原子 package；权威 coverage、Retrieval | 无可实现候选阻断 Gate 2；选择变化使 Gate 2 及下游 stale |
| `script_candidates.json` | `generate-script-candidates` | Gate 2 批准包、Gate 3 evidence、叙事报告 | 候选选择；物化 `production_script_candidate.json` | 全部候选失败阻断 Gate 4 pre；文案/素材/证据变化按 DAG 闭包 stale |
| `script_candidate_validation_report.json` | `validate-script-candidates` | 脚本候选、目标、证据、叙事报告、画面预算 | 候选选择；Gate 4 pre package | 只允许 passed 候选被选择；候选或任一校验输入变化即 stale |
| `shot_quality_report.json` | Gate 4 post 批准后代理生成后的 `validate-shot-quality` | 批准脚本、material、timeline、代理帧、叙事/布局报告 | 正式渲染准入；Gate 5/工作台 | 确定性问题 blocked，主观问题 manual_review；脚本/素材/裁点按 §9.1 失效 |
| `enhancement_plan.json` | 用户发起修改后的可选 `propose-shot-enhancement` | 指定分镜、诊断、批准素材、修改意图 | Gate 3 material selection 候选 | 不属于默认 DAG；采用候选使 Gate 3 两子状态及下游 stale |
| `final_content_diagnostic_report.json` | 正式渲染后的 `build-final-content-diagnostic` | 成片、最终校验、shot report、批准目标/策略 | Gate 5 package；工作台 | 确定性硬问题 blocked，主观项 manual_review；任何成片输入变化即 stale |

候选 artifact 和机器诊断都不能携带 approval。`production_script_candidate.json`、`approved_production_script.json`、`pipeline_state.json` 和 Track C 不可变评价快照继续保持各自现有权威边界。

## 13. 失败与恢复

- 无合格拆解候选：停在 Gate 1，展示低置信度段和人工修订建议。
- 复刻目标不可实现：停在 Gate 2，明确缺素材、缺证据或目标冲突，不用无关素材凑数。
- 脚本候选全部失败：事实/目标冲突返回 Gate 2；已选素材本身缺少所需动作返回 `gate3_material_selection` 并使 evidence closure stale；素材具备动作但证据映射缺失才返回 `gate3_evidence_closure`；只有表达问题时停在 Gate 4 生成前并在批准边界内重写。任何情况都不调用 TTS。
- AI 增强失败或输出不合格：保留原分镜版本，不替换当前批准素材。
- 分镜诊断失败：脚本问题返回 Gate 4 生成前；素材、动作或证据问题返回 `gate3_material_selection` 并使 `gate3_evidence_closure` stale；结构或声明问题返回 Gate 2。
- 成片诊断失败：按报告中的 `earliest_recovery_gate` 返回 Gate 2、Gate 3 对应子状态或 Gate 4；创建新 `video_version_id`，原版本和正式评价快照保持不变。
- 评价来源缺失：显示 `not_measured` 和补测方法，不阻塞与该指标无关的上游工作。

## 14. 实施顺序

1. P0a 契约基础：schema/registry、DAG 节点、Gate package 绑定、ChangeService 闭包、事件计量和 baseline fixture。
2. P0b 工作台关键产物：先把现有真实产物业务化展示，并建立 lineage、版本抽屉和决策计时；不伪造尚未生成的新产物。
3. P1 策略层：实现多策略拆解，再实现 `creative_objective`、复刻候选和 Gate 1/2 原子选择。
4. P2 脚本层：在现有 narrative DAG 中插入候选生成/选择，扩展生产脚本与分镜目标绑定。
5. P3a 成片诊断：实现分镜质量、前三秒、高光和非权威成片诊断。
6. P3b 可选 AI 增强：只在 P3a 监督样本证明存在重复且可修复的分镜问题后接 provider adapter；不作为 P3a 验收依赖。
7. Track C 校准：用监督运营样本冻结正式 L1 和阶段 policy，再接入真实 L2 线上反馈。

P0b 不依赖生成模型，可先交付；P1–P3 必须在隔离 V2 新任务中验证，不回写当前 `tablemat-mix-v2` 历史批准产物。每个阶段先完成契约和失败测试，再接生产 adapter 与工作台。

## 15. 基线比较协议

- 唯一历史比较对象为 cold run `gb-cold-1786890259`，记为 `baseline_v0`；hot 只用于 cache/效率测量，不作为第二条内容基线。
- `baseline_v1` 是使用新契约创建的一条新 cold run，必须复用同一 `g_b_frozen_input_snapshot`；允许变化项严格限定为下条所列的创作与制作选择。
- 两版各自创建包含自身 `video_version_id` 的独立 `evaluation_context_id`，再用同一个 `comparison_id` 关联；记录策略版本、诊断 policy 和 Track C policy。
- 比较中固定参考片哈希、Brief、素材池及全部源素材哈希、声明范围、受众、平台、音色/语速和输出规格。允许变化的只有选中拆解/复刻策略、脚本、同一素材池内的素材选择与范围、时间线和由此产生的成片；P3b AI 增强在首次 baseline 比较中关闭，避免增加额外变量。
- owner 使用同一份盲评表分别判断前三秒、脚本连贯性、目标覆盖、画面一致性、高光与观看体验，状态固定为 `low|ordinary|high`，同时保留问题和证据时间点。
- 比较通过要求：两版 L0 都通过；v1 所有 required 目标与声明证据通过；v1 的前三秒和脚本连贯性均严格高于 v0；画面一致性、高光与观看体验均不低于 v0；没有引入未批准事实、素材或增强结果。
- 有效决策时间和返工轮数必须记录，但首次内容基线比较只做观测，不作为质量通过条件。

## 16. 验收标准

- 工作台在两次操作内可从任一阶段查看关键产物、候选差异、问题、修改方法和影响范围。
- 相同冻结输入可重建每个策略候选的输入、配置和审计链；候选进入审核包后按哈希不可变，且只允许批准候选进入下游。
- 新任务脚本不再出现连续四句同构卖点罗列，并能解释每句服务的目标、证据和画面。
- 每个生产分镜都绑定目标、脚本、动作和证据；无目标的素材不能因可用而自动入片。
- 前三秒、连贯性、一致性和高光有独立结果与证据路径，不隐藏在总分中。
- 局部 AI 增强不覆盖原素材，失败可回退，采用后按最早影响 Gate 重新审核。
- L0、L1、阶段质量、过程效率和 L2 经营结果分别展示，不互相冒充。
- 按 §15 使用相同冻结输入新建并盲评 `baseline_v1`，比较结果、证据和 policy version 可重复计算。
- 未完成 G-B owner 复核和监督运营试用前，不解除普通 V2 production lock。
