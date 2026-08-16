# 参考视频复刻可重复生产后端设计

> 状态：已完成业务设计确认，等待书面规格复核  
> 日期：2026-08-15  
> 适用版本：`2.0.0-alpha.1` 设计基线  
> 前置门槛：G-A 通过前不得实现或启用 Track B 真实生产

## 1. 背景与决策

`work/2026-08-15-tablemat-ga-replacement-pilot/` 已生成并通过 Gate 5 的 27.936 秒成片，证明五阶段方法能够在人工编排下得到可接受结果。但该任务仍有三个阻塞生产化的问题：

1. Gate 3 范围扩展的批准时间晚于其绑定的 Gate 4 生成前批准，审批链不可审计；
2. 真实任务缺少 `execution_mode`、单调 `state_revision` 和事件序列，Fast Path 只读审计失败；
3. 任务根目录存在 22 个一次性 `.mjs/.py` 脚本，成功路径不能被其他任务稳定复用。

本设计把这条人工成功路径转化为可重复、可审计、可缓存、可测量的生产后端。它不改变既有治理顺序：`track_b` 继续保持 `locked_until_g_a`。本轮可以完成设计、计划、接口和测试夹具准备，但只有一个审批顺序干净的 G-A pilot 由 owner 明确判定通过后，才能开始 Track B 实现或启用真实生产。

## 2. 目标与非目标

### 2.1 目标

- 以一个统一 CLI 和一个 Gate-aware orchestrator 执行五阶段生产；
- 将每个生产步骤定义为具有明确输入、输出、Gate 前置、缓存键和失败恢复点的确定性命令；
- 以 `pipeline_state.json` 作为唯一审批和当前状态权威；
- 通过单调事件、输入哈希和结构化审批形成完整审计链；
- 通过共享素材索引、阶段缓存和依赖图只重算受影响节点；
- 记录机器、API、运营操作、人工等待和返工时间，支持 G-B 配对验收；
- 提供只读 FastAPI/SSE 投影，为后续 Backlot 式运营界面提供稳定接口。

### 2.2 非目标

- 不在 G-A 通过前修改 Skill manifest 的 Track B 锁定状态；
- 不把现有替代 pilot 或其审批作为 golden fixture；
- 不复用 pilot 的人工批准；
- 不把任务目录中的一次性脚本直接复制到 Skill；
- 不在本阶段建设 Backlot 前端；
- 不在本阶段建设 Track C 完整评分产品；
- 不减少或合并 Gate 1–5 的人工审核责任；
- 不支持覆盖历史 V1 产物或自动迁移在制任务。

## 3. 总体架构

```text
reference video + brief + read-only assets
                    |
                    v
          remixctl unified CLI
 init / run / resume / status / audit / approve-gate
                    |
                    v
          Gate-aware Orchestrator
                    |
        +-----------+-----------+
        |                       |
        v                       v
 Five-stage command adapters   Shared asset index
        |                       |
        +-----------+-----------+
                    v
       staging -> validate -> promote
                    |
                    v
             Artifact Store
                    |
        +-----------+-----------+
        |                       |
        v                       v
 pipeline_state.json   events.jsonl / metrics.jsonl
        |
        v
 FastAPI ProgressView + SSE revision notice
```

### 3.1 单一执行器

Fast Path v0 已有的 runner、storage、asset index、contracts 和 CLI 是唯一演进底座，不新增平行执行器。Track B 在这些模块上增加真实阶段适配器、审批事务、完整产物校验和 API 读取层。

### 3.2 单一状态权威

`pipeline_state.json` 只保存当前权威快照。`pipeline_events.jsonl` 用于审计和崩溃恢复，`stage_metrics.jsonl` 用于性能测量；后两者不能反向覆盖审批状态。FastAPI 和未来前端只投影权威快照，不维护第二套状态机。

### 3.3 生产产物提升

所有生产命令必须先输出到任务内 staging 路径。只有 shape、schema、输入哈希、路径和媒体校验全部通过，才能原子提升到 canonical artifact 路径并登记状态。失败的 staging 产物不得成为下游输入。

## 4. 组件边界

### 4.1 CLI

CLI 负责参数解析、退出码、锁获取和调用应用服务，不包含阶段业务逻辑。稳定入口为：

```text
remixctl init
remixctl run
remixctl resume
remixctl stage
remixctl status
remixctl audit
remixctl approve-gate
remixctl index-assets
```

`run` 执行到下一人工 Gate 即停止；`resume` 从最后有效状态继续；`stage` 只允许运行当前 Gate 授权的单一节点；`status/audit` 只读；`approve-gate` 是唯一审批写入口。

### 4.2 Orchestrator

Orchestrator 负责：

- 根据显式 DAG 选择下一可执行节点；
- 校验 Gate 前置、当前 revision 和输入状态；
- 生成缓存键并决定执行或 cache hit；
- 为每次执行创建独立 attempt；
- 调用阶段适配器；
- 校验并提升产物；
- 原子更新状态并追加事件和指标；
- 在上游变化时按依赖图传播 `stale`。

Orchestrator 不负责理解视频内容，也不能生成或修改人工决定。

### 4.3 Stage Adapter

每个 adapter 暴露统一接口：

```python
class StageAdapter(Protocol):
    command_id: str
    implementation_version: str

    def required_inputs(self, context) -> list[ArtifactRef]: ...
    def required_gates(self, context) -> list[GateRequirement]: ...
    def declared_outputs(self, context) -> list[ArtifactDeclaration]: ...
    def cache_fingerprint(self, context) -> dict: ...
    def execute(self, context, staging_dir) -> StageResult: ...
```

adapter 只产生声明的输出，不能直接写 `pipeline_state.json`，不能审批 Gate，不能读取未登记的任意 `assets/` 路径。

#### 阶段交接契约 `stage_inputs/<stage>.json`

Agent/运营提交给 adapter 的业务输入统一落在任务目录的 `stage_inputs/` 下。文件使用 V2 五字段 envelope，并额外要求 `stage_id`、`producer`、可信 `created_at`、`lifecycle_status`、任务内相对路径到 SHA-256 的 `input_hashes` 和对象型 `payload`。`stage_id` 必须与文件名和 adapter 节点一致；每个输入路径拒绝绝对路径、`..`、symlink 和越界，哈希必须在执行前重算并匹配。生命周期只允许 `draft|awaiting_user|stale|consumed`。

该文件是只读交接，不是审批权威：禁止携带 `approval`、`approved`、`gate_status`、审核包哈希等字段，不能推进或伪造 Gate。上游产物哈希变化时交接失效；runner 在 adapter 执行前校验，`audit` 扫描并报告错误。Gate 决定、`state_revision` 和审批输入哈希仍只能由 `ApprovalService` 写入 `pipeline_state.json`。

### 4.4 Artifact Validator

Validator 按 registry 解析 artifact 类型并执行：

- envelope 和完整字段 shape 校验；
- artifact 间输入哈希和版本兼容校验；
- 路径 allowlist、逃逸和 symlink 检查；
- 媒体流、帧率、时长、范围和时间轴校验；
- Gate 3 宽范围与最终精确裁点包含关系校验；
- Gate 5 输出 bundle 一致性校验。

Validator 只返回结构化结果，不推进状态。

### 4.5 Approval Service

`approve-gate` 调用 Approval Service，并在同一任务锁内完成：

```text
读取当前 state_revision
-> 重算 review package hash
-> 校验 Gate 前置与子状态
-> 校验决定时间和适用范围
-> 写入 scoped decision
-> 推进 Gate 状态
-> 标记下一允许节点
-> 原子替换 pipeline_state.json
-> 追加 approval event
```

任一校验失败则不写入任何部分状态。Approval Service 不接受沉默、旧批准、跨任务批准或不绑定当前审核包的自然语言指令。

### 4.6 Asset Index

素材索引分成两层：

- 共享技术层：内容哈希、感知重复、媒体流、时长、分辨率、帧率、抽帧位置和探测错误；
- 任务语义层：镜头业务标签、动作、场景、产品可见度、构图、叠字和声明证据。

共享层按内容和实现版本缓存，路径只作为定位信息。任务语义层随 Blueprint 和匹配策略变化，不污染共享事实。

### 4.7 Read-only API

FastAPI 首版只提供任务列表、任务快照、artifact 元数据/预览和 SSE revision 通知。它不接受 Gate 决定，也不直接读取未登记文件。浏览器收到 revision 后重新获取 `ProgressView`，不在前端重放事件构造状态。

## 5. 权威状态与事件契约

### 5.1 `pipeline_state.json`

最小新增结构：

```json
{
  "execution_mode": "track-b-production",
  "run_id": "uuid",
  "state_revision": 18,
  "active_stage": "retrieval",
  "active_command": "match-assets",
  "stage_status": {},
  "gate_status": {},
  "decisions": [],
  "artifacts": {},
  "blockers": [],
  "cache_summary": {}
}
```

工作状态固定为：

```text
not_started / running / succeeded / blocked / failed / stale
```

Gate 状态固定为：

```text
not_ready / awaiting_user / approved / rejected / blocked / stale
```

`succeeded` 只表示机器产物完成，不能自动变成 `approved`。状态事务每次成功写入必须使 `state_revision` 严格递增。

### 5.2 事件

每条事件至少包含：

```text
run_id
sequence
state_revision_before
state_revision_after
event_type
stage_id / command_id / gate_id
attempt_id
occurred_at
payload_summary
```

sequence 在单任务内严格单调。恢复时若事件与 state 之间存在 gap，系统只允许执行 reconciliation，不继续生产。

### 5.3 指标

每个 attempt 结束后写入：

```text
machine_seconds
api_seconds
operator_touch_seconds
human_wait_seconds
rework_seconds
cache_status
retry_count
failure_category
started_at / completed_at
```

机器无法自动获知的人工时间保持 `unknown`，不得写为 `0`。端到端报告将机器关键路径和人工等待分别显示。

### 5.4 提交顺序与崩溃恢复

文件系统无法把 canonical artifact、JSON state 和 JSONL append 合并成一个原生事务，因此每次写操作使用带 `transaction_id` 的可恢复提交协议：

```text
取得任务锁
-> 校验 expected state_revision
-> 在 staging 生成并校验全部输出
-> 写 .transactions/<transaction_id>.json，状态为 prepared
-> 把产物提升到不可变版本路径
-> 原子替换 pipeline_state.json，并递增 revision
-> 以 transaction_id 幂等追加事件
-> 写 attempt metrics
-> 把 transaction 记录原子标记为 committed
-> 释放任务锁
```

canonical artifact 引用指向不可变版本；事务完成前不覆盖旧有效文件。`reconcile` 在任何生产命令前扫描未完成事务，并按以下唯一规则处理：

- state 仍为 `state_revision_before`：新版本产物未取得权威引用，将其标为 orphan 并回滚 prepared transaction；
- state 已为 `state_revision_after`、事件缺失：从 transaction 记录补写同一 `transaction_id` 的事件；
- state 和事件均已提交、metrics 缺失：补写 `measurement_status=partial` 的指标记录，不改变审批状态；
- state revision 与 transaction 的 before/after 均不一致：标记任务 `blocked`，等待人工审计，不继续执行；
- 同一 `transaction_id` 的事件或指标已存在：幂等跳过，不重复计数。

`pipeline_state.json` 始终是恢复后的当前权威；transaction 记录只用于证明和补齐提交过程，不能创造新的人工批准。

## 6. Gate 与审核包

### 6.1 审批绑定

每个决定必须绑定：

- `gate_id` 和可选 `substate_id`；
- 当前 review package hash；
- 适用 artifact IDs 和各自 SHA-256；
- 当前 `state_revision`；
- decision、timestamp、actor 和 note；
- 用户明确批准的策略项。

审批时间由 Approval Service 的可信服务器时钟生成，调用方不能自行提交时间戳。审批时间不得早于审核包生成时间，不得晚于输入被替换的时间。上游输入变化后，原决定只能保留为历史事件，不能继续授权生产。

Gate 子状态和汇总规则固定如下：

| Gate | 必需子状态 | 汇总为 `approved` 的条件 |
| --- | --- | --- |
| Gate 1 | `gate1` | 当前参考事实审核包获批 |
| Gate 2 | `gate2` | `content_baseline + mutation_plan` 当前原子包获批 |
| Gate 3 | `gate3_material_selection`、`gate3_evidence_closure` | 两者均对当前输入获批；任一 `blocked/stale` 时汇总不得获批 |
| Gate 4 | `gate4_pre_generation`、`gate4_post_generation` | 两者均对当前输入获批；生成前批准必须先于 TTS |
| Gate 5 | `gate5` | 当前输出 bundle 获批 |

Gate 4 生成前批准是特殊事务：Approval Service 在同一个 prepared transaction 中把 `production_script_candidate.json`、TTS provider/model/voice/参数和决定哈希提升为不可变 `approved_production_script.json`，再推进 `gate4_pre_generation=approved`。两者不能部分成功，TTS 只能读取该批准版。

### 6.2 叠字策略前置

Gate 3 选材审核包必须为每个候选明确记录：

```text
retain_source_text
crop
cover
replace
no_action
```

审核包展示开头三秒、主体区域、上下文字区、声明卡、保障条款和 CTA 的代表帧或代理视频。叠字、源水印或字幕策略未决时，Gate 3 选材不能批准。

### 6.3 Gate 返回

- 缺素材但结构不变：停留 Gate 3；
- 需要删并段、重排或改变声明：返回 Gate 2；
- 精确裁点越过宽范围：受影响的 Gate 3 子状态 `stale`；
- TTS 参数或文案变化：Gate 4 生成前及下游 `stale`；
- 仅渲染样式变化：保留 TTS 和时间轴，只使代理/渲染/Gate 5 `stale`。

### 6.4 决策失效矩阵

| 变化 | 必须 stale 的 Gate | 必须 stale 的机器产物 | 可保留内容 |
| --- | --- | --- | --- |
| 参考视频或切点修订变化 | Gate 1–5 | 全部下游 | 无关共享素材技术索引 |
| Brief、目标结构、声明或 Gate 2 fallback 变化 | Gate 2–5 | baseline、mutation 下游全部产物 | 参考事实、共享索引 |
| 候选素材、宽范围、叠字/水印策略变化 | `gate3_material_selection`、`gate3_evidence_closure`、Gate 3 汇总、Gate 4–5 | 当前 Gate 3 审核包、证据矩阵、脚本、代理和渲染链 | 参考事实、Gate 2 包、无关素材索引；未变 TTS 只能作为历史产物，不具执行资格 |
| 仅证据窗或 fallback 选择变化 | `gate3_evidence_closure`、Gate 3 汇总、Gate 4–5 | 证据矩阵、生产脚本及下游 | 已批准素材宽范围 |
| 候选生产脚本或 TTS 设置变化 | `gate4_pre_generation`、`gate4_post_generation`、Gate 4 汇总、Gate 5 | 批准脚本、TTS、时间轴、字幕、代理、渲染 | Gate 3 两个批准 |
| TTS 二进制输出变化 | `gate4_post_generation`、Gate 4 汇总、Gate 5 | 时间轴、字幕、代理、渲染 | Gate 4 生成前批准、Gate 3 宽范围 |
| 仅精确裁点变化且仍在宽范围内 | `gate4_post_generation`、Gate 4 汇总、Gate 5 | 时间轴、字幕代理、渲染 | Gate 3 和 Gate 4 生成前批准 |
| 仅渲染参数或视觉 overlay 实现变化，业务策略不变 | Gate 5 | 代理、边界报告、正式渲染 | Gate 1–4、TTS、时间轴 |

`stale` 传播时可以保留旧文件作为历史版本，但必须移除其 current/eligible 引用；缓存命中不能恢复已经失效的人工授权。

## 7. 缓存与增量失效

### 7.1 缓存键

节点缓存键由规范化内容构成：

```text
command_id
+ command schema version
+ implementation hash
+ normalized input artifact hashes
+ applicable approved decision hashes
+ relevant configuration
+ external provider/model/protocol identity
```

路径、mtime、任务名和未参与行为的备注不得单独决定缓存命中。

### 7.2 缓存复用边界

- 缓存只复用机器结果，不复用人工批准；
- cache hit 仍需校验当前 artifact 和 Gate 前置；
- 外部模型、协议或参数变化必须改变缓存键；
- 失败、半成品和未提升 staging 输出不得进入缓存；
- 共享缓存可删除并重建，不能是唯一事实来源。

### 7.3 典型失效传播

```text
叠字策略变化
-> stale: gate3_material_selection, Gate 3 summary, Gate 4-5 execution eligibility, review package, proxy, render
-> preserve current: reference split, Blueprint, asset technical index
-> preserve history only: old TTS file, which cannot authorize or feed a new render until affected Gates are reapproved
```

```text
Gate 2 baseline/fallback 变化
-> stale: Gate 2-5 and every derived machine artifact
-> preserve: reference facts and shared technical index
```

```text
Gate 3 evidence fallback selection 变化（Gate 2 已授权该 fallback）
-> stale: gate3_evidence_closure, Gate 3 summary, Gate 4-5, script, TTS, timeline, captions, render
-> preserve: approved broad material ranges
```

```text
素材文件内容变化
-> stale: asset profile, affected matches, fragment plan, evidence rows, material copy, downstream timeline/render
-> preserve: unrelated asset index entries and reference facts
```

素材内容变化还必须使受影响的 `gate3_material_selection`、`gate3_evidence_closure`、Gate 3 汇总、Gate 4 和 Gate 5 当前批准失效；未受影响素材的 Gate 3 决定可以保留，但只有在汇总重新满足当前输入哈希后才能继续生产。

## 8. 五阶段可执行 DAG

下表是规范性执行顺序。`approve-gate` 不参与机器缓存；它只绑定当前审核包并原子推进决定。素材技术索引可与参考片拆解并行，Gate 3 汇总通过后的素材物化可与生产脚本编译支路并行；其他依赖不得重排。

| 顺序 | 工作包 / 命令 | 精确输入 | 输出 | Gate 前置 / 下一停止点 |
| ---: | --- | --- | --- | --- |
| 0 | B0 `init` | reference、Brief、assets root、输出配置 | 初始 state、Stage 0 报告 | Stage 0 阻塞则停止 |
| 1a | B1 `split-reference analyze/export` | reference hash、探测/切镜参数、切点修订 | `recipe.json`、clips、接触表、Gate 1 包 | 等待 `gate1` |
| 1b | B4a `index-assets` | assets snapshot、probe/index 实现版本 | 共享技术索引 | 无 Gate，可与 1a 并行 |
| 2a | B4 `build-coverage --scope precheck` | Gate 1 事实、Brief、蓝图草案、共享索引 | `coverage_precheck.json` | 只供规划，不可批准 |
| 2b | B2 `compile-blueprint` | Gate 1 事实、Brief、precheck | `shot_blueprint.json`、`content_baseline.json` 草案 | Gate 1 approved |
| 2c | B3 `compile-mutation-plan` | reference facts、baseline 草案、Brief | `mutation_plan.json` 草案 | Gate 1 approved |
| 2d | B2/B3 `lint-gate2-package` | baseline、mutation、字速/时长参数 | Gate 2 review package | 等待 `gate2` 原子批准 |
| 3a | B4 `build-coverage --scope authoritative` | 当前 Gate 2 bundle、共享索引 | `coverage_report.json` | Gate 2 approved |
| 3b | B4 `match-assets` | Gate 2 bundle、权威 coverage、索引、匹配策略 | `matches.json`、候选代理 | Gate 2 approved |
| 3c | B4 `build-material-selection-package` | matches、候选代理、叠字策略、宽范围 | Gate 3 选材包、候选 `fragment_plan` | 等待 `gate3_material_selection` |
| 3d | B4 `freeze-fragment-plan` | 当前选材包、选材决定 | 不可变 `fragment_plan.json` | 选材子状态 approved |
| 3e | B4 `validate-script-evidence` | Gate 2 bundle、approved fragment plan | `script_evidence_matrix.json`、证据审核包 | 等待 `gate3_evidence_closure` |
| 3f | B0 `summarize-gate3` | 两个当前子状态 | Gate 3 汇总 | 两者均 approved 才继续 |
| 4a | B3 `build-production-script` | baseline、mutation、approved evidence matrix | `production_script_candidate.json` | Gate 3 approved |
| 4b | B5 `materialize-approved-broad` | approved fragment plan、源素材 | `material/`、`material_manifest.json` | Gate 3 approved，可与 4a 并行 |
| 4c | B5 `voice-preflight` | production script candidate、Gate 3 fragment plan、字速/标点/音色历史语速 | `voice_preflight.json` | 预检失败则不生成 Gate 4 包、不调用 TTS |
| 4d | B3/B5 `build-gate4-pre-package` | script candidate、`voice_preflight.json`、material status、TTS 设置 | Gate 4 生成前审核包 | 等待 `gate4_pre_generation` |
| 4e | B3 `promote-production-script` | candidate、TTS 设置、当前决定、预检哈希 | 不可变 `approved_production_script.json` | 与生成前批准同一事务；语速必须与预检一致 |
| 4f | B5 `generate-voice` | approved production script | voice、manifest、实测时长 | Gate 4 pre approved 且预检通过 |
| 4g | B5 `build-reconstruction-timeline` | voice 实测、fragment plan、material manifest、fps | timeline、SRT、精确裁点 | 先复核视频预算；越界则返回受影响 Gate 3/4 |
| 4h | B5 `build-gate4-post-package` | voice、timeline、SRT、听审代理 | Gate 4 生成后审核包 | 等待 `gate4_post_generation` |
| 4i | B0 `summarize-gate4` | 两个当前子状态 | Gate 4 汇总 | 两者均 approved 才继续 |
| 5a | B5 `render-proxy` | approved timeline、material、voice | 代理视频、边界片 | Gate 4 approved |
| 5b | B5 `validate-proxy-boundaries` | proxy、timeline、边界规则 | 代理/边界校验报告 | 未通过则阻塞正式渲染 |
| 5c | B5 `render-final` | 已批准输入、通过的代理报告 | MP4、SRT、render/validation/import reports | 只生成 Gate 5 包，不自批 |
| 5d | B5 `build-gate5-package` | 当前 output bundle | Gate 5 审核包 | 等待 `gate5` |
| 6 | B5 `archive-approved` | Gate 5 decision、当前 bundle | `final/` 归档记录 | 只适用于普通生产任务，pilot 禁止 |

每个命令都有独立 adapter、输入/输出声明、缓存键和纵向测试。禁止在 `work/<task>/` 生成执行源码。

### 8.1 TTS 重试和幂等

- 正常响应目标仍为 `<=45 秒`；人工等待不计入机器 SLA；
- provider 请求使用由 approved script hash、voice settings hash 和 attempt family 生成的 idempotency key；
- 单次 provider 调用超时默认 60 秒，最多 3 次 attempt；仅网络超时、连接失败、429 和明确 5xx 可重试；
- 429 尊重 `Retry-After`，单次等待上限 60 秒；其他重试采用 2 秒、4 秒退避；
- 参数错误、鉴权错误、内容拒绝和解码校验失败不盲目重试；
- 超时、限流和 provider 故障单独标记为外部异常，不伪装成满足 13/8 分钟 SLA；
- 只有解码和媒体校验通过的完整音频可以提升并进入缓存。

### 8.2 代理规格

Track B entry 在 G-A 通过后由 owner 固定任务级代理配置。默认效率方案为 `540x960/30fps`；只有细字、声明卡或边界检查无法可靠判断时使用 `720x1280/30fps`。配置进入缓存键和审核包，不得在一次运行中静默变化。

## 9. 异常与恢复

| 异常 | 系统行为 | 保留内容 | 运营动作 |
| --- | --- | --- | --- |
| 缺素材 | `blocked` 在 Gate 3 | 参考事实、Blueprint、已有候选 | 补素材或返回 Gate 2 |
| 叠字未决 | Gate 3 保持 `awaiting_user` | 候选和预览 | 选择处理策略 |
| TTS API 失败 | 当前 attempt 失败，可重试 | Gate 4 生成前批准 | 重试，不重复审批 |
| 范围不足 | 受影响 Gate 3 `stale` | 无关片段和批准 | 审核扩展范围 |
| 媒体校验失败 | 不提升输出，不生成 Gate 5 包 | 所有有效上游 | 查看校验原因后重试 |
| 进程崩溃 | reconciliation 后恢复 | state、events、有效 artifacts | `resume` |
| revision 冲突 | 拒绝写入 | 当前权威状态 | 刷新状态后重试 |
| 外部模型变化 | cache miss 并记录新 identity | 历史 attempt | 按当前 Gate 继续 |

失败信息必须包含：发生了什么、影响哪些产物、最早返回 Gate、可否自动重试和下一命令。

## 10. 测试与验收

### 10.1 B0 契约测试

必须覆盖：

- 原子 JSON 替换和 JSONL append；
- 并发锁和 stale revision 拒绝；
- 单调 state revision 和事件 sequence；
- review package hash 绑定和审批时间顺序；
- Gate 子状态完整性；
- DAG 选择和 Gate 停止；
- 缓存命中、实现 hash 变化和部分失效；
- task root、symlink、路径逃逸和媒体 allowlist；
- 崩溃前后 reconciliation；
- 完整 artifact shape validator。

### 10.2 五阶段纵向测试

隔离 fixture 必须覆盖：

1. 正常流程逐 Gate 停止直到 Gate 5；
2. 缺素材停在 Gate 3；
3. Gate 2 baseline/fallback 变化使 Gate 2–5 和全部派生产物 stale，但保留参考事实和共享技术索引；
4. Gate 3 已授权 fallback 选择变化只使证据闭环、Gate 3 汇总、Gate 4–5 和脚本下游 stale，并保留批准宽范围；
5. 叠字改变使 `gate3_material_selection`、Gate 3 汇总和下游批准 stale，但保留参考事实、Gate 2 包、共享索引和未改变的历史 TTS 文件；
6. TTS 失败后重试且不重复 Gate 4 生成前批准；
7. 素材宽范围扩展后必须重新绑定两个 Gate 3 子状态和 Gate 4；
8. 渲染失败不生成 Gate 5 审核包；
9. 第二次相同输入报告 cache hit；
10. 在事务提交各边界模拟崩溃并验证 reconciliation；
11. 任务目录中不存在生成的执行源码。

fixture 使用合成或专用测试媒体，不复制现有 pilot 的人工批准或业务状态。

### 10.3 G-B 冻结案例

G-A 通过且 Track B 完成后，使用同一冻结输入执行 V1/V2 配对：

- 冷启动机器/API 关键路径 `<=13 分钟`；
- 热缓存机器/API 关键路径 `<=8 分钟`；
- 五阶段质量分均不低于主优化方案各自的 V2 最低验收线，视频总分 `>=88`（`91` 为目标值）；
- 无 Gate 越权、审批复用、范围越界和未登记生产输入；
- 分开报告机器/API、运营操作、人工等待和返工时间；
- 受控增量变更的 `rework_seconds` 和 `gate_return_count` 不高于配对 V1；
- 生成可重复的 `phase6_score_snapshot.json`。

配对控制固定为：V1/V2 使用相同参考片、Brief、素材快照和 TTS 设置；两次运行的业务选择必须等价，但每个运行都要重新生成并绑定自己的审核包、哈希和批准记录，绝不复用另一运行的 approval record。冷启动分别使用隔离且初始为空的缓存根；热缓存从同一预建快照克隆两个隔离缓存根，并对同一片段执行同样的受控视觉变更；人工 Gate 等待排除在 13/8 分钟机器/API 关键路径之外；任一运行不得读取另一运行产生的缓存。若 V1 缺少可比机器数据，先补采集，不得把无法比较判为通过。

只有 G-B 通过后才允许提升为 `2.0.0-rc.1` 和运营陪跑。单次 Gate 5 通过不能代替 G-B。

## 11. 实施顺序与治理

```text
当前：Track A / G-A not_passed
  |
  +-- 允许：设计、实施计划、隔离测试夹具、WP-A2 G-A Evidence Harness
  +-- 禁止：真实 Track B 生产、普通 V2 发布、pilot 归档
  |
WP-A2: prepare-review -> record-decision -> audit-ga
  |
干净 G-A 由 owner 通过
  v
B0 状态/审批/执行器
  v
B1 reference split + B4a shared technical index
  v
B2 Blueprint + B3 Mutation
  v
B4 Retrieval / Gate 3
  v
B5 Reconstruction / Gate 4-5
  v
G-B frozen paired validation
  v
2.0.0-rc.1 + supervised operations trial
```

FastAPI/SSE 的读取契约随 B0 实现，但 Backlot 前端等待 G-B 后再建设。Track C 完整评分和成熟度看板仍等待 G-B 通过。

### 11.1 WP-A2 的临时边界

WP-A2 是解决 G-A 证据循环的临时 Track A 工具，只提供：

```text
ga-prepare-review
ga-record-decision
ga-audit
```

它要求任务为 `manual-contract-only`，所有 artifact 必须是任务内已存在的普通文件，review package 必须先生成，批准时间由工具可信时钟生成。它不执行 stage adapter、不创建媒体/缓存、不归档、不修改 manifest、不跨任务复用决定，也不能把结构删并请求记录为 Gate 3 批准。G-A 通过后，WP-A2 只保留为历史 pilot 审计兼容入口；普通生产统一使用 B0 Approval Service。

## 12. 文档同步范围

书面规格确认后，实施计划和项目文档必须同步：

- `docs/reference-video-remix-optimization-plan.md`：更新替代 pilot 结论、Track B 固化路径、依赖图和当前锁定状态；
- `docs/reference-video-remix-backend-first-technical-design.md`：以本规格为确认基线，补齐统一命令、adapter、审批事务、缓存和恢复；
- `AGENTS.md`：记录 G-A 已通过、真实 cold/hot 配对状态、G-B 待复核和下一阶段允许/禁止事项；
- `.agents/skills/remix-reference-video/manifest.json`：本轮保持不变，继续 `track_b=locked_until_g_a`；
- pilot 目录：不修改任何 artifact、Gate 决定或审批时间。

## 13. 完成定义

本设计阶段完成需同时满足：

- 设计文档通过独立规格审查并由用户确认；
- 实施计划列出准确文件、测试、命令、预期结果和提交边界；
- 主方案、后端技术设计和 `AGENTS.md` 对 G-A、Track B 和一线开放条件表述一致；
- manifest 和 pilot 保持未修改；
- 文档不得宣称 Track B、G-B、一小时 SLA 或一线发布已经通过。
