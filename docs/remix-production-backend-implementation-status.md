# 参考视频复刻生产后端实施状态

更新时间：2026-08-16
实现分支：`codex/remix-production-backend`  
基线：`G-A = passed`

## 当前结论

B0 的权威状态、可恢复事务、哈希绑定审批、显式 DAG、只读产物校验、B1 reference split、B4a 增量索引和 B2–B5 adapter 层已实现并通过隔离测试。native runner 已接通完整 Gate 3–5 链路；新增 `voice_preflight` 在 Gate 3 画面预算之后、Gate 4 生成前和真实 TTS 之前运行。普通 V2 生产仍未启用，原因是 G-B 冻结真实素材配对与监督运营验收尚未收口。

2026-08-16 已把 Native Runner 接入正式 CLI：`production-run`、`production-resume`、`production-stage`、`production-status`、`production-audit` 使用显式 `production_runtime_config.json` 构建完整 Native Registry；普通 `run/stage/resume` 仍受 manifest 锁保护。新增受保护的 `gb-pair` 只接受 `g_b_frozen_input_snapshot.json`，为 cold/hot 创建独立任务、审批和缓存根目录。

真实配对证据：`work/2026-08-16-gb-pair-real-2/gb_measurement.json`。cold 与 hot 均使用真实 `ffprobe/ffmpeg/TTS` 完成完整链路，Gate 1–5 均由各自当前审核包独立批准；cold 成片为 27.720 秒，hot 成片为 27.552 秒，均为 1080×1920、60fps，最终技术校验通过。11 个片段均为 matched，候选置信度为 0.934，保留源文字/水印；`fragment05=7.3–8.8s`、`fragment07=0–2.8s` 均在真实源范围内，实际 TTS 后未变速、未冻结尾帧。cold 与 hot 的决定完全隔离，hot `run_id=gb-hot-1786872405`、`state_revision=74`。Gate 5 后仅复制声明的 SQLite cache；hot 首次启动复用冷快照，后续续跑保留 hot 自己的增量索引，不再次覆盖。配对结果当前为 `measured_pending_review`，同时已作为 V2 `measured_baseline_v0` 记录在 `docs/remix-production-v2-baseline-report-2026-08-16.md`：机器关键路径累计 cold 32.178 秒、hot 36.183 秒，已证明真实执行链路和缓存/审批隔离可运行；但人工等待、运营触达、完整 Track C 质量分和 owner G-B 阈值尚未测量/复核，因此普通 V2 生产、共享缓存和一线发布仍保持关闭。

## 已实现

### 权威状态契约

- `PipelineState` 只接受 `execution_mode=track-b-production`。
- 固定工作状态与 Gate 状态枚举。
- 固定 Gate 3/4 子状态及汇总 ID。
- 旧 V1/Fast Path 状态只读投影为 `supported=false`，不静默升级。

### 可恢复事务

- `.transactions/<transaction_id>.json` prepared/committed 记录。
- expected revision 冲突拒绝。
- staging 到不可变版本路径的原子提升。
- 声明产物类型的 staging 文件在提升前执行完整 V2 envelope 校验；失败不更新状态或生成最终文件。
- state 已提交但 event/metric 缺失时幂等恢复。
- state 未提交时清理孤儿产物。
- 无法自动测得的指标恢复为 `measurement_status=partial`，不伪造零耗时。

### Approval Service

- 新增 `approve-gate`，绑定审核包 SHA-256、任务 `run_id`、当前 `state_revision` 和可信服务时间。
- 决定文件使用枚举字段；调用方不能提交审批时间。
- 支持重复请求幂等、跨任务拒绝、过期 revision 拒绝和 Gate 顺序校验。
- Gate 4 生成前批准在同一事务中提升 `approved_production_script.json` 和 TTS 设置。
- Orchestrator 没有自审批接口。

### 显式生产 DAG

- 已编码设计规格中的 B0–B5 规范节点与依赖。
- 支持 Gate 停止、精确下一节点选择、blocked/stale 传播和唯一 attempt ID。
- 参考拆解/素材技术索引与脚本编译/素材物化的并行资格已声明。
- `ProductionRunner` 已接入 reference split native adapter；它在 Gate 1 后停止，审核包由 runner 按当前 `run_id`、`state_revision`、可信服务时间和输入哈希封装后才可交给 `ApprovalService`。
- `test_production_fixture.py` 以隔离 JSON fixture 覆盖完整 B0–B5 DAG：逐 Gate 停止、真实 `ApprovalService` 决定、Gate 3/4 汇总、Gate 5 和重复运行无写入；该测试证明流程契约，不证明真实媒体质量。

### 产物校验

- V2 五字段 envelope 与 artifact type 校验。
- 任务根路径、symlink 和 SHA-256 校验。
- Gate 3 宽范围与精确时间轴包含关系校验。
- Gate 5 五件套登记与当前哈希校验。
- Track B `audit` 已接入严格状态和登记产物校验，保持只读。
- `stage_inputs/<stage>.json` 交接契约已落地：validator 校验 V2 envelope、阶段 ID、生命周期、任务内路径/symlink、输入 SHA-256 和审批伪字段；ProductionRunner 在对应 adapter 执行前校验，`audit` 只读扫描全部交接文件。该契约不改变 `pipeline_state.json` 的审批权威。
- Native Registry v0 已落地：`NativeAdapterRegistry` 按规范 DAG 排序并拒绝未知/重复节点，`NativeStageAdapter` 统一读取交接 payload、调用阶段函数、写声明 JSON 产物；Blueprint、Mutation、权威 Coverage 和 Match 已提供真实 adapter 绑定。`ProductionRunner.from_registry()` 可在隔离任务中运行这些节点，仍受 manifest Track B 锁约束；正式 CLI 只通过显式运行时配置加载它。
- Native completion registry 已接通 Gate 3 → Gate 5：选材包/冻结宽范围/证据闭环、生产脚本、素材物化、幂等 TTS、实测时间轴/SRT、代理边界、正式渲染、Gate 5 包和隔离归档均由真实 adapter 调用；端到端 fixture 已验证五次 `approve-gate` 与五次 `resume` 的顺序、哈希绑定和最终归档。
- Render adapter 增加了 Runner 事务内的非状态管理模式：领域 adapter 负责 staging/媒体校验，Runner 负责唯一状态提交，避免嵌套任务锁；Gate 5 只有在 package builder 生成审核包后才阻塞下一次 resume。

### B1/B4a adapter manifest

- `split-reference` 与 `index-assets` 已提供声明式输入、输出、Gate 停止点、实现版本和缓存指纹。
- 参考视频 fingerprint 使用内容哈希；素材目录 fingerprint 使用路径/size/mtime/ctime 快照，避免在增量索引前重复读取全部媒体字节。
- adapter manifest 拒绝参考路径逃逸、symlink 和写入 `assets/` 根目录。
- `AssetIndexAdapter` 已接入共享 SQLite 增量索引；冷扫描后可 warm cache hit，索引实现版本变化会只清空可重建技术事实并重新探测。
- `index-assets --json` 返回 `implementation_version`，源素材始终只读。

### B2/B3 Blueprint 与 Gate 2 包

- `coverage_precheck.json` 只以 `advisory_only` 身份进入 Blueprint；权威 coverage 不得冒充规划输入。
- 目标声明必须来自 Brief 的 `approved_claims`，禁用声明与未批准新声明在草案编译时失败。
- fallback 只能从 Brief 的逐项批准集合选择；软时长不足会建议扩展成片时长，不删段或强压语速。
- Gate 2 审核包原子绑定实际 `content_baseline.json` 与 `mutation_plan.json` 文件 SHA、运行 ID 和当前 revision；相关输入变化生成 Gate 2–5 stale 投影。
- `ProductionScriptCompiler` 只从 Gate 2 声明边界、mutation fallback 和已批准证据矩阵编译候选；缺证据、fallback 越界和声明强化会阻断。
- 编译器只返回 `production_script_candidate` 并登记实际输入文件 SHA；`approved_production_script.json` 仍只由 Gate 4 Approval Service 事务生成。

### B4 权威覆盖与确定性匹配

- `authoritative` coverage 必须绑定当前 Gate 2；precheck 始终保持建议性质。
- match 是目标 fragment 需求与素材 profile/segment 的匹配：先校验产品、语义证据、动作、媒体类型、禁用语义和可用时长，再按固定版本六维加权评分。
- 同 SHA 或感知哈希候选去重；全局排程避免连续第三段继续使用同一来源；最佳合格候选低于 `0.60` 明确阻断为 `missing_material`。
- 候选选择记录 overlay policy 和宽可用范围；最终 Gate 3 哈希绑定与不可变 `fragment_plan.json` 留在 Task 12。
- Gate 3 冻结 `media_type` 与 `visual_duration_budget_seconds`；视频预算等于批准宽范围差值，图片预算为 `null`，并由 `voice_preflight.json` 在 TTS 前校验文案时长估算。

### Gate 3 双子状态与证据闭环

- 选材审核包绑定当前 `material_selection_candidate.json` 哈希；Approval Service 批准后才能冻结不可变 `fragment_plan.json`。
- 运营可在素材真实可用范围内扩展宽范围；越过源范围立即失败，不通过变速或冻结帧补齐。
- `script_evidence_matrix.json` 使用独立 `gate3_evidence_closure` 审核包；两个子状态都由 Approval Service 批准后才汇总 Gate 3。
- 素材内容、overlay 或宽范围变化会使两个 Gate 3 子状态及 Gate 4–5 stale，同时保留未受影响素材索引；删并段请求明确返回 Gate 2。
- 生产脚本编译以 `pipeline_state` 审批记录和当前 evidence SHA 为准，不信任产物自报审批状态。

### B5 素材物化与幂等配音

- 冻结计划中的 `source_path` 从 Retrieval 贯通到物化；先校验所有源哈希，再以 copy-only 方式写入 `material/`，源素材不移动、不改写。
- TTS 只接受 `approved_production_script.json`，幂等键绑定脚本 SHA、provider 身份与音色设置。
- 单次 provider timeout 为 60 秒，每段最多三次；仅超时、连接、429 和明确 5xx 重试，退避及 `Retry-After` 上限 60 秒。
- 所有分段音频完整性通过后才原子生成最终音频；失败不会留下可被误用的 `final_voice`。
- 时间轴只使用实测语音时长累计，精确裁点保持在 Gate 3 宽范围内且播放速度固定 `1.00x`；字幕从批准脚本生成旁路 SRT。
- `voice_preflight` 逐段按字数、标点停顿和音色历史平均语速估算时长；负 margin 在 TTS 前阻断并列出缩文案、Gate 2 fallback、扩大 Gate 3 范围或返回 Gate 2 四种恢复路径。TTS 实测仍必须再次检查预算，不能变速或冻结尾帧补齐。
- 代理默认 540×960/30fps，可显式升到 720×1280/30fps；Gate 4 生成后未批准时拒绝代理渲染，并输出边界帧校验报告。
- 正式渲染通过 staging、1080×1920/60fps H.264/AAC 流与时长校验后，原子提升 MP4 和报告并登记五件套哈希；Gate 5 保持 `awaiting_user`。
- `captions.srt` 作为 Task 14 canonical 产物只复核和登记，不在最终渲染时覆盖；普通任务仅 Gate 5 批准后归档，pilot 永久拒绝归档。
- FastAPI/SSE 采用 optional `api` extra 和惰性导入；核心投影、脱敏、ETag、artifact allowlist、SSE 续连/去重已通过测试，无任何 Gate 写路由。
- 当前环境 FastAPI optional extra 安装被外部审批服务 503 拦截，真实路由集成测试暂时跳过 1 项，不能表述为 Task 16 完整验收通过。
- Phase 6 最小测量 harness 已覆盖隔离冷缓存、热缓存克隆、受控变更、审批隔离、V1 可比性、跨运行缓存拒绝，以及冷 ≤780 秒/热 ≤480 秒、五阶段与总分 ≥88 的判定。
- 该 harness 的判定逻辑先在 fixture 中验证；G-A clean harness 已通过，真实 Track B 冻结配对也已完成并写入 `gb_measurement.json`，但当前仍是 `measured_pending_review`，因此没有 G-B 正式通过结论。

## 验证

```text
186 tests passed, 1 skipped (FastAPI optional-extra route integration)
Track A static contract checks passed
```

生产锁测试仍保持通过，说明新增 B0 模块没有绕过 `v2_production_enabled=false` 或直接启动真实生产。

## G-B 配对现状

- `gb-pair` 不调用普通 Track B 解锁逻辑，也不改变 `manifest.json`；这是唯一允许在锁定期间创建的隔离测量入口。
- 冷/热任务只复制冻结参考输入、Brief、素材画像和 stage handoff；不复制 `pipeline_state.json`、`decisions/`、Gate 审核包、媒体输出或绝对源路径。
- 缓存只有在 cold 通过 fresh Gate 5 后才允许复制到 hot；本次 cold 已通过，hot 首次启动只收到声明的 SQLite cache，后续 hot 运行产生的扫描批次元数据保留在 hot，不覆盖 cold，也不复制状态、审核包或决定。
- cold/hot 已分别完成 Gate 1–5，所有决定绑定各自审核包与 `state_revision`；两侧 `production-audit` 均为 `passed`。后续任何范围、文案或声音设置变化仍必须从最早受影响 Gate 重新批准；cold 或旧 hot 的任何批准都不能被其他任务消费。

## 下一批

1. 由 owner 审阅并接受 `measured_baseline_v0`，明确它是后续 V2 回归基线；历史 V1 继续保留为 `retrospective_baseline`，不伪造严格可比的 V1 cold/hot 数据。
2. 生成当前真实配对的最小 `phase6_score_snapshot.json`，校验 cold `≤13 分钟`、hot `≤8 分钟`、五阶段最低线和视频总分 `≥88`；同时补采人工等待、运营触达、缓存命中和完整墙钟，由 owner 复核 G-B 是否接受新的基线口径。
3. G-B 通过后仅晋级 `2.0.0-rc.1`，再做监督运营试用和 FastAPI optional extra 真实路由测试；Backlot 式前端及普通 V2 production 仍不得提前开放。

在上述条件完成前，`run/stage/resume` 只允许临时隔离 fixture；既有 pilot 保持只读，任何批准都不能跨任务复用。
