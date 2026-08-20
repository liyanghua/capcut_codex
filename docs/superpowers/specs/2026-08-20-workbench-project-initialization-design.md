# 工作台项目初始化与 Stage 0 设计

## 1. 文档状态

- 状态：设计稿，待评审
- 日期：2026-08-20
- 适用范围：`remix-reference-video` 新 V2 任务的本地项目初始化
- 关联规范：`AGENTS.md`、`README.md`、`2026-08-15-remix-production-backend-design.md`、`2026-08-18-business-video-workbench-design.md`

本文解决“必须向 Codex 粘贴一大段启动提示词”的使用问题：运营人员在本机工作台填写参考视频、自有素材目录和产品 Brief，Skill 接收结构化输入后执行 Stage 0，再进入现有 Gate 1–5 工作流。

本文不改变 `pipeline_state.json` 的审批权威、Gate 合同、普通 V2 production lock、`gb-pair` 隔离边界或现有 run 审核页。

## 2. 目标与非目标

### 2.1 目标

1. 用户可以在工作台创建新项目，不需要记忆 Skill 启动提示词。
2. 参考片和素材目录支持 macOS 原生选择器，并保留手动绝对路径输入。
3. 表单内容先保存为可修改草稿；Stage 0 只做输入检查、素材画像和冻结草案准备，不生成媒体。
4. 用户能在冻结前看懂输入事实、素材异常和声明边界，并显式确认 Brief。
5. 确认后生成独立冻结快照，进入隔离 `gb-pair` cold 的 Gate 1，不复用任何旧 run 审批、脚本、缓存或成片。
6. 输入路径、状态变更、失败原因和恢复动作可审计、可重试。

### 2.2 非目标

- 不在浏览器中上传或复制整个素材目录。
- 不在 Stage 0 调用 TTS、FFmpeg 派生媒体/正式渲染、生成字幕或运行 Gate 1；复制参考视频作为冻结输入不是派生媒体。
- 不修改已冻结任务的产品身份、参考片、素材根、平台、受众或输出规格；这些变化新建任务。
- 不把 `initialization_draft.json` 或 `stage0_report.json` 当作审批权威。
- 不建设开放式 Agent 对话、完整剪辑器或跨项目模板继承。

## 3. 入口与信息架构

新增工作台入口：

- `/workbench`：项目列表，显示草稿、Stage 0 阻断、Stage 0 待确认、等待 Gate 1、审核中、运行中和已完成项目。
- `/workbench/projects/new`：新建项目初始化页。
- `/workbench/projects/{project_id}/stage0`：Stage 0 结果与 Brief 确认页。
- `/workbench/runs/{run_id}`：保持现有五阶段审核工作台，不改变已有路径或决策接口。

初始化页按三组组织：

1. **参考片与自有素材**：参考视频、自有素材目录、路径状态、扫描数量。
2. **项目目标**：产品名称、任务名称、目标平台、受众。
3. **允许与限制**：允许卖点、禁止/待确认声明、输出规格、音色和语速。

底部提供：

- `保存草稿`：只保存初始化草稿，不创建任务目录、run 或审批。
- `开始 Stage 0 预检`：提交草稿，执行服务端预检。

Stage 0 结果页提供：

- 输入事实摘要和修改入口。
- 参考片流信息、素材数量与媒体类型分布。
- 异常文件、叠字/水印风险、不可读素材、重复提示。
- Brief 草案、允许卖点、禁止声明和输出设置。
- `返回修改` 与 `确认 Brief 并冻结`。

## 4. 本地路径选择

### 4.1 选择器策略

工作台运行在 `127.0.0.1` 时，点击选择按钮调用本机服务的原生 macOS 选择器：

- 参考视频：单文件选择，只接受视频扩展名并在服务端再次验证媒体流。
- 自有素材：目录选择，服务端只接收目录路径并扫描目录内容。

浏览器标准 `<input type=file>` 只能作为兼容兜底显示文件名/目录文件数，不能作为冻结输入来源，因为无法可靠提供本机绝对路径。正式路径来源必须是本地服务返回的绝对路径。

### 4.2 手动路径备用

- 允许粘贴绝对路径，失焦或提交时执行同一套服务端校验。
- 拒绝相对路径、symlink、不可读路径、目录逃逸和不支持扩展名。
- 服务端返回结构化状态：`valid`、`missing`、`not_readable`、`unsupported`、`symlink`、`scan_error`。
- 页面展示路径 basename、校验结果和必要错误，不默认枚举用户磁盘其他目录。

### 4.3 安全边界

- 原生选择器接口以实际连接 peer 的 loopback 地址判定；远程请求返回 `403`，不能仅依赖服务监听地址。
- picker 只接受固定服务端操作类型 `reference_video|asset_directory`，不接受客户端命令、脚本、路径过滤表达式或任意执行参数；写请求还需同源会话 nonce，防止本机其他网页诱导弹出选择窗口。
- 不上传用户文件，不把路径发送到外部服务。
- Stage 0 成功时只复制参考视频到新任务目录；原始素材保留在用户指定目录，生产阶段仍按批准范围复制到 `material/`。

## 5. Stage 0 数据模型

### 5.1 初始化草稿

每个项目的稳定容器固定为 `workbench/projects/<project_id>/`。草稿从不写入 `work/`，避免半成品被误解为可运行任务。`initialization_draft.json` 保存在该稳定容器，字段包括：

```json
{
  "artifact_type": "project_initialization_draft",
  "schema_id": "urn:capcut:remix-reference-video:artifact:project-initialization-draft",
  "schema_version": "1.0.0",
  "contract_version": "2.0.0-alpha.1",
  "skill_version": "2.0.0-alpha.1",
  "reference_path": "/absolute/reference.mp4",
  "asset_root": "/absolute/source",
  "product_name": "透明桌垫",
  "task_name": "tablemat-summer-01",
  "platform": "抖音",
  "audience": "精致白领",
  "approved_claims": ["极简透明", "防水防油"],
  "forbidden_claims": [],
  "output": {"aspect_ratio": "9:16", "width": 1080, "height": 1920, "fps": 60},
  "voice": {"provider": "doubao", "speaker": "", "speed": 1.0},
  "created_by": "local-operator",
  "draft_revision": 1
}
```

草稿可修改；卖点去重；“无”转换为空数组，不作为一条禁用声明。

freeze 将每个规范化后的卖点文本转换为对象 `{claim_id, text}`。先对文本执行 Unicode NFC、首尾空白清理和内部连续空白折叠；规范化后重复文本拒绝为同一 claim。`claim_id` 为 `claim-` 加该规范化 UTF-8 文本 SHA-256 的前 16 位小写十六进制，按规范化文本字典序稳定排序。该规则保证同一草稿跨重试 byte-identical，且 `BlueprintAdapter`、Gate 1 handoff 和下游只读取该对象列表，绝不以表单下标生成 ID。

### 5.2 Stage 0 产物

服务在项目私有 staging 目录生成预检产物；原子提升后，冻结输入位于新建且尚不可运行的 `work/YYYY-MM-DD-<task-name>/frozen-input/`：

```text
workbench/projects/<project_id>/initialization_draft.json
workbench/projects/<project_id>/stage0_report.json
work/YYYY-MM-DD-<task-name>/frozen-input/project_brief.json
work/YYYY-MM-DD-<task-name>/frozen-input/project_brief.yaml
work/YYYY-MM-DD-<task-name>/frozen-input/asset_profiles.json
work/YYYY-MM-DD-<task-name>/frozen-input/reference-YYYY-MM-DD.mp4
```

`stage0_report.json` 记录：输入哈希、检查项、素材扫描摘要、异常/风险、缺失字段、建议动作和报告状态。报告不能携带 Gate approval 字段。

#### 技术画像与业务素材证据

Stage 0 的 `asset_profiles.json` 仅写可验证的技术事实：相对路径、哈希、媒体类型、尺寸、时长、帧率、可读性、重复线索和可检测叠字风险。它不得从文件名、图像像素或参考片文字推断 `product_type`、`semantic_tags`、`action_tags`、`scores`、卖点或动作完成度。

新项目可以带技术画像启动 Gate 1；这不表示素材足够通过 Gate 3。没有人工或可信视觉证据来源的业务字段必须显式为 `unknown`/`not_evidenced`，并在 Gate 3 以 `missing_material` 或 `manual_classification_required` 阻断。运营可在 Gate 3 为候选补充可审查的产品、场景、动作、叠字和来源证据；该注释是独立、哈希绑定 artifact，不回写 Stage 0 技术事实。没有合格证据时不得凑数或放行。

该 artifact 定义为 `material_evidence_annotations`：每一条注释绑定 `asset_id`、Stage 0 技术画像 `sha256`、相对源路径、人工/受信任视觉来源、产品类型、语义/动作标签、叠字决定、可审查证据帧或时间窗和可选评分依据。它必须注册 schema/registry/validator，并作为 `matches.json`/Gate 3 package 的输入哈希。检索层只将技术画像与当前 hash 匹配的注释合成为业务候选；缺少注释的素材产生确定性 `manual_classification_required`，不进入评分或自动选择。素材注释变化使 Gate 3 及下游 stale。`material_evidence_requirements` 同样是注册、严格校验且 `production_state_authority=false` 的 V2 artifact；它只表达当前缺口和可候选素材，不携带审批字段。

补证据不是新人工 Gate，而是 Gate 2 通过后、权威 coverage/match 之前的可操作准备状态：

1. `build-material-evidence-requirements` 读取 Gate 2 baseline、技术画像和当前注释，生成非权威 `material_evidence_requirements.json`，列出每个目标片段缺少的产品/语义/动作/叠字证据与可候选素材。
2. 若存在缺口，runner 写 `active_stage=collect-material-evidence` 和 blocker，但仍生成工作台可读的准备包；工作台在“素材与证据”阶段展示缩略图、所需字段和证据窗编辑，不要求或伪造 Gate 3 approval package。
3. `POST /api/v1/runs/{run_id}/material-evidence` 只允许当前 owner/operator 对当前 requirements hash 和 profile hash 提交结构化注释；它不是 Gate decision，不能携带 approval 字段。服务原子写 `material_evidence_annotations.json`、审计 actor/request/idempotency，并使 requirements 重新计算。
4. 注释补齐后通过既有 durable resume 机制从 `build-material-evidence-requirements` 重跑，随后才执行 `build-coverage-authoritative → match-assets → build-material-selection-package` 并进入正常 Gate 3 选材审批。
5. 无注释停在可操作状态，注释不完整继续显示缺口；注释 source/hash 过期时拒绝并重新计算 requirements。不会因缺证据在 Gate 3 页面出现前形成不可恢复死锁。

runner 对此使用专用的 recoverable pause，而不是把节点记为永久 `blocked`/`failed`：requirements 文件成功落盘后，当前节点保持可重跑，`pipeline_state.json` 记录 `active_stage=collect-material-evidence`、唯一可替换的 `manual_classification_required` blocker 和 `submit_material_evidence` next action。提交服务在同一 invocation lock 下校验 owner、requirements/profile hash、幂等键和当前状态，原子写注释与审计，清除该 blocker，将 requirements 及下游置回 `not_started` 并调用现有 runner `resume=True`。若仍有缺口则生成新 requirements hash 后再次暂停；只有无缺口时才继续生成权威 coverage、matches 和真正的 Gate 3 package。

`project_brief.json` 是运行时和快照哈希的唯一 canonical Brief；`project_brief.yaml` 是同内容的人工查看副本。两个文件都须在冻结时由同一 canonical JSON 序列化生成，YAML 不参与运行时读取或哈希绑定。

`project_initialization_draft` 和 `stage0_report` 是 V2 非权威 artifact：实施必须为二者新增严格 schema、registry `artifact_type` enum/`oneOf`/`x-artifacts` 登记和 validator 校验，登记 `production_state_authority=false`。二者均不得携带 Gate approval 字段。

### 5.3 冻结快照和 pair 目录

用户明确确认后，在 `frozen-input/` 中原子生成：

```text
g_b_frozen_input_snapshot.json
```

快照绑定参考片、Brief、素材画像和素材源哈希，并写入新任务的单一 capability marker：

```json
"creative_contract_version": "creative_contract_v1"
```

该 marker 只由 Stage 0 冻结服务写入；`gb-pair` 只验证，不补写或覆盖。

冻结输入不是 Track-B run：它不得包含 `pipeline_state.json`、`run_id`、`pair_role`、`production_runtime_config.json`、Gate package 或 run registry 条目。项目容器结构固定为：

```text
work/YYYY-MM-DD-<task-name>/
  frozen-input/             # Stage 0 唯一冻结来源，永不携带审批
  cold/                     # gb-pair 从 frozen-input 创建，runner 初始化 pipeline_state
  hot/                      # cold Gate 5 后按既有规则创建/运行
  gb_measurement.json       # 两侧完成后生成
```

freeze 只将项目推进到 `frozen_waiting_gate1`。用户点击“启动 Gate 1”后，项目服务调用既有 `gb-pair`，以 `frozen-input/`、`cold/`、`hot/` 为显式参数。该命令创建 cold 后运行到首个 Gate 停止；只有 cold runner 完成初始化，才会生成其 `pipeline_state.json`、`pair_role="cold"` runtime config，并向仓库根 `RunRegistry` 显式登记。服务随后跳转 `/workbench/runs/{cold_run_id}`。绝不向 frozen-input 注册伪 run。

## 6. 状态机与接口边界

项目状态：

```text
draft
→ stage0_running
→ stage0_awaiting_confirmation
→ frozen_waiting_gate1
→ cold_running_or_awaiting_review
→ hot_running_or_awaiting_review
→ completed | blocked | stale
```

建议新增本地 API：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/workbench` | 项目列表 |
| `POST` | `/api/v1/projects/drafts` | 创建/保存草稿 |
| `POST` | `/api/v1/projects/path-picker` | 调用原生选择器，返回路径摘要 |
| `POST` | `/api/v1/projects/{id}/stage0` | 执行 Stage 0 预检 |
| `GET` | `/api/v1/projects/{id}/stage0` | 读取 Stage 0 报告与草案 |
| `POST` | `/api/v1/projects/{id}/freeze` | 确认 Brief，生成冻结输入快照 |
| `POST` | `/api/v1/projects/{id}/start-cold` | 调用隔离 gb-pair 创建并运行 cold 至 Gate 1 |

接口约束：

- 所有写操作需要本机 actor、请求 ID 和幂等键；`freeze` 与 `start-cold` 还须携带当前 `draft_revision`/Stage 0 报告哈希，双击返回同一个项目状态而不重复创建目录。
- Stage 0 失败不得生成 `g_b_frozen_input_snapshot.json`、`pipeline_state.json` 或任何 Gate decision。
- freeze 只允许从 `stage0_awaiting_confirmation` 进入，且必须重新校验输入哈希，防止预检后源文件变化。
- freeze 成功后只显示“启动 Gate 1”；普通 V2 production 仍锁定，只能通过隔离 `gb-pair`。`start-cold` 成功后才跳转 cold run 的 Gate 1 包。
- 服务端 runtime resolver 只从工作区受信任配置解析 Doubao client、Python executable 和环境凭证引用；初始化表单不能提供脚本路径、密钥或凭证。配置缺失时返回 `runtime_unavailable`，不创建 cold/hot 目录或 runtime config，也不向页面回显密钥。
- 本机同源会话 nonce 在首次 `GET /workbench` 或项目页时由服务签发：HttpOnly + SameSite=Strict cookie 保存 nonce ID，页面 `<meta>` 保存一次性 nonce 值；每个 picker 或项目写请求同时校验 peer loopback、Host/Origin、cookie ID、nonce 值、TTL 和未使用状态。缺少、跨源、不同端口或重放请求分别返回结构化 `403`/`422`。
- 成功的 nonce 保护请求必须在响应中返回下一枚 nonce；客户端仅在收到成功响应后原子替换 `<meta>`/内存 token。路径验证、保存草稿、Stage 0、freeze 和 start-cold 可在同一页面连续执行；旧 token 重放仍被拒绝。

## 7. 失败恢复与并发

- 任务名冲突：拒绝覆盖，用户修改任务名或打开已有项目。
- 路径/媒体/必填字段失败：保留草稿和报告，允许编辑后重试。
- 素材扫描中断：标记 `scan_error`，不把部分画像当作完整快照。
- freeze 过程失败：staging 保留诊断，目标项目不进入可运行状态；重试使用新的请求 ID 和同一草稿版本。
- 预检后参考片或素材变化：freeze 重新计算哈希并返回 `input_changed`，要求重新 Stage 0。
- 同一草稿并发提交：按 `draft_revision` 乐观锁拒绝旧请求。
- 已冻结任务发生身份变化：只能新建项目，不能通过 ChangeService 原地改写。
- Stage 0 任务以服务端 job 运行，页面可轮询其 `stage0_running` 状态；取消仅在扫描尚未原子提升前有效，取消后保留草稿、清理 staging，并生成 `cancelled` 报告事件。
- 每次写入在项目容器记录不可变 audit event：actor、request ID、idempotency key、输入 revision/hash、动作、时间和结果。项目任务名通过受锁原子目录提升保留，两个项目不能占用同一 `work/YYYY-MM-DD-<task-name>/`；重复 freeze/start-cold 返回先前成功结果，取消/失败不得遗留可被 `gb-pair` 使用的半成品。

### 7.1 素材目录快照

首版支持无 symlink 的递归素材目录。为此要升级冻结快照及其验证器，使 `asset_snapshot` 的 key 为严格相对 POSIX 路径，而不是现有“直接子文件名”限制：

- key 不得为空、绝对、包含 `.`/`..` 段或反斜杠；解析后必须位于 `asset_root` 内。
- 每个路径组件和最终文件均不得是 symlink；扫描到 symlink 时作为 Stage 0 阻断项。
- `asset_profiles.source_path` 使用同一相对 POSIX 路径；运行时、`validate_frozen_input()` 和 `RunRegistry` 用同一 containment helper 解析及校验哈希。
- 为已冻结历史输入保留 legacy 顶层文件验证；只有新 Stage 0 project snapshot 使用 `asset_snapshot_contract_version="relative_path_v1"`。

这样常见的图片/视频子目录可以作为自有素材根使用，同时不放宽路径逃逸或 symlink 风险。

## 8. 与现有 Skill 的衔接

初始化服务只负责把 UI 事实转换为 Skill 既有输入。冻结后：

1. `validate_frozen_input()` 校验 frozen-input 快照和素材哈希。
2. `gb-pair` 将 frozen-input 复制成独立 cold/hot 任务；cold 按 Gate 1–5 停止等待审批。
3. cold Gate 5 完成后，按既有规则复制声明的技术 cache，再运行 hot 侧和测量。
4. cold/hot 初始化后显式登记到仓库根 registry；现有审核工作台继续读取其 `pipeline_state.json`、Gate review package 和 canonical artifacts。

初始化页不得直接调用 adapter、写 Gate 状态或跳过审核。

### 8.1 Gate 1 到 Blueprint 的通用交接

Stage 0 不生成 `target_fragments`、分镜、动作、叙事角色或 fallback；这些都不是表单事实，不能由初始化服务编造。新 creative run 的交接由 Gate 1 之后的生产节点完成：

1. `build-decomposition-candidates` 只读取冻结参考片与 Brief 的非声明身份字段，输出版本化 `decomposition_id` 候选和镜头事实。
2. Gate 1 package 绑定候选集、策略 ID/版本和 `decomposition_bundle.json` 哈希，但不预绑定候选第一项。审批决定使用现有 `selected_decomposition_id`，并由 Approval Service 校验它属于当前 bundle；审核人只批准“如何拆解参考片”，不批准产品声明。
3. `materialize-approved-decomposition` 的唯一输入为当前 Gate 1 decision record、当前 bundle、冻结 Brief 和策略注册表；输出是 hash-bound `stage_inputs/compile-blueprint.json` 与 `stage_inputs/compile-mutation-plan.json`。前者包含 `target_fragments[]`、`required_actions[]`、`narrative_role`、镜头范围、`selected_decomposition_id`、策略 ID/版本和 bundle 哈希；后者初始 `fallback_ids=[]`。该节点不得新增 claim 或推断素材事实。
4. 节点将 decision、bundle、Brief、策略与两个 handoff 的哈希写入 stage input metadata。Gate 1 decision/bundle/Brief/策略变化必须使 handoff、Gate 2 和所有下游失效；ChangeService stale closure 和 StageInputValidator 必须注册此节点与这两个 handoff。
5. DAG 中 `materialize-approved-decomposition` 必须在 Gate 1 批准后执行，`build-coverage-precheck` 依赖它；`compile-blueprint` 只读取该节点生成的当前 hash-bound handoff。缺少候选、策略、决策或受控字段时，Gate 1 保持阻断，不能退回使用 `prepare_tablemat_case()` 的硬编码桌垫 fragments。

这项交接是现有 creative DAG 的必要补全，实施时应以失败测试先行，并作为项目初始化后的首个 cold 运行节点，而不是 Stage 0 的副作用。

## 9. 验收标准

1. 用户可通过页面完成新项目创建，不需要粘贴启动提示词。
2. 原生选择器和手动绝对路径都能进入同一服务端校验路径。
3. Stage 0 前无媒体、TTS、Gate package 或审批写入。
4. Stage 0 结果能展示 Brief、素材数量、类型、异常和风险。
5. 只有明确 freeze 后才有 frozen-input 快照；只有启动 cold 后才有 pipeline state、run registry 条目和 Gate 1 包。
6. 新 run 不继承历史审批、脚本、素材计划、缓存或成片。
7. 缺依赖、macOS 选择器不可用时，手动路径仍可完成。
8. 现有 run 工作台、媒体 allowlist、普通生产锁和全量 Skill 测试不回归。

## 10. 实施拆分

实施计划应按以下顺序展开：

1. 初始化/Stage 0 schemas、稳定草稿存储和路径校验。
2. macOS 原生选择器桥接与 API。
3. Stage 0 服务、staging、递归相对路径素材画像、冻结服务和 legacy snapshot 兼容。
4. 项目列表、初始化页、结果确认页。
5. 连接 `gb-pair`、显式注册 cold/hot run 并跳转 Gate 1。
6. 测试：路径安全、草稿幂等、Stage 0 失败闭环、freeze 哈希、旧工作台回归和 macOS 手动路径兜底。
