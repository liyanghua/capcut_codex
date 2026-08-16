# 参考视频复刻 Skill 性能与效果优化方案

版本：2026-08-16
状态：Track A 静态护栏与独立 clean harness 的 G-A 已通过；Track B Native Runner、审批服务、真实媒体 adapter 和正式 CLI 已合并到主干。真实 cold/hot 配对已完成 Gate 1–5，当前为 `measured_pending_review`；V2 新版本基线见 `docs/remix-production-v2-baseline-report-2026-08-16.md`。普通 V2 生产、共享生产缓存与 Track C 仍等待 G-B 和监督运营试用。详见 `docs/g-a-assessment-2026-08-15.md`、`docs/superpowers/specs/2026-08-15-remix-production-backend-design.md` 和 `docs/remix-production-backend-implementation-status.md`。
适用范围：`.agents/skills/remix-reference-video/` 及其后续确定性执行工具  
关联文档：`docs/reference-video-remix-sop.md`、`AGENTS.md`

当前发布口径固定为：`skill_version=2.0.0-alpha.1`、`contract_version=2.0.0-alpha.1`。V2 新建产物的格式版本使用 `schema_version=1.0.0`，并同时声明 `artifact_type` 与 `schema_id`；历史 V1 产物继续保留创建时的 `schema_version=1.0`，不得为了通过 V2 校验原地改写。canonical registry 为 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`。

“静态护栏已通过”只表示当前版本标记、registry envelope、Brief/OpenAI YAML 解析、trigger fixture 结构和静态安全字面量检查通过。Track A 收口已在静态检查器之外完成 12 条独立 trigger 前向评测和 `work/` 媒体摘要前后对比；完整 artifact shape 校验已由 Track B 测试覆盖。以上静态证据不能替代 G-B 或发布质量验收；G-A 的独立结论见 `docs/g-a-assessment-2026-08-15.md`。

当前前向 pilot 为 `work/2026-08-13-tablemat-pilot/`。其参考事实层为 16 个原始镜头，Gate 2 批准后的目标结构为 11 个生产片段；Gate 1–5 均已形成证据，11/11 个片段已有批准素材，9/9 句口播已有画面证据，真实 TTS、字幕、精确时间轴和最终预览均已形成。该历史 pilot 的越权记录仍保留为失败事实；独立 clean harness 的 G-A 通过不回写历史 pilot。下文 `work/2026-08-11-douyin-tablemat-01/` 的数据只代表历史 V1 回溯基线，不得与该 pilot 的前向状态混称为“当前案例”。

替代 pilot 为 `work/2026-08-15-tablemat-ga-replacement-pilot/`。该任务最终 27.936 秒成片已通过 Gate 5，但 Fast Path 只读审计报告 `unsupported execution_mode`、`state_revision=null`、`event_count=0`，且存在 Gate 3 范围扩展与 Gate 4 生成前批准的时间线倒置。因此它只能作为成片与人工路径评估证据，不能作为 golden fixture、不能复用批准、不能直接解锁普通 V2 生产、不能归档到 `final/`。

### 当前后端固化边界（2026-08-16）

- G-A 通过后已按 B0 → B1/B4a → B2/B3 → B4 → B5 顺序实现确定性执行器；Native Runner 已通过真实 cold/hot 配对，普通 V2 生产、共享生产缓存和一线发布仍等待 G-B 与监督运营试用。
- `pipeline_state.json` 是唯一状态/审批权威；`approve-gate` 必须使用 schema 校验的结构化决定文件、当前审核包哈希、trusted server timestamp 和 state revision。
- FastAPI/SSE 只读投影与 `ProgressView` 契约已实现但真实 optional-extra 路由测试受环境依赖阻塞；Backlot 前端等待 G-B；manifest 保持普通生产锁与 `track_c=locked_until_g_b` 作为发布保险栓。新 V2 case 当前通过隔离 `gb-pair` 运行，历史 V1 按创建时契约续跑。

**sentence08 契约修复（2026-08-14）**：一次脚本编译曾把 Gate 2 批准的“铺好以后，日常使用都好打理。”静默改成“铺好以后，日常使用更省心。”。现已恢复 Gate 2 原句，并用当前 11 段素材重新生成 `script_evidence_matrix.json` 与 `production_script_candidate.json`；用户已明确通过修复后的 Gate 3 证据闭环。编译器和 Gate 4 适配器都校验候选句子必须等于 Gate 2 基线或命中已批准 fallback，防止该问题再次进入 TTS。Gate 4 生成前仍需单独确认最终文案与声音设置。

### 当前 pilot 的状态口径（2026-08-14）

- `fragment_plan.json` 是 Gate 3 已批准的不可变宽范围契约；其中早期生成器留下的 `authority` 和 `production_material_copied` 字段属于历史元数据债务，不能原地修订，否则会使 Gate 3 批准哈希失效。
- 物化事实以 `material_manifest.json` 和 `material_validation_report.json` 为准：11 份生产副本已经复制/导出，源/副本 SHA、可读性、原音轨移除和范围校验均通过。
- `production_script_candidate.json` 仍是候选，不是 TTS 授权。只有用户明确通过 Gate 4 生成前审核后，才生成 `approved_production_script.json` 并调用豆包；“开始实施”“直接做”或已有 Gate 3 批准都不替代这次确认。
- 因此当前五阶段结论是：Performance-proven Video、Blueprint 和 Retrieval 已完成；Controlled Mutation 已形成与 Gate 2 一致的生产脚本候选，等待 Gate 4 生成前确认；Reconstruction 仅完成批准素材物化支路。各阶段仍按 `stage_assessments/` 中的证据状态报告，未有完整 rubric 时保持 `not_scored`。

## 0. 一页总览：运营先看这一页

这套 Skill 不只是“把参考片拆开，再找几个相似素材”。它把业务过程拆成五个可独立评估的阶段：先把参考片变成可信事实，再形成自有产品蓝图，只执行经过批准的变化，然后从素材库找准可用画面，最后把已批准的画面、配音和字幕稳定重建成片。

```mermaid
flowchart LR
  A["Performance-proven Video\n把参考片变成可核对的事实"] --> B["Blueprint\n把事实变成目标片方案"]
  B --> C["Controlled Mutation\n只修改已批准的内容"]
  C --> D["Retrieval\n找到能证明卖点的素材"]
  D --> E["Reconstruction\n按真实配音重建成片"]
  E --> F["评分卡 + 效率看板\n决定是否返工或归档"]
```

### 0.1 五阶段与现有流程的映射

| 总览阶段 | 目前实现映射 | 主要 Gate | 一线运营要做的业务判断 | 关键产物 |
|---|---|---|---|---|
| **Performance-proven Video** | 旧执行层 `legacy Stage 0` Brief 预检 + `legacy Stage 1` 参考片探测、切镜、关键帧、音轨、转写和节奏证据 | Gate 1（输入预检不属于 Gate） | “参考片文件和任务目标是否明确？镜头切得对不对？哪些画面只是异常闪帧，哪些是有意节奏？” | `project_brief.yaml`、`recipe.json`、`video_clips/`、参考音频、接触表 |
| **Blueprint** | 旧执行层 `legacy Stage 2` 前半：叙事骨架、片段职责、卖点证明链、素材需求和字速预检；读取 Retrieval 只读预计算的覆盖预判发现明显不可实现结构 | Gate 2 | “这条片要让用户记住什么？每个卖点需要什么画面证据？现有素材缺口是否要补拍或改结构？” | `shot_blueprint.json`、`script.txt`、`content_baseline.json`；审核包引用 `coverage_precheck.json`，但不取得其 ownership |
| **Controlled Mutation** | 旧执行层 `legacy Stage 2` 后半：定义保留、替换、删除、改写、禁用声明和已批准 fallback；Gate 2 与 Blueprint 基线原子锁定；Gate 3 后由本阶段编译器消费证据矩阵生成脚本候选，Gate 4 生成前才提升 | Gate 2 变更契约；Gate 4 生成前完成候选升级授权 | “相对参考片允许改什么？哪些话不能说？证据不足时允许改弱成哪句话？” | `mutation_plan.json`、`production_script_candidate.json`、`approved_production_script.json`、`pipeline_state.json` |
| **Retrieval** | 素材索引、任务覆盖分析、语义/动作/技术资格判断、视觉评分、去重、全局排程、Gate 3 宽范围决定，以及逐句画面证据校验 | Gate 3 的选材确认与证据闭环两个子状态 | “这些候选真的能证明对应卖点吗？动作完整吗？每句口播是否都能落到已批准画面？” | `asset_profiles.json`、`coverage_precheck.json`、`coverage_report.json`、`matches.json`、候选接触表/微视频、`fragment_plan.json`（不可变宽范围）、`script_evidence_matrix.json` |
| **Reconstruction** | 只消费 Gate 3 宽范围与已批准生产脚本；Gate 3 汇总通过后可先准备批准素材，Gate 4 生成前通过后才执行真实 TTS，再按实测时长生成字幕、精确裁点和累计画面时间轴；Gate 4 生成后听审通过才做代理、正式渲染和交付闭环 | Gate 4 生成前/生成后 + Gate 5 | “最终文案和声音设置能否生成？实际声音、字幕和画面是否对齐？成片能否发布？” | `material_manifest.json`、`material/`、`voice_manifest.json`、`duration_report.json`、`reconstruction_timeline.json`（最终精确计划）、`captions.srt`、`remix.mp4`、验收与渲染报告 |

五个阶段不是五次重复审核：Performance-proven Video 决定“参考片事实是否可信”，Blueprint 决定“我们要做什么”，Controlled Mutation 决定“允许改什么”，Retrieval 决定“素材能否证明卖点”，Reconstruction 决定“能否把已批准输入稳定做成片”。Gate 编号保持不变，只是用一个运营更容易理解的框架解释职责。旧文档中的 `Stage 0/1/2` 统一称为 `legacy execution stage`；输入预检不计入五阶段质量平均分。

`fragment_plan.json` 与 `reconstruction_timeline.json` 必须分开：前者是 Retrieval 在 Gate 3 后形成的不可变宽范围批准契约；后者是 Reconstruction 根据实测配音生成的最终精确渲染计划。后者只能引用前者的哈希并在其范围内收窄，不能原地改写 Gate 3 已批准的范围。物理复制/导出记录单独写入 `material_manifest.json`。

五阶段是业务决策框架；不影响依赖的只读任务可以并行，但生产依赖必须严格遵守下面的唯一基线。**真实 TTS 不与 Retrieval 并行，也不在 Gate 3 前生成。** Gate 4 包含生成前确认和生成后听审两个必需决定，但不增加新的 Gate 编号。

```text
Gate 2 内容基线
        ↓
Gate 3 选材确认 → 逐句证据闭环 → Gate 3 汇总批准
        ↓
Controlled Mutation 编译脚本候选 + Reconstruction 准备批准素材（可并行）
        ↓
Gate 4 生成前确认
        ↓
TTS → 实测时长 → 字幕、精确裁点与画面时间轴
        ↓
Gate 4 生成后听审
        ↓
代理/正式渲染 → Gate 5
```

### 0.1.1 Track B 内部优先级：把运行效率做成可测、可续跑

历史 V1 基线明确记录的纯媒体操作只有约 56 秒，已知的人工组织和返工却以几十分钟计。Track A 必须先完成 Gate 契约纠正并通过 G-A；下表只表示 Track B 获准启动后的内部建设顺序，不得据此越过 Track A 直接写执行器。Track B 的重点不是继续微调 FFmpeg 参数或增加 TTS 并发，而是消除重复组织、全量重算和过早生成下游产物。

| 顺序 | 先实施的能力 | 主要消除的浪费 | 预期影响 |
|---:|---|---|---|
| 1 | 确定性阶段执行器与 `full/resume/stage/audit` 模式 | 每次重写命令、找恢复点和手工拼报告 | 降低运营等待和重复操作，是所有后续提速的前提 |
| 2 | 共享素材索引、单源批量解码和描述符缓存 | 每个任务重扫素材、逐帧启动 FFmpeg | 素材冷建档一次，后续任务按哈希复用 |
| 3 | 输入指纹、片段/动作组增量重算 | 改一段却重做整条匹配、配音或渲染 | 只重算受影响片段及相邻窗口 |
| 4 | Gate/状态事务更新和可复用审核包 | 重复整理 Gate 材料、读取过期批准 | 审核包自动生成，失败可从有效上游续跑 |
| 5 | 自动逐句证据矩阵和生产脚本编译 | Gate 3 后再次手工整理脚本，或无证据文案进入 TTS | 把新增顺序约束变成秒级机器检查，避免增加一轮人工整理 |
| 6 | 代理片和边界片先行、正式渲染后置 | 每轮反馈都做完整 1080×1920/60fps 编码 | 在低成本预览中先发现卡顿、重复和抖动 |
| 7 | TTS 常驻工作进程和组内有界并发 | 单次连接和编码开销 | P0/P1 完成后再做，属于次级收益 |

按历史记录，删除/修订结构、重建匹配和重新组织 Gate 4 脚本包合计约 65 分钟，但这些时间同时包含结构修改、全量重匹配和人工整理，不能全部归因于精确裁点顺序。新基线会比“Gate 2 后 TTS 与 Retrieval 并行”的旧设想多支付约 30–45 秒外部 API 等待；“Gate 3 批宽范围、TTS 后再裁精确点”能避免其中由真实音频改变源时段造成的返工，是**高可信待验证假设**。索引、增量重算和脚本整理的收益分别归 Track B，不与 Track A 重复归因；全部收益必须在冻结案例配对运行后才可标记为实测。

以当前约 277 分钟回溯墙钟为参照，用户及时确认时的 20–30 分钟目标相当于约 89%–93% 的模型降幅；由于历史数字混合了人工等待、机器执行和未记录操作，这个百分比不能作为已经实现的收益。机器/API 冷启动目标调整为不超过 13 分钟，热缓存目标不超过 8 分钟，详见第 10 节。

效率收益先按“瓶颈是否被消除”评估，再用冻结案例配对运行校准。下表是当前阶段的**模型估算**，不是承诺值：

| 瓶颈 | 当前可见基线 | V2 目标 | 预计收益口径 |
|---|---|---|---|
| 手工命令、路径和报告组织 | 多次临时执行，恢复点不统一 | `stage`/`resume` 自动恢复，审核包可复用 | 降低运营触点和重复整理；不把节省时间归因于 FFmpeg |
| 素材重复扫描与逐帧启动 | 约 48 秒/批分析帧，且每次任务重做 | SHA 缓存 + 单源批量解码 | 首次冷建档后，重复任务目标 ≤5 秒命中索引 |
| Gate 修订后的全量重算 | 历史删除/修订及重建约 65 分钟 | 片段/动作组增量重算，受影响审核包 ≤30 秒 | 主要收益来源；需用 `rework_seconds` 配对验证 |
| Gate 4 脚本包重复组织 | 历史约 12 分钟 | 逐句证据矩阵 + 脚本编译 ≤20 秒 | 以机器契约替代二次手工抄录，减少错配返工 |
| 过早正式渲染 | 每轮反馈都可能支付完整编码 | 代理/边界片先审，正式渲染后置 | 每次返修避免一次 1080×1920/60fps 编码 |
| TTS/素材并行收益 | 旧方案可省约 30–45 秒 | 新顺序放弃该并行 | 用几十分钟级返工风险换取证据闭环；需记录净收益而非只看 API 延迟 |

只有在同一冻结输入、同一审核决定、隔离冷/热缓存的 V1/V2 配对运行中，才能把“预计收益”改成 `measured`，并报告每阶段质量分、成熟度分、总分和机器/API 关键路径。

### 0.2 两套分数，避免把流程稳定性和视频效果混在一起

完整评分能力启用后，每次运行同时记录两套指标：

1. **阶段产物质量分 `stage_output_quality_score`（0–100）**：这一条视频在该阶段的实际结果质量。例如镜头切分是否可信、卖点是否有证据、画面是否真的匹配。
2. **流程成熟度分 `workflow_maturity_score`（0–100）**：这套 Skill 是否可复用、可缓存、可续跑、可让运营看懂。它不是单条视频的创意质量。

视频总分（运营界面显示为“整体视频总分”）默认取五个阶段质量分的等权平均：

```text
video_quality_score = round(
  (performance_proven_video
   + blueprint
   + controlled_mutation
   + retrieval
   + reconstruction) / 5
)
```

五个阶段必须全部有分数才计算最终分；任一阶段没有可验证数字时，`video_quality_score=not_scored`，不能用 `provisional` 代替。`provisional` 只描述已有完整数字但尚未通过该阶段对应人工 Gate 的审批状态。这个总分用于比较同一套输入的前后改进，不代表播放量、转化率或“爆款概率”。

Track C 启用前，pilot 仍要在每个阶段保存完整业务评估，但不强行生成数字分：没有逐项 `earned_points/max_points/evidence_paths/reason` 时，`stage_output_quality_score` 必须为 `not_scored`；没有阶段计时时，效率状态必须为 `incomplete`；任一阶段未计分时，不计算整体视频总分。阶段评估的“完整”是指结论、证据、未验证项、风险、审批状态、效率证据和下一阶段准入齐全，不是指必须手工补出一个数字。

总分不能绕过硬门禁。出现禁用声明、`missing_material`、过期哈希、时间轴 gap/overlap、媒体不可读或未批准的叠字时，仍可展示分数帮助定位问题，但状态必须是 `blocked` 或 `review_required`，不能标记为可发布。

效率单独记录分钟和秒，不折算进视频质量分：

- `local_compute_seconds`：本机 FFmpeg、哈希、评分、文件和报告时间；
- `external_api_seconds`：ASR、TTS 等外部服务时间；
- `human_wait_seconds`：等待运营确认的时间；
- `rework_seconds`：上游修改后重新执行的时间；
- `machine_api_critical_path_seconds`：只按声明允许的只读预处理并行计算机器/API 关键路径；生产 TTS 不与 Retrieval 并行。

### 0.3 每个阶段如何评分

每个阶段的 rubric 固定为 100 分。机器先依据产物计算可验证项，语义和审片项由运营确认；没有证据的项目不得给满分。

| 阶段 | 评分项 | 权重 |
|---|---|---:|
| Performance-proven Video | 源文件完整且可追溯 | 15 |
| Performance-proven Video | 切点准确、低分切点和异常帧有处理结论 | 30 |
| Performance-proven Video | 关键帧、音轨、转写和候选证据完整 | 20 |
| Performance-proven Video | 钩子、节奏、证明动作和 CTA 等有效结构已提取 | 25 |
| Performance-proven Video | 审核包清楚、候选帧与时间点可追溯 | 10 |
| Blueprint | 叙事骨架和每段职责清楚 | 25 |
| Blueprint | 自有产品卖点有证据且声明合规 | 25 |
| Blueprint | 结构在现有素材覆盖范围内可实现 | 20 |
| Blueprint | 文案、语义组和预计时长可实现 | 20 |
| Blueprint | 相对参考片的删并、改写和重排可追溯 | 10 |
| Controlled Mutation | 保留、替换、删除和不可变项定义完整 | 20 |
| Controlled Mutation | 新声明和口播语义正确、无禁用声明 | 25 |
| Controlled Mutation | 内容基线中的口播意图、语义组边界和允许声明获得批准；最终生产脚本与 TTS 设置留到 Gate 4 生成前确认 | 20 |
| Controlled Mutation | 变化幅度、字速和素材时长风险在执行前可控 | 20 |
| Controlled Mutation | 人工覆盖、部分批准和失效传播可追溯 | 15 |
| Retrieval | 候选通过产品、语义、动作和技术资格门禁 | 25 |
| Retrieval | 卖点证据、动作阶段和视觉构图匹配 | 25 |
| Retrieval | 素材覆盖、多样性和感知去重 | 20 |
| Retrieval | 全局排程、动作组和相邻镜头连续性 | 20 |
| Retrieval | 逐句口播均关联 Gate 3 批准画面证据，候选分项分数、证据帧和人工改选可追溯 | 10 |
| Reconstruction | 只使用 Gate 3 批准来源，路径、哈希和源范围正确 | 20 |
| Reconstruction | 配音、字幕和累计时间轴以实测音频为准 | 25 |
| Reconstruction | 精确裁点、镜头边界和整体组装连续 | 20 |
| Reconstruction | 分辨率、帧率、色彩、音视频流和编码技术正确 | 20 |
| Reconstruction | 最终生产脚本与 TTS 设置已通过 Gate 4 生成前确认；代理审查、最终审片和交付风险已闭环 | 15 |

计分规则：

- 每个评分项必须记录 `earned_points`、`max_points`、`evidence_paths` 和 `reason`；
- 机器可验证项按规则计算；若完整 rubric 已有数字、但语义项尚未通过对应 Gate，则保持该数字并将独立的 `approval_status` 标为 `provisional`。没有完整数字时必须用 `measurement_status=not_scored`，不得把 `provisional` 写入分数字段；
- `not_applicable` 只能用于 Brief 明确不需要的能力，并按其余项目同比例归一化；不得用它隐藏缺素材或缺证据；
- 回溯案例缺少当时应保存的证据时，扣分并降低 `score_confidence`，不能靠事后主观补满；
- 人工改选候选不会改写机器原始分，评分卡另记 `override_reason` 和最终结果分。

上表是可逐条审计的评分子项，合计得到每个阶段的质量分；后文“阶段质量的评分维度”是面向看板的同口径聚合，不是第二套可任选的评分规则。实现时先计算子项，再按对应维度映射汇总；历史分数若缺少子项证据，只能标为回溯分并降低置信度。

### 0.4 历史 V1 案例回溯基线与 V2 目标

下表是对 `work/2026-08-11-douyin-tablemat-01/` 的**回溯基线**，不是经过统计校准的模型概率。分数依据现有产物、Gate 记录和已知返工事实计算，置信度用于提醒运营不要把回溯分当成绝对真值。

| 阶段产物质量 | 当前回溯基线 | 置信度 | V2 最低验收线 / 目标分（同一案例复跑后转为实测） | 主要原因 |
|---|---:|---|---:|---|
| Performance-proven Video | **82** | 高 | ≥88（目标 92） | Gate 1 已保留低分动作切点并处理单帧异常；候选 manifest 和全分辨率证据仍不完整 |
| Blueprint | **65** | 中 | ≥88（目标 90） | 结构和声明审计存在，但缺少高层结构图；初版 10 秒目标与真实语速明显不匹配 |
| Controlled Mutation | **58** | 中 | ≥88（目标 90） | 卖点禁用审计有记录，但素材覆盖和文案时长发现偏晚，发生多轮 Gate 修订与音色回退 |
| Retrieval | **66** | 中 | ≥88（目标 90） | 已有候选评分和去重规则，但任务级覆盖、动作证据和全局排程仍不够确定，缺口发现偏晚 |
| Reconstruction | **74** | 中 | ≥88（目标 93） | 技术检查通过，但 Gate 5 尚未人工通过；重复画面、边界卡顿、静态图抖动仍依赖人工发现 |
| **视频总分 `video_quality_score`** | **69** | 中 | **≥88（目标 91）** | 五阶段等权平均；这是历史 V1 回溯分，历史审批状态为 `provisional`，不是当前 V2 pilot 的分数 |

当前流程成熟度的回溯分为 **41/100**：产物和 Gate 契约较完整，但没有通用执行器、共享索引、覆盖报告和可复用的阶段计时。V2 的目标是 **≥80/100（目标 85）**。这项分数提升代表“同样的运营输入能更稳定、更快地得到可审结果”，不代表每条片的创意质量自动提高。

本节已按五阶段做一次**回溯重基线**。原合并阶段的历史分 **72** 从本版本起停用，不能与拆分后的 Retrieval 或 Reconstruction 单项直接比较。整体质量仍为 **69**、流程成熟度仍为 **41**，是因为本次只拆分并重新加权旧证据，不代表视频效果或执行能力已经提升；只有 V2 在相同冻结输入上前向实测后，才能报告真实改进。

这里的 `Performance-proven Video` 是框架名称。只有 Brief 提供平台播放、完播、互动或转化证据时，才可以在 `performance_evidence` 字段中确认“表现已验证”；没有外部表现数据时，只评估“参考结构是否被可靠拆解”，不推断爆款真实性或预计转化。无数据的任务将 `reference_status` 记为 `user_designated_reference`。

### 0.4.1 分阶段看板：效果分和流程成熟度分同时展示

运营看板必须按五个业务阶段展示两套分数。**表中当前分数是历史 V1 案例的五阶段回溯基线，V2 分数是实施后的验收目标；在执行器和评分卡上线前，不得把目标分称为实测分。**

| Stage | 当前成熟度 | V2 成熟度目标 | 当前产物质量 | V2 质量目标 |
|---|---:|---:|---:|---:|
| Performance-proven Video | 50 | 85 | 82 | 92 |
| Blueprint | 35 | 82 | 65 | 90 |
| Controlled Mutation | 32 | 86 | 58 | 90 |
| Retrieval | 38 | 84 | 66 | 90 |
| Reconstruction | 50 | 88 | 74 | 93 |
| **总体（等权平均）** | **41** | **85** | **69** | **91** |

分数旁必须拆开显示两种状态，不能再把它们拼成一个未定义的 `score_status`：`measurement_status` 表示分数从哪里来，枚举为 `modeled|retrospective_baseline|measured|target|not_scored`；`approval_status` 表示对应产物是否经过当前输入哈希下的审核，枚举为 `provisional|awaiting_user|approved|blocked|stale`。`not_scored` 只属于分数/测量来源，表示当前没有完整可验证数字；`provisional` 只属于审批状态，表示已有完整数字但对应 Gate 尚未批准。两者不可互换，也不能组合成 `not_scored/provisional` 来暗示已有分数。历史 V1 基线分别为 `retrospective_baseline` 和 `provisional`；当前 V2 pilot 在完整 rubric 证据不足时为 `not_scored`，各阶段审批状态独立按 Gate 事实记录。只有具备完整当前运行证据的前向评分才可标记 `measured`，对应 Gate 通过后再将 `approval_status` 改为 `approved`。若上游输入变化，受影响阶段和下游的 `approval_status` 改为 `stale`，旧实测仍可留作历史记录但不得当作当前分数。效率单独显示，不折算进质量分。

### 0.5 流程成熟度如何评分

流程成熟度采用固定的五维 100 分 rubric。它评估 Skill/执行器，不评某条视频的创意好坏：

| 能力 | 权重 | 当前回溯分 | V2 目标分 |
|---|---:|---:|---:|
| 确定性自动化 | 25 | 8 | 22 |
| 机器契约与可追溯 | 25 | 15 | 23 |
| 缓存、增量重算与续跑 | 20 | 3 | 17 |
| 验证、失败恢复与失效传播 | 15 | 9 | 13 |
| 一线运营可用性 | 15 | 6 | 10 |
| **合计 `workflow_maturity_score`** | **100** | **41** | **85** |

流程成熟度只在 Skill 或执行器版本变化后重算；同一版本处理不同视频时不随视频质量变化。

阶段成熟度的评分维度固定如下，脚本只给有证据的项目计分。旧执行层 `legacy Stage 0` 仅作为输入前置校验和可追溯证据，不纳入五阶段质量或成熟度的加权平均；旧执行层 `legacy Stage 1` 的参考拆解结果承担 Performance-proven Video 的阶段评分。

| 业务 Stage | 成熟度维度与权重 |
|---|---|
| Performance-proven Video | 确定性自动化 20、可追溯 20、Gate 完整性 20、复用/缓存 20、可观测性 20 |
| Blueprint | 契约一致性 25、证据可追溯 25、字速/时长 lint 20、可复用性 15、审核清晰度 15 |
| Controlled Mutation | 允许变更清单 20、stale/失效传播 20、哈希/审计 20、Gate 纪律 20、增量复用 20 |
| Retrieval | 素材索引复用 20、资格/评分确定性 20、全局排程 20、缓存/增量重算 20、Gate 3 审核可用性 20 |
| Reconstruction | 批准源约束 20、TTS/时间轴可复现 20、代理/正式渲染可复现 20、验证/失败恢复 20、指标与交付可观测 20 |

阶段质量的评分维度也固定如下：

| 业务 Stage | 产物质量维度与权重 |
|---|---|
| Performance-proven Video | 切点可信 35、镜头/音频证据完整 25、帧与关键帧完整 25、参考结构保真 15 |
| Blueprint | 叙事顺序 25、卖点证据覆盖 30、文案准确 20、时长可行 15、结构清晰 10 |
| Controlled Mutation | 声明安全 30、内容基线/fallback 可执行性 25、语义连续 20、变化保真 15、变更可审核 10 |
| Retrieval | 资格门禁 25、语义/动作匹配 25、覆盖/多样性 20、排程/连续性 20、候选可追溯 10 |
| Reconstruction | Gate 4 生成授权与批准源完整性 20、TTS/实测时间轴 25、组装连续性 20、媒体技术质量 20、审核/交付闭环 15 |

候选素材的 `match_confidence`（0–1）与上述评分完全分离；`0.60` 是资格/匹配阈值，不是 60 分质量分。

### 0.6 评分卡的最小字段与状态

Track C 拟新增 `quality_scorecard.json`，当前 Skill 尚未自动生成，canonical registry 也只把它登记为 `planned_track_c`。因此下面是待 Track C 激活时采用的字段形状，不是当前可声称已生成或已通过 registry 验证的产物。激活时必须同步更新 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`、`AGENTS.md`、Skill 和 references。

V2 artifact envelope 的版本语义固定如下：

- `skill_version=2.0.0-alpha.1`：当前 Skill 试运行版本；
- `contract_version=2.0.0-alpha.1`：五阶段、Gate 与 ownership 契约版本；
- `schema_version=1.0.0`：单个 V2 产物的格式版本，不等于 Skill 版本；
- `artifact_type` 与 `schema_id`：机器识别产物类型的必填字段；
- 历史 V1 的 `schema_version=1.0` 原样保留，只读续跑或显式迁移，不就地升级。

每个阶段分别记录测量来源和审批状态：计算完成不代表已批准。字段命名固定如下：阶段质量统一为 `stage_output_quality_score`，阶段流程成熟度统一为 `stage_workflow_maturity_score`，全局质量为 `video_quality_score`，全局成熟度为 `workflow_maturity_score`；其他历史命名全部废弃，不进入 V2 schema。至少包含：

```json
{
  "artifact_type": "quality_scorecard",
  "schema_id": "urn:capcut:remix-reference-video:artifact:quality-scorecard",
  "schema_version": "1.0.0",
  "contract_version": "2.0.0-alpha.1",
  "skill_version": "2.0.0-alpha.1",
  "example_context": "planned_track_c_shape; not_current_artifact",
  "measurement_status": "measured|modeled|retrospective_baseline|target|not_scored",
  "approval_status": "provisional|awaiting_user|approved|blocked|stale",
  "overall_status": "review_required",
  "release_eligible": false,
  "blocking_items": ["gate5_awaiting_user"],
  "review_status": "awaiting_user",
  "skill": {
    "name": "remix-reference-video",
    "version": "2.0.0-alpha.1",
    "manifest_hash": "sha256",
    "trigger_eval_status": "not_run|passed|failed",
    "contract_validation_status": "not_run|passed|failed",
    "security_check_status": "not_run|passed|failed",
    "promotion_status": "not_eligible|eligible|approved"
  },
  "gate_status": {
    "gate1": "approved",
    "gate2": "approved",
    "gate3_material_selection": "approved",
    "gate3_evidence_closure": "approved",
    "gate3": "approved",
    "gate4_pre_generation": "approved",
    "gate4_post_generation": "awaiting_user",
    "gate4": "awaiting_user",
    "gate5": "awaiting_user"
  },
  "framework_stage_order": [
    "performance_proven_video",
    "blueprint",
    "controlled_mutation",
    "retrieval",
    "reconstruction"
  ],
  "framework_stages": [
    {
      "stage_id": "performance_proven_video",
      "business_stage_id": "performance_proven_video",
      "execution_stage_ids": ["brief_preflight", "reference_split"],
      "stage_output_quality_score": 82,
      "stage_workflow_maturity_score": 50,
      "measurement_status": "retrospective_baseline",
      "approval_status": "approved",
      "score_confidence": "high",
      "rubric": [
        {
          "metric_id": "boundary_accuracy",
          "earned_points": 26,
          "max_points": 30,
          "evidence_paths": ["recipe.json"],
          "reason": "低分动作切点已保留，运动峰值已压制"
        }
      ],
      "evidence_paths": ["recipe.json", "video_clips/reference_contact_sheet.jpg"],
      "blocking_items": [],
      "review_status": "approved",
      "gate_status": "approved"
    }
  ],
  "video_quality_score": 69,
  "video_quality_status": "provisional",
  "workflow_maturity_score": 41,
  "workflow_maturity_status": "retrospective_baseline",
  "efficiency": {
    "local_compute_seconds": null,
    "external_api_seconds": null,
    "human_wait_seconds": null,
    "rework_seconds": null,
    "machine_api_critical_path_seconds": null,
    "operator_touch_seconds": null,
    "gate_return_count": null,
    "first_pass_gate_rate": null,
    "cache_hit_rate": null,
    "time_to_first_review_seconds": null,
    "time_to_gate5_preview_seconds": null,
    "comparison_status": "not_comparable"
  }
}
```

上面示例只展开一个阶段的 `framework_stages` 条目，并明确标为 Track C 计划形状，不代表当前存在该产物；其中的 69 分和 `video_quality_status=provisional` 仅是历史 V1 回溯示例，不能写入或推断为当前 V2 pilot 状态。实际评分卡必须按照 `framework_stage_order` 恰好包含五个阶段，且 `retrieval` 与 `reconstruction` 各自独立，不接受任何旧合并阶段 ID。阶段的审批提升点固定为：Performance-proven Video 对应 Gate 1；Blueprint 对应 Gate 2；Controlled Mutation 对应 Gate 4 生成前（Gate 2 只锁其变更契约）；Retrieval 必须同时完成 Gate 3 选材确认和证据闭环；Reconstruction 只有 Gate 5 通过才为 `approved`，Gate 4 生成后只是音频/时间轴检查点。对当前 V2 pilot，若没有完整可验证数字，必须使用 `video_quality_score=not_scored`；`overall_status=review_required` 或 `blocked`、`release_eligible=false` 表示当前不能归档发布。

V2 实施后，`stage_metrics.jsonl` 保存逐阶段计时，`quality_scorecard.json` 只保存汇总分和证据引用；当前 V2 pilot 尚无这两个自动产物，不能用历史回溯估算冒充实测。两者都不能通过手改数字来“过 Gate”。

Track C 启用前，唯一 `manual-contract-only` pilot 在每个业务阶段完成时必须生成一份人工阶段评估快照，例如 `stage_assessments/retrieval.md`。快照至少列出：`framework_stage_id`、阶段状态、当前输入哈希、逐项可验证结果、未验证项、业务风险、Gate 决定、效率证据及下一阶段准入条件。它不是 `quality_scorecard.json`，也不得手工补算自动评分；缺少第 0.3 节逐项 `earned_points/max_points/evidence_paths/reason` 或缺少阶段计时时，分别记录 `stage_output_quality_score: not_scored`、`measurement_status: not_scored`、`efficiency_measurement_status: incomplete`。候选 `match_confidence` 不得换算成阶段质量分。完成阶段在 Gate 决定后更新为最终评估；跨 Gate 的阶段（Controlled Mutation、Reconstruction）在等待中保存明确标注的进行中快照，不能冒充完成评估。这样既保证每阶段都有完整业务评估，又不提前建设 Track C 或把估算冒充实测。

硬阻塞项至少包括：`missing_material`、禁用声明、哈希过期或不匹配、媒体损坏/不可读、时间轴 gap/overlap、未处理叠字风险、Gate 未批准或审批已 `stale`。存在任一硬阻塞时，`release_eligible` 必须为 `false`；`overall_status` 只能为 `blocked` 或 `review_required`，即使分数高于目标也不能发布。

### 0.7 历史 V1 效率基线与 V2 看板

历史 V1 基线从 `project_brief.yaml` 文件时间到 Gate 5 预览生成约 **277 分钟**；从首次参考拆解记录到预览约 **264 分钟**。这两个数字都包含机器处理、API 调用、人工审核等待和多次回退，不能把它们全部归因于 FFmpeg。该历史案例的 Gate 1–4 是 V1 状态，不等于当前 V2 pilot 的五阶段已经完成；当前 pilot 必须按新子状态、当前输入哈希和 `stage_assessments/` 独立记录。

| 指标 | 当前回溯基线 | V2 目标 | 说明 |
|---|---:|---:|---|
| Brief 到 Gate 5 预览墙钟时间 | 约 277 分钟（回溯约数） | 用户及时确认时 20–30 分钟 | 当前包含人工等待；目标需同口径复跑 |
| 机器/API 冷启动关键路径 | 无法重建 | ≤13 分钟 | 当前没有 `stage_metrics.jsonl`，不伪造基线 |
| 机器/API 热缓存关键路径 | 无法重建 | ≤8 分钟 | 必须从相同缓存快照做配对验证 |
| 已明确记录的纯媒体操作 | 约 56 秒 | 仅作子集参考 | 不包括人工组织 JSON、语义判断、TTS 和正式渲染 |
| 因晚发现问题产生的主要回退 | 至少 2 次 | 0 次为目标 | Gate 3 → Gate 2；Gate 4 → Gate 3 → Gate 4 |
| 初版蓝图到真实配音时长 | 10.000001s → 26.832063s | Gate 2 做字速/时长包络预检；Gate 3 后先做证据审计再生成最终脚本 | 增加 16.832062s，触发素材范围扩展 |
| 技术成片与批准音频差异 | 约 0.001013s | ≤1 帧 | 技术检查通过，Gate 5 仍待人工审片 |
| 生产缺素材/占位 | 0 段 | 0 段 | 这是计划事实，不等于内容审核通过 |

看板必须同时展示“本阶段用时、累计用时、等待运营用时、返工用时、缓存是否命中”。只有相同参考片、Brief、素材快照、TTS 设置和审核决定的配对运行，才能宣称提速百分比。

### 0.8 给一线运营看的执行提示

系统每次停在 Gate 前，先用业务语言告诉运营“为什么要看”和“只需要回答什么”，不要让运营阅读 FFmpeg 参数或 JSON 字段。

| 停留点 | 系统正在做什么 | 运营只需确认什么 | 可直接回复 | 未通过回到哪里 |
|---|---|---|---|---|
| 输入预检（旧执行层 `legacy Stage 0`） | “我先检查参考片、产品信息、已批准卖点和素材库是否齐全；现在还没有开始剪辑。” | 补齐缺少的文件、产品事实或发布要求 | `参考片已提供 / 补素材路径 / 补卖点 / 暂停` | 留在 **输入预检**，不生成后续产物 |
| Gate 1 | “我已经把参考片切成 N 个镜头，并标出疑似闪帧和漏切位置。” | 切换是否自然，异常画面是否保留 | `保留 / 合并 / 删除 / 在 X 秒补切` | 回 **Performance-proven Video** |
| Gate 2 | “我把参考片整理成这版目标结构和内容基线，并标出卖点证据需求、禁用说法和素材缺口。” | 卖点是否要讲、结构是否合理、哪些话不能说、时长包络是否接受 | `内容基线通过 / 改结构 / 删除卖点 / 补充证据` | 结构问题回 **Blueprint**；声明或口播意图问题回 **Controlled Mutation** |
| Gate 3（选材确认子状态） | “我已从素材库筛出候选，并检查产品、动作、时长和相邻画面重复；确认后会逐句核对口播证据。” | 候选画面是否真的能证明这一段；批准哪个素材和宽可用范围 | `选 A / 选 B / 批准范围 / 换候选 / 缺素材 / 申请删段` | 画面问题留在 **Retrieval**；`申请删段` 只记录请求并返回 **Gate 2**，不能在 Gate 3 直接改结构 |
| Gate 3（证据闭环子状态） | “我已把每句口播逐句落到已选画面的时间窗；Gate 3 只有这一步也通过才算完成。” | 只处理系统标为 `review_required` 的证据项；不能在此新增卖点 | `证据通过 / 换候选 / 使用已批准弱化说法 / 返回 Gate 2` | 任一必需范围未决时 Gate 3 汇总仍为 `awaiting_user`；无证据句子不能编译生产脚本 |
| Gate 4（生成前） | “每句口播都已经关联到批准画面；现在只确认最终生产脚本、音色、语速和发音风险，确认后才生成声音。” | 最终文案、品牌名、语气、音色和语速是否可以生成 | `生成前通过 / 改第 N 段 / 换音色或语气` | 回 **Controlled Mutation**；画面证据不足回 **Retrieval** |
| Gate 4（生成后） | “配音已经生成，现在进入 Reconstruction 的成片组装；我已按实际音频重排画面和字幕。” | 发音、停顿、开头/转场/结尾是否自然，时长是否接受 | `声音通过 / 重做第 N 组 / 接受延长 / 补素材` | 声音或文案回 **Controlled Mutation**；画面范围不够回 **Retrieval**；通过后留在 **Reconstruction** |
| Gate 5 | “Reconstruction 已生成去字幕烧录的最终预览；我已检查技术连续性，仍需要你判断发布观感。” | 完整播放后是否有重复、卡顿、抖动、错位或品牌风险 | `通过归档 / 指定时间点返修` | 按问题分别回 **Blueprint**、**Controlled Mutation**、**Retrieval** 或 **Reconstruction** |

运营不需要判断“模型分数是否数学上合理”；运营只需要判断画面、文案和卖点是否适合发布。系统负责保留证据、解释扣分和指出下一步回到哪个 Gate。

统一提示模板（每次只问一个 Gate 的业务决定）：

```text
【现在到哪一步】用一句话说明当前产物已经准备到哪里
【我发现了什么】只列业务影响、低分项和缺口
【请你确认】一次只问当前 Gate 必须决定的事项
【建议】给出默认建议和理由，但不代替用户批准
【可直接回复】提供 2–4 个短选项
【不处理的影响】说明会阻塞、返工还是降低分数
【查看证据】最后再给接触表、音频、视频和报告路径
```

默认先展示业务摘要，再展示技术证据；不得把 JSON、哈希、模型字段或 FFmpeg 日志直接当成运营提示正文。用户需要排查时再展开技术细节。

## 1. 方案结论

当前主要问题不是 FFmpeg 或豆包接口本身慢，而是 Skill 仍以流程文档为主，缺少可复用、可缓存、可增量续跑的执行器；同时，素材覆盖和口播证据发现过晚，导致已经批准和导出的下游产物反复失效。

本方案推荐采用“效率优先的基础设施 + 五业务阶段 + 前向验证”路线：

1. 保留 Brief 和 Gate 1–5，所有原本需要人工确认的事项仍须由用户明确批准，不以提速为由取消审核；Gate 2–5 的输入职责按本文件锁定。
2. 把不依赖本次语义批准的素材技术建档提前，使用共享索引和批量解码。
3. Gate 2 只批准内容基线：结构、卖点、禁用声明、目标口播意图和时长包络；不调用真实 TTS。
4. Gate 3 选材批准后自动生成逐句画面证据审核包；用户对当前证据哈希明确批准、Gate 3 汇总通过后，才确定性编译生产脚本候选。无证据的句子返回 Gate 3，必要时返回 Gate 2。
5. Gate 4 生成前只确认最终生产脚本、模型/协议、音色、语速和发音风险；通过后才调用真实 TTS。
6. 以 TTS 实测时长重建字幕和画面时间轴，并在 Gate 4 生成后听审；只在 Gate 3 批准范围内确定精确裁点。
7. 先生成低成本代理片和边界审查片，内容通过后只做一次正式 1080×1920、60fps 渲染。
8. 用输入哈希、阶段指纹、事务性 Gate 状态和按片段增量重算实现可续跑；最小化加入 Skill 版本、触发评测、契约验证、安全检查和发布晋级。

目标是在不降低证据门禁和人工审核质量的前提下，把同等规模案例的端到端机器/API 关键路径控制在冷启动 13 分钟内、缓存命中 8 分钟内；用户及时确认时，端到端墙钟时间目标为 20–30 分钟。用户等待时间、返工时间和机器/API 时间必须分开统计。

## 2. 实施边界

本文最初只定义优化方向、目标架构、阶段计划和验收标准；当前已进入 Track A 契约实施和唯一 pilot 前向验证。文档更新本身不得越过业务 Gate，媒体执行必须以 `pipeline_state.json` 的当前状态为准。

Track A / 当前 pilot 不做：

- 不绕过或合并用户必须确认的 Gate；
- 不在没有对应用户决定时修改 Gate 状态；
- 不在 Gate 4 生成前批准前调用 TTS，也不在 Gate 4 生成后批准前渲染正式成片；
- 不修改 Gate 1 参考事实或 Gate 3 已批准宽范围；
- 不设计或生成剪映加密草稿；
- 不建设 Web 管理后台、数据库服务或分布式任务系统；
- 不以测试覆盖率为目标扩展大型测试套件。

## 3. 真实案例基线

审计案例：`work/2026-08-11-douyin-tablemat-01/`。这是历史 V1 案例：原参考片有 16 个镜头，重构蓝图在删除/合并后为 12 段；不能把它与其他任务的 13 段蓝图当成固定模板。

案例的 `voice/` 目录已有真实 TTS 和技术渲染产物，`pipeline_state.json` 将 Gate 1–4 标为已通过、Gate 5 标为 `awaiting_user`；但 `recipe.json.audio.replacement_voice.status` 仍为 `not_started`，且语音 manifest 的合计时长字段未完整回写。这是一个历史产物回写不一致，说明当前案例不能作为“所有机器契约已闭环”的正向样板；评分和耗时只作回溯基线，不能据此宣称 V2 已实现。

参考片为 12.433333 秒、373 帧、16 个原始镜头；初版目标蓝图为 10.000001 秒，语音目录/技术成片记录的配音约 26.832063 秒，技术成片为 26.833008 秒。以下时间均标记为 `measurement_status=retrospective_not_stage_metrics`，混合了机器、API、人工等待和手工组织，不能当作机器性能实测。

### 3.1 墙钟时间

| 环节 | 约耗时 | 主要原因 |
|---|---:|---|
| Brief 到 Gate 1 | 20 分钟 | 临时命令、产物整理、人工确认 |
| Gate 1 到 Gate 2 | 11 分钟 | 手工组织蓝图、声明和脚本 |
| 第一版素材匹配 | 21 分钟 | 素材建档、人工语义判断、逐步生成候选 |
| Gate 3 等待 | 24 分钟 | 人工审核等待 |
| 删除三段并修订 Gate 2 | 38 分钟 | 蓝图、文案、时间轴和状态重编 |
| 修订后重建匹配 | 15 分钟 | 缺少按差异复用机制 |
| Gate 4 脚本包准备 | 12 分钟 | 再次组织语义组和审核产物 |

### 3.2 媒体计算子集（秒）

| 操作 | 约耗时 |
|---|---:|
| 导出 16 个参考镜头和关键帧 | 3 秒 |
| 生成约 96 张素材分析帧 | 48 秒 |
| 导出 12 个批准素材片段 | 5 秒 |

3.1 墙钟明细合计约 141 分钟；3.2 媒体操作合计约 56 秒。二者与文件时间到 Gate 5 预览约 277 分钟不一致，说明仍有未记录的手工组织、等待和返工时间。V2 必须用 `stage_metrics.jsonl` 逐项记录，不再用人工回忆补齐。

### 3.3 已发现的返工风险

当前重构蓝图为 12 段、`10.000001s`，同时声明 `duration_policy: voice_actual`。语音目录/成片记录的当前配音约为 `26.832063s`；当前蓝图口播有 99 个中文/字母/数字有效字符。上一个同类豆包案例中，85 个有效字符生成了 `25.776077s` 音频，约为 3.3 字/秒；后者只是历史字速参考，不是本案例的 TTS 实测。

按历史音色粗估，新文案可能接近 30 秒。即使最终音色语速存在差异，以下目标字速也已经明显不可行：

| 片段 | 有效字符 | 原目标时长 | 目标字速 |
|---|---:|---:|---:|
| fragment08 | 9 | 0.233333s | 38.6 字/秒 |
| fragment09 | 6 | 0.166667s | 36.0 字/秒 |
| fragment10 | 8 | 0.300000s | 26.7 字/秒 |
| fragment11 | 6 | 0.133333s | 45.0 字/秒 |

因此，旧的“Gate 3 先按参考时长精确导出画面，Gate 4 再取得真实语音时长”的顺序会使已批准源时段失效，是当前最大的潜在返工源；V2 改为 Gate 3 批准宽范围，Gate 4 实测音频后才确定精确裁点。

## 4. 根因与优先级

| 优先级 | 根因 | 类型 | 直接后果 |
|---|---|---|---|
| P0 | Skill 没有通用确定性执行器 | 架构 | 每次重复写命令、JSON 和恢复逻辑 |
| P0 | 旧流程在精确选材和导出后才发现真实配音/证据风险 | 依赖顺序 | 时间轴或文案变化后重做 Gate 3 |
| P0 | 素材覆盖晚于结构设计 | 内容流程 | Gate 3 才发现缺素材并返回 Gate 2 |
| P1 | 素材逐帧启动 FFmpeg 子进程 | 机器性能 | 候选数增长时匹配耗时近似线性放大 |
| P1 | 无跨任务素材索引和按片段缓存 | 机器性能 | 每次重扫、重抽帧、重算描述符 |
| P1 | 审批、计划和产物更新缺少统一事务 | 续跑可靠性 | 可能重复询问或读取过期状态 |
| P2 | 只看中点静帧审核动作候选 | 效果 | 动作不完整、跳切和重复构图发现过晚 |
| P2 | 过早反复正式渲染 | 机器性能/效果 | 每轮反馈都支付完整编码成本 |
| P3 | TTS 独立任务串行连接 | 机器性能 | 有优化空间，但不是当前主要耗时 |

## 5. 方案选型

### 方案 A：最小改造，保持现有依赖顺序

增加素材缓存、匹配批处理、字速预估和代理渲染，但仍在 Gate 3 后调用真实 TTS。

优点：Gate 文档改动小，实施风险最低。  
缺点：只能提前预警时长问题，不能彻底消除“真实配音改变精确素材时段”的返工。

### 方案 B：Gate 顺序纠正 + 增量执行器（V2 目标基线）

Gate 2 只批准内容基线；Gate 3 先批准素材源和宽可用范围，再生成逐句画面证据矩阵并等待用户对当前哈希明确批准；Gate 3 汇总通过后确定性编译生产脚本候选；Gate 4 生成前确认脚本与 TTS 设置，通过后才调用真实 TTS；实测时长确定字幕与累计画面时间轴，Gate 4 生成后听审通过后才进入代理和正式渲染。

优点：把“素材证据不足”和“口播不可落地”拦在真实 TTS 前，减少废弃音频和 Gate 往返；同时保留最终声音听审。  
缺点：不再获得约 30–45 秒的 TTS/素材匹配并行收益；需要同步升级产物契约和执行器。

### 方案 C：建设常驻服务和任务平台

把素材索引、队列、审批和渲染做成常驻服务或 Web 平台。

优点：适合大量运营并发和集中监控。  
缺点：当前案例量不足以支持该复杂度，开发与维护成本过高。

结论：采用方案 B 作为 V2 生产基线；Track B 增量执行器已经合并到主干并完成真实 cold/hot 配对。暂不建设方案 C。V1 任务继续按创建时契约续跑，不能把旧批准解释成 V2 授权；新 V2 case 先完成 Stage 0 冻结输入，再通过隔离 `gb-pair` 逐 Gate 运行。只有 G-B 和监督运营试用通过后，才允许普通新任务按 V2 production 入口启动。

## 6. 目标流程

```text
输入预检（旧执行层 legacy Stage 0）
                  ↓
[Performance-proven Video]
  参考片探测 → 镜头候选 → 关键帧/音轨/ASR → Gate 1
                  ↓
[Blueprint]
  叙事骨架 → 卖点证明链 → 覆盖缺口预判 → content_baseline 草案
                  ↓
[Controlled Mutation]
  记录允许/禁止变化与 fallback → mutation_plan 草案
                  ↓
Gate 2 原子批准 content_baseline + mutation_plan
                  ↓
[Retrieval]
  素材索引/覆盖 → 资格门禁 → 视觉评分 → 全局排程
                  ↓
  Gate 3 选材确认 → 逐句口播-画面证据校验 → Gate 3 证据闭环
                  ↓
[Controlled Mutation]
  编译最终生产脚本候选
                  ↓
Gate 4 生成前确认（脚本、模型、音色、语速、发音风险）
                  ↓
[Reconstruction]
  TTS + 宽范围素材准备 → 实测时长 → 字幕/画面累计时间轴 → 精确裁点（限 Gate 3 宽范围）
                  ↓
Gate 4 生成后听审 → 代理/边界审查 → 正式渲染
                  ↓
Gate 5：最终预览
```

五阶段是 ownership 域，不要求每个阶段只出现一次连续执行块：Controlled Mutation 在 Gate 2 前定义变更契约，并在 Gate 3 证据闭环后再次执行确定性脚本编译。只有不依赖待批准内容的技术索引和参考片预处理可以提前并行。所有生产 TTS、最终生产脚本、精确裁点和成片组装都服从上图顺序；不得用“候选音频”绕过 Gate 4 生成前确认。

### 6.1 V2 契约迁移边界

本 V2 基线会改变 Gate 2、Gate 3 和 Gate 4 的输入与允许动作，属于明确的契约迁移，不是对现行 V1 的解释性微调。下方顺序只适用于完成迁移并升级 schema 的 V2 任务；未迁移的 V1 任务继续遵循创建时的 Gate 契约。

实施时必须同步更新：

- `AGENTS.md`；
- `.agents/skills/remix-reference-video/SKILL.md`；
- 五份 `references/*.md`；
- `docs/reference-video-remix-sop.md`；
- Brief 模板和受影响的 JSON schema/version；
- `agents/openai.yaml` 中与默认流程相关的描述。

旧任务迁移规则：

1. 已经开始的 V1 任务默认继续按创建时的 V1 契约续跑，不自动迁移。
2. V1 任务不得复用 V2 Gate 批准或把 V1 旧批准解释成 V2 授权。
3. 用户明确要求迁移单个任务时，生成迁移报告，列出旧/新阶段映射、失效 Gate、输入哈希和需重新批准项。
4. G-A 通过后，新 V2 case 先通过隔离 `gb-pair` 采集真实生产证据；该配对不是普通生产发布，不进入 `final/`，也不能复用其他任务审批。只有 G-B 和监督运营试用通过后，才允许普通新任务按 V2 production 入口启动。
5. 共享技术缓存可以跨版本复用，但只有缓存 schema 和生成器版本都匹配时才可命中；审批和生产计划不能跨版本复用。

### 6.2 Gate 调整

Gate 编号和最终授权人不变，只调整 Gate 2 与 Gate 4 的输入、允许动作和职责边界：

| Gate | 调整后职责 |
|---|---|
| Gate 1 | 参考镜头切分和异常切点 |
| Gate 2 | 原子批准 `{content_baseline_hash, mutation_plan_hash}`：目标结构、批准卖点、禁用声明、口播意图/时长包络、允许变更与回退规则；不调用真实 TTS |
| Gate 3 选材确认 | 批准素材源、动作完整性、叠字/连续性和足够宽的可用时间范围，形成不可变 `fragment_plan.json`；同时冻结 `media_type` 与视频画面时长预算（`approved_end-approved_start`，图片为 `null`）；不锁死最终精确裁点 |
| Gate 3 证据闭环 | 将每句候选口播映射到选材确认子状态批准的证据窗；机器 `pass` 只表示审核包可提交，仍须用户对当前哈希明确批准后才闭环；`review_required` 必须回到同一 Gate 3 取得明确决定 |
| Gate 4 生成前 | `voice_preflight.json` 通过后的最终生产脚本、模型/协议、音色、语速、发音和字速风险；预检必须先于 TTS |
| Gate 4 生成后 | 实际音频、实测时长、字幕断句、累计画面时间轴、Gate 3 宽范围内的精确裁点和听审结果 |
| Gate 5 | 最终视频、SRT、报告和导入清单 |

V2 中，Gate 2 之前和 Gate 3 之前不得调用真实 TTS；Gate 2 不批准最终生产脚本，只原子批准 Blueprint 的 `content_baseline.json` 与 Controlled Mutation 的 `mutation_plan.json`。Gate 3 汇总状态只有在 `gate3_material_selection` 与 `gate3_evidence_closure` 都对当前输入哈希有效时才为 `approved`；任一必需片段或动作组仍为 `awaiting_user|blocked|stale` 时，不得编译完整生产脚本或生成生产媒体。Gate 3 通过后，Controlled Mutation 编译 `production_script_candidate.json`，Reconstruction 根据 Gate 3 画面预算生成 `voice_preflight.json`；只有预检通过才生成 Gate 4 生成前确认包。通过后由同一审批事务提升为不可变 `approved_production_script.json` 并允许 Reconstruction 开始。Gate 4 的生成后听审不能因生成前已批准而取消。V1 任务仍按创建时的 Skill 契约执行，不把本段当作对旧任务的追溯授权。

配音调用的唯一时机是：Gate 3 画面预算 → `voice_preflight` → `gate4_pre_generation=approved` → 真实 TTS。精确源时段的唯一时机是：TTS → 实测音频预算复核 → 构建 `reconstruction_timeline.json` → `gate4_post_generation` 听审。不得把“Gate 4 后”含混理解为生成后听审完成后才裁点。失效规则如下：

- 精确时段完全位于 Gate 3 批准的宽范围内：执行确定性裁点和验证，不新增 Gate；
- `voice_preflight` 估算超出视频预算：在 TTS 前阻断，只允许缩短文案、使用 Gate 2 fallback、扩大 Gate 3 宽范围或返回 Gate 2 调整结构；预检未通过不得生成 Gate 4 审核包；
- TTS 实测超出视频预算：保留诊断音频但不得进入正式时间轴，返回受影响 Gate 3/4；不得自动变速、冻结尾帧或越过批准范围；
- 精确时段超出批准范围，或需要更换源素材：将受影响片段/动作组的 Gate 3 和下游状态标为 `stale`，返回 Gate 3；
- 相同文案、相同模型/音色/语速下的技术性重试：只使 Gate 4 生成后音频和下游失效；新时长仍落在 Gate 3 宽范围内时复用素材批准，否则使受影响片段/动作组的 Gate 3 失效；
- 更换模型、音色、语速或其他已批准配音设置：使 `gate4_pre_generation`、`gate4_post_generation`、对应音频、字幕、精确时间轴、渲染和 Gate 5 失效；只有新实测时长超出 Gate 3 宽范围时才使相关 Gate 3 失效，只有超出 Gate 2 时长包络时才返回 Gate 2；
- 修改口播文本但命中 Gate 2 已批准 fallback，且不改变口播意图、声明、语义组和时长包络：使证据矩阵、生产脚本、Gate 4 和下游失效，Gate 2 可复用；新增声明、改变口播意图/语义组或超出时长包络时，才使 Gate 2、受影响 Gate 3 和全部下游失效；
- 返回 Gate 3 时复用素材索引、语义粗排和未变化片段，缓存命中目标为 30 秒内重新生成受影响审核包；不得复用旧的 Gate 4 生产批准。

Gate 3 不拥有删并段权限。运营在 Gate 3 发现缺素材时只能记录 `request_omit`、`request_merge` 或 `request_restructure`；系统必须返回 Gate 2，重新生成并批准 `content_baseline.json + mutation_plan.json`，再重跑受影响 Retrieval。只有 Gate 2 新基线通过后，下游才能把片段记为 `omitted_by_user`。

### 6.3 五阶段产物 ownership

| 产物 | 唯一 owner | 是否可变 | 下游使用规则 |
|---|---|---|---|
| `recipe.json` 的参考拆解事实 | Performance-proven Video | Gate 1 后不可变 | 只记录参考视频、参考镜头和参考音频；V2 不再由 TTS 回写 |
| `coverage_precheck.json` | Retrieval 只读预计算 | Blueprint 草案变化后重算 | 只供 Gate 2 发现缺口，不是批准依据 |
| `content_baseline.json` | Blueprint | Gate 2 以新版本替换 | 与 `mutation_plan_hash` 组成 Gate 2 原子批准 bundle |
| `mutation_plan.json` | Controlled Mutation | Gate 2 以新版本替换 | 记录允许/禁止变化和 fallback，不得由 Retrieval 改写 |
| `coverage_report.json`、`matches.json`、`script_evidence_matrix.json` | Retrieval | 输入变化后生成新版本 | 生命周期为 `ready|blocked|stale`；审批引用写在 `pipeline_state.json` |
| `fragment_plan.json` | Retrieval | Gate 3 后不可变 | 只保存批准素材源和宽范围；精确裁点不得覆盖它 |
| `voice_preflight.json` | Reconstruction | Gate 3 汇总后、Gate 4 生成前 | 逐段绑定画面预算和配音估算；阻塞项必须在 TTS 前处理 |
| `production_script_candidate.json`、`approved_production_script.json` | Controlled Mutation | 候选可重建；批准版不可变 | 批准版只能由 Gate 4 生成前事务提升，是 TTS 唯一文本输入 |
| `material_manifest.json`、`reconstruction_timeline.json` | Reconstruction | 按有效批准输入重建 | 前者记录物理复制/宽范围导出，后者记录实测音频后的精确裁点并验证 containment |
| 配音、字幕、代理、正式视频和交付报告 | Reconstruction | 输入哈希变化后重建 | 只消费批准脚本、Gate 3 宽范围和任务目录 `material/` |

为避免事实层自我失效，V2 的真实配音时长只写 `voice_manifest.json`、`duration_report.json` 和 `reconstruction_timeline.json`。V1 为兼容而保留的 `recipe.audio.replacement_voice` 只视为派生指针；迁移工具必须明确 Gate 1 哈希只覆盖参考事实子树，不能因 Reconstruction 回写而让 Gate 1 反向变为 `stale`。

## 7. 优化模块

### 7.1 参数化增量执行器（P0）

未来为 Skill 增加 `scripts/`，执行器只负责确定性动作，Codex 负责语义判断和 Gate 沟通。

V2 不再使用含混的 `export-approved` / `export-approved-broad`。统一命令契约如下；`apply-gate-decision` 只写入 Codex 已整理且用户明确确认的结构化决定，绝不自行批准：

| 命令 | Owner | 前置状态 | 主要输入 → 输出 | 状态写入与失效范围 | 幂等键 / 退出码 |
|---|---|---|---|---|---|
| `preflight` | 支持事件（不计五阶段） | 无 | Brief、参考片、素材根 → 预检报告 | 只记录阻塞项，不创建 Gate 批准 | 输入指纹；`0` 成功，`2` 待补输入，`10` 契约错误，`20` 媒体/工具错误 |
| `split-reference analyze|export` | Performance-proven Video | 预检通过；`export` 需切点修订文件 | 参考片、切点修订 → `recipe.json`、`video_clips/`、Gate 1 审核包 | 不自批；参考输入变化使 Gate 1 及下游 stale | 参考 SHA + 参数/修订哈希；统一退出码 |
| `index-assets` | Retrieval 只读预计算 | 素材根可读 | `assets/` → 共享技术索引、任务级 `asset_profiles.json` | 不修改 Gate；索引版本变化只使依赖它的覆盖/匹配 stale | 素材 SHA + 索引器版本 |
| `build-coverage --scope precheck|authoritative` | Retrieval | `precheck` 需蓝图草案；`authoritative` 需 Gate 2 | Brief、蓝图/内容基线、索引 → 两类 coverage 产物 | 不自批；权威报告变化使 Gate 3 及下游 stale | scope + 输入哈希 + taxonomy 版本 |
| `compile-blueprint` / `compile-mutation-plan` | Blueprint / Controlled Mutation | Gate 1 | 参考事实、Brief、覆盖预判 → `content_baseline.json` / `mutation_plan.json` 草案 | 草案变化使 Gate 2 及下游 stale | 输入哈希 + 编译器版本 |
| `lint-voice-timing` | Blueprint | Gate 2 前草案可用 | 内容基线、历史字速统计 → 时长/字速报告 | 只阻塞 Gate 2，不写批准 | 文本/语义组/音色方向哈希 |
| `match-assets` | Retrieval | Gate 2 | 内容基线、变更计划、索引、权威 coverage → `matches.json`、候选审核包 | 不自批；候选输入变化使 Gate 3 及下游 stale | Gate 2 bundle + index/scoring 版本 |
| `prepare-review --gate <id>` | 对应阶段 | 当前 Gate 输入齐全 | 当前产物 → 业务摘要、证据包和结构化选项 | 只将当前 Gate 置 `awaiting_user` | Gate 输入 bundle 哈希 |
| `apply-gate-decision` | 横向状态事务 | 用户已对当前展示哈希明确决定 | 结构化决定 → `pipeline_state.json` 审批记录 | 按 scope 原子写入批准/拒绝并传播 stale；不执行媒体生成 | `gate_id + scope + input_hash + decision_id`；冲突为 `30` |
| `validate-script-evidence` | Retrieval | Gate 3 选材确认子状态齐全 | Gate 2 bundle、`fragment_plan.json` → `script_evidence_matrix.json` | `review_required` 令 Gate 3 证据闭环保持 awaiting；不隐式批准 | 选材决定哈希 + 证据规则版本 |
| `build-production-script` | Controlled Mutation | Gate 3 汇总 approved | 内容基线、变更计划、证据矩阵 → `production_script_candidate.json` | 不写 Gate 4 批准；未命中 fallback 时返回 Gate 2/3 阻塞 | 三个输入哈希 + 编译器版本 |
| `promote-production-script` | Controlled Mutation | Gate 4 生成前明确批准 | 候选脚本、TTS 设置、Gate 决定 → `approved_production_script.json` | 与 `gate4_pre_generation` 在同一小型事务中原子提升；使旧音频下游 stale | 决定 ID + 候选/TTS 设置哈希 |
| `materialize-approved-broad` | Reconstruction | Gate 3 汇总 approved | `fragment_plan.json`、源素材 → `material/`、`material_manifest.json` | 不改变 Gate 3 哈希；失败阻塞 Reconstruction，可重试 | Gate 3 bundle + 源 SHA |
| `voice-preflight` | Reconstruction | Gate 3 汇总 approved、脚本候选和 fragment plan 可用 | `production_script_candidate.json`、`fragment_plan.json` → `voice_preflight.json` | 负 margin 阻塞 Gate 4 包和 TTS；图片不计算源时长预算 | 候选/范围/估算器/语速哈希 |
| `generate-voice` | Reconstruction | Gate 4 生成前 approved | 批准脚本、TTS 设置 → voice 产物、实测时长 | 只写生成状态；失败不生成半成品、不自批 Gate 4 后状态 | 文本/TTS/协议哈希；外部服务错误为 `40` |
| `build-reconstruction-timeline` | Reconstruction | 有完整实测音频和 material manifest | Gate 3 宽范围、实测时长 → `reconstruction_timeline.json`、SRT | 超宽范围返回受影响 Gate 3；不原地改 `fragment_plan.json` | 宽范围 + 音频 + 帧率哈希 |
| `render-proxy` / `render-final` | Reconstruction | 前者需 Gate 4 生成后 approved；后者还需代理检查通过 | 精确时间轴、material、voice → 代理/正式 MP4 与报告 | 不自批 Gate 5；输入变化使旧渲染/Gate 5 stale | 全部渲染输入哈希 |
| `validate [stage|delivery]` | 横向验证 | 对应产物存在 | schema、路径、哈希、媒体、Gate → 验证报告 | 只报告/阻塞，不把 failed 改为 passed | 验证器版本 + 输入 bundle |
| `archive-approved` | Reconstruction 交付 | Gate 5 approved 且哈希仍有效 | 正式 MP4、SRT、报告 → `final/` | 记录归档，不改上游批准 | Gate 5 决定 + 交付 bundle；权限/路径错误为 `50` |
| `resume` / `status` / `audit` | 横向编排 | 任务目录存在 | `pipeline_state.json`、指纹 → 下一可执行步骤/只读报告 | `resume` 只运行有效 Gate 允许的步骤；`audit` 不生成生产媒体 | 当前状态版本 |

统一退出码：`0=success_or_cache_hit`、`2=awaiting_user_or_input`、`10=contract_validation_failed`、`20=local_media_or_tool_failed`、`30=gate_or_state_conflict`、`40=external_api_failed`、`50=promotion_or_archive_failed`。具体错误写入可读报告；命令行和报告都不得包含凭证值。

执行器需要支持：

- 所有输入路径参数化，不包含旧案例日期、绝对路径、13 段或固定时长；
- `--resume` 从 `pipeline_state.json` 的有效阶段继续；
- `--force` 只覆盖明确命名的本工具产物，并先 staging；
- 每阶段生成输入指纹、输出哈希、开始时间、结束时间和缓存命中信息；
- 输入未变时返回 `cache_hit`，不重复处理；
- 片段变化时只重算对应片段和受影响的连续动作组；
- Gate 未批准时，只允许生成该 Gate 的审核包，不得越级产生生产产物；
- 失败时保留有效上游结果，并给出明确恢复阶段。

执行器不负责自动决定卖点是否获批、低置信度候选是否可以使用、音色是否符合品牌或最终视频是否可发布。

#### 7.1.1 `split-reference` 的固化边界

参考片拆解建议固化成“分析”和“按审核决定导出”两步，避免把单一阈值当成最终镜头事实：

```text
split-reference analyze
  → ffprobe、解码检查、源哈希
  → 全帧 scene score、强切候选、低分局部峰值
  → 单帧/超短镜头/密集蒙太奇报警
  → 候选前/当前/后帧和 raw_detection.json
  → Gate 1 审核包

split-reference export --revision cut-review.json
  → 应用人工 add/remove/merge/keep 决定
  → 生成连续帧边界、代理镜头、关键帧、参考音轨和 recipe.json
  → 校验后等待 Gate 1 批准
```

可确定性固化的部分包括：探测/解码、候选分数采集、异常规则、帧边界计算、关键帧和审核代理导出、哈希、缓存、续跑及校验。低分变化是动作切换还是镜头内运动、单帧是有意闪切还是异常、渐变/遮挡如何归类，仍由 Gate 1 人工裁决。本案例证明这一点：只用主阈值会漏掉低分真实动作切换，而把所有运动峰值都当切点又会误切。

固化本身不会损伤参考源：原视频不改写，参考音轨优先码流复制；生产和机器分析始终以“原片 + 帧边界”为权威。代理镜头和低清接触表允许有损重编码，但不得再作为最终生产源；每镜头至少保存一张全分辨率关键帧，动作镜头增加 start/mid/end 三帧或短审核微视频。自动校验必须证明从帧 0 到总帧数无 gap/overlap，并记录每个候选的帧号、时间、分数和人工结论。

### 7.2 共享素材索引（P0）

素材索引是可删除、可重建的缓存，不是生产依据。不得写入或修改 `assets/`。共享缓存只保存与任务 Brief 无关的技术事实和通用描述符；与具体产品、卖点和场景目标相关的语义资格仍写入单次任务的 `asset_profiles.json`。

建议缓存位置：

```text
work/_cache/remix-reference-video/assets/<source-sha256>/<cache-version>/
```

每个源 SHA 缓存：

- `ffprobe` 元数据；
- 场景切点；
- 低分辨率批量采样帧；
- 颜色、亮度、构图、清晰度描述符；
- 关键帧感知哈希；
- OCR 结果和叠字区域；
- 可复用的产品类别、通用场景、可见动作、景别和来源类型候选标签；
- 索引器版本、参数版本和错误信息。

缓存键至少包含：

```text
source_sha256 + index_schema_version + sampler_version + model_or_rule_version
```

同一素材只冷建档一次。文件名变化但 SHA 不变时复用；源内容或索引版本变化时自动失效。

共享目录还需要一个可重建的路径目录：

```text
work/_cache/remix-reference-video/asset_catalog.json
```

目录记录当前扫描到的 `assets/` 相对路径、源 SHA、媒体类型、源文件夹组和最近一次可见时间。每次任务都重新扫描当前路径并验证 SHA：

- 文件改名或移动但 SHA 不变：复用技术缓存，同时更新当前相对路径；
- 文件被删除：缓存可保留，但不得作为当前可选素材；
- 来源文件夹变化：任务级连续性分组使用当前路径和显式 `source_group`，不能只看 SHA；
- 同一 SHA 出现在多个路径：识别为重复内容，同时保留当前路径清单供人工溯源。

并发写入规则：

1. 以 `source_sha256 + cache_version` 为锁粒度，锁和最终目标目录使用同一组键；
2. 写入唯一 staging 目录；
3. 所有帧、描述符和 manifest 校验通过后原子提升；
4. 其他任务只读取已经提升的完整版本；
5. 进程异常留下的 staging 可清理，不得被视为缓存命中。

`asset_catalog.json` 使用独立的目录级写锁。写入者取得锁后重新读取最新快照、合并本次扫描结果、写入唯一临时文件，验证完成后原子替换；读者只读取完整快照。不得让不同素材锁的写入者直接同时覆盖同一 catalog。catalog 可以从 `assets/` 和已提升缓存重新构建，损坏时不得影响源素材。

引入该目录前，V2 必须同步更新 `AGENTS.md` 和 `references/project-layout.md`，明确 `_cache` 不属于单次任务、不进入 `final/`、不承载审批或生产权威。

### 7.3 素材覆盖矩阵（P0）

素材覆盖分成三层，不能混为一个“素材分数”：

- `index-assets` 只生成跨任务可复用的技术事实和通用标签，写入共享缓存；
- `build-coverage --scope precheck` 结合 Brief、蓝图草案和当前索引生成 `coverage_precheck.json`，只用于 Gate 2 前发现明显缺口，不代表 Retrieval 已完成，也不能批准候选或进入生产；
- `build-coverage --scope authoritative` 在 Gate 2 内容基线通过后，结合其哈希和素材索引生成权威 `coverage_report.json`，供资格门禁、排程和 Gate 3 使用。

两个产物不得通过改字段原地晋级：权威报告必须以 Gate 2 内容基线重新计算并记录新输入哈希。最小契约如下：

```json
{
  "artifact_type": "coverage_report",
  "schema_id": "urn:capcut:remix-reference-video:artifact:coverage-report",
  "schema_version": "1.0.0",
  "contract_version": "2.0.0-alpha.1",
  "skill_version": "2.0.0-alpha.1",
  "coverage_scope": "authoritative",
  "run_id": "uuid",
  "input_hashes": {
    "brief": "sha256",
    "recipe": "sha256",
    "draft_blueprint_or_content_baseline": "sha256",
    "asset_index": "sha256"
  },
  "taxonomy_version": "claims-actions-v1",
  "rows": [
    {
      "fragment_id": "fragment01",
      "claim_ids": ["claim_transparent"],
      "required_evidence": ["product_visible", "wood_grain_visible"],
      "evidence_asset_ids": ["asset-..."],
      "coverage_level": "strong",
      "action_completeness": "complete",
      "allowed_media_types": ["video", "image"],
      "risk_flags": ["overlay_present"],
      "decision": "design_ready"
    }
  ],
  "summary": {"strong": 0, "partial": 0, "static_only": 0, "none": 0},
  "lifecycle_status": "ready|blocked|stale",
  "approval_ref": null
}
```

`coverage_precheck.json` 使用相同 envelope，但将 `artifact_type`/`schema_id` 分别改为 `coverage_precheck`/`urn:capcut:remix-reference-video:artifact:coverage-precheck`，并令 `coverage_scope=precheck`。两者都是独立产物，不能通过手改 `coverage_scope` 原地晋级。

每个任务级语义标签必须同时记录：标签词表/版本、来源（规则/模型/人工）、置信度、证据帧或时间窗、人工覆盖值和审核状态。例如“倒油”不能只写在文件级 `visual_tags`，还要记录它发生的 `[start_frame, end_frame_exclusive)`；无法定位到时间窗时只能标为 `partial` 或 `needs_review`。

Gate 2 审核包只展示 `coverage_precheck.json`，在结构批准前回答：

- 哪些卖点有强视觉证据；
- 哪些动作有完整视频；
- 哪些只能由静态图承载；
- 哪些片段会重复同一房间或同一来源；
- 可支持的最大蒙太奇数量；
- 缺素材、需补拍和建议删并段项。

蓝图优先围绕已有证据设计。不得先批准理想化结构，再到 Gate 3 用无关素材补洞。

覆盖判断的最低规则是：`strong` 才能直接支撑强声明；`partial` 必须人工确认或使用 Gate 2 已批准的 fallback；`static_only` 只能用于允许静态承载的片段，不得证明动作完整性；`none` 直接阻塞该片段并建议补素材、改结构或删段。Brief、蓝图或卖点变化使预判和权威报告 stale，并返回 Gate 2；素材内容/哈希、标签或索引版本变化只使权威 `coverage_report`、Gate 3 及下游 stale，除非新的权威报告证明 Gate 2 结构已不可实现，才提出返回 Gate 2。

Gate 3 的人工覆盖也要结构化记录：运营可以对候选执行 `lock`（锁定）、`replace`（替换）、`reject`（拒绝）、`approve_broad_range`（批准宽范围）、`approve_overlay`（批准叠字）或 `request_omit`（申请返回 Gate 2 删段）。每个决定保存展示输入哈希、候选/时间范围、操作人、时间和备注；部分批准只影响指定片段或动作组。候选源、文案、证据窗或素材哈希变化时，系统只使受影响片段/动作组及其下游变为 `stale`，不能继续使用旧批准；单纯改变音色、模型或语速不直接使 Gate 3 失效。

### 7.4 逐句证据与配音时长可行性（P0）

每个音色维护历史统计：

- 有效字符数；
- 解码后实测时长；
- 中位字速和 P10/P90；
- 标点、数字、英文和停顿对时长的影响；
- 语速参数和模型版本。

Gate 2 只检查内容基线的可行性：

1. 单片段目标字速；
2. `span_group_id` 整句目标字速；
3. 全片目标字速；
4. 目标时长与历史区间的偏差；
5. 是否同时存在“不能删字、不能变速、必须固定时长”等冲突要求。

明显不可能时停止进入素材批准，给出三种选择：精简口播意图、放宽成片时长包络或更换已验证的语速/音色方向。不得自动删字或加速。Gate 2 记录的是目标范围和风险，不把尚未有画面证据的最终句子标为可生成。

短闪切镜头可以共享一句口播。音频按语义组生成，画面切点不必等于语音断句点。

#### 7.4.1 `script_evidence_matrix.json` 与生产脚本候选

Gate 3 选材确认子状态齐全后，执行器为每句口播生成逐句证据矩阵；此时 Gate 3 汇总状态仍不得提前显示 `approved`。最小字段如下：

```json
{
  "artifact_type": "script_evidence_matrix",
  "schema_id": "urn:capcut:remix-reference-video:artifact:script-evidence-matrix",
  "schema_version": "1.0.0",
  "contract_version": "2.0.0-alpha.1",
  "skill_version": "2.0.0-alpha.1",
  "status": "pass|blocked|review_required|stale",
  "content_baseline_hash": "sha256",
  "gate3_decision_hash": "sha256",
  "rows": [
    {
      "sentence_id": "sentence01",
      "fragment_ids": ["fragment01"],
      "text": "餐桌要保护, 木纹要看见。",
      "claim_ids": ["claim_protect_table", "claim_wood_grain_visible"],
      "approved_asset_ids": ["asset-..."],
    "evidence_windows": [{
      "asset_id": "asset-...",
      "media_type": "video",
      "source_start": 0.0,
      "source_end": 1.2,
      "start_frame": 0,
      "end_frame_exclusive": 36,
      "approved_broad_range": {"start": 0.0, "end": 2.0}
    }],
      "evidence_level": "strong|partial|missing",
      "action_status": "complete|static_only|not_applicable|missing",
      "decision": "pass|revise_at_gate3|return_gate2",
      "reason": ""
    }
  ]
}
```

`strong + complete` 才能直接支撑强声明；`partial` 必须改弱文案或取得运营覆盖；`static_only` 只能用于允许静态承载的句子；`missing` 阻塞最终生产脚本。任何句子新增未在 `content_baseline` 中批准的声明，直接 `return_gate2`。

通过矩阵后，Retrieval 只输出 `script_evidence_matrix.json` 和 `pass|blocked|review_required` 结果；每个 `evidence_window` 必须记录 `asset_id`、`media_type`、`source_start`、`source_end`（或起止帧）及 `approved_broad_range`，明确它属于 Gate 3 宽范围而非最终裁点。`review_required` 只允许在 Gate 3 审核包中由运营选择已批准候选、改用 Gate 2 fallback 或返回 Gate 2；没有明确决定不能自动转为 `pass`。Controlled Mutation 的 `build-production-script` 再将内容基线中的句子、已批准 fallback、画面证据、语义组和宽时长包络编译为 `production_script_candidate.json`。编译器必须记录 `content_baseline_hash`、`gate3_decision_hash`、`script_evidence_matrix_hash` 和编译器版本；不得静默删句、改弱声明或新增卖点，任何变化都必须命中 Gate 2 已批准的 fallback，否则返回 Gate 3 或 Gate 2。Gate 4 生成前通过后，才将候选提升为 `approved_production_script.json`，作为唯一 TTS 输入。

#### 7.4.2 `voice-preflight` 与 `generate-voice` 的固化边界

`voice-preflight` 是 TTS 前的硬阻塞检查，不是对真实音频时长的替代：

- Gate 3 冻结的视频 `visual_duration_budget_seconds = approved_end - approved_start`；图片没有源视频预算，记录为 `null`；
- 预检按逐段文案的非标点字数、标点停顿、音色历史平均语速和拟用语速估算 `voice_duration_estimate_seconds`，并记录 `voice_duration_margin_seconds = visual_budget - estimate`；
- 任一视频 margin 为负时，不生成 Gate 4 审核包、不调用 TTS。恢复只能是缩短文案、使用 Gate 2 fallback、扩大 Gate 3 范围或返回 Gate 2 调整结构；
- Gate 4 批准的语速必须与预检一致。TTS 完成后仍要用实测时长复核预算，超出时保留诊断音频但返回 Gate 3/4，不得变速、冻结尾帧或越过宽范围。

TTS 执行器可以固化机械流程，但不能替运营批准文案、音色或品牌语气：

- 输入只接受 Gate 4 生成前批准的 `approved_production_script.json`、`span_group_id`、模型/音色/语速设置和凭证引用；密钥只从运行时环境读取，不写入 JSON、日志或错误截图；
- 同一 `span_group_id` 整句调用一次，调用键包含文本哈希、模型/音色/语速、协议版本和请求参数；命中缓存时复用已验证音频，不重复请求；
- 每个响应立即落 staging，解码并用 `ffprobe` 读取实际采样率、声道和时长；任何接口错误、空音频、损坏文件或音色无效都停止批处理，不生成不完整的 `final_voice.mp3`；
- 片段文件按稳定的 `fragment_id` 顺序生成；需要从整句切片时在解码 PCM 上按累计采样边界切分，切片和原句的总采样误差不得超过一个采样；
- manifest 记录 `requested_model`、实际协议、voice type、调用组、输入/输出哈希、实际时长、目标时长和 `delta=actual-target`，但不伪造 OpenSpeech 不接受的模型字段为路由参数；
- 全部片段和时长报告通过校验后才拼接最终音频，并将真实时长写入 `duration_report.json` 和 `reconstruction_timeline.json`；V2 不改写 Gate 1 的 `recipe.json`。文案或设置变化只使受影响语义组及其下游失效。

配音执行器只负责“调用、解码、测量、切片、拼接、回写和报告”，不负责自动删字、变速、补静音、替换音色或把失败候选当作成功产物。

### 7.5 批量粗排与精排匹配（P1）

匹配从“每个候选独立抽帧”改为：

1. 每个视频单次批量解码低清分析帧；
2. 使用场景边界和约 1 秒锚点做粗排；
3. 每个片段只保留少量高分源范围；
4. 在前几名附近按 0.2 秒做局部精排；
5. 对动作候选检查开始、中间、结束及动作完整性；
6. 全局排程后才生成前三候选审核微视频和接触表；
7. Gate 3 汇总通过后，Reconstruction 才复制完整源或导出批准的宽素材范围；`gate4_pre_generation` 通过并取得 TTS 实测时长后，再在该范围内确定精确裁点。

#### 7.5.1 资格门禁和评分口径

资格按固定顺序裁决，先于任何视觉排序：

1. **产品兼容**：主体产品类别、尺寸和可见度满足片段要求；
2. **卖点证据**：有对应证据帧/时间窗，且声明在批准清单内；
3. **动作完整**：需要动作时必须有开始、进行、结束，动作对必须同源且零间隙；
4. **媒体与时长**：媒体类型被允许，源范围足够，不能靠变速或长尾冻结补足；
5. **裁切与叠字**：竖屏裁切、产品主体、内嵌文字/品牌/水印风险可处理；
6. **身份连续**：角色、场景或产品身份要求不能被破坏。

每项输出 `pass|fail|review`、证据路径和原因。产品/证据/动作/媒体类型/越界属于硬失败；裁切、叠字和身份不确定属于人工 `review`。硬失败候选 `eligible=false`，最高 `confidence=0.59`，不得被颜色或构图分数救回。

审核分数拆为：

- `eligibility`：产品、动作、媒体类型和禁用语义是否合格；
- `evidence_score`：能否证明当前卖点；
- `visual_similarity_score`：颜色、亮度、构图和景别是否接近；
- `continuity_score`：与前后镜头的房间、身份、动作和色彩连续性；
- `technical_score`：清晰度、裁切、叠字和可用时长。

为兼容现行 V1，候选置信度仍使用六项固定权重：

```text
confidence = 0.30 * semantic_score
           + 0.20 * action_timing_score
           + 0.20 * composition_score
           + 0.15 * color_score
           + 0.10 * brightness_contrast_score
           + 0.05 * technical_score
```

上述五类审核摘要映射为：`evidence_score` 纳入 `semantic_score`，`visual_similarity_score` 拆为构图/颜色/亮度三项，`continuity_score` 只用于全局排程的软约束，不重复计入单候选置信度，`technical_score` 保持 5%。所有分项先归一化到 0–1，缺失值不得默认为满分，必须标记 `unknown` 并触发人工复核。评分报告记录 `scoring_policy_version` 和校准日期，跨版本比较时标记不可比。

总置信度不能掩盖语义不合格。资格失败仍保持最高 `0.59`；低于 `0.60` 的片段必须是 `missing_material`，不能静默降级为占位。

#### 7.5.2 全局排程是确定性约束模型

全局选择不是逐段贪心。输入为候选集合、人工锁定、动作组和相邻片段上下文；输出必须包含选择顺序、约束命中和无解原因。约束分三层：

- **硬约束**：候选必须 `eligible=true` 且 `confidence>=0.60`；源时段不越界；同一动作对同源、零间隙（`next.start_frame == previous.end_frame_exclusive`）；不得使用损坏媒体或未决叠字；人工 `reject`/`lock` 必须服从；
- **软约束**：连续三段不使用同一源文件；相邻同房间且构图相似度 `>=0.90` 不连用；减少同一感知哈希重复；保持角色/空间/色彩连续；最大化 `continuity_score` 和候选总分；
- **优先级与平分**：先最大化合格命中数，再最大化总置信度，再最大化连续性分，最后按 `fragment_id`、候选排名和源起始帧升序确定性打破平分。

无解时输出 `schedule_status=blocked`、最早冲突约束、受影响片段/动作组和三种可操作建议（换候选、补素材、改结构）；不得自动放宽硬约束。运营锁定或替换候选后，只重算受影响片段及其相邻窗口/动作组，并记录旧计划已失效。

### 7.6 增量重算（P1）

建立阶段依赖图：

```text
[Performance-proven Video] Brief/参考片 → recipe
[Retrieval 只读预判] Brief/recipe/asset-index → coverage_precheck (non-authoritative)
[Blueprint] Brief/recipe/coverage_precheck → draft-blueprint → content_baseline
[Controlled Mutation] content_baseline/claims → mutation_plan → Gate 2 atomic bundle
[Retrieval] Gate 2 bundle/asset-index → coverage_report (authoritative) → matches → Gate 3 material selection
[Retrieval] matches/Gate 3 material selection/content_baseline → script_evidence_matrix → Gate 3 evidence closure
[Controlled Mutation] content_baseline/fallbacks/script_evidence_matrix → production_script_candidate
[Controlled Mutation] production_script_candidate/Gate 4-pre → approved_production_script
[Reconstruction] Gate 3 broad ranges → material/material_manifest (may run after Gate 3)
[Reconstruction] approved_production_script → voice/voice-span
[Reconstruction] approved-voice/voice-span/fragment_plan broad ranges → captions/reconstruction_timeline/exact-source-trims
[Reconstruction] Gate 4-post → proxy/boundary-review → render → Gate 5
```

典型变更策略：

| 变更 | 必须重算 | 应复用 |
|---|---|---|
| 使用 Gate 2 已批准 fallback 改一句文案 | 对应证据矩阵、生产脚本、Gate 4、配音、字幕、精确时间轴和渲染；若改变证据要求则重算相关匹配 | Gate 2 bundle、参考拆解、素材索引、无关片段 |
| 新增声明或改变口播意图/语义组/时长包络 | Gate 2 bundle、相关匹配、证据矩阵、生产脚本、Gate 4 和全部下游 | 参考拆解、素材索引、明确不受影响片段 |
| 删除三个片段 | 后续编号、相关匹配、证据矩阵、生产脚本、配音、字幕、渲染 | 其他源素材描述符和候选缓存 |
| 替换一个素材源 | 该素材索引、权威覆盖报告、命中片段、Gate 3 决定、证据矩阵、脚本候选/批准和下游 | 其他素材和参考拆解 |
| 调整一个源时段 | 对应生产片段、时间轴和渲染；若超出 Gate 3 宽范围或改变证据窗口，则连同 Gate 3、证据矩阵和脚本候选失效 | 不受影响的语义评分、其他片段、TTS |
| 修改音色/模型/语速 | Gate 4 生成前批准、相关语音跨度、字幕、精确时间轴和渲染；新时长越出宽范围才重做相关 Gate 3，越出时长包络才返回 Gate 2 | 素材索引、证据矩阵、Gate 3 宽范围和语义候选粗排（范围仍足够时） |

连续动作组和语义组是最小一致性单元，组内任一片段变化时整组重算。

### 7.7 审批状态单一权威（P1）

`pipeline_state.json` 是审批和续跑状态的唯一权威。其他产物只能引用批准记录，不单独声明互相矛盾的审批状态。

小型批准状态和批准快照应原子完成；大媒体复制/导出属于可重试的 Reconstruction materialization，不与用户决定绑在同一文件系统事务中：

1. 校验审核输入哈希；
2. 写入 Gate 决定；
3. 生成或提升小型批准快照（例如 Gate 2 bundle、Gate 3 宽范围或 Gate 4 批准脚本）；
4. 写入输出哈希；
5. 更新当前阶段；
6. 任一步失败则不留下半批准状态。

Gate 5 生成包也遵守同一事务边界。正式渲染授权必须同时验证 `gate_status.gate1/gate2` 与 `stages.reference_split/content_blueprint` 汇总状态，以及 Gate 3/4 的所有必需子状态和汇总状态；不能因下游状态为 `approved` 就忽略已 `stale` 的 Gate 1/2 阶段汇总。成片原子提升后必须将 `remix.mp4`、`final_validation_report.json`、`render_report.json`、`jianying_import_manifest.json` 的 SHA-256 写入 `pipeline_state.json.artifacts`，推进 `current_stage=final_review`、`gate5=awaiting_user`；回写失败则回滚本轮输出。

用户批准只对展示过的输入哈希有效。Gate 3 必须拆成 `gate3_material_selection` 和 `gate3_evidence_closure`，Gate 4 必须拆成 `gate4_pre_generation` 和 `gate4_post_generation`；每个汇总 Gate 只有所有必需 scope 和子状态都为 `approved` 时才显示 `approved`。上游变更后自动将受影响 scope、Gate 和下游状态标为 `stale`。

部分批准记录在 `decisions[]`：每条包含 `decision_id`、`gate_id`、`substate_id`、`scope_type`（`project|fragment|action_group|sentence|voice_span`）、`scope_ids`、`input_hashes`、`decision`、`status`、`actor`、`timestamp` 和备注。未变化 scope 可以复用；任一生产必需 scope 为 `awaiting_user|blocked|stale` 时，Gate 汇总不得为 `approved`，执行器也不得越过汇总 Gate 生成完整生产媒体。

最小状态字段：

```json
{
  "gate_status": {
    "gate1": "approved|awaiting_user|stale|blocked",
    "gate2": "approved|awaiting_user|stale|blocked",
    "gate3_material_selection": "approved|awaiting_user|stale|blocked",
    "gate3_evidence_closure": "approved|awaiting_user|stale|blocked",
    "gate3": "approved|awaiting_user|stale|blocked",
    "gate4_pre_generation": "approved|awaiting_user|stale|blocked",
    "gate4_post_generation": "approved|awaiting_user|stale|blocked",
    "gate4": "approved|awaiting_user|stale|blocked",
    "gate5": "approved|awaiting_user|stale|blocked"
  },
  "decisions": []
}
```

### 7.8 代理预览与边界审查（P2）

正式渲染前先生成：

- 540×960 或 720×1280、30fps 代理预览；
- 每个切换点前后约 0.5 秒的边界审查片；
- 动作组完整性片段；
- 重复画面和重复卖点摘要。

代理片重点发现：

- 画面切换卡顿、闪黑、色彩跳变；
- 相邻房间或构图明显重复；
- 静态图片抖动；
- 一张图片重复承载多个卖点；
- 动作切在错误阶段；
- 源叠字与新字幕冲突；
- 口播、字幕和画面语义错位。

代理审查不是新增 Gate，也不要求用户增加第六次批准。它属于 Gate 5 审核包生成前的内部质量检查：

- 只有 `gate4_post_generation=approved` 后才允许运行这一步；它只检查已听审通过的音频/时间轴对应画面，不替代 Gate 4 生成后听审；
- 自动检查通过且没有高风险项时，直接进入正式渲染；
- 自动检查发现重复、边界或时长风险时，停止正式渲染并返回最早受影响的既有 Gate；
- 用户可以查看代理片，但只有 Gate 5 对正式预览的决定构成最终审核授权。

自动通过条件至少包括：媒体可读、累计帧连续、无 gap/overlap、无黑帧边界、无未批准重复静态图、无长尾冻结、音画时长差不超过一帧。动作是否自然、产品是否正确和品牌调性仍由 Gate 5 人工判断。

代理检查通过后，对同一组未变化且已批准的输入至多执行一次正式 1080×1920、60fps 渲染。Gate 5 驳回导致上游内容、音频、素材或时间轴哈希变化时允许重新渲染；不能把“只做一次”解释为禁止必要返工。正式渲染使用稳定静帧、统一 BT.709 和单一最终编码链；只在边界审查确认必要时使用 2–3 帧短叠化。

### 7.9 TTS 与渲染次级优化（P2/P3）

在 P0/P1 完成后再优化。它们不能改变 Gate 顺序：

- 使用常驻 TTS 工作进程，避免每段重复启动运行时；
- 在服务限流允许时，以 2–3 个并发执行独立语义组；
- 同一 `span_group_id` 始终保持单次合成；
- PCM 编码和 `ffprobe` 校验可并行；
- 按输入哈希复用未变化的标准化视频片段；
- 独立片段准备可使用有界并发，最终时间轴和编码仍保持确定性。

不得为了并发破坏语义组语气、触发接口限流或生成顺序不确定的音频。

### 7.10 横向 Skill Engineering Track（最小化）

这不是第六个视频阶段，而是贯穿五个阶段的 Skill 质量护栏。只采用能直接证明“可触发、可续跑、可验证、可安全发布”的最小 Production 子集，不引入完整 Skill OS。

| 横向能力 | 最小落地 | 触发时机 | 发布/晋级证据 |
|---|---|---|---|
| 版本与元数据 | `manifest.json` 固定 `skill_version=2.0.0-alpha.1`；V2 产物固定 `contract_version=2.0.0-alpha.1`、`schema_version=1.0.0`、`artifact_type`、`schema_id`，canonical registry 为 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`；历史 V1 保留 `schema_version=1.0` | 每次运行和每次 Skill 更新 | 元数据可解析，版本与 registry 兼容；不原地改写 V1 |
| 触发评测 | 12–15 条 `should_trigger`、`should_not_trigger`、`near_neighbor` smoke cases | 发布候选和重大流程改动 | 误触发/漏触发为 0，或有明确人工例外 |
| 契约验证 | 统一 `validate` 命令：JSON schema、路径 containment、哈希、媒体、时段、Gate stale | 每个阶段完成、resume 前、发布前 | 核心产物验证通过；阻塞项可解释 |
| 安全检查 | 密钥扫描、工作目录路径边界、允许的 `ffmpeg/ffprobe` 子进程和指定 TTS 域名 | 运行前、失败后、发布前 | 无凭证泄露、无路径逃逸、网络/子进程边界符合声明 |
| 发布晋级 | `1.0.0` → `2.0.0-alpha.1`（仅一个 `manual-contract-only` pilot 采集 G-A）→ `2.0.0-rc.1`（G-B）→ `2.0.0`（G-C 后 owner 单独发布批准），保留上一版本回滚边界 | Skill 更新后 | 元数据、触发 smoke、契约、安全、冻结案例前向验证、效率不回退、owner 批准 |

执行模式固定为：

```text
full    从输入预检开始，遇 Gate 即停
resume  读取有效状态，只重算 stale/缺失阶段
stage   只执行指定阶段，不越过 Gate
audit   只生成评分、契约、安全和效率报告，不生成生产媒体
```

不纳入当前方案：Skill IR、跨平台编译器、registry/Skill Atlas、Review Studio、日报周报、大型测试矩阵、自动自我修改或自动晋级。未来只有在多个相邻 Skill、跨团队分发或积累足够真实运行后，才考虑扩展。

## 8. 可观测性

V2 实施后每个任务新增独立性能记录，建议文件名为（当前任务尚未生成）：

```text
stage_metrics.jsonl
```

每条记录包含：

- `event_id`、`run_id`、`framework_stage_id`、`execution_stage_id`、`fragment_id`；其中 `framework_stage_id` 只能是 `performance_proven_video`、`blueprint`、`controlled_mutation`、`retrieval`、`reconstruction` 之一，细粒度执行步骤写入 `execution_stage_id`。输入预检、素材索引预热等不阻塞的辅助事件必须标记 `blocking=false`，归入明确的 PPV/Retrieval 预处理或 `excluded_support_event`，不得另造第六个业务阶段；
- `dependency_event_ids`、`blocking` 和 `resource_lane`（`local_cpu|local_io|external_api|human_wait`），用于重建 DAG 而不是按行简单求和；
- 输入指纹和缓存命中状态；
- `compute_started_at`、`compute_finished_at`、`local_compute_seconds`、`external_api_seconds`；
- `awaiting_user_started_at`、`approved_at`、`human_wait_seconds`；
- FFmpeg/ffprobe 调用数；
- 解码帧数、候选数、精排数和导出数；
- `attempt_number`、`retry_count`、`rework_of_event_id`、`rework_reason`；TTS 调用数、重试数和服务耗时；
- 渲染帧数、编码耗时和复用片段数；
- 失败阶段、恢复阶段和阻塞原因。

状态页面和最终报告必须分别展示：机器计算、外部 API、用户等待和返工时间。不能把用户未回复的 20 分钟归因于 FFmpeg，也不能把代理手工组织产物的时间隐藏在“匹配耗时”中。

Retrieval 与 Reconstruction 的时间必须分别汇总：前者从素材覆盖、候选资格、排程和逐句证据校验中定位“找素材/证据慢”，后者从 Gate 4 生成前等待、脚本提升、TTS、裁点、代理和正式渲染中定位“做成片慢”。跨阶段共享的 lint/编译步骤只归其拥有者一次，其他阶段引用事件 ID，不得双计。新基线中 TTS 依赖 Retrieval 出口，关键路径按严格依赖图计算，不再使用 `max(TTS, matching)` 的并行假设。

性能口径定义：

- `local_compute_seconds`：本机 FFmpeg、哈希、评分、文件和报告处理时间；
- `external_api_seconds`：ASR、TTS 或其他外部服务从请求到完整响应的时间；
- `machine_api_critical_path_seconds`：考虑已声明并行关系后，本机计算与外部 API 的关键路径；
- `human_wait_seconds`：产物已就绪到用户决定之间的时间；
- `rework_seconds`：上游变化后重复执行的本机/API 时间。

本方案的 13 分钟/8 分钟目标使用 `machine_api_critical_path_seconds`，包含外部 TTS 正常响应时间，不包含用户等待。外部服务超时、限流和人工补素材单独报告，不隐藏在 SLA 内。

## 9. 效果验收指标

### 9.1 Performance-proven Video：参考事实

- 参考文件可读、哈希和流信息完整；
- 镜头帧边界从 0 到总帧数无 gap/overlap；
- 低分切点、单帧异常和密集闪切都有人工结论；
- 每镜头关键帧、音轨和 ASR/文案证据可追溯；
- Gate 1 前只生成审核包，不生成目标生产媒体。

### 9.2 Blueprint：内容蓝图

- `coverage_precheck.json` 明确标记为非权威，仅用于 Gate 2 前发现明显缺口；
- 叙事骨架、卖点、禁用声明、fallback 和时长包络齐全；
- Gate 2 只原子批准 `content_baseline.json + mutation_plan.json` 内容包，不把最终生产脚本或真实 TTS 视为已批准；
- 文案和语义组通过字速/时长 lint，风险和回退选项可解释。

### 9.3 Controlled Mutation：受控变更

- 每个保留/替换/删除/改写都有来源、理由和允许 fallback；
- 不新增 Gate 2 未批准声明；
- 生产脚本候选只能由已通过证据矩阵和已批准 fallback 编译，不能静默删句或弱化；
- Gate 2 变更会使受影响 Gate 3 以后状态 stale。

### 9.4 Retrieval：素材检索与证据

- Gate 2 之前生成 `coverage_precheck.json`，仅作为 Blueprint 的缺口预判；Gate 2 通过后、Gate 3 前使用内容基线重新计算权威 `coverage_report.json`（V1 当前流程暂无这两个自动产物）；
- `missing_material` 不进入生产状态；
- 每句最终口播必须在 `script_evidence_matrix.json` 中有 Gate 3 批准素材、证据帧/时间窗和 `pass`；否则不能提升为 `approved_production_script`；
- 卖点必须有独立 `evidence_score` 和证据来源；
- 同一感知哈希静态图默认只承载一个卖点；
- 三个连续镜头内尽量避免同一来源，无法满足时必须在审核包中说明；
- 相邻同房间且构图高度相似时禁止自动连用；
- 动作候选使用微视频审核，不以单张中点帧判断动作完整性。

### 9.5 Reconstruction：配音、时间轴与渲染

- Gate 2 阻止明显不可行的字速；
- 所有最终视觉跨度来自实测音频或批准的无口播语义组；
- 短镜头不机械拆成短促独立 TTS；
- 不删字、不变速、不补外部静音来强压参考时长；
- 画面默认 1.00x，不使用长尾冻结补素材。
- `voice_preflight.json` 必须在 Gate 4 生成前审核包之前通过；预估超出视频画面预算时不得调用 TTS。
- `fragment_plan.json` 的 Gate 3 宽范围保持不可变，精确裁点只写 `reconstruction_timeline.json`；
- 正式渲染前必须通过代理边界审查；
- 静态图片无逐帧浮点缩放抖动；
- 片段边界无闪黑、明显时基停顿或无依据转场；
- 视频与音频时长差不超过一帧；
- 最终只有一条视频流和一条批准音轨；
- SRT 旁路交付，不静默烧录或嵌入。

## 10. 性能目标

以下目标以当前案例规模为参考：约 12–16 个片段、7 个素材文件、3 个视频约 45 秒、素材总体约 436MB。

| 执行项 | 归属业务阶段 | 冷启动目标 | 缓存命中目标 |
|---|---|---:|---:|
| 参考片拆解审核包 | Performance-proven Video | ≤ 2 分钟 | ≤ 20 秒 |
| 素材索引 | Retrieval（只读预计算） | ≤ 90 秒 | ≤ 5 秒 |
| 结构和时长 lint（Blueprint） | Blueprint | ≤ 20 秒 | ≤ 3 秒 |
| 变更/fallback lint（Controlled Mutation） | Controlled Mutation | ≤ 10 秒 | ≤ 2 秒 |
| 素材匹配提案 | Retrieval | ≤ 30 秒 | ≤ 10 秒 |
| Gate 3 批准后宽范围导出/复制 | Reconstruction | ≤ 30 秒 | ≤ 10 秒 |
| 逐句证据矩阵（Retrieval） | Retrieval | ≤ 10 秒 | ≤ 3 秒 |
| 生产脚本候选编译（Controlled Mutation） | Controlled Mutation | ≤ 10 秒 | ≤ 2 秒 |
| Gate 3 后配音时长预检 | Reconstruction | ≤ 5 秒 | ≤ 3 秒 |
| Gate 4 生成前确认包 | Controlled Mutation / Reconstruction 交接 | 用户确认前 ≤ 10 秒生成 | ≤ 3 秒 |
| TTS 生成和媒体验证 | Reconstruction（Gate 4 生成前批准后） | ≤ 45 秒 | ≤ 45 秒；不复用未批准音频 |
| 字幕、累计时间轴和 Gate 3 范围内精确裁点 | Reconstruction | ≤ 30 秒 | ≤ 10 秒 |
| 代理预览和边界片 | Reconstruction | ≤ 2 分钟 | ≤ 30 秒 |
| 正式渲染和验证 | Reconstruction | ≤ 5 分钟 | ≤ 5 分钟；完整输出哈希命中时无需重渲染 |
| 端到端机器/API 关键路径 | 五阶段整体 | ≤ 13 分钟 | ≤ 8 分钟 |

关键路径按新基线的严格依赖图计算：素材技术索引与参考片拆解可以并行；Gate 2 后先经过素材匹配和 Gate 3 两个子状态；Gate 3 汇总通过后，`materialize-approved-broad` 与“证据矩阵 + 脚本编译”两条支路可以并行，之后依次进入 `voice-preflight`、Gate 4 生成前确认、TTS、实测预算复核、时间轴、Gate 4 生成后听审、代理审查和正式渲染。不得把两条支路相加，也不得再用 `max(TTS, matching)` 计算。人工 Gate 1–5 的确认时间全部只记入 `human_wait_seconds`，不进入机器/API SLA。

缓存命中预算按依赖图逐项计算：`max(reference_split=20s, asset_index=5s) + blueprint_lint=3s + mutation_lint=2s + match_assets=10s + max(materialize_broad=10s, evidence_matrix=3s + script_compile=2s) + voice_preflight=3s + gate4_pre_package=3s + generate_voice=45s + build_timeline=10s + proxy_boundary=30s + render_final=300s = 436s`，约 7.3 分钟，向上预留为 8 分钟。Gate 3、Gate 4 生成前、Gate 4 生成后和 Gate 5 的人工等待均明确排除；完整输出 bundle 哈希命中时无需支付最后 300 秒正式渲染。冷启动和热缓存目标都必须按同一依赖图实测，不能用估算数字替代验收。

目标是优化同规模任务的可重复执行，不承诺对超长视频、损坏媒体、外部 API 限流或用户等待使用相同 SLA。13/8 分钟只统计机器/API critical path，不包含 Gate 1–4/5 的运营等待；运营墙钟另行显示 `human_wait_seconds` 和 `rework_seconds`。

## 11. 实施阶段

本节把原「Phase 0 → Phase 6 单线捆绑」改为三条串联交付线。Track A 的 Gate 顺序纠正是契约级改造，历史返工为其提供了高可信假设但还不是配对实测；Track B 是执行器与共享索引的重工程；Track C 是完整评分和看板。五个业务阶段定义每次视频如何运行，三条 Track 定义系统能力如何建设，两者不能混为一组阶段编号。

### 11.0 交付拓扑：三条 Track 与晋级门槛

```text
Track A  五阶段与 Gate 契约迁移（文档/schema/模板；不写生产执行器，允许静态检查脚本）
  │  工作包：WP-A（五阶段 ownership、Gate 3/4 双子状态、V1/V2 迁移、人工计时表）
  │  以 2.0.0-alpha.1 运行一个 manual-contract-only pilot，不启用 V2 自动执行器、不归档发布
  ▼  门槛 G-A：该 pilot 不再因真实音频时长重做 Gate 3 精确裁点，且无新增 Gate 越权
  ▼  契约顺序有效性证实后才投入 Track B
Track B  确定性执行器 + 共享索引 + 缓存 + 增量（重工程）
  │  工作包：WP-B0 执行器骨架、WP-B1..B5（原 Phase 1–5 的脚本实现）
  ▼  门槛 G-B：冻结案例配对运行达到最低晋级线；保留 2.0.0-rc.1
  ▼  流程提速证实后才投入 Track C
Track C  评分卡 + 成熟度体系（观测仪表，瘦身版）
  │  工作包：WP-C（原 Phase 0 的评分卡计算器 + 分阶段看板）
  ▼  门槛 G-C：完整评分能自动生成且与实测数据一致
  │  G-C 通过后由 owner 单独作 stable 发布批准
  ▼  发布 2.0.0
```

三条 Track 的边界与理由：

| Track | 本质 | 实现成本 | 证据状态 | 启动前置 |
|---|---|---|---|---|
| A：五阶段与 Gate 契约迁移 | 文档/schema/模板 | 低（改 `AGENTS.md`/Skill/references/schema/template） | 静态迁移与 G-A clean harness 已通过 | 已完成 |
| B：执行器与索引 | 重工程 | 高（新增 `scripts/`、缓存目录、锁） | Native Runner 已实现；真实 cold/hot 为 `measured_pending_review` | G-B/监督运营待完成 |
| C：评分体系 | 观测仪表 | 中（计算器 + 看板） | 最小 harness 已有；完整评分仍锁定 | 门槛 G-B 通过 |

**硬规则：Track 之间只能顺序晋级，不得并行抢跑。** 未通过 G-A 不写或启动 V2 生产执行器；未通过 G-B 不建完整评分计算器/看板。任一门槛未达标时，停在当前 Track 复盘。Gate 1–5 的人工审核纪律在三条 Track 全程不变。

### 11.1 Track A：五阶段与 Gate 契约迁移（第一可交付）

目标：不写生产执行器，允许使用只读/静态检查脚本；先把五阶段 ownership、Gate 子状态、宽/精确计划、失效传播和 V1/V2 边界改成唯一契约，再用一个 `manual-contract-only` 真实 pilot 验证“真实配音不再改写 Gate 3 批准”。

工作包 WP-A 产出范围：

- 在 `AGENTS.md`、`.agents/skills/remix-reference-video/SKILL.md`、五份 `references/*.md`、`docs/reference-video-remix-sop.md`、Brief 模板、`.agents/skills/remix-reference-video/agents/openai.yaml` 和 V2 schema 中同步迁移本文件第 6.2/6.3 节；Track A 静态迁移完成后只允许一个 owner 指定的 `manual-contract-only` V2 pilot，G-A 通过前不得启用普通 V2 生产任务或改写在制 V1 数据；
- `pipeline_state.json` 增加 Gate 3 与 Gate 4 双子状态和 scoped `decisions[]`（人工按模板维护，暂不要求事务执行器）；
- 定义 `fragment_plan.json`（Gate 3 不可变宽范围）、`material_manifest.json` 和 `reconstruction_timeline.json` 三份独立契约；
- 明确 V1/V2 契约迁移边界：旧任务按创建时契约续跑，不追溯授权；
- 逐句证据、生产脚本编译和 G-A 指标以人工检查/计时模板落地；
- 新增 Skill `manifest.json`，固定 `skill_version=2.0.0-alpha.1`、`contract_version=2.0.0-alpha.1`、V2 artifact `schema_version=1.0.0`、owner、schema 兼容范围和 `1.0.0` 回滚边界；Track A 只提供静态检查入口，不提供 V2 生产执行器；canonical registry 固定为 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`；
- 在自动护栏上线前，Track A 每次 Skill 更新人工执行最小版本标记、触发 smoke、契约一致性检查、密钥/路径安全检查，并保存结果。
- 在每个已完成业务阶段输出 `stage_assessments/overview.md` 和五份固定的 `<stage>.md` 人工评估快照；至少记录阶段标识、当前输入哈希、阶段/审批状态、已证实结果、未验证项、风险、效率证据和下一阶段准入。数字评分与效率实测证据不足时必须分别写 `stage_output_quality_score: not_scored`、`measurement_status: not_scored`、`efficiency_measurement_status: incomplete`；只有已有完整数字但尚未完成当前 Gate 审核时才将独立 `approval_status` 写为 `provisional`，不得把它当作 `not_scored` 的替代值。不能复用历史案例分数或目标分；跨 Gate 阶段只能保存明确标注的进行中快照。

**WP-A2：G-A Evidence Harness（G-A 前允许的窄工具）**

为避免“必须先有 Track B 审批入口才能证明 G-A、但 Track B 又必须等 G-A”的循环，Track A 允许一个不执行媒体生产、不启用缓存、只服务 `manual-contract-only` pilot 的证据工具：

- `ga-prepare-review`：对当前 Gate 已存在的审核产物计算 SHA-256，使用可信本机时间生成不可变 review package；
- `ga-record-decision`：只接受 schema 校验的结构化决定文件，重算 review package 与输入哈希后，原子写入 scoped decision；调用方不能提交审批时间戳；
- `ga-audit`：只读检查 Gate 顺序、Gate 3/4 子状态、审核包先于批准、当前输入哈希、审批不复用、Gate 3 不直接批准结构删并和最终 Gate 状态。

WP-A2 只能操作 owner 指定的单一 `manual-contract-only` pilot；不得运行五阶段命令、生成 TTS/媒体、创建生产缓存、归档、迁移 V1、修改 manifest 或自动判定业务批准。它是 G-A 前向证据护栏，不属于 Track B 执行器；G-A 通过后由 B0 的通用 Approval Service 替代，不形成第二套生产状态机。

门槛 G-A 验收（只在一个 `manual-contract-only` V2 pilot 上采集，不依赖 V2 执行器）：

- pilot 只能用于前向验证：可以按人工契约走到真实 TTS、实测时长、精确裁点和 Gate 4 生成后听审，以便验证顺序；不得标记为普通 V2 生产发布，不得迁移到 `final/`，不得启动 Track B 执行器，也不得把其 Gate 决定复用于其他任务；

- 用统一人工计时表记录 `operator_touch_seconds`、`rework_seconds`、`gate_return_count`、`配音后是否重做 Gate 3`、`缺素材发现阶段`，明确标记 `measurement_method=manual_forward_log`，不伪装成 `stage_metrics.jsonl`；
- 与 `tablemat-01` 回溯基线（至少 2 次返工：Gate 3→Gate 2、Gate 4→Gate 3→Gate 4）对比；
- 唯一最低通过线：Track A 跨文件契约迁移、版本/触发/契约/安全静态检查均通过；pilot 在同类结构下**不再因真实音频时长触发 Gate 3 精确时段重做**，且 Gate 3 未直接批准删段、Gate 3/4 汇总状态没有跳过子状态。`rework_seconds`、`gate_return_count` 和 `net_time_delta_seconds` 作为前向趋势证据；本门槛只验证 Gate 顺序，不把历史约 65 分钟的结构修改、全量重匹配和人工整理全部归因于 Track A，也不把单案例绝对提速冒充已实测。若出现新增返工或 Gate 越权，普通 V2 生产和 Track B 都继续锁定。

### 11.2 Track B：确定性执行器与共享索引（重工程，G-A 通过后启动）

目标：在 Gate 顺序有效性已证实的前提下，把重复命令、全量重算和逐帧启动固化为可缓存、可续跑的执行器。以下工作包沿用原 Phase 编号语义，仅重新归属交付顺序。

**WP-B0：执行器骨架与状态权威（原 Phase 0 的基建子集）**

产出范围：

- 参数化阶段执行器和 `full/resume/stage/audit` 模式；
- 输入指纹、阶段缓存键、`stage_metrics.jsonl` 和关键路径计时；
- `pipeline_state.json` 单一审批权威、结构化决定解析与事务性更新（把 Track A 手动维护的双子状态/scoped decisions 升级为原子写入）；
- 共享素材索引的 schema、锁、staging 和原子提升规则；
- 最小 `manifest.json`、触发 smoke 夹具、统一 `validate` 入口；
- 密钥/路径/子进程/网络边界检查；
- V1/V2 schema 兼容与迁移边界的机器校验；
- Phase 6 使用的最小 `phase6_score_snapshot.json` 生成器接口：固定消费第 0.3/0.5 节 rubric 与实测指标；接口可以随 B0 交付，但只有 B1–B5 完成后在 Phase 6/G-B 配对运行中才能调用并标记验证结果，不实现完整看板。

WP-B0 验收：相同输入第二次运行可报告 `cache_hit`，上游变更只标记受影响下游 `stale`，不会生成半批准生产产物。

> 注：原 Phase 0 中的「评分卡 schema/计算器」已移出，归入 Track C，不在 WP-B0 交付。

**WP-B1：Performance-proven Video（原 Phase 1，P0）**

目标：把参考片拆解从临时命令固化为可审核、可重跑的事实层。

产出范围：参考流探测、镜头候选、异常规则、关键帧/音轨/ASR、Gate 1 审核包、参考指纹和前向评分。

**WP-B2：Blueprint（原 Phase 2，P0）**

目标：先围绕证据规划可实现的目标结构，减少 Gate 3 才发现缺素材。

产出范围：叙事骨架、片段职责、卖点证明链、禁用声明、覆盖缺口预判、字速/时长包络和唯一 `content_baseline.json`。

> 注：Gate 2 只批内容基线的**契约**已在 Track A/WP-A 落地；WP-B2 只负责把该契约自动化为可重跑脚本，不重新定义 Gate 职责。

**WP-B3：Controlled Mutation（原 Phase 3，P0）**

目标：只执行明确批准的变化，并把最终生产脚本的生成责任放在证据审计之后。

产出范围：保留/替换/删除/改写清单、`mutation_plan.json`、已批准 fallback、失效传播，以及 `build-production-script` 编译器。运行时必须在 WP-B4 产出且 Gate 3 汇总通过后，消费 `script_evidence_matrix.json` 生成 `production_script_candidate.json`；Gate 4 生成前由本阶段将候选提升为 `approved_production_script.json`。`content_baseline.json` 只由 Blueprint 产出，本工作包不得重复拥有，也不生成真实 TTS。

**WP-B4：Retrieval（原 Phase 4，P0/P1）**

目标：以共享索引和全局约束快速找到能证明卖点的素材，并在 Gate 3 后完成逐句证据闭环。

产出范围：批量抽帧、资格门禁、视觉评分、去重/连续性、权威 `coverage_report.json`、全局排程、候选微视频、Gate 3 选材确认、不可变宽范围 `fragment_plan.json`、Gate 3 证据闭环、`script_evidence_matrix.json` 自动生成和增量重算。

> 注：`script_evidence_matrix` 的**契约**在 Track A 已定义并以人工清单形式使用；WP-B4 把它从人工清单升级为自动产物。

**WP-B5：Reconstruction（原 Phase 5，P1/P2）**

目标：Gate 4 生成前确认后，才生成真实配音，并以实测音频稳定重建字幕、画面和成片；Gate 4 生成后先听审音频与时间轴，批准后才运行代理边界审查和正式渲染。

产出范围：Gate 3 汇总通过后将批准宽范围复制/导出到 `material/` 并写 `material_manifest.json`；先以 Gate 3 视频画面预算和生产脚本候选生成 `voice_preflight.json`，通过后才创建 Gate 4 生成前审核包；只消费 Controlled Mutation 已提升的 `approved_production_script.json` 执行 TTS，实测音频再次复核预算后生成字幕与 `reconstruction_timeline.json`，并在 Gate 3 范围内确定精确裁点；先完成 Gate 4 生成后音频/时间轴听审，再做代理/边界审查、正式渲染和 Gate 5 交付包。

### 11.3 Track C：评分卡与成熟度体系（观测仪表，G-B 通过后启动，瘦身版）

目标：在 Phase 6 配对运行验证流程提速和质量不回退之后，才把评分从人工回溯升级为自动生成。**Track C 是观测仪表，不是瓶颈**；在被度量的流程尚未完成验证前建它，只会先花大力气度量一个还没被证明变快的流程。

工作包 WP-C 产出范围（从原 Phase 0 移出）：

- 评分卡 schema/计算器（`quality_scorecard.json`）；
- 五阶段 `framework_stage_id` 映射与 `execution_stage_id` 双层归属；
- 分阶段一线业务提示模板；Gate 决定 parser 与结构化回写已属于 WP-B0，Track C 只读取决定用于展示；
- 分阶段看板（质量分 + 成熟度分 + 效率三口径分离展示）。

瘦身原则（避免评分复杂度超过它所治理的流程）：

- 计算器只消费**已实测**的效率与返工数据，不接受手工回溯补分作为 `measured`；
- 第 0.3/0.5 节的子项 rubric 是唯一计分来源，看板维度只做同口径聚合，不引入第二套可任选规则；
- Track B/Phase 6 由最小快照生成器按冻结 rubric 计算单次运行的 `measurement_status=measured`、`approval_status=provisional|approved` 五阶段验证分，但不建设完整评分产品或看板；V1/V2 提速差异只有在配对数据齐全后才能标为 `measured`，否则仍为 `modeled`。Track C 只把这套已冻结规则产品化。没有当前运行证据的项目仍标为 `modeled|retrospective_baseline`，不得冒充实测。

WP-C 验收（门槛 G-C）：评分卡能由机器自动生成、与已实测 `stage_metrics.jsonl` 数据一致、五阶段 `framework_stage_id` 恰好五项且 `retrieval`/`reconstruction` 独立；不再依赖人工抄录回溯分。

### 11.4 Phase 6：冻结案例前向验证与发布晋级（门槛 G-B，非业务阶段）

实施状态（2026-08-16）：隔离冷/热缓存、受控视觉变更、审批隔离、跨运行缓存拒绝、V1 可比性校验和最小 `phase6_score_snapshot.json` 生成器已在 Track B 隔离 fixture 中实现并通过测试。Native Runner 已通过正式 CLI 的显式 runtime config 接入；`gb-pair` 已用真实冻结输入完成 cold/hot 的 ffprobe/ffmpeg/TTS 全链路，双方 Gate 1–5 均由独立审核包批准并通过最终技术校验。cold Gate 5 后只复制声明的 SQLite cache，hot 以独立 `run_id` 启动并保留自己的增量索引；配对记录当前为 `measured_pending_review`，机器关键路径已测得 cold 32.178 秒、hot 36.183 秒。V1 可比性、人工运营计时和 owner G-B 阈值仍未复核，因此 G-B 尚未通过，普通 V2 生产和共享缓存继续锁定。

Phase 6 是 Track B 的出口门槛 G-B，同时为 Track C 的启动前置。目标：证明五阶段质量没有因提速回退、关键路径达到 13/8 分钟硬线，并为 `2.0.0-rc.1` 提供可回滚证据；正式 `2.0.0` 必须等待 G-C 及其后的 owner 发布批准。

历史 V1 基线案例已经完成 TTS、正式技术渲染，并在其 V1 `pipeline_state.json` 中将 Gate 1–4 标为已通过、Gate 5 标为 `awaiting_user`。早期 V2 pilot 已完成 Gate 1–5，但曾留下 Gate 3 越权失败记录；后续独立 clean harness 已通过 G-A，真实 Native Runner cold/hot 也已各自通过 Gate 1–5。历史 V1 的测量状态仍为 `retrospective_baseline`；当前 V2 配对的技术与效率状态为 `measured_pending_review`，质量仍为 `not_scored`。这些证据证明端到端后端可以运行，但不能据此宣称 G-B、普通 V2 发布质量或一线无监督使用已经通过。

实施验证采用以下最小配对设计：

1. 冻结一组完全相同的参考片、Brief、素材库快照、TTS 设置和审核决定，V1 与 V2 都使用这一组输入。
2. 冷启动比较：为 V1 与 V2 分配隔离且初始为空的缓存根目录，各运行一次完整流程；执行顺序不得让后一流程读取前一流程的缓存。
3. 热缓存比较：从同一份预建缓存快照分别克隆两个隔离缓存根目录，对同一个片段做同样的受控视觉变更，再比较增量续跑；不重复无关 TTS 和正式渲染。
4. 历史 V1 案例已有技术成片；当前 V2 pilot 只有在走完 Gate 4/5 并使用满足配对条件的冻结输入复跑时，才能进入完整比较，现有两组记录仍分别用于回溯参考和 G-A 顺序前向证据。
5. 只做这一组真实案例的冷启动全链路和热缓存增量配对，不扩展成大规模性能测试集。
6. 使用 Track B 最小快照生成器按冻结 rubric 计算五阶段 `stage_output_quality_score`、`stage_workflow_maturity_score`、整体 `video_quality_score` 和关键路径效率；这是 G-B 的固定验收快照，不依赖 Track C 看板；没有配对实测的提升仍标为 `modeled`。
7. G-B 唯一最低晋级线：核心契约、安全、触发 smoke 和冻结案例硬门禁全部通过；Gate 5 审核包可用且无硬阻塞；冷启动机器/API 关键路径 `≤13 分钟`、热缓存关键路径 `≤8 分钟`；五阶段质量分均不低于各自 V2 最低验收线，视频总分最低线为 `≥88`（`91` 为目标值）；受控增量变更的 `rework_seconds` 与 `gate_return_count` 不得高于配对 V1。若配对 V1 缺少可比机器数据，必须先补采集，不能把“无法比较”当作通过。
8. G-B 通过只允许 `2.0.0-alpha.1` 晋级为 `2.0.0-rc.1`，不发布 stable；保留 `1.0.0` 作为生产回滚边界。G-C 只判断评分卡是否自动生成且与实测数据一致；G-C 通过后再由 owner 单独作 stable 发布批准，随后才允许晋级 `2.0.0`。

配对比较：

- 总机器时间和各阶段时间；
- 缓存命中率和 FFmpeg 进程数；
- Gate 返回次数；
- 配音后是否重新做 Gate 3；
- 缺素材发现阶段；
- 重复画面、图片抖动和边界卡顿数量；
- 最终未决风险。

## 12. 验证策略

遵循“验证关键契约，不堆测试数量”：

1. 每个机器产物做 JSON/schema、路径、哈希和媒体可读性检查。
2. 为缓存失效、阶段续跑、字速 lint、匹配资格门禁和累计帧边界各保留少量核心测试。
3. 使用一个小型固定素材夹具做快速 smoke test。
4. 使用一个真实案例做端到端前向验证。
5. 最终效果依赖候选微视频、边界审查片、配音听审和 Gate 5 人工审核。

不要求为每个 FFmpeg 参数、格式化辅助函数或报告字段排列编写独立测试；不以代码覆盖率数字作为上线门槛。

## 13. 风险与控制

| 风险 | 控制措施 |
|---|---|
| Gate 顺序调整被误解为减少审核 | 明确 Gate 2 只批准内容基线，Gate 4 生成前确认生产脚本/设置，生成后仍批准实际音频和时间轴 |
| 素材索引模型或规则变化导致脏缓存 | 缓存键包含 schema、采样器和模型/规则版本 |
| 共享缓存成为错误权威 | 缓存可删除重建；生产仍以任务目录哈希和 Gate 批准为准 |
| TTS 依赖顺序被误解或接口限流 | `generate-voice` 只能消费 Gate 4 生成前批准的生产脚本；连接复用和有界并发仅作为 P2/P3，失败即停，不生成半成品 |
| 代理片效果与正式片不一致 | 使用相同裁切、时间轴和转场决策，仅降低分辨率和帧率 |
| 增量复用遗漏上游变更 | 每阶段使用显式输入指纹，不依赖文件时间戳判断 |
| 自动评分继续过度自信 | 分离证据、视觉、连续性和技术分，保留人工候选审核 |

## 14. 审核决策

本节按第 11 节的三 Track 拓扑拆分确认项。**确认是分批的，不是一次性批准整条单线**：Track A 静态迁移与唯一 pilot 授权已经确认；接下来用 G-A 结果决定是否投入 Track B，再用 G-B 结果决定是否投入 Track C。

### 14.1 已确认项（Track A 静态迁移与 pilot 授权）

1. 批准 Gate 2 内容基线 → Gate 3 素材（宽范围） → 逐句证据 → 最终生产脚本 → Gate 4 生成前 → TTS/实测时长/时间轴 → Gate 4 生成后 → 渲染 → Gate 5 这一唯一生产顺序；
2. 批准 Track A 以契约/schema/文档形式落地：同步修订 `AGENTS.md`、Skill、五份 references、SOP、Brief 模板、`agents/openai.yaml` 与 V2 契约示例；`pipeline_state.json` 增加 Gate 3/4 双子状态和 scoped decisions（人工维护），`script_evidence_matrix` 先定义契约、以人工清单使用；
3. 确认 Track A 不写生产执行器，允许静态检查脚本；不建缓存目录、不改动现有生产数据。
4. 授权 owner 指定唯一一个 `manual-contract-only` V2 pilot 采集 G-A；该授权不等于普通 V2 生产发布，也不解锁 Track B/C。

### 14.2 门槛后确认项（达标才逐条解锁）

5. **G-A 通过后**才确认启动 Track B，并同时确认：接受共享缓存目录 `work/_cache/remix-reference-video/` 及其可删除、可重建的定位；选择代理预览规格（540×960/30fps 默认效率优先，或 720×1280/30fps）。Track A 不创建或预热该缓存目录；
6. 接受第 11.4 节的唯一 G-B 判定式，其中冷启动 `≤13 分钟`、热缓存 `≤8 分钟` 和五阶段/总分最低线 `≥88` 是 Track B 出口硬线，整体总分 `91` 为目标值，不是当前实测承诺；
7. **G-B 通过后**才确认启动 Track C（完整评分卡与看板，瘦身版）。G-B 验收由 Track B 的最小 `phase6_score_snapshot.json` 生成器按冻结 rubric 计算五阶段、总分和效率快照；它不是完整评分卡产品，也不解锁 Track C 看板。

### 14.3 全程约束

8. 三条 Track 只能顺序晋级，不得并行抢跑；任一门槛（G-A/G-B/G-C）未达标时停在当前 Track 复盘；
9. 指定 Skill owner；Track A 使用 `2.0.0-alpha.1` 运行唯一一个 `manual-contract-only` pilot，G-B 通过后进入 `2.0.0-rc.1`，G-C 通过且 owner 人工批准后才发布 `2.0.0`；始终保留 `1.0.0` 为生产回滚边界；
10. Track A 静态护栏通过后只授权上述 pilot；G-A 通过后才允许普通 V2 生产任务。G-A 前不得启动生产执行器、不得归档 pilot、不得修改在制 V1 生产数据；Track A 的修改不追溯授权任何在制 V1 任务。
