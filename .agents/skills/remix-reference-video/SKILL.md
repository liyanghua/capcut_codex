---
name: remix-reference-video
description: Use when a project must turn a complete reference or viral video into a reviewable vertical remix from a reusable local asset library, including reference-video replication, shot replacement, material matching, new voiceover, sidecar subtitles, delivery validation, or a Jianying import package.
---

# 参考视频复刻成片

把完整参考视频转换为可审计、可续跑的复刻成片。参考视频决定整体结构和节奏；项目 Brief、已批准素材、配音与声明决定实际内容。

**铁律：赶时间不能绕过证据、验证或人工 Gate。**

## V2 运行边界

- 当前只允许一个 `manual-contract-only` V2 alpha pilot 按五阶段运行，用于采集 G-A 前向证据；它必须逐 Gate 停止。无论 Gate 5 结果如何，该 pilot 都不得归档到 `final/`、不得视为正式生产发布，也不得复用其批准。G-A 通过前，其他新生产任务继续使用稳定 V1 或等待迁移决定。
- 当前 Skill 版本与行为契约版本均为 `2.0.0-alpha.1`；任务产物格式版本为独立的 `1.0.0`。V2 任务产物必须携带 `artifact_type`、`schema_id`、`schema_version`、`contract_version` 和 `skill_version`，以 `schemas/v2-alpha.registry.schema.json` 为 canonical registry。
- Track B 执行器和 Track C 评分看板尚未启用。Track A 只提供 registry/envelope 静态检查，不提供完整字段 validator 或生产执行器。
- 生产后端固化设计和实施计划已经确认，但不改变上述锁定边界：`docs/superpowers/specs/2026-08-15-remix-production-backend-design.md` 与 `docs/superpowers/plans/2026-08-15-remix-production-backend.md` 只定义 G-A 通过后的 Track B 工作；G-A 前不得实现或启用真实五阶段生产运行时。
- G-A 前唯一新增的写工具是 WP-A2 Evidence Harness：它只为 owner 指定的 `manual-contract-only` clean pilot 生成 Gate 审核包、绑定结构化人工决定并做只读 G-A 审计；它不能执行五阶段媒体命令、启用缓存、归档、修改 manifest 或复用审批。
- 实验性的 Fast Path v0 只提供单任务 Gate-aware 编排、续跑/计时和素材技术预索引；它不启用 Track B 或 V2 production。仅对隔离 fixture/明确的新实验任务使用 `fast`、`resume`、`index-assets`；当前 `manual-contract-only` pilot 只允许只读 `status/audit`。运行契约见 `references/fast-path-v0.md`。
- 已开始的 V1 任务继续使用创建时契约，不自动取得 V2 授权。需要迁移时，先生成旧/新映射、输入哈希、失效 Gate 和重新确认清单。
- `recipe.json` 是 Gate 1 后不可变的参考事实层。V2 的真实配音时长只写入 `voice/` 报告和 `reconstruction_timeline.json`，不原地回写参考事实。
- `fragment_plan.json` 是 Gate 3 已批准的不可变宽范围契约，不是物化状态或最终渲染计划。若历史生成器留下与批准状态冲突的描述字段，不要原地修订已批准文件；以 `material_manifest.json` / `material_validation_report.json` 的当前输入哈希和校验结果为物化事实，并在阶段评估中记录元数据债务。
- Track A 静态护栏可用 `python3 .agents/skills/remix-reference-video/track_a_static_check.py` 运行；它检查 registry、共同 envelope、YAML 可解析性、触发夹具结构和安全字面量，不生成媒体、不修改任务状态。真实触发行为、完整产物字段和媒体校验必须单独报告，不能由此命令推定通过。
- Track C 启用前，`manual-contract-only` pilot 每完成一个业务阶段都要保存 `stage_assessments/` 下的人工阶段评估：`overview.md` 加上 `performance_proven_video.md`、`blueprint.md`、`controlled_mutation.md`、`retrieval.md`、`reconstruction.md`。每份至少写明 `framework_stage_id`、阶段/审批状态、当前输入哈希、逐项结果、未验证项、风险、效率证据和下一阶段准入。没有逐项计分时写 `stage_output_quality_score: not_scored` 与 `measurement_status: not_scored`；只有完整数字但尚未完成当前 Gate 审核时才可用 `approval_status: provisional`；没有阶段计时时写 `efficiency_measurement_status: incomplete`。不得用候选置信度、历史回溯分或目标分冒充当前实测分。跨 Gate 的阶段在等待时保存“进行中快照”，只有对应最终 Gate 通过后才改为完成评估。

## 启动与 Stage 0

1. 定位包含 `AGENTS.md`、`assets/`、`work/`、`final/` 的项目根目录，完整读取 `AGENTS.md`。
2. 完整读取 `references/project-layout.md` 和 `references/artifact-contracts.md`。
3. 把 `assets/project_brief.yaml` 复制到当次任务目录。只填写用户提供或已验证的事实，不编造卖点、受众、素材路径或配置。
4. 执行 **Stage 0 — Brief 完整性预检**：检查必填字段、参考视频、素材根目录、输出规格和本阶段所需工具。缺失时补问并暂停。

Stage 0 只是预检，不是 Gate，也不代表用户批准任何后续产物。不得复用旧案例的绝对路径、日期、片段数、时长、凭证或审批状态。

## V1 边界

V1 的交付包是：MP4、旁路 SRT、旧版 `validation_report.json`、`render_report.json` 和 `jianying_import_manifest.json`。V2 不复用旧报告路径，按阶段生成 `match_validation_report.json`、`material_validation_report.json` 和 `final_validation_report.json`。

`jianying_import_manifest.json` 只是人工导入剪映的轨道和素材清单，不是剪映草稿。V1 不创建 `jianying_draft/`，不生成、修改、逆向或覆盖剪映/CapCut 原生或加密缓存，也不得宣称已生成可编辑草稿。用户要求草稿时，说明边界并交付导入清单。

## 严格 Gate

- 只能在 Gate 产物已经生成、展示路径、输入哈希、阻塞项、低置信度项和实质变化后接受批准。
- 把每次决定写入 `pipeline_state.json`：`gate_id`、decision、timestamp、批准输入哈希和可选备注。
- 沉默、旧批准、预先豁免或“直接做”“不用等我审”“赶时间”“覆盖上次”“直接放 final”都不算后续 Gate 批准。
- 每个 Gate 后停止并等待；不得自批，不得把多个 Gate 合并为一次推定授权。
- 上游输入哈希变化后，把该 Gate 及全部下游状态改为 `stale`，重新展示并取得批准。
- 用户只批准部分内容时记录部分决定，并停留在当前 Gate。

| Gate | 必须展示 | 批准后才可执行 |
| --- | --- | --- |
| **Gate 1 — 镜头切分** | 参考流信息、`recipe.json`、镜头表、关键帧/接触表、可疑切点和例外 | 目标结构与声明规划 |
| **Gate 2 — 内容基线与受控变更** | `shot_blueprint.json`、`content_baseline.json`、`mutation_plan.json`、批准卖点、禁用声明、fallback、时长包络 | 权威素材覆盖与匹配 |
| **Gate 3 选材确认** | `matches.json`、候选接触表/微视频、拟选素材、分数、叠字、重复/连续性检查、缺素材、宽可用范围 | 形成不可变宽范围 `fragment_plan.json` |
| **Gate 3 证据闭环** | `script_evidence_matrix.json`，逐句口播与已批准画面证据、动作完整性和 fallback 决定 | 编译 `production_script_candidate.json`；两个子状态都通过前不得进入完整生产 |
| **Gate 4 生成前** | `production_script_candidate.json`、最终文案、协议/模型标签、音色、语速和发音风险 | 原子提升 `approved_production_script.json`，允许真实 TTS |
| **Gate 4 生成后** | 实际音频、实测时长、字幕、`reconstruction_timeline.json`、精确裁点和听审风险 | 代理/边界检查和最终渲染 |
| **Gate 5 — 最终预览** | MP4、SRT、`final_validation_report.json`、`render_report.json`、`jianying_import_manifest.json` 和未决风险 | 普通生产任务可把批准 MP4 归档到 `final/`；pilot 只保留 G-A 证据，不归档 |

Gate 3 只有 `gate3_material_selection` 和 `gate3_evidence_closure` 都对当前输入哈希为 `approved` 时，汇总状态才可为 `approved`。Gate 4 也包含两个必需决定：先批准最终生产脚本和声音设置，再调用真实 TTS；生成后按“实测时长 → 精确裁点/累计时间轴 → 听审实际音频”批准。任何子状态未齐全时保持 `awaiting_user`，不得以“文件已生成”代替人工批准。

Gate 4 生成前只能接受对当前审核包的明确业务确认，例如：`Gate 4 生成前通过，按当前文案和音色生成。` “开始实施”“直接做”“继续”或已有 Gate 3 批准均不构成该授权。

每次停在 Gate 时先给一线运营业务摘要，再给技术证据。固定顺序为：现在到哪一步、发现的业务影响、只需确认的事项、建议、可直接回复、未处理影响、证据路径。一次只请求当前 Gate 的决定，不把 JSON、哈希或 FFmpeg 日志当成正文。

## 总控流程

### 1. 初始化或续跑

- 按 `references/project-layout.md` 创建 `work/YYYY-MM-DD[-slug]/`；续跑时先读取 `pipeline_state.json` 并重算输入哈希。
- 复制完整参考视频，不修改来源。默认拒绝覆盖；只有对明确命名的本工具产物取得单独授权后，才可经 staging、备份、验证和回滚流程替换。

### 2. 切分参考片并完成 Gate 1

- 探测音视频流，自动切镜头，提取关键帧和参考音频，把客观事实写入 `recipe.json`。
- 展示镜头表、接触表、单帧噪声、可疑切点和人工修订建议；批准前不进入目标蓝图。

### 3. 规划内容并完成 Gate 2

- 从参考音频或用户文案整理 `script.txt`；参考片声明在项目证据支持前一律视为未批准。
- 按叙事功能生成 `shot_blueprint.json`，不盲目复制原声明、原画面或精确切点。
- 由 Blueprint 和 Controlled Mutation 分别生成 `content_baseline.json`、`mutation_plan.json`；Gate 2 原子批准二者的哈希、卖点证据要求、禁用声明、允许 fallback 和时长包络。
- 缺素材导致的删段、并段或重排只能记录为 `request_omit`、`request_merge` 或 `request_restructure` 并返回 Gate 2，不能在 Gate 3 原地批准结构变化。

### 4. 匹配素材并完成 Gate 3

完整读取 `references/material-matching.md`。看真实画面而不是只看文件名；记录 SHA-256 和感知重复；先过语义、动作、产品、场景、构图、裁切、叠字、身份连续和技术资格，再评分。

没有合格候选时保留 `missing_material`，不得拿无关素材凑数。Gate 3 只批准素材来源、哈希、叠字决定和足够宽的源时间范围；不可变 `fragment_plan.json` 不写最终精确裁点。两个 Gate 3 子状态汇总通过后，Reconstruction 才从 `assets/` **复制**批准宽范围到 `material/fragmentNN/`，并写 `material_manifest.json`，不得移动或破坏原文件。

逐句证据闭环必须把每句候选口播映射到已批准素材的证据帧/时间窗。无证据句子只能选择 Gate 2 已批准 fallback，或返回 Gate 2 改变声明/口播意图。

### 5. 生成配音并完成 Gate 4

完整读取 `references/voice-caption-timing.md`。只用批准文案和配置；不输出凭证，不把密钥写入清单。记录提供商、协议、模型标签、音色、参数、文件哈希和解码实测时长。

真实 TTS 的唯一文本输入是 Gate 4 生成前批准的 `approved_production_script.json`。用累计实测语音端点生成 `reconstruction_timeline.json` 和字幕，再在 Gate 3 批准的宽范围内确定精确裁点；不把配音强压回参考时长。画面默认保持 `1.00x`；字幕按语义断句，不越界、不重叠、不产生孤立短 cue。
- Gate 4 生成后听审通过前，不得运行正式渲染；只要精确裁点超出宽范围，就返回受影响的 Gate 3 子状态。

### 6. 渲染、验证并完成 Gate 5

完整读取 `references/rendering-qc.md`。只有 Gate 1/2 的 `gate_status` 和业务阶段汇总（`stages.reference_split`、`stages.content_blueprint`）、Gate 3 两个子状态、Gate 4 生成前/生成后均对当前输入哈希有效时，才从 `reconstruction_timeline.json`、`material_manifest.json`、`material/` 和批准音频渲染；不得绕过生产计划直接读取任意 `assets/` 文件。正式渲染完成后必须把 `remix.mp4`、`final_validation_report.json`、`render_report.json` 和 `jianying_import_manifest.json` 的 SHA-256 原子登记回 `pipeline_state.json`，推进到 `final_review=awaiting_user`/`gate5=awaiting_user`；文件生成成功不等于状态已更新或 Gate 5 已通过。

默认输出 9:16、1080×1920、60fps、H.264/yuv420p 和一条批准音轨。SRT 独立交付，不静默烧录或嵌入字幕流。使用 staging；媒体、JSON、SRT、路径、哈希、时长和时间轴全部通过后再原子提升，并从同一批准时间轴生成 `jianying_import_manifest.json`。

预览留在 `work/` 并保持审核状态。普通生产任务只有 Gate 5 批准后，才按项目命名规则把 MP4 复制或迁移到 `final/`；`manual-contract-only` pilot 即使 Gate 5 批准也永久留在 `work/`，只供 G-A 评估。其余证据和可编辑生产输入留在任务目录。

## 不可妥协的失败规则

- 缺素材或不合格素材：返回 Gate 3；若需要删并段或改变声明，记录请求并返回 Gate 2。占位仅在 Brief 明确允许的审核模式使用，绝不能进入 `final/`。
- 删并段、重排、改声明、删口播或重构时间轴：返回最早受影响 Gate，并使下游批准失效。
- 叠字、品牌、水印、产品可见度或裁切风险未决定：保持 review-required，不得声称 production-ready。
- 哈希不符、路径逃逸、源范围越界、时间轴 gap/overlap、报告过期或审批 stale：渲染或提升前失败。
- 失败时保留已验证上游产物，清理临时半成品，把阻塞原因和恢复命令写入 `pipeline_state.json`。

## Reference Map

- `references/project-layout.md`：目录、路径、权威顺序、续跑与归档。
- `references/artifact-contracts.md`：产物 schema、状态、审批、哈希和一致性。
- `references/material-matching.md`：建档、资格门禁、评分、去重、连续性和接触表。
- `references/voice-caption-timing.md`：配音文案、TTS、实测时长、字幕和听审。
- `references/rendering-qc.md`：渲染、原子提升、媒体/SRT 验证、导入清单和审片。
- `references/fast-path-v0.md`：实验执行器、素材预索引、命令、退出码、产物和生产锁边界。
- `schemas/v2-alpha.registry.schema.json`：Track A 的 V2 artifact identity、版本轴和共同 metadata envelope；完整字段 schema 延后到 Track B。
- `assets/project_brief.yaml`：复制使用的 Brief 模板；单次任务不得修改安装模板。
