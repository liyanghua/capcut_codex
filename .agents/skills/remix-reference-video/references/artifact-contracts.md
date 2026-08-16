# 产物契约

## 目录

- [通用规则](#通用规则)
- [`project_brief.yaml`](#project_briefyaml)
- [`stage_inputs/<stage>.json`](#stage_inputsstagejson)
- [`pipeline_state.json`](#pipeline_statejson)
- [`recipe.json`](#recipejson)
- [`shot_blueprint.json`](#shot_blueprintjson)
- [`asset_profiles.json`](#asset_profilesjson)
- [`matches.json`](#matchesjson)
- [`fragment_plan.json`](#fragment_planjson)
- [配音与渲染产物](#配音与渲染产物)
- [一致性规则](#一致性规则)

## 通用规则

- V2 任务产物的版本轴必须分开：`skill_version` 表示生成它的 Skill 包，`contract_version` 表示五阶段/Gate 行为契约，`schema_version` 表示该产物的 wire shape。当前 V2 alpha 的 canonical 值分别为 `2.0.0-alpha.1`、`2.0.0-alpha.1`、`1.0.0`；每个 JSON/YAML 还必须有 `artifact_type` 和 `schema_id`。非任务资源使用自己的版本字段（例如 `manifest_schema_version`、`fixture_schema_version`）。
- V1 历史文件保留现有 `schema_version: "1.0"` 和创建时契约，不回写、不批量升级；V1/V2 迁移以 `contract_version` 和审批映射判断，不能用短别名 `v1`/`v2`/`v2-contract-alpha.1` 代替 canonical 值。
- Track A 只检查 canonical registry 和共同 envelope；完整字段 schema、YAML 业务字段、路径、哈希、媒体和 stale 状态验证延后到 Track B。
- canonical registry：`.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`。
- 时间使用秒，字段名以 `_seconds` 结尾。
- 时间区间统一使用左闭右开 `[start, end)`；时长为 `end - start`。
- 帧数是视觉时间轴的最终真实单位。秒数转帧数后必须使用累计帧边界，避免逐段四舍五入造成 gap/overlap。
- 所有引用的媒体文件记录 `sha256`。图像或视频关键帧同时记录感知哈希。
- `shot_id` 只用于参考片原镜头；`fragment_id` 只用于重构后的目标片段。两者不要混用。
- `fragment_id` 格式为 `fragmentNN`，但片段数不固定。

## `stage_inputs/<stage>.json`

阶段交接文件是 Agent/运营决策到 adapter 的只读输入契约，不是 Gate 审批记录。审批唯一权威仍是 `pipeline_state.json`；交接文件不得推进 Gate、携带 `approval`/`approved`/`gate_status` 或审核包哈希。

最小结构：

```json
{
  "artifact_type": "stage_input",
  "schema_id": "urn:capcut:remix-reference-video:artifact:stage-input",
  "schema_version": "1.0.0",
  "contract_version": "2.0.0-alpha.1",
  "skill_version": "2.0.0-alpha.1",
  "stage_id": "compile-blueprint",
  "producer": {"kind": "agent", "id": "operator", "version": "1"},
  "created_at": "2026-08-16T10:00:00Z",
  "lifecycle_status": "awaiting_user",
  "input_hashes": {"recipe.json": "<sha256>"},
  "payload": {"target_fragments": []}
}
```

`stage_id` 必须与文件名 `<stage>.json` 和当前 adapter 节点一致；`input_hashes` 的键只能是任务目录内的相对普通文件路径，不能使用绝对路径、`..` 或 symlink，且每个 SHA-256 必须与当前文件内容一致。`lifecycle_status` 只允许 `draft`、`awaiting_user`、`stale`、`consumed`。上游产物哈希变化后交接文件只能标记为 `stale`，不能继续作为有效输入。`payload` 保存阶段业务决策，例如 Blueprint 的 `target_fragments`、Mutation 的 `fallback_ids`、Retrieval 的 `overlay_decisions` 或 Reconstruction 的生成设置；它不能替代 Gate 决定。Runner 在发现对应文件时会在 adapter 执行前进行同样的只读校验，`audit` 会扫描全部 `stage_inputs/*.json`。

## `project_brief.yaml`

人工意图的首要来源。最小必填内容：

- 参考视频路径和素材库路径；
- 产品名称、受众和平台；
- 已批准卖点与禁用声明；
- 输出画布、帧率和语言；
- 配音模式和审批策略。

缺少必填字段时不得自动填入产品声明。Skill 必须向用户补问并暂停。

## `pipeline_state.json`

用于续跑和阶段门禁，至少包含：

```json
{
  "artifact_type": "pipeline_state",
  "schema_id": "urn:capcut:remix-reference-video:artifact:pipeline-state",
  "schema_version": "1.0.0",
  "skill_version": "2.0.0-alpha.1",
  "contract_version": "2.0.0-alpha.1",
  "run_id": "uuid",
  "work_dir": "work/YYYY-MM-DD-slug",
  "current_stage": "gate3_material_selection",
  "stages": {
    "brief": {"status": "approved"},
    "reference_split": {"status": "approved"},
    "content_blueprint": {"status": "approved"},
    "material_matching": {"status": "awaiting_user"},
    "voice": {"status": "not_started"},
    "render": {"status": "not_started"},
    "final_review": {"status": "not_started"}
  },
  "gate_status": {
    "gate1": "approved",
    "gate2": "approved",
    "gate3_material_selection": "awaiting_user",
    "gate3_evidence_closure": "not_started",
    "gate3": "awaiting_user",
    "gate4_pre_generation": "not_started",
    "gate4_post_generation": "not_started",
    "gate4": "not_started",
    "gate5": "not_started"
  },
  "decisions": [],
  "blocking_reasons": [],
  "artifacts": {}
}
```

阶段状态只使用：

- `not_started`
- `running`
- `awaiting_user`
- `approved`
- `blocked`
- `stale`
- `failed`

V2 审批只写入 `decisions[]`，不再同时维护 `approvals[]`。历史 V1 的 `approvals[]` 是只读兼容字段；迁移时必须映射为 scoped `decisions[]`，V2 冲突时以 `decisions[]` 和当前输入哈希为唯一权威。每次决定记录 `gate_id`、`substate_id`、`scope_type`、`scope_ids`、`decision`、`timestamp`、`input_hashes` 和可选 `note`。上游输入哈希变化后，下游 `approved` 状态必须改为 `stale`。Gate 3 和 Gate 4 的汇总状态只有所有必需子状态都为 `approved` 时才可为 `approved`。

## `recipe.json`

`recipe.json` 保留参考视频的客观拆解结果，不因后续重构而改写原镜头。核心字段：

- `reference_video`：路径、SHA-256、分辨率、帧率、总时长和音视频流。
- `scene_detection`：算法、阈值、候选切点、分数和人工修订。
- `shots[]`：`shot_id`、开始/结束/时长、帧范围、片段路径、关键帧路径和审核状态。
- `audio.reference`：参考音轨和 ASR 产物。
- V2 不在 `recipe.json` 写入真实替换配音时长；`voice_manifest.json`、`duration_report.json` 和 `reconstruction_timeline.json` 是唯一权威。历史 V1 的 `audio.replacement_voice` 若存在，只能作为明确标记的派生兼容指针，不能参与 Gate 1 参考事实哈希。

## `shot_blueprint.json`

记录重构后的目标叙事。顶层包含 `target_video`、`fragments`、`matching_policy` 和 `claim_policy`。

`fragments[]` 至少包含：

- `fragment_id`、`source_shot_ids`；
- `target_start_seconds`、`target_end_seconds`、`target_duration_seconds`；
- `narrative_role`、`message`、`approved_claim_ids`；
- `action_tags`、`scene_tags`、`shot_size`、`composition`；
- `allowed_media_types`、`forbidden_semantics`；
- `voice_text`、`span_group_id`；
- `status` 和素材证据要求。

删除或合并目标片段后，必须重新计算所有目标时间和下游配音/字幕时间轴。

## `asset_profiles.json`

每个素材记录：

- 源路径、媒体类型、SHA-256 和感知哈希；
- 时长、帧率、分辨率、音轨和可裁切性；
- 采样关键帧及时间点；
- 颜色、亮度、对比度、构图、边缘密度等视觉描述；
- 产品、场景、动作、景别、角色、内嵌文字、品牌和水印标签；
- 处理失败时的可读错误，不得默默忽略。

## `matches.json`

保存全部候选，不只保存获选者。每个候选记录：

- `eligible` 及资格失败原因；
- 语义、动作、构图、颜色、亮度/对比度、技术可用性分项得分；
- `confidence`；
- 源文件和源时段；
- 连续动作组、来源去重组和相邻构图约束；
- `overlay_present` 与审核建议。

不兼容候选最高 `0.59`；低于 `0.60` 时片段状态为 `missing_material`。

## `fragment_plan.json`

V2 的 `fragment_plan.json` 只保存 Gate 3 批准的不可变宽范围，不是最终精确渲染计划。每段至少记录：

- `fragment_id`、`status`、`confidence`；
- `source_path`、`source_sha256`、`media_type`；
- `source_start_seconds`、`source_end_seconds`；
- `approved_broad_range`（起止秒或起止帧）；不得写入 TTS 后的最终精确裁点；
- `visual_duration_budget_seconds`：视频严格等于批准宽范围的 `end-start`，图片为 `null`；
- `overlay_present`、`overlay_decision`；
- `action_group_id`、`span_group_id`；
- 用户批准决定。

`fragment_plan.json` 的批准哈希一旦进入 `pipeline_state.json`，不得为了修正文案债务而原地修改。历史生成器若留下 `authority`、`production_material_copied` 等与当前运行态不一致的字段，必须在校验报告或迁移说明中暴露；物理复制/导出是否完成，以 `material_manifest.json` 和 `material_validation_report.json` 的当前哈希为准。该分离避免把“已批准宽范围”和“已经有生产副本”混成同一个状态，也避免下游误把宽范围当作精确裁点。

`missing_material` 段不得伪造 `output_path`。Gate 3 只能记录 `request_omit`、`request_merge` 或 `request_restructure`；结构决定必须返回 Gate 2。只有 Gate 2 新基线批准后，才可在新版本蓝图中出现 `omitted_by_user`。

## V2 变更与证据产物

- `content_baseline.json`：Blueprint 的目标结构、卖点、禁用声明、口播意图和时长包络。
- `mutation_plan.json`：Controlled Mutation 的允许/禁止变化、fallback、删并段请求和失效规则；与 `content_baseline.json` 组成 Gate 2 原子批准包。
- `coverage_precheck.json`：Gate 2 前的非权威覆盖预判；不能批准素材或进入生产。
- `coverage_report.json`：Gate 2 后按当前内容基线重算的权威覆盖报告。
- `script_evidence_matrix.json`：逐句口播与 Gate 3 批准素材证据窗、动作完整性、fallback 和闭环决定。
- `production_script_candidate.json`：证据闭环后由 Controlled Mutation 编译的待批准脚本。
- `approved_production_script.json`：Gate 4 生成前提升的唯一 TTS 文本和设置快照。
- `voice_preflight.json`：Gate 4 生成前审核包的强制输入；绑定当前 `production_script_candidate.json` 与 `fragment_plan.json` 哈希，逐段记录媒体类型、视频画面预算、配音估算、margin 和 `passed|blocked`。图片预算与 margin 为 `null`。
- `material_manifest.json`：Reconstruction 复制/导出 Gate 3 批准宽范围到 `material/` 的物理记录和副本哈希。
- `reconstruction_timeline.json`：TTS 实测后生成的字幕、累计时间轴和 Gate 3 宽范围内的精确裁点。
- `match_validation_report.json`：Gate 3 选材确认前的不可变候选校验快照。
- `material_validation_report.json`：Gate 3 汇总通过后对物理素材副本、哈希和范围的校验；不得覆盖匹配快照。
- `final_validation_report.json`：Gate 5 对最终预览的路径、流、帧数、时间轴和硬门禁校验。
- `stage_assessments/overview.md` 与五份 `<stage>.md`（`performance_proven_video`、`blueprint`、`controlled_mutation`、`retrieval`、`reconstruction`）：Track C 启用前仅供 `manual-contract-only` pilot 使用的人工阶段评估快照；记录 `framework_stage_id`、当前输入哈希、阶段/审批状态、已证实结果、未验证项、风险、效率证据和下一阶段准入，不是自动评分卡。缺少逐项 rubric 时必须同时写 `stage_output_quality_score: not_scored` 和 `measurement_status: not_scored`；`approval_status: provisional` 只用于已有完整数字但尚未完成当前 Gate 审核的结果，不能替代 `not_scored`；缺少阶段计时时写 `efficiency_measurement_status: incomplete`。不得从 `match_confidence`、历史回溯分或目标分换算当前阶段分。跨 Gate 阶段可以保存明确标注的进行中快照，但只有对应最终 Gate 通过后才能标记 `completed`。

## 配音与渲染产物

- `voice/voice_script.json`：由 `approved_production_script.json` 确定性生成的只读执行投影，记录片段/span、卖点来源、禁用声明审计及 `source_approved_script_sha256`；不得成为第二份文本权威，不得由人工独立锁定或改写。
- `voice/voice_manifest.json`：提供商、协议、模型标签、音色、语速、每段文件和哈希。不包含密钥。
- `voice/duration_report.json`：目标时长、实测时长和 `actual - target` 差值。
- `captions.srt`：按语义断句的旁路字幕。
- `render_report.json`：输入哈希、视频/音频流、时间轴、转场、占位、缺素材和验收状态。
- `jianying_import_manifest.json`：可供人工导入剪映的轨道、素材、时段、配音和字幕清单。它不是剪映草稿。

Gate 5 生成后的状态回写是交付契约的一部分：正式渲染适配器必须在输出文件原子提升后，将 `remix.mp4`、`final_validation_report.json`、`render_report.json` 和 `jianying_import_manifest.json` 的路径与 SHA-256 写入 `pipeline_state.json`，并把 `current_stage` 推进为 `final_review`、`stages.render.status` 与 `stages.final_review.status` 设为 `awaiting_user`、`gate_status.gate5` 设为 `awaiting_user`。回写失败时必须删除本轮新产物并恢复旧状态；不得以文件存在代替状态登记。

## 一致性规则

- `recipe.json`、`shot_blueprint.json`、`content_baseline.json`、`mutation_plan.json`、`matches.json`、`fragment_plan.json` 和 `script_evidence_matrix.json` 的片段映射必须可追溯。
- 蓝图、匹配计划、配音和字幕中的 `fragment_id` 顺序必须一致，除非用户确认删段并已重编。
- 实际配音存在时，渲染时间轴必须以实测配音时长为准。
- `reconstruction_timeline.json` 只能引用 `fragment_plan.json` 的哈希并在批准宽范围内收窄；不得覆盖或原地改写 `fragment_plan.json`。
- `material_manifest.json` 的副本 SHA 必须与批准源 SHA 和实际文件一致；物理复制失败可重试，不改变 Gate 3 决定。
- TTS 只能消费 `approved_production_script.json`；Gate 4 生成前未批准时不得生成真实生产音频。
- Gate 4 生成前审核包必须绑定当前且 `passed` 的 `voice_preflight.json`；批准的 TTS 语速必须与预检语速一致。预检 `blocked` 时不得生成真实 TTS。
- 任何保存报告的输入哈希与当前文件不一致时，报告状态必须为 `stale`。
- 生产状态不允许 `missing_material`、未审批卖点、未处理叠字或未审批配音。
