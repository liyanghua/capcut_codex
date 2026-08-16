# 项目目录与路径规范

## 适用范围

本文定义「参考视频到可审核成片」每次任务的稳定目录、真实数据来源和归档规则。新任务不得复制旧案例中的日期、固定片段数或时长。

## 根目录

```text
AGENTS.md
assets/
docs/
work/
final/
.agents/skills/remix-reference-video/
```

- `assets/`：可复用素材库。只读取和复制，不移动、重命名或改写源素材。
- `docs/`：团队级 SOP 和运营文档。
- `work/`：未完成或待审核项目。
- `final/`：仅保存用户明确确认通过的成片。
- `.agents/skills/remix-reference-video/`：项目内可版本化的 Skill 源文档和后续工具。
- `.agents/skills/remix-reference-video/schemas/v2-alpha.registry.schema.json`：V2 alpha 任务产物 identity、三版本轴和共同 metadata envelope 的 canonical registry；它不是完整字段 validator。

## 单次任务目录

```text
work/YYYY-MM-DD[-slug]/
  project_brief.yaml
  pipeline_state.json
  reference-YYYY-MM-DD.mp4
  recipe.json
  shot_blueprint.json
  content_baseline.json
  mutation_plan.json
  asset_profiles.json
  coverage_precheck.json
  coverage_report.json
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
  stage_assessments/
    overview.md
    performance_proven_video.md
    blueprint.md
    controlled_mutation.md
    retrieval.md
    reconstruction.md
  review_contact_sheet.jpg
  video_clips/
    shots/
    keyframes/
    transcript_raw.json
    reference_contact_sheet.jpg
  script.txt
  material/
    fragment01/
    fragment02/
  voice/
    reference-audio.m4a
    voice_script.json
    voice_script.txt
    fragments/
    final_voice.mp3
    voice_manifest.json
    duration_report.json
    voice_qa_report.json
  reconstruction_timeline.json
  captions.srt
  remix.mp4
  render_report.json
  jianying_import_manifest.json
```

`slug` 使用简短英文或数字；同日多任务必须添加 `slug` 或序号。新流程不再另建 `replace_YYYYMMDD/`，拆解、匹配、配音和渲染产物统一放在同一任务目录。

## 真实数据来源

按以下优先级解决冲突：

1. `project_brief.yaml`：用户目标、已批准卖点、禁用声明和输出配置。
2. `recipe.json`：参考片镜头和参考音频事实，不承载 V2 替换配音时间轴。
3. `shot_blueprint.json`、`content_baseline.json`：重构后的目标片段、叙事和内容基线。
4. `mutation_plan.json`：允许/禁止变化、fallback 和失效规则。
5. `matches.json`、`coverage_report.json`：全部候选、资格门禁、覆盖和评分证据。
6. `fragment_plan.json`：Gate 3 批准的不可变素材来源、哈希、媒体类型、宽可用范围和画面时长预算。
7. `script_evidence_matrix.json`：逐句口播与已批准画面证据的闭环结果。
8. `production_script_candidate.json`：Gate 3 后编译的 TTS 候选文案。
9. `voice_preflight.json`：候选文案相对 Gate 3 画面预算的生成前估算、margin 和阻塞结果。
10. `approved_production_script.json`：预检通过后由 Gate 4 生成前批准的唯一 TTS 输入。
11. `material_manifest.json`、`material/fragmentNN/`：Reconstruction 对批准宽范围的物理复制及副本。
12. `reconstruction_timeline.json`：真实配音实测并再次通过范围校验后的精确时间轴和裁点。
13. `pipeline_state.json`：阶段状态、用户审批、阻塞原因和产物哈希；审批唯一权威。

三份校验报告按阶段分开且不可互相覆盖：`match_validation_report.json` 固化 Gate 3 选材输入，`material_validation_report.json` 校验 Gate 3 后的物理素材副本，`final_validation_report.json` 校验 Gate 5 成片。Gate 5 输出完成后，成片与三份 Gate 5 交付产物（`remix.mp4`、`final_validation_report.json`、`render_report.json`、`jianying_import_manifest.json`）的 SHA-256 必须回写 `pipeline_state.json.artifacts`，否则仍属于未登记的阶段产物。

保存的报告如果哈希与当前输入不一致，必须视为过期，不能继续作为通过证据。

V2 新建任务的 JSON/YAML 顶层必须包含 `artifact_type`、`schema_id`、`schema_version`、`contract_version` 和 `skill_version`；历史 V1 任务保持原有格式，只读续跑或显式迁移，不批量回写。

## 路径与覆盖规则

- JSON 中的项目路径优先相对于声明它的 JSON 文件，并必须能解析为存在的文件。
- 正式渲染不得越过 `material/` 直接读取 `assets/`。
- `fragment_plan.json` 是宽范围批准，不是最终精确裁点；精确裁点只能写入 `reconstruction_timeline.json`。
- `recipe.json` Gate 1 通过后只保存参考事实；V2 不因 TTS 或渲染原地回写。
- 复制素材时保留源路径、SHA-256、感知哈希和源时段。
- 已有产物默认不覆盖。重新生成前必须明确使用 `--force`，并先将本工具的旧产物归档到任务目录内。
- 不得修改用户提供的参考片、原始文案和 `assets/` 中的源素材。

## 续跑与归档

- 续跑时先读取 `pipeline_state.json`，重新计算当前输入哈希。
- 某阶段输入改变时，该阶段及下游审批全部失效，上游有效产物可保留。
- Gate 3 必须同时通过 `gate3_material_selection` 和 `gate3_evidence_closure`；Gate 4 必须同时通过 `gate4_pre_generation` 和 `gate4_post_generation`。
- Gate 5 正式渲染前还必须复核 `gate_status.gate1`、`gate_status.gate2` 以及 `stages.reference_split.status`、`stages.content_blueprint.status` 均为 `approved`；不得只依赖被手工编辑的 Gate 映射。
- 普通生产任务由用户确认最终预览后，才能把正式成片复制或迁移到 `final/`。`manual-contract-only` pilot 无论 Gate 5 是否通过都不得进入 `final/`。
- V1 只生成 `jianying_import_manifest.json`。没有真实、可编辑且通过验证的草稿时，不得声称已生成剪映草稿。
