# 参考视频复刻生产后端实施状态

更新时间：2026-08-15  
实现分支：`codex/remix-production-backend`  
基线：`G-A = passed`

## 当前结论

B0 的权威状态、可恢复事务、哈希绑定审批、显式 DAG 和只读产物校验基础已经实现并通过自动测试。普通 V2 生产仍未启用：真实五阶段 adapter、共享生产索引、TTS/渲染执行器、FastAPI/SSE 和 G-B 尚未完成。

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
- 当前只完成选择器和 adapter 协议，尚未运行真实媒体 adapter。

### 产物校验

- V2 五字段 envelope 与 artifact type 校验。
- 任务根路径、symlink 和 SHA-256 校验。
- Gate 3 宽范围与精确时间轴包含关系校验。
- Gate 5 五件套登记与当前哈希校验。
- Track B `audit` 已接入严格状态和登记产物校验，保持只读。

### B1/B4a adapter manifest

- `split-reference` 与 `index-assets` 已提供声明式输入、输出、Gate 停止点、实现版本和缓存指纹。
- 参考视频 fingerprint 使用内容哈希；素材目录 fingerprint 使用路径/size/mtime/ctime 快照，避免在增量索引前重复读取全部媒体字节。
- adapter manifest 拒绝参考路径逃逸、symlink 和写入 `assets/` 根目录；实际索引执行接线留在 Task 8。

## 验证

```text
110 tests passed
Track A static contract checks passed
```

生产锁测试仍保持通过，说明新增 B0 模块没有绕过 `v2_production_enabled=false` 或直接启动真实生产。

## 下一批

1. Task 7–8：B1 reference split adapter 与 B4a 共享技术素材索引。
2. Task 9–10：Blueprint、Controlled Mutation 和证据约束脚本编译。
3. Task 11–12：权威覆盖、匹配和 Gate 3 双子状态。
4. Task 13–15：素材物化、TTS、时间轴、代理和正式渲染。
5. Task 16–18：FastAPI/SSE、G-B 配对验证和发布状态同步。

在 Task 7–15 完成前，`run/stage/resume` 不得对普通 V2 任务执行真实媒体生产；当前 B0 只能用于隔离 fixture、状态/审批事务和只读审计。
