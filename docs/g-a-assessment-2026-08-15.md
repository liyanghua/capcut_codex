# G-A 前向证据收口评估

评估日期：2026-08-15  
通过对象：`work/2026-08-15-tablemat-ga-harness-pilot/`  
历史失败对象：`work/2026-08-13-tablemat-pilot/`  
Skill / contract：`2.0.0-alpha.1`  
执行模式：`manual-contract-only`

## 结论

`G-A = passed`

owner 指定的 clean harness pilot 使用新的 `run_id=f9cbf031-c790-41e9-9e8b-6fa9358ed465`、空决定集和未复用审批，按固定顺序完成 Gate 1、Gate 2、Gate 3 两个子状态、Gate 4 两个子状态和 Gate 5。每个决定均在当前审核包生成后由 owner 明确给出，由 WP-A2 绑定当前输入 SHA-256 和可信工具时间写入。

最终 `ga-audit` 结果为：

```json
{
  "status": "passed",
  "ga_ready": true,
  "errors": [],
  "warnings": [],
  "approved_gates": [
    "gate1",
    "gate2",
    "gate3_material_selection",
    "gate3_evidence_closure",
    "gate4_pre_generation",
    "gate4_post_generation",
    "gate5"
  ]
}
```

因此 G-A 的审批顺序、哈希绑定、无审批复用和无 Gate 越权最低线通过。Track B 可以按已确认实施计划开始建设，但普通 V2 生产、Track C、G-B、一小时 SLA 和一线开放仍未通过，不得由本结论推定。

## Gate 证据

| Gate | 决定 ID | 结果 | 审核包 |
|---|---|---|---|
| Gate 1 | `ga-gate1-1` | approved | `gate_review_packages/gate1.json` |
| Gate 2 | `ga-gate2-2` | approved | `gate_review_packages/gate2.json` |
| Gate 3 选材 | `ga-gate3_material_selection-3` | approved | `gate_review_packages/gate3_material_selection.json` |
| Gate 3 证据闭环 | `ga-gate3_evidence_closure-4` | approved | `gate_review_packages/gate3_evidence_closure.json` |
| Gate 4 生成前 | `ga-gate4_pre_generation-5` | approved | `gate_review_packages/gate4_pre_generation.json` |
| Gate 4 生成后 | `ga-gate4_post_generation-6` | approved | `gate_review_packages/gate4_post_generation.json` |
| Gate 5 | `ga-gate5-7` | approved | `gate_review_packages/gate5.json` |

所有相对路径均相对于 `work/2026-08-15-tablemat-ga-harness-pilot/`。审批唯一权威为该目录的 `pipeline_state.json`。

## 验收结果

| G-A 验收项 | 结果 | 证据 |
|---|---|---|
| 独立 run 与空决定集启动 | 通过 | 新 `run_id`；`approval_reuse=false`；初始 `state_revision=0` |
| 审核包先于人工决定 | 通过 | WP-A2 可信创建/批准时间与最终审计 |
| 当前输入哈希绑定 | 通过 | 7 个审核包及决定中的 `input_hashes` |
| Gate 3 子状态顺序 | 通过 | 选材后才批准证据闭环 |
| Gate 4 子状态顺序 | 通过 | 生成前批准后才进入生成后听审 |
| Gate 3 无结构越权 | 通过 | 无结构请求被当作批准 |
| 无审批复用 | 通过 | 所有决定均为当前 run 新决定 |
| Gate 5 最终预览 | 通过 | MP4、SRT、三份交付报告当前哈希获批 |
| 最终只读审计 | 通过 | `status=passed`、`ga_ready=true`、无错误和警告 |

## 媒体与策略边界

- 当前成片约 `27.936s`，1080x1920、60fps、H.264/AAC，最终报告硬检查通过。
- 视频不增加顶部或底部遮盖，接受源文字/水印；`fragment03/04` 只重构已批准声明，`fragment09` 保留完整保障条款。
- WP-A2 不执行 TTS、渲染、缓存或归档；本次 harness 对冻结媒体证据重新取得了当前哈希绑定的逐 Gate 决定，没有复用历史批准。
- pilot 永久留在 `work/`，不得进入 `final/`，不得作为普通生产发布。

## 效率证据边界

- WP-A2 已记录审核包和决定的可信时间，可验证审批顺序，但没有完整测量五阶段机器执行时间、人工等待时间和返工时间。
- 正式渲染、TTS 和素材处理来自冻结媒体证据，不能据此声称 Track B 已经达到一小时端到端目标。
- 完整机器关键路径、缓存收益和一线操作耗时必须在 Track B 完成后由 G-B 冻结配对验证。

## 后续准入

1. 允许按 `docs/superpowers/plans/2026-08-15-remix-production-backend.md` 从 B0 开始实现 Track B。
2. Track B 实现期间继续保持 `v2_production_enabled=false`，只使用隔离 fixture 和明确的开发任务。
3. B0 → B1/B4a → B2/B3 → B4 → B5 完成后执行 G-B 冻结配对验证。
4. 只有 G-B、性能目标和监督运营试用通过后，才开放一线普通 V2 生产。

## 历史失败保留

`work/2026-08-13-tablemat-pilot/` 曾发生一次已撤销的 Gate 3 越权，仍保持其原结论 `not_passed`，不得用本次 clean harness 的决定回写或洗掉历史记录。本次 G-A 通过来自独立的新 run。
