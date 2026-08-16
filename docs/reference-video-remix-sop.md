# 参考视频复刻运营 SOP

版本：2026-08-16
适用对象：一线运营、内容审核、剪辑协作人员  
适用范围：以一条完整参考视频为结构依据，从 `assets/` 选择替换素材，生成新配音和最终预览，并在确认后归档成片。V1/V2 默认都生成 `jianying_import_manifest.json`，但没有专用适配器和明确授权时不生成新版加密剪映草稿。

当前状态：Track A 静态护栏和 G-A clean harness 已通过；Track B Native Runner、Approval Service、真实媒体 adapter 和正式 CLI 已合并到主干。真实 cold/hot 配对已完成 Gate 1–5，当前记录为 `measured_pending_review`，V2 基线报告见 `docs/remix-production-v2-baseline-report-2026-08-16.md`。在 G-B 和监督运营试用通过前，普通 V2 production、共享生产缓存和一线无监督发布仍保持关闭；新 V2 case 使用隔离 `gb-pair`。当前 `skill_version=2.0.0-alpha.1`、`contract_version=2.0.0-alpha.1`；V2 新建机器产物使用 `schema_version=1.0.0` 并声明 `artifact_type`、`schema_id`，canonical registry 为 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`。历史 V1 产物继续保留 `schema_version=1.0`，不得就地改写。静态检查器不覆盖完整生产质量；真实媒体验证以冻结配对和本地测试为准。

当前 pilot 的 sentence08 已恢复为 Gate 2 批准原句“铺好以后，日常使用都好打理。”，修复后的 Gate 3 证据闭环已获用户通过。编译器和 Gate 4 适配器必须继续校验每句候选等于 Gate 2 基线或命中已批准 fallback，禁止静默改句。

当前运营动作：审核 `gate4_pre_generation_review.md` 中的 9 句文案、豆包 `DOUBAO_AUDIO` / V3 协议、音色和语速。明确回复“Gate 4 生成前通过，按当前文案和音色生成”后，才允许真实 TTS；“开始实施”或 Gate 3 批准不能替代该授权。`fragment_plan.json` 的宽范围和历史元数据不原地改写，物化状态以 `material_manifest.json` 为准。

## 1. 交付目标

本流程的目标不是逐帧照搬参考片，而是保留其叙事顺序、镜头节奏和信息结构，换成经过审核的素材、文案和配音，最终交付：

- 一条可审核或可发布的 9:16 视频；
- 一份与视频一致的独立 SRT；
- 可追溯的素材匹配、配音和渲染报告；
- 一份 `jianying_import_manifest.json` 作为剪映人工/后续工具导入清单；V1 不把该清单表述为剪映草稿。

五阶段业务主线：

```text
输入预检 → Performance-proven Video/Gate 1 → Blueprint + Controlled Mutation/Gate 2 → Retrieval/Gate 3 → Reconstruction/Gate 4 → Gate 5 最终预览 → 确认归档
```

运行边界：已经开始的 V1 任务按创建时契约续跑，不自动取得 V2 授权。G-A 通过前只允许一个 `manual-contract-only` V2 pilot 逐 Gate 采集证据；pilot 不是生产发布，不进入 `final/`，不启动 Track B 执行器，也不得把其 Gate 决定复用于其他任务。其他新任务继续使用稳定 V1 或等待迁移决定；G-A 通过后，普通新任务才默认使用 V2 生产契约。迁移必须记录旧/新阶段映射、输入哈希、失效 Gate 和重新确认项。

### 一线运营最短操作路径

当前新任务分两类：已经开始的 V1 任务按创建时契约续跑；新 V2 case 先冻结输入，再通过隔离 `gb-pair` 运行。普通 `production-run` 在 G-B/监督运营通过前仍不可用。

1. 准备完整参考视频、自有素材目录、产品信息、平台、受众、已批准卖点和禁用声明。
2. 在新的 Codex 窗口打开项目根目录，向 Codex 发送：

   ```text
   使用 $remix-reference-video 创建一个新的参考视频复刻任务。
   参考视频：<绝对路径>
   自有素材目录：<绝对路径>
   产品和目标：<产品、平台、受众、已批准卖点、禁用声明>
   任务名称：<英文短名称>
   先完成 Stage 0，生成 Brief 草案、素材画像和冻结输入草案；缺少信息就暂停提问。
   当前普通 V2 production 仍受锁保护，准备完成后使用隔离 gb-pair。
   从 Gate 1 开始逐 Gate 停止，等待我明确审批，不复用任何历史或其他运行的审批。
   ```

3. Stage 0 完成后确认 `frozen-root/` 中有唯一 `reference-*.mp4`、`project_brief.json`、`asset_profiles.json` 和 `g_b_frozen_input_snapshot.json`；CLI 不会替运营编造产品事实或声明。
4. Gate 1 只审镜头切分；Gate 2 同时审内容基线和变更包；Gate 3 先审素材宽范围，再审逐句画面证据；Gate 4 先审生成前脚本/声音设置，生成后再听审实际音频和时间轴；Gate 5 审最终预览。
5. 任一 Gate 出现缺素材、未批准卖点、错误发音或媒体问题时，选择补充、替换或返工，不要为了“先出片”直接通过。
6. Gate 5 通过后，隔离配对仍保留在 `work/`，运行 `production-audit` 并等待 G-B/归档授权；不能直接迁移到 `final/`。

历史 V1 任务继续使用原 V1 产物和审批；如需迁移，先生成旧/新阶段映射、输入哈希、失效 Gate 和重新确认清单。

## 2. 不可违反的工作原则

1. 完整参考视频决定整体顺序、参考节奏和原始音频；`video_clips/` 决定视觉拆解顺序。
2. `assets/` 永远只读。选中素材只能复制或导出到 `material/fragmentNN/`，不得移动、覆盖或破坏原文件。
3. 文件名只能作为线索，选材必须看实际画面。
4. 缺素材必须明确显示为“缺素材”，不能用无关画面硬凑。
5. 使用新配音时，以解码后的真实配音时长决定画面和字幕时间轴，不能只看脚本字数或参考片时长。
6. 视频默认保持 `1.00x`。素材不足时优先扩展同一源窗口；仍不足则退回 Gate 3 补素材。只允许因累计端点舍入产生的最多 2 帧边界补齐，禁止长尾帧冻结和变速硬拉。
7. 审核预览和生产成片是两种状态：审核预览可以显式占位；生产成片不能有占位、未处理的阻塞项或伪造的通过状态。
8. 默认字幕交付为独立 SRT，不烧录、不嵌入字幕流。新字幕与源画面自带文字是两件事；关闭字幕烧录不会自动去掉素材里的品牌、账号名或宣传文字。
9. 任何上游机器产物变化后，下游报告都必须重新生成；不能沿用旧哈希、旧统计或旧验收结论。
10. 新任务的全部过程产物必须位于同一个 `work/YYYY-MM-DD[-slug]/`，不得另建 `work/replace_*` 作为并行权威目录。
11. V1/V2 默认只生成 `jianying_import_manifest.json`；没有专用适配器和用户明确要求时，不创建或修改新版加密剪映草稿。
12. 只有用户或项目负责人明确确认通过后，才能迁移到 `final/`。
13. `recipe.json` 是 Gate 1 后的参考事实层，V2 不因 TTS 或渲染原地回写；真实音频时长和最终精确裁点分别写入 `voice/` 报告与 `reconstruction_timeline.json`。
14. `fragment_plan.json` 是 Retrieval/Gate 3 的不可变宽范围批准；`material_manifest.json` 记录 Reconstruction 的物理复制；精确裁点不得覆盖宽范围批准。
15. `manual-contract-only` pilot 每完成一个业务阶段，都要在 `stage_assessments/` 保存 `overview.md` 与五份固定阶段评估快照。快照必须写明 `framework_stage_id`、当前输入哈希、阶段/审批状态、已证实结果、未验证项、风险、效率证据和下一阶段准入；没有逐项评分时写 `stage_output_quality_score: not_scored`、`measurement_status: not_scored`，只有已有完整数字但当前 Gate 尚未审核时才用 `approval_status: provisional`，没有计时证据时写 `efficiency_measurement_status: incomplete`。不得用素材匹配置信度、旧案例分数或目标分冒充本次实测分。跨 Gate 阶段的等待稿必须明确标成“进行中快照”，不能冒充完成评估。

## 3. Brief：开工前由运营补齐

每个任务都先完成 Brief。Brief 属于 Preflight，不计入 Gate。建议将下表复制到当日工作目录的审核记录中；标为“必填”的项目未确认时，不开始 Gate 1 镜头切分。

| 字段 | 是否必填 | 运营填写要求 |
|---|---:|---|
| 任务名称 / 短标题 | 是 | 用于同日多任务区分，例如 `2026-08-11-table-mat-01` |
| 平台 | 是 | 抖音、小红书、视频号等；用于最终文件名和平台限制 |
| 产品 / 主题 | 是 | 明确具体产品、型号或内容主题 |
| 参考视频来源 | 是 | 本地文件或已下载文件；确认可用于内部制作 |
| 内容目标 | 是 | 转化、种草、功能说明、活动通知等 |
| 目标受众 | 是 | 谁会看、核心使用场景是什么 |
| 必讲卖点 | 是 | 只能填写已有证据支持或已获批准的表述 |
| 禁用表述 | 是 | 法务、平台或本次任务明确禁止的声明 |
| 文案来源 | 是 | 参考音频、用户稿、运营改写稿或已有配音 |
| 配音要求 | 是 | 是否生成；音色、语气、语速、语言；是否允许重写或删字 |
| 时长策略 | 是 | 跟随参考片、跟随新配音，或明确目标区间 |
| 字幕要求 | 是 | 默认独立 SRT、不烧录；如需例外必须在 Brief 明确 |
| 素材库范围 | 是 | 默认只用项目根目录 `assets/`；额外来源须明确 |
| 画面限制 | 是 | 禁止品牌、必须露脸、产品必须可见、不可裁切区域等 |
| 交付物 | 是 | 最终预览、正式 MP4、独立 SRT；需要进入剪映时可附导入清单 |
| 截止时间 / 审核人 | 是 | 明确谁负责 Gate 决策 |
| 最终命名信息 | 是 | `YYMMDD-platform-product-序号` 中的平台、产品缩写和序号 |

Brief 中出现互相冲突的要求时，先由运营确认优先级。例如“必须保持参考片 12 秒”与“文案不能删字且使用自然语速”可能无法同时满足。

## 4. 工作目录与命名

在项目根目录执行任务。每个任务使用独立工作目录：

```text
work/
  YYYY-MM-DD[-短标题或序号]/
    project_brief.yaml
    pipeline_state.json
    reference-YYYY-MM-DD.mp4
    recipe.json
    shot_blueprint.json
    asset_profiles.json
    content_blueprint.md
    technical_spec.md
    video_clips/
    script.txt
    matches.json
    content_baseline.json
    mutation_plan.json
    coverage_precheck.json
    coverage_report.json
    fragment_plan.json
    script_evidence_matrix.json
    production_script_candidate.json
    approved_production_script.json
    material_manifest.json
    match_validation_report.json
    material_validation_report.json
    final_validation_report.json
    stage_assessments/
      overview.md
      performance_proven_video.md
      blueprint.md
      controlled_mutation.md
      retrieval.md
      reconstruction.md
    review_contact_sheet.jpg
    material/
      fragment01/
      fragment02/
    voice/
    reconstruction_timeline.json
    remix.mp4
    captions.srt
    render_report.json
    jianying_import_manifest.json
```

`recipe.json`、`shot_blueprint.json`、`content_baseline.json`、`mutation_plan.json`、`matches.json`、`fragment_plan.json`、`material_manifest.json`、`material/`、`voice/`、`reconstruction_timeline.json` 和渲染产物必须共享同一个任务目录。旧样例中的 `work/replace_20260809/` 只作为历史实现保留，不是新任务模板。

### 4.1 Skill 使用方式

项目内 Skill 源文档位于 `.agents/skills/remix-reference-video/`。在当前项目中可直接要求 Codex：

```text
使用 $remix-reference-video，读取我的 project_brief.yaml，从 Preflight 开始执行。
```

需要在其他项目中使用时，可将整个 `remix-reference-video/` 目录安装到 `~/.agents/skills/`。安装前先确认目标不存在，不得盲目覆盖已安装版本。运营实际开工时复制 Skill 内的 `assets/project_brief.yaml`，不直接改安装模板。

最终视频命名：

```text
YYMMDD-platform-product-序号.mp4
```

示例：`260811-dy-tablemat-01.mp4`。英文缩写优先，避免过长文件名和乱码。

## 5. Preflight 与 Gate 1–5 总览

| 阶段 | 决策点 | 默认通过条件 | 未通过时 |
|---|---|---|---|
| Preflight（非 Gate） | Brief 与参考片是否具备开工条件 | 必填 Brief 完整；参考片已复制并可正常探测 | 补 Brief 或更换文件，不开始 Gate 1 |
| Gate 1 | 镜头切分是否可信 | 自动切点已逐帧复核；漏切、误切、单帧异常均有处理结论；镜头片段和关键帧完整 | 修正切点并重新导出，不进入结构设计 |
| Gate 2 | 内容基线和允许变化是否锁定 | `shot_blueprint.json`、`content_baseline.json`、`mutation_plan.json` 一致；卖点、禁用声明、口播意图、时长包络和 fallback 已确认；两份 hash 以一个 Gate 2 bundle 原子记录 | 修改蓝图/变更包，不进入素材匹配 |
| Gate 3 选材确认 | 素材宽范围是否可用于生产 | 候选通过语义/动作/技术门禁；人工看过接触表；每段记录批准源、SHA、叠字决定和足够宽的源时间范围；输出不可变 `fragment_plan.json` | 补素材、换候选或记录 `request_omit`；结构变化返回 Gate 2 |
| Gate 3 证据闭环 | 每句口播是否有批准画面证据 | `script_evidence_matrix.json` 的必需句子均为 `pass`，或已选择 Gate 2 批准的 fallback；无隐形改句 | 返回 Gate 3 重新选材，或返回 Gate 2 改变声明/口播意图 |
| Gate 3 汇总 | 是否允许进入脚本编译 | `gate3_material_selection` 与 `gate3_evidence_closure` 均为 `approved`；否则不能生成完整生产脚本或生产媒体 | 留在 Gate 3 |
| Gate 4 生成前 | 是否允许调用真实 TTS | `production_script_candidate.json`、最终文案、模型/协议、音色、语速和发音风险已确认，并提升为不可变 `approved_production_script.json` | 改稿、改设置或返回 Gate 3/2 |
| Gate 4 生成后 | 实际配音和精确时间轴是否可用 | TTS 实测通过；字幕、累计时间轴和精确裁点均在 Gate 3 宽范围内；人工听审通过 | 重生成，或范围不足时返回 Gate 3 |
| Gate 5 | 最终预览是否可确认 | 无生产阻塞；媒体参数、独立 SRT、音画边界和人工审核通过；导入清单有效 | 保留为待审核版本，不迁移 `final/` |

Gate 通过必须有明确的运营或负责人结论。机器报告“生成成功”不等于内容审核通过。

Gate 3 包含两个必需子状态，只有选材确认和证据闭环都通过，Gate 3 汇总才可通过。Gate 4 包含两次必需决定：先确认文案、音色和语速，再允许调用真实 TTS；生成后按顺序执行“实测时长 → 精确裁点/累计时间轴 → 听审实际音频”。两次决定未全部完成时，Gate 4 保持待审核。

Gate 5 的正式渲染还必须同时验证 Gate 1/2 的 `gate_status` 与 `stages.reference_split/content_blueprint` 汇总状态，二者都为 `approved` 才能执行。生成预览后必须把成片、最终校验报告、渲染报告和导入清单的 SHA-256 回写 `pipeline_state.json`，将任务推进为 `final_review/awaiting_user`；文件存在但状态或哈希未登记时，不得提交运营审核。

## 6. 分阶段执行

### Preflight：接收 Brief 与参考视频（非 Gate）

**输入**

- 已填写的 Brief；
- 用户提供的完整参考视频；
- 本次允许使用的素材范围。

**AI 动作**

- 检查文件是否存在、能否解码；
- 读取分辨率、帧率、帧数、时长、音视频流；
- 识别 Brief 中的冲突、缺项和高风险声明；
- 建议当日工作目录名称和交付文件名。

**运营补充**

- 确认平台、产品、受众、卖点、禁用表述、字幕和配音策略；
- 确认参考片是否只是结构参考，还是还需要保留其原音频或时长；
- 确认审核负责人。

**输出**

- `work/YYYY-MM-DD[-slug]/reference-YYYY-MM-DD.mp4`；
- 完整 Brief / 审核记录；
- 参考片基础探测信息。

**验收**

- 参考片可正常播放和探测；
- 文件名、任务目录和 Brief 对应同一任务；
- 所有必填项已确认；
- 参考片没有被移动回外部来源或覆盖。

### 阶段 1：镜头切分（Gate 1）

**输入**

- Preflight 完成的参考片；
- 参考片基础探测信息。

**AI 动作**

- 进行镜头切分、关键帧抽取和参考音频提取；
- 对自动切点做逐帧检查，识别漏切、误切和单帧异常；
- 生成包含参考媒体信息、切点、镜头起止时间和文件路径的参考事实 `recipe.json`；Gate 1 通过后该事实层不可因后续 TTS/渲染原地改写；
- 导出参考音频和原始转写（如需要）。

**运营补充**

- 逐帧确认切点；
- 标记漏切、误切、单帧异常和需要人工补切的动作边界；
- 只确认参考事实层中的误切、漏切、单帧异常是否需要修正；目标片是否保留、合并或删除留到 Gate 2。

**输出**

- `video_clips/shots/shot_NNN.mp4`；
- `video_clips/keyframes/shot_NNN_keyframe.jpg`；
- `video_clips/reference_contact_sheet.jpg`；
- `video_clips/transcript_raw.json`（如生成 ASR）；
- `voice/reference-audio.*` 及转写文件（如有）；
- 基础 `recipe.json`。

**验收**

- 镜头顺序、起止时间和总时长能回到参考片；
- 每个 `shot_id` 唯一，路径存在；
- 单帧异常、低分切点和人工补切均有说明；
- 每个导出片段和关键帧都能打开；
- Gate 1 只确认镜头切分可信，不在此阶段批准卖点或目标结构。

### 阶段 2：结构、卖点与禁用声明（Gate 2）

**输入**

- Gate 1 通过的 `recipe.json`、镜头片段、关键帧和参考音频/转写；
- Preflight Brief 中的目标受众、内容目标、已批准卖点和禁用表述。

**AI 动作**

- 从参考音频、用户稿或运营改写稿整理 `script.txt`；
- 将参考镜头结构转换为目标片段，生成 `shot_blueprint.json`；
- 为每个片段记录语义、动作、景别、目标时长、素材类型和连续动作组；
- 建立卖点证据与目标片段的对应关系；
- 将参考片中不可沿用或未获证据支持的声明列入禁用清单；
- 根据已确认的结构变化生成 `content_baseline.json` 和 `mutation_plan.json`；参考 `recipe.json` 只保留原始镜头事实和可追溯的人工备注，不把目标蓝图写回参考事实层。

**运营补充**

- 校对人名、品牌、数字、单位、卖点和禁用表述；
- 确认目标片段顺序、每段信息任务和证据来源；
- 确认异常镜头的最终处理，以及是否允许重组参考片结构；
- 确认默认字幕为独立 SRT、不烧录；本次例外要求写入 Brief。

**输出**

- `script.txt`；
- `shot_blueprint.json`；
- `content_baseline.json`；
- `mutation_plan.json`；
- `content_blueprint.md` 和 `technical_spec.md`（如本次需要人工可读说明）；
- Gate 2 人工审核记录。

**验收**

- 目标 `fragment_id` 连续且唯一；
- 蓝图的片段总数、目标时长、连续动作组和声明策略已由运营确认；
- 每个卖点有证据来源或已批准依据；禁用声明不会进入新脚本；
- `recipe.json`、`script.txt`、`shot_blueprint.json` 和 Gate 2 bundle 的片段顺序与路径一致；
- Gate 2 同时记录 `content_baseline_hash` 与 `mutation_plan_hash`，二者必须来自同一轮展示和批准；
- `script.txt` 只作为人类可读稿或参考稿；进入配音后，以 Gate 4 生成前批准的 `approved_production_script.json` 为唯一文本权威。

### 阶段 3：素材匹配与人工审校（Gate 3）

**输入**

- Gate 2 通过的 `recipe.json`、`shot_blueprint.json`、`content_baseline.json` 和 `mutation_plan.json`，以及四者的批准输入哈希；
- 基于当前 Gate 2 原子内容包重新计算的权威 `coverage_report.json`；
- 只读的 `assets/`。

**AI 动作：选材确认子状态**

- 对素材进行媒体探测、抽帧、语义门禁、视觉评分和重复识别；
- 为每个片段生成候选与理由；
- 做全局排程，避免连续三镜同源、相邻明显重复构图和动作不连续；
- Gate 3 选材确认前生成 `matches.json`、待审选材方案、接触表和不可变 `match_validation_report.json`，不复制生产素材；
- 选材确认通过后写入不可变 `fragment_plan.json`，只记录批准素材、SHA、叠字决定和宽可用时间范围；此时不写最终精确裁点，也不允许删段；

**AI 动作：证据闭环子状态**

- 使用选材确认的 `fragment_plan.json` 生成 `script_evidence_matrix.json`，将每句口播映射到已批准画面证据窗；
- `review_required` 只能在 Gate 3 审核包中取得明确的候选替换或 Gate 2 已批准 fallback；不得隐式改写口播；
- 两个子状态都通过后，Gate 3 汇总才可通过，并将脚本编译交给 Controlled Mutation；

**Gate 3 后的物理准备（Reconstruction）**

- Gate 3 汇总通过后，Reconstruction 才从 `assets/` 复制/导出批准宽范围到 `material/fragmentNN/`，并写 `material_manifest.json`；物理复制失败可重试，不改变 Gate 3 决定。

**运营补充**

- 逐组查看“参考帧 / 选中帧”接触表，不能只看分数；
- 确认产品、场景、动作、景别、角度、光线、产品可见度和构图；
- 对每个源画面叠字/品牌作出“保留、裁切、遮盖、换素材”决定；
- 对低置信度和缺素材片段补充具体素材需求。

**输出**

- `matches.json`：候选、分数、来源、哈希与拒绝原因；
- `fragment_plan.json`：Gate 3 批准的不可变宽范围计划；
- `script_evidence_matrix.json`：逐句证据闭环结果；
- 待审选材方案：拟选素材或缺素材状态；
- `review_contact_sheet.jpg`；
- `match_validation_report.json`：Gate 3 选材输入的不可变候选校验快照；
- 人工审核记录。

Gate 3 汇总通过后由 Reconstruction 追加产物：

- `material/fragmentNN/selected.mp4|jpg`；
- `material_manifest.json`；
- 基于当前批准宽范围和复制文件生成独立的 `material_validation_report.json`；不得覆盖 `match_validation_report.json`。

**验收**

- 每个目标片段只能处于 `matched` 或明确的 `缺素材` 状态；Gate 3 两个子状态和汇总状态必须可追溯；
- 缺素材记录不能携带伪造的选中项、输出路径或非零置信度；
- 所有 `output_path` 存在，源路径、SHA-256、媒体类型和实际导出范围一致；
- 视频导出范围不超过源时长，素材原声已移除；
- 连续动作组同源且源时间连续；
- 重复素材、连续三镜同源和相邻近似构图检查通过；
- `match_validation_report.json` 必须与 Gate 3 选材批准输入哈希一致；`material_validation_report.json` 必须与当前 `fragment_plan.json` 和复制文件一致。任一报告失败都不能手改为 passed；应换素材、修正数据，或由负责人书面决定是否接受例外；
- 任何缺素材或未决叠字都阻止生产成片，但允许进入带明确标识的审核预览；若需要删段，只能记录 `request_omit` 并返回 Gate 2，不能在 Gate 3 直接批准结构变化。

### 阶段 4：配音脚本、生成与 QA（Gate 4）

**输入**

- Gate 3 汇总通过的不可变 `fragment_plan.json`；
- Gate 3 证据闭环通过的 `script_evidence_matrix.json`；
- Controlled Mutation 编译的 `production_script_candidate.json`；
- 已批准卖点和禁用表述；
- 豆包语音凭证和待确认的音色配置。

**AI 动作：生成前子状态**

- 校验候选脚本与内容基线、变更包、证据矩阵、素材类型、缺素材清单、片段数量和跨段口播 span 一致；
- 运营确认最终文案、模型/协议、音色、语速和发音风险后，将候选提升为不可变 `approved_production_script.json`，记录 `gate4_pre_generation=approved`；
- 只有生成前子状态通过后，先执行 dry-run，再按片段或 span 调用 TTS；

**AI 动作：生成后子状态**

- 生成分段音频、`final_voice.mp3`、`voice_manifest.json` 和 `duration_report.json`；
- 读取真实音频时长，生成 `reconstruction_timeline.json` 和 `captions.srt`；精确裁点只能在 Gate 3 宽范围内收窄，不能覆盖 `fragment_plan.json`；
- 检查开头、片段边界、最长停顿、最紧字幕边界和结尾，生成 `voice_qa_report.json`。

**运营补充**

- 审核每句话是否准确、合规、自然；
- 必须完整试听开头、中间边界、最长停顿附近和结尾；
- 确认发音、音色、情绪、节奏和断句；
- 生成前确认后才允许调用真实 TTS；生成后还要试听实际音频并确认字幕、累计时间轴和精确裁点，记录 `gate4_post_generation=approved`；
- 当配音明显长于目标时，从“精简文案后重生成、裁除合成静音、调整蓝图并扩展真实源窗口”中作出选择；源窗口不足时退回 Gate 3，不能靠视频变速或长尾冻结解决。

**输出**

- `voice/voice_script.json` 和 `voice/voice_script.txt`：由 `approved_production_script.json` 确定性生成的只读执行投影，必须记录源路径和 SHA-256；
- `voice/fragments/fragmentNN.mp3`；
- `voice/final_voice.mp3`；
- `voice/voice_manifest.json`；
- `voice/duration_report.json`；
- `voice/voice_qa_report.json`；
- `reconstruction_timeline.json`；
- `captions.srt`；
- Gate 4 生成前/生成后决定记录；V2 不原地更新参考事实 `recipe.json`。

**验收**

- dry-run 通过，且脚本的媒体统计、缺素材清单和 `fragment_plan.json` 一致；
- 分段音频、合并音频和 manifest 数量一致；跨段口播只生成一次并无缝切分；
- `duration_report.json` 与实际音频探测时长一致；
- 字幕 span 单调、不重叠、不越过最终音频；
- `voice_qa_report.json` 的阻塞项已有处理结论；
- 人工试听完成，且 `gate4_pre_generation` 与 `gate4_post_generation` 均对当前输入哈希有效。`final_voice.mp3` 存在不代表 Gate 4 自动通过。

### 阶段 5：最终预览与交付（Gate 5）

**输入**

- 当前 `recipe.json`、`matches.json`、不可变 `fragment_plan.json`、`material_manifest.json`、`reconstruction_timeline.json`；
- `material/fragmentNN/selected.*`；
- 通过 Gate 4 的 `final_voice.mp3`；
- 字幕策略与人工叠字决策。

**AI 动作**

- 先运行渲染 dry-run，校验所有路径、哈希、片段状态、音频和时间轴；
- 按 `reconstruction_timeline.json` 的真实配音累计端点计算 60fps 帧预算；
- 视频保持 `1.00x`，不足时先扩展同一源窗口；若仍不足则退回 Gate 3，只有累计端点舍入误差允许最多 2 帧边界补齐；
- 图片按片段时长稳定显示；
- 移除素材原声，封装指定配音；
- 输出最终预览 MP4、独立 SRT 和 `render_report.json`；
- 生成 `jianying_import_manifest.json`；V1 不创建新版加密剪映草稿。
- 原子提升输出后更新 `pipeline_state.json`：登记四个 Gate 5 交付文件哈希，并把 `current_stage`、`render`、`final_review` 和 `gate5` 更新为待最终审核；回写失败则回滚本轮输出。

**运营补充**

- 逐镜查看画面是否匹配、是否重复、是否被裁掉主体；
- 检查源叠字、品牌、字幕安全区和平台风险；
- 完整播放一次，并重点检查开头、所有边界、连续动作、异常静止帧、字幕和结尾；
- 确认当前文件是 Gate 5 最终预览，不是带占位的阶段性审核片；
- 如需进入剪映，复核导入清单中的媒体、配音、SRT、路径、哈希和源范围。

**输出**

- 最终预览 MP4；
- 独立 `captions.srt`；
- `render_report.json`；
- `final_validation_report.json`；
- `jianying_import_manifest.json`；
- Gate 5 审核结论。

**验收**

- 正式视频为 9:16、1080x1920、60fps、H.264、`yuv420p`；
- 默认只有一个视频流和一个 AAC 音频流；字幕为独立 SRT，不烧录、不嵌入字幕流；
- 视频帧时间轴与真实配音误差不超过一帧；
- 片段顺序完整，连续动作切点未被改写，媒体读取范围未超出源时长；
- 没有长尾帧冻结；只有累计端点舍入造成的最多 2 帧边界补齐；
- 生产模式无占位、无缺素材、无未决叠字和未解决的配音阻塞；
- `render_report.json` 中的输入/输出路径、SHA-256、帧数、流信息和实际文件一致；
- 导入清单中所有素材、配音和 SRT 路径存在，哈希与当前文件一致，媒体源范围合法；清单不得被表述为剪映草稿；
- 用户或负责人明确确认后才可归档。

## 7. 必须保留的机器产物契约

下表中的文件用于串联上下游。不要为了“让流程继续”而手改统计、状态或哈希。

V2 新建机器产物必须采用 canonical envelope：`artifact_type`、`schema_id`、`schema_version=1.0.0`、`contract_version=2.0.0-alpha.1`、`skill_version=2.0.0-alpha.1`。具体类型和 `schema_id` 以 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json` 为唯一 registry。历史 V1 产物的 `schema_version=1.0` 是创建时事实，只能按 V1 续跑或显式迁移，不能通过替换版本字符串伪装成 V2。

| 产物 | 权威内容 | 下游依赖 |
|---|---|---|
| `recipe.json` | Gate 1 后不可变的参考片媒体信息、镜头、路径、原音频和参考事实哈希；V2 不因 TTS/渲染原地回写 | Blueprint、匹配、审计 |
| `video_clips/` | 参考镜头片段、关键帧和视觉顺序 | 蓝图、人工视觉审核 |
| `script.txt` | 人工可读参考稿/校正稿 | 蓝图和脚本审计；不是配音后唯一权威 |
| `shot_blueprint.json` | 目标片段、语义、动作、时长、素材类型、连续动作组和声明策略 | 匹配、配音脚本 |
| `content_baseline.json` | Blueprint 产出的结构、卖点、禁用声明、口播意图和时长包络 | Gate 2 原子批准、Mutation、Retrieval |
| `mutation_plan.json` | Controlled Mutation 的允许/禁止变化、fallback、删并段请求和失效规则 | Gate 2 原子批准、脚本编译 |
| `matches.json` | 每段候选、来源、哈希、评分、门禁和原因 | `fragment_plan.json` 交叉校验、渲染审计 |
| `fragment_plan.json` | Retrieval/Gate 3 的不可变批准宽范围、源 SHA、叠字决定、缺素材和人工备注；不记录最终精确裁点 | 脚本证据、物理复制、Reconstruction |
| `script_evidence_matrix.json` | 每句口播与 Gate 3 已批准画面证据窗、动作完整性和闭环决定 | Controlled Mutation 脚本编译 |
| `material/fragmentNN/selected.*` | 已批准的生产素材副本或导出片段 | 配音对齐、渲染、剪映导入清单 |
| `material_manifest.json` | Reconstruction 对批准宽范围的物理复制/导出、路径和副本哈希 | 渲染、交付审计 |
| `match_validation_report.json` | Gate 3 选材确认前的候选、评分、来源和宽范围不可变校验快照 | Gate 3 选材确认 |
| `material_validation_report.json` | Gate 3 汇总通过后实际复制/导出素材、哈希和范围校验 | Reconstruction、Gate 4/5 前置 |
| `final_validation_report.json` | Gate 5 最终预览的路径、流、帧数、时间轴和硬门禁校验 | Gate 5 |
| `production_script_candidate.json` | Gate 3 证据闭环后由 Controlled Mutation 编译的待批准脚本 | Gate 4 生成前 |
| `approved_production_script.json` | Gate 4 生成前批准的唯一 TTS 文本输入和设置快照 | TTS、时间轴 |
| `voice_script.json` | `approved_production_script.json` 的确定性只读执行投影；必须记录 `source_approved_script_sha256`，不得独立改文案 | TTS 调用编排、字幕编排 |
| `voice_manifest.json` | TTS 配置、调用 provenance、输出探测和哈希 | 配音 QA、审计 |
| `duration_report.json` | 真实分段时长、累计时间和差异 | `reconstruction_timeline.json`、渲染 |
| `reconstruction_timeline.json` | 以实测配音为基准的字幕、累计时间轴和 Gate 3 宽范围内精确裁点 | 渲染、Gate 4 生成后听审 |
| `voice_qa_report.json` | 静音、边界、时长、缺画面和人工试听要求 | Gate 4 |
| `captions.srt` | 与 canonical 配音时间轴一致的独立字幕 | 审核、交付或导入剪映 |
| `render_report.json` | 输入/输出哈希、帧预算、媒体流、占位、字幕和最终状态 | Gate 5、归档审计 |
| `jianying_import_manifest.json` | 需导入剪映的成片、素材、配音、SRT、哈希和合法源范围；它不是草稿 | 可选的剪映后续编辑 |

路径解释规则：相对路径默认以声明该路径的 JSON 文件所在目录为基准。修改目录或复制工作包后，必须重新验证路径和哈希。

## 8. 缺素材处理 SOP

### 8.1 识别和登记

当没有候选、置信度不足、语义不符、动作不符、相邻构图冲突或导出失败时，将该段标记为 `缺素材`。登记内容至少包括：

- `fragment_id`；
- 目标语义和要证明的卖点；
- 所需动作、景别、机位、场景、光线和产品可见度；
- 目标时长；
- 已有候选被拒绝的原因；
- 是否属于连续动作组或身份连续组；
- 下一步负责人和预计补齐时间。

### 8.2 可选处理

1. 向 `assets/` 增加已批准的新素材，再重新运行匹配和校验。
2. 由运营批准调整蓝图语义或镜头结构，再从 Gate 2 重新向下执行。
3. 仅为沟通生成带“缺素材”中性占位卡的审核预览。
4. 如果用户明确批准删掉该叙事段，重新设计音画时间轴；不能静默删除。

### 8.3 禁止事项

- 不得用低相关画面冒充命中；
- 不得只删画面、保留不再对应的口播，或只删口播、保留失去语义的画面；
- 不得把带占位卡的文件标为 production 或迁移到 `final/`；
- `render_no_missing.mjs` 属于特定审核变体，会改变片段和语音排程，不是默认生产路径；只有用户明确接受删除/重排后才能作为新的叙事方案重新验收。

## 9. 配音专项操作

### 9.1 生成前

- 先锁定 `approved_production_script.json`，再由其确定性生成带源哈希的 `voice_script.json` 执行投影；投影文本或哈希不一致时停止 TTS；
- 文案中的数字、单位、品牌和声明由运营逐条确认；
- 脚本记录的片段数、媒体类型统计和缺素材列表必须与当前 `fragment_plan.json` 一致；
- 连续口播跨多个视觉片段时，使用一个 span 生成，再在 PCM 上切分，避免接缝音色或语气变化；
- 默认豆包 V3 WebSocket 使用 `DOUBAO_TTS_KEY`；只在明确配置旧版 OpenSpeech 时使用 `DOUBAO_TTS_API_KEY` 或 `VOLCENGINE_TTS_APPID + VOLCENGINE_TTS_ACCESS_TOKEN`；
- `DOUBAO_LITE_API_KEY` 不得自动当作 OpenSpeech 凭证，`DOUBAO_AUDIO` 只记录为模型标签，不伪造成 `voice_type`；
- 凭证放在本地环境或 `--env-file` 指定文件，不写入 Brief、JSON、脚本、报告或提交记录。

### 9.2 生成后

- 先看 `duration_report.json`，再决定画面长度；
- 抽查每个分段文件和合并文件是否一致；
- 对开头、每个中间边界、最长停顿和结尾做定点试听；
- 检查 SRT 文本是否来自同一 canonical cue 数据，不能从旧 `script.txt` 重新拼一版；
- 当素材或蓝图发生变化时，先更新脚本基线并重新 dry-run，不能沿用旧 manifest 冒充当前状态。

## 10. 渲染与剪映导入清单专项操作

### 10.1 审核预览

有缺素材时只能使用 `review-with-placeholders`。占位卡必须显示片段 ID 和缺失语义，并在 `render_report.json` 中记录；输出状态只能是 `preview_review_required` 或同义审核状态。

### 10.2 最终预览渲染

只有 Gate 1–4 全部通过后才生成 Gate 5 最终预览。默认输出规则：

- 1080x1920、60fps、H.264、`yuv420p`；
- 视频素材 `1.00x`；不足时先扩展同一源窗口，仍不足则退回 Gate 3；
- 只允许累计端点舍入产生的最多 2 帧边界补齐，禁止长尾帧冻结；
- 图片等比 contain/letterbox，不拉伸，不裁掉主体；
- 移除素材原声，只保留指定配音；
- 默认字幕为独立 SRT，不烧录、不嵌入字幕流；
- 不用 `-shortest` 或容器时长掩盖音画时间轴错误。

使用 `--force` 前，运营必须确认：旧输出已审核或备份、上游产物是当前版本、准备有意替换同名输出。不能为绕过“输出已存在”提示而习惯性加 `--force`。

### 10.3 剪映导入清单（V1/V2 默认产物）

V1/V2 默认不生成新版加密剪映草稿，但生成 `jianying_import_manifest.json`，为人工导入和后续适配器提供稳定交接面。它至少记录：

- 任务目录，以及 `artifact_type`、`schema_id`、`schema_version`、`contract_version`、`skill_version`；
- 最终预览、配音和独立 SRT 的路径与 SHA-256；
- 每个 `fragment_id` 的已批准素材路径、媒体类型、源入点/出点和真实时长；
- 时间轴顺序、片段时长和需要运营在剪映中完成的动作；
- 缺失路径、越界源范围或哈希不一致时的阻塞状态。

导入清单只用于人工或后续工具导入，不是可直接打开的草稿，也不得覆盖任何剪映缓存。

## 11. 归档 SOP

1. 确认 `render_report.json` 为当前输出生成，输入和输出哈希一致。
2. 确认 Gate 5 有明确“通过”记录，且用户已经确认版本。
3. 按 `YYMMDD-platform-product-序号.mp4` 重命名正式视频。
4. 将确认通过的视频从 `work/` 迁移到 `final/`；默认同时交付独立 SRT，Brief 明确不需要时除外。
5. `work/` 中保留机器契约、报告、审核记录和导入清单，直到项目关闭；不要把未通过 Gate 5 的预览误放入 `final/`。
6. 若用户要求返修，从相关 Gate 重新执行并产生新报告，不覆盖历史结论后继续沿用旧哈希。

## 12. 常见阻塞与处理

| 阻塞/症状 | 常见原因 | 运营动作 |
|---|---|---|
| 参考片无法探测或无画面 | 文件损坏、下载不完整、编码异常 | 重新获取源文件；不要继续拆解 |
| 自动切镜出现一帧镜头 | 转场闪帧、压缩噪声或真正插帧 | 逐帧确认，决定删除、合并或保留并记录 |
| 自动切镜漏掉动作切点 | 相邻画面构图接近，scene score 低 | 人工补切并在 `recipe.json` 说明 |
| 转写数字/卖点不可靠 | ASR 同音、背景音乐、语速快 | 运营听原音校正，并核对证据与禁用表述 |
| 匹配结果低置信度 | 语义或动作不足、画面差异大 | 补素材或调整蓝图；不要硬凑 |
| validator 报相邻构图冲突 | 同房间、同机位画面过近 | 换候选、换场景；若接受例外，书面记录但不伪造 passed |
| 接触表与 plan 不一致 | 上游文件变更后报告未重跑 | 重新执行匹配校验，检查生成时间和哈希 |
| 素材路径或 SHA 不一致 | 手工替换 `selected.*`、移动目录 | 恢复匹配产物或重新匹配；不要手改哈希 |
| 源画面有品牌/宣传字 | 素材本身烧录，关闭字幕无效 | 保留、裁切、遮盖或换无字素材，逐镜记录 |
| voice dry-run 报媒体统计或源哈希不一致 | `fragment_plan.json` 改过，或 `voice_script.json` 不是当前批准脚本的投影 | 从当前 `approved_production_script.json` 重新生成投影后 dry-run |
| TTS 鉴权失败 | 凭证缺失、凭证类型或资源 ID 不匹配 | 使用正确的本地凭证配置；不要把密钥写进仓库 |
| 配音远长于参考片 | 文案过长、自然语速、句间停顿 | 精简重生成、裁静音或接受延长画面；不能默认视频变速 |
| `voice_qa_report` 为 `review_blocked` | 时长、长停顿、缺视觉或人工试听未完成 | 逐项处理并记录人工决定 |
| renderer 拒绝 production | 缺素材、路径/哈希漂移或输入契约不一致 | 回到 Gate 3/4 修复；审核时改用显式占位模式 |
| renderer 拒绝覆盖 | 同名输出已存在 | 先确认和备份旧版本；只有有意替换时使用 `--force` |
| 最新预览与报告哈希不一致 | 上游改动后仍在看旧 MP4 | 重新 dry-run 和渲染，以当前报告为准 |
| 误把导入清单当成剪映草稿 | V1 只生成 manifest，不生成新版加密草稿 | 对外明确交付物是 `jianying_import_manifest.json`；如需草稿，另立 V2 需求 |

## 附录 A：旧脚本现状与最小核验命令

以下命令只用于复现和核验 `2026-08-09` 旧样例。它们包含任务目录和 `work/replace_20260809/` 硬编码，不是新版 Skill 接口，也不是新任务目录模板。新任务仍必须把全部权威产物放在单一 `work/YYYY-MM-DD[-slug]/` 中。特别是旧 TTS 脚本只接收 `--voice-script`，不会验证 `approved_production_script.json` 的源哈希，因此禁止用于 V2 pilot 或普通 V2 生产。

### 13.1 参考片探测

```bash
ffprobe -v error \
  -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,sample_rate,channels:format=duration \
  -of json \
  work/2026-08-09/reference-2026-08-09.mp4
```

当前样例记录的 scene cut 诊断命令如下。它只输出候选切点，不会自动完成镜头导出、异常检查和 `recipe.json` 生成：

```bash
ffprobe -v error -f lavfi \
  -i "movie=work/2026-08-09/reference-2026-08-09.mp4,select=gt(scene\,0.10)" \
  -show_entries frame=pts_time:frame_tags=lavfi.scene_score \
  -of csv=p=0
```

### 13.2 素材匹配

注意：这是旧样例的原位重跑命令。匹配器会重写 `matches.json`、`fragment_plan.json`，并替换各片段的 `selected.*`；只读盘点或运营审核时不要执行。

```bash
python3 work/replace_20260809/match_materials.py \
  --recipe work/2026-08-09/recipe.json \
  --blueprint work/replace_20260809/shot_blueprint.json \
  --assets assets \
  --output work/replace_20260809
```

### 13.3 独立校验匹配结果

```bash
python3 work/replace_20260809/validate_results.py \
  --recipe work/2026-08-09/recipe.json \
  --blueprint work/replace_20260809/shot_blueprint.json \
  --matches work/replace_20260809/matches.json \
  --plan work/replace_20260809/fragment_plan.json \
  --assets assets \
  --output work/replace_20260809
```

### 13.4 配音 dry-run

```bash
node work/2026-08-09/voice/generate_doubao_voice.mjs \
  --blueprint work/replace_20260809/shot_blueprint.json \
  --fragment-plan work/replace_20260809/fragment_plan.json \
  --voice-script work/2026-08-09/voice/voice_script.json \
  --recipe work/2026-08-09/recipe.json \
  --output-dir work/2026-08-09/voice \
  --dry-run
```

### 13.5 生成配音

凭证写入本地环境文件，不要提交。确认 dry-run 通过后去掉 `--dry-run`：

```bash
node work/2026-08-09/voice/generate_doubao_voice.mjs \
  --blueprint work/replace_20260809/shot_blueprint.json \
  --fragment-plan work/replace_20260809/fragment_plan.json \
  --voice-script work/2026-08-09/voice/voice_script.json \
  --recipe work/2026-08-09/recipe.json \
  --output-dir work/2026-08-09/voice \
  --env-file /absolute/path/to/local-tts.env
```

已有同名配音时工具会拒绝覆盖。只有确认替换后才使用 `--force`；旧输出的归档情况仍需检查。

### 13.6 配音 QA

```bash
node work/2026-08-09/voice/verify_voice_outputs.mjs \
  --voice work/2026-08-09/voice/final_voice.mp3 \
  --recipe work/2026-08-09/recipe.json \
  --manifest work/2026-08-09/voice/voice_manifest.json \
  --duration-report work/2026-08-09/voice/duration_report.json \
  --output work/2026-08-09/voice/voice_qa_report.json
```

### 13.7 渲染 dry-run

有缺素材时：

```bash
node work/2026-08-09/render_remix.mjs \
  --dry-run \
  --review-with-placeholders
```

无缺素材、准备生产时：

```bash
node work/2026-08-09/render_remix.mjs \
  --dry-run \
  --production
```

### 13.8 生成审核预览或生产文件

审核预览：

```bash
node work/2026-08-09/render_remix.mjs \
  --review-with-placeholders
```

以下旧脚本命令仅用于历史样例诊断，不构成新版流程的前置条件。新版仍须 Gate 1–4 全部通过、无缺素材后才能生产渲染：

```bash
node work/2026-08-09/render_remix.mjs \
  --production
```

旧渲染器虽支持 `--recipe`、`--matches`、`--fragment-plan`、`--material-dir`、`--voice`、`--reference`、`--output`、`--captions` 和 `--report`，但它仍包含旧任务契约和长尾冻结策略，不能直接作为新版 Skill 的 Gate 5 实现。

## 附录 B：旧脚本可复用程度与硬编码点

| 环节 | 当前可复用程度 | 运营注意事项 |
|---|---|---|
| 参考片探测/切点诊断 | 低至中 | 有 FFprobe 命令记录，但没有新版 Skill 的统一拆解接口；切片、关键帧、转写和 recipe 仍需按任务编排 |
| 蓝图制作 | 低 | 当前主要是任务文档和 JSON，强依赖人工确认卖点、异常镜头和叙事结构 |
| 素材匹配 | 高 | `match_materials.py` 参数完整，但脚本位于旧 `replace_*` 工作包；新 Skill 必须把输出定向到单一任务目录 |
| 匹配校验 | 高 | `validate_results.py` 参数完整；每次选材变化后都应重跑 |
| 配音生成 | 中 | 支持显式输入输出参数和 dry-run，但脚本位于单次工作目录，默认路径、片段契约和样例结构仍有任务特化 |
| 配音 QA | 中至高 | 可显式传入 voice、recipe、manifest、duration report 和 output；当前检查逻辑仍假定 replacement voice 契约 |
| 标准渲染 | 低至中 | 支持显式路径、审核/生产模式和 dry-run，但旧实现允许长尾帧冻结，与本 SOP 的“扩源或回 Gate 3、最多补 2 帧”不一致 |
| no-missing 变体 | 低 | 会删减/重排音画，只适合特定审核目的，不是标准生产流程 |
| 剪映导入清单 | 待纳入新版 Skill | V1 只允许生成 `jianying_import_manifest.json`，不生成新版加密剪映草稿 |
| 新版 Skill 接口 | 未实现于这些旧脚本 | 当前命令只能作为实现参考；不得向运营承诺它们就是新 Skill 接口 |

## 一线运营交付前勾选表

- [ ] Brief 必填项完整，Preflight 已完成；未把 Brief 记作 Gate。
- [ ] 镜头片段、关键帧和基础 `recipe.json` 对得上，Gate 1 已通过。
- [ ] 结构、卖点证据、禁用声明和目标蓝图已确认，Gate 2 已通过。
- [ ] 每个 fragment 已看实际画面，不是只看文件名或分数。
- [ ] 缺素材清单准确；没有用无关素材补位。
- [ ] 源画面叠字/品牌逐镜有处理决定。
- [ ] `match_validation_report.json` 与 Gate 3 审批输入一致，`material_validation_report.json` 与当前生产素材一致；两者未互相覆盖。
- [ ] `final_validation_report.json` 与当前 Gate 5 预览一致。
- [ ] 配音 dry-run 通过，脚本基线与当前素材计划一致。
- [ ] 已试听开头、边界、最长停顿和结尾，Gate 4 已通过。
- [ ] 渲染 dry-run 通过；预览/production 模式选择正确。
- [ ] 视频没有长尾帧冻结；边界舍入补齐不超过 2 帧。
- [ ] 输出分辨率、帧率、编码、音轨、字幕和时长符合 Brief。
- [ ] `render_report.json` 的路径、哈希和实际文件一致。
- [ ] 默认字幕为独立 SRT，视频中没有新增烧录字幕或字幕流。
- [ ] 已生成并校验 `jianying_import_manifest.json`；未把它表述为草稿。
- [ ] 普通生产任务由用户明确确认 Gate 5 后，才按命名规则迁移到 `final/`；pilot 永不归档。
