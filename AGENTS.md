# AGENTS.md

## 当前能力状态与版本

- 当前状态：Track A 静态护栏与 G-A 已通过；通过证据来自 `work/2026-08-15-tablemat-ga-harness-pilot/` 的 7 个当前哈希绑定决定和最终 `ga-audit status=passed, ga_ready=true`。历史 pilot `work/2026-08-13-tablemat-pilot/` 的越权失败记录保留。结论见 `docs/g-a-assessment-2026-08-15.md`。
- 生产后端固化设计已确认，实施计划位于 `docs/superpowers/specs/2026-08-15-remix-production-backend-design.md` 和 `docs/superpowers/plans/2026-08-15-remix-production-backend.md`。现在允许按 B0 → B1/B4a → B2/B3 → B4 → B5 顺序实现 Track B；在 G-B 和监督运营试用通过前，仍不得启用普通 V2 生产、共享生产缓存或一线发布。
- WP-A2 只提供 `ga-prepare-review`、`ga-record-decision`、`ga-audit`，仅服务 owner 指定的 `manual-contract-only` clean pilot；不得运行媒体生产、缓存、归档、迁移或复用审批。G-A 通过后由 B0 通用 Approval Service 替代。
- G-A 通过后，Track B 必须按 B0 → B1/B4a → B2/B3 → B4 → B5 顺序执行；`pipeline_state.json` 是唯一状态/审批权威，`approve-gate` 必须绑定当前审核包哈希、可信服务时间和 `state_revision`，不能复用其他任务批准。
- 当前 `skill_version` 与 `contract_version` 均为 `2.0.0-alpha.1`。V2 新建机器产物统一使用 `schema_version=1.0.0`，并声明 `artifact_type` 与 `schema_id`；canonical registry 为 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`。
- 历史 V1 产物保留创建时的 `schema_version=1.0`，不得为了兼容 V2 而原地改写。
- 静态检查器不负责 trigger 行为或生产媒体比较。Track A 收口已另行完成 12 条独立 trigger 前向评测和 `work/` 媒体摘要前后对比；完整产物 shape、事务、审批和真实 adapter 已由 Track B 测试覆盖。任何单项结果都不能被扩大表述为 G-B 或发布质量已通过。
- Native Runner 已接入正式 CLI 的显式 `production_runtime_config.json`；普通 `run/stage/resume` 仍受 `track_b=locked_until_g_a` 保护。唯一隔离例外 `gb-pair` 已在 `work/2026-08-16-gb-pair-real-2/` 完成真实 cold/hot 配对：两侧均独立通过 Gate 1–5，真实 FFmpeg/TTS 成片、代理检查和最终校验通过；Gate 5 后只复制声明 cache，hot 保留自己的增量索引，未复用审批。配对当前为 `measured_pending_review`，G-B 仍需 V1 可比性和 owner 阈值复核，普通 V2 生产与一线发布继续锁定。
- 主干 Skill 入口为 `.agents/skills/remix-reference-video/README.md`。历史 V1 任务按创建时契约续跑；新 V2 case 先完成 Stage 0，冻结 `reference-*.mp4`、`project_brief.json`、`asset_profiles.json` 和 `g_b_frozen_input_snapshot.json`，再使用隔离 `gb-pair`。缺少冻结事实时必须暂停补齐，不得从文件名或空白信息推断产品声明。

## 目标

将完整参考视频转化为可审核、可追溯的自有产品竖屏成片，并用机器契约和人工闸门控制素材、文案、配音和渲染风险。

## 目录

项目根目录只保留稳定结构，单次剪辑产生的过程文件放进当日工作文件夹。

- `AGENTS.md`：项目长期上下文，记录目标、目录、流程、输出和验收标准。
- `assets/`：提前准备好的产品素材、场景素材、人物素材、AI 片段和其他可复用素材。剪辑时只从这里复制素材，不移动或破坏原文件。
- `docs/`：团队级运营 SOP、产物契约和审核说明。
- `.agents/skills/`：项目内可版本化、可安装的 Codex Skill 包；工作产物不放在 Skill 包内。
- `work/`：正在制作或待审核的视频项目。每次剪辑在这里创建一个当日工作文件夹。
- `final/`：已经完成并确认通过的视频，从 `work/` 迁移到这里，避免工作区文件过多。
- `.agents/skills/remix-reference-video/README.md`：新窗口启动模板、V1 续跑边界、V2 冻结输入和 `gb-pair` 操作说明。

每次剪辑时，在 `work/` 下创建一个当日工作文件夹：

work/
  YYYY-MM-DD[-slug]/
    project_brief.yaml
    pipeline_state.json
    reference-YYYY-MM-DD.mp4
    recipe.json
    shot_blueprint.json
    content_baseline.json
    mutation_plan.json
    coverage_precheck.json
    coverage_report.json
    asset_profiles.json
    matches.json
    fragment_plan.json
    script_evidence_matrix.json
    production_script_candidate.json
    approved_production_script.json
    voice_preflight.json
    material_manifest.json
    match_validation_report.json
    material_validation_report.json
    final_validation_report.json
    review_contact_sheet.jpg
    video_clips/
    script.txt
    material/
      fragment01/
      fragment02/
    stage_assessments/
      overview.md
      performance_proven_video.md
      blueprint.md
      controlled_mutation.md
      retrieval.md
      reconstruction.md
    voice/
    reconstruction_timeline.json
    captions.srt
    remix.mp4
    render_report.json
    jianying_import_manifest.json

当日工作文件夹说明：

- `reference-YYYY-MM-DD.mp4`：用户提供的完整参考视频，作为整体顺序、节奏、时长、音频和拆解依据。若同一天有多个任务，可在日期后追加短标题或序号。
- `video_clips/`：自动拆解参考视频后得到的画面片段和参考帧，用作视觉顺序和素材匹配依据。
- `script.txt`：从参考视频、用户文案、口播稿或配音文件整理出的口播/字幕/配音文本；没有文案时可为空或不创建。
- `material/fragmentNN/`：Gate 3 汇总通过后由 Reconstruction 从 `assets/` 复制的已批准宽范围生产素材；候选素材和接触表留在匹配产物中，不得混入生产目录。
- `content_baseline.json`：Blueprint 产出的目标结构、卖点、禁用声明、口播意图和时长包络；Gate 2 批准后形成不可变版本。
- `mutation_plan.json`：Controlled Mutation 产出的允许/禁止变化、fallback 和失效规则；与 `content_baseline.json` 组成 Gate 2 原子批准包。
- `coverage_precheck.json`：Gate 2 前的非权威素材覆盖预判，只用于提前暴露明显缺口。
- `coverage_report.json`：Gate 2 通过后按当前内容基线重算的权威覆盖报告，供 Gate 3 使用。
- `fragment_plan.json`：Retrieval 在 Gate 3 形成的不可变素材批准计划，记录源素材、哈希、媒体类型、叠字决定、宽可用范围和由该范围确定的画面时长预算，不记录最终精确裁点；图片预算为 `null`。
- `script_evidence_matrix.json`：Gate 3 证据闭环的逐句口播、画面证据窗、动作完整性和 fallback 决定。
- `production_script_candidate.json`：证据闭环后由 Controlled Mutation 编译的待批准生产脚本。
- `approved_production_script.json`：Gate 4 生成前批准的唯一 TTS 文本和设置快照。
- `voice_preflight.json`：Gate 3 汇总通过后、Gate 4 生成前审核包生成前的配音时长预检；逐段记录画面预算、按字数/标点/音色历史语速估算的配音时长、margin 和阻塞状态。
- `material_manifest.json`：Reconstruction 对 Gate 3 批准宽范围的复制/导出记录和副本哈希。
- `match_validation_report.json`：Gate 3 选材确认前，对候选、评分、来源和宽范围的不可变校验快照。
- `material_validation_report.json`：Gate 3 汇总通过后，对实际复制/导出的生产素材、哈希和范围的校验；不得覆盖选材快照。
- `final_validation_report.json`：Gate 5 最终预览的路径、流、帧数、时间轴和硬门禁校验；不得复用前两个报告路径。
- `reconstruction_timeline.json`：Reconstruction 在 Gate 4 生成前通过、真实 TTS 实测后生成的字幕、累计时间轴和精确裁点；只能在 Gate 3 宽范围内收窄。
- `voice/`：按片段生成的配音、清理后人声、分段语音和拼接后的成品音频。
- `jianying_import_manifest.json`：V1 的剪映导入清单，记录素材、时段、配音和字幕；它不等同于可编辑草稿。
- `jianying_draft/`：V2 可选目录，用于可编辑剪映草稿、草稿检查报告和必要备份。V1 不创建；只有可靠草稿适配器和用户明确要求时才可新建。
- `stage_assessments/`：Track C 启用前 pilot 的五阶段人工评估快照，固定包含 `overview.md`、五个阶段文件和当前输入哈希；必须区分质量分/来源的 `not_scored|measured|retrospective_baseline|target`、审批状态的 `provisional|awaiting_user|approved|blocked|stale` 与效率状态的 `incomplete|measured`，不得用候选置信度或历史回溯分冒充当前实测。`provisional` 只表示已有完整数字但尚未完成当前 Gate 审核，不是 `not_scored` 的替代值。
- `stage_assessments/overview.md`：当前 pilot 的五阶段总评估入口；汇总各阶段状态、证据、风险、分数状态、效率状态和下一阶段准入。

关键来源规则：

- 完整参考视频是音频、整体顺序和总时长的依据。
- `video_clips/` 是视觉顺序和视觉匹配的依据。
- `material/fragmentNN/` 是审校通过后的生产素材来源。
- 使用生成配音时，以每段真实完成语音时长作为画面和字幕时长依据；真实时长写入 `voice/` 报告和 `reconstruction_timeline.json`，不回写参考事实层。
- `recipe.json` 是 Gate 1 后的参考视频事实层；V2 不因配音或渲染而原地改写它。V1 兼容指针若存在，必须作为派生字段单独校验，不能使 Gate 1 重新失效。
- `pipeline_state.json`、`recipe.json`、`shot_blueprint.json`、`content_baseline.json`、`mutation_plan.json`、`coverage_report.json`、`matches.json`、`fragment_plan.json`、`script_evidence_matrix.json`、`voice_preflight.json`、`approved_production_script.json` 和 `reconstruction_timeline.json` 是核心自动化流程的机器可读依据；审批唯一权威是 `pipeline_state.json`。
- V2 任务产物使用五字段 envelope：`artifact_type`、`schema_id`、`schema_version`、`contract_version`、`skill_version`。canonical registry 位于 `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`；历史 V1 文件保持原样，不批量回写。

## 流程

流程路径：

Performance-proven Video → Blueprint → Controlled Mutation → Retrieval → Reconstruction

1. 读取参考视频：在 `work/YYYY-MM-DD[-slug]/` 下创建当日工作文件夹，将用户提供的参考视频保存为 `reference-YYYY-MM-DD.mp4`。
2. Performance-proven Video：使用自动镜头切分和关键帧抽取拆解参考视频，片段和参考帧保存到 `video_clips/`，参考事实写入 `recipe.json`，完成 Gate 1。
3. Blueprint：根据参考结构、Brief 和覆盖预判生成 `shot_blueprint.json`、`content_baseline.json` 和可读稿，准备 Gate 2。
4. Controlled Mutation：生成 `mutation_plan.json`，记录保留、替换、改写、删并段请求和已批准 fallback；Gate 2 原子批准内容基线与变更包。Gate 3 证据闭环后再编译最终生产脚本候选，Gate 4 生成前才提升为批准脚本。
5. Retrieval：读取只读 `assets/`，完成覆盖分析、资格门禁、视觉匹配、全局排程和逐句证据校验。Gate 3 拆为选材确认与证据闭环两个子状态；汇总通过后才形成不可变宽范围 `fragment_plan.json`。
6. Reconstruction：复制/导出 Gate 3 批准宽范围到 `material/`，生成 `material_manifest.json`；先以 Gate 3 画面预算、候选文案和拟用语速生成 `voice_preflight.json`，通过后才生成 Gate 4 生成前审核包。Gate 4 生成前批准后调用 TTS，以实测时长再次校验预算并生成 `reconstruction_timeline.json` 和 SRT；先完成 Gate 4 生成后听审，再做代理/边界检查和正式成片，最后进入 Gate 5。

V1/V2 边界：已经开始的 V1 任务按创建时契约续跑，不自动取得 V2 Gate 授权。G-A 已通过，Track B 已合并主干；在 G-B 和监督运营试用通过前，普通 V2 production、共享生产缓存和一线发布仍关闭。新 V2 case 先完成 Stage 0 冻结输入，再通过隔离 `gb-pair` 逐 Gate 运行；配对不是普通发布，不进入 `final/`，也不能复用其他任务审批。旧任务迁移必须生成映射、输入哈希、失效 Gate 和重新确认清单，不能用旧批准替代新子状态。

## 输出

保存通用输出配置；单次特殊要求以用户当前指令和 skill 执行结果为准。

- 视频比例：9:16 竖屏。
- 分辨率：1080x1920。
- 帧率：60fps。
- 文件命名规则：`YYMMDD-platform-product-序号.mp4`，英文缩写优先，避免文件名过长或乱码。
- 默认审核方式：生成无字幕烧录的预览 MP4、独立 SRT、渲染报告和剪映导入清单；可编辑草稿需要专用适配器和用户明确要求。
- 默认归档方式：普通生产任务由用户确认 Gate 5 通过后，从 `work/` 迁移到 `final/`；`manual-contract-only` pilot 无论 Gate 5 结果如何都不得归档。
- V2 默认不覆盖已批准产物；宽范围 `fragment_plan.json`、`material_manifest.json` 和精确 `reconstruction_timeline.json` 分开保存，精确裁点不得原地改写 Gate 3 批准哈希。

## 验收

视频合格标准：

- 每个视觉片段都有可用素材；缺素材和低置信度片段必须明确暴露。
- 不用无关素材硬凑数量。
- 素材画面和产品、场景、动作、景别、角度、光线、产品可见度和构图基本匹配。
- 文件名和文件夹名只能作为线索，最终要看画面。
- 复制素材，不移动或破坏原始素材。
- 识别重复素材，不能把不同文件名当成不同内容。
- 三个连续镜头范围内尽量避免同一来源文件夹重复出现。
- 相邻片段避免明显重复的构图或语义场景。
- 有关联的 AI 片段或同一角色片段要保持身份连续。
- 成片视觉速度保持 `1.00x`，除非用户明确要求变速；短素材先扩展已批准的同源时段，仍不足时返回素材审核，不使用长尾帧冻结或变速硬拉；仅允许不超过 2 帧的舍入补齐。
- 成片比例、分辨率和帧率符合本文件的通用配置；时长和数量符合用户当前要求或本次任务设置。
- 成片时长和参考或本次目标时长的偏差应在可接受范围内，明显偏差要说明。
- 字幕必须在所属片段内，按语义断句，不机械凑字数。
- 如本次任务设置字幕字数上限，应把它当作上限，不是目标；避免 1-2 个字的孤立字幕。
- 字幕不遮挡产品主体、关键动作或重要信息。
- 如果使用配音，以真实成品配音时长为画面和字幕依据。
- Gate 5 产物生成后，`pipeline_state.json` 是当前状态唯一权威：输出哈希登记完成且 `gate5=awaiting_user` 后，才可向运营提交最终预览审核；用户确认前不得归档。
- Gate 3 必须同时通过 `gate3_material_selection` 和 `gate3_evidence_closure`；任一片段或动作组未决时，不得生成完整生产脚本或生产媒体。
- Gate 4 必须分为 `gate4_pre_generation` 和 `gate4_post_generation`。顺序固定为：Gate 3 画面预算 → `voice_preflight` → 生成前批准 → TTS → 实测时长校验 → 精确裁点/累计时间轴 → 生成后听审。预检或实测超预算都不得变速、冻结尾帧或越过 Gate 3 范围。
- Gate 5 正式渲染授权必须同时复核 `gate_status.gate1`、`gate_status.gate2`、Gate 3/4 子状态及汇总状态，并确认 `stages.reference_split.status` 与 `stages.content_blueprint.status` 均为 `approved`；渲染完成后必须将 `pipeline_state.json` 推进到 `final_review/awaiting_user` 并登记成片、校验报告和导入清单的 SHA-256，不能只生成文件而不回写状态。
- Gate 3 只能记录 `request_omit`/`request_merge`/`request_restructure`，不能直接批准删段；结构变化必须返回 Gate 2。
- 配音要检查开头、中间边界、最长停顿、最紧字幕边界和结尾。
- 如生成剪映草稿，必须是新建可编辑草稿，不能覆盖原生或加密缓存；只生成导入清单时，不得声称草稿已生成。
- 剪映草稿的内容 ID、元数据 ID 和根索引 ID 必须一致，批量草稿 ID 不能重复。
- 剪映草稿的素材路径必须存在，媒体源范围不能超过真实时长。
