# Review Workbench P0b 人工验收

## 范围与结论边界

本文用于验收本机七 Gate 审核工作台 P0b。通过本检查只说明工作台、静态降级、受控修改和恢复链路具备进入监督运行的条件，不代表 G-B 已批准，也不解除普通 V2 production、共享生产缓存、归档或一线发布锁。

浏览器采用人工验收，不运行 Playwright、截图回归或浏览器录像。页面控制和 API 数据流由自动化服务测试覆盖。

## 启动前检查

在仓库根目录执行：

```bash
cd .agents/skills/remix-reference-video
python3 -m pip install -e '.[api,test]'
PYTHONPATH=src python3 -m unittest discover -s tests -q
python3 track_a_static_check.py
```

待验收任务必须是冻结的 `gb-pair` cold/hot 侧，且具有当前 `pipeline_state.json` 和 `g_b_frozen_input_snapshot.json`。首次使用时显式登记，不允许按目录名推断：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-register-run \
  --workspace-root . \
  --task-dir work/<frozen-task> \
  --json
```

以固定本机身份启动，只允许 loopback host：

```bash
WORKBENCH_UI_MODE=workspace \
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-serve \
  --workspace-root . \
  --actor <operator-id> \
  --role operator \
  --host 127.0.0.1 \
  --port 8765
```

打开 `http://127.0.0.1:8765/workbench`。新任务从“新建项目”进入；已有 run 可直接打开 `http://127.0.0.1:8765/workbench/runs/<run-id>`。不要用历史任务、另一侧 cold/hot 或其他 actor 的 session 做决定。

## 新项目初始化检查

在 1440px 与 390px 分别人工检查：

- “选择文件”和“选择目录”能调用 macOS 原生选择器；取消后保留当前输入，选择器不可用时可继续手动输入绝对路径。
- 手动路径失焦后显示 `valid|missing|not_readable|unsupported|symlink|scan_error` 对应业务提示；相对路径和 symlink 不得通过。
- 保存草稿后进入稳定项目 URL；刷新仍保留 Brief，旧 revision 提交返回冲突且不覆盖新内容。
- Stage 0 展示参考片、素材数量、媒体类型与风险；此时不存在 `pipeline_state.json`、Gate 包、TTS、代理、字幕或成片。
- “确认 Brief 并冻结”只创建 `frozen-input/`；输入在预检后变化时必须拒绝冻结。
- runtime 缺失时“启动 Gate 1”返回可恢复提示且不创建 cold/hot；runtime 可用时只跳转服务端返回的 cold `run_id`。
- Gate 2 后缺素材业务证据时，工作台显示候选素材、缺失字段和证据窗表单，隐藏通过/驳回；补齐后自动恢复并在真正 Gate 3 包生成后才显示审核按钮。

自动化已覆盖 localhost/Origin/nonce、picker 固定模式、路径验证、草稿并发、Stage 0/freeze 边界、素材证据提交与恢复、DOM 按钮执行。人工检查未完成前，不把初始化页或 `workspace` 模式声明为一线默认入口。

## 六类状态检查

人工依次使用对应 fixture 或真实运行状态检查：

| 状态 | 页面必须表达 | 可执行动作 |
| --- | --- | --- |
| 处理中 | 当前业务步骤和系统处理中状态，不伪装成待确认 | 等待或刷新 |
| 待确认 | 当前 Gate、业务问题、证据、风险和影响清晰 | 通过、驳回、要求修改 |
| 阻塞 | 阻塞原因置顶，说明缺什么和恢复动作 | 驳回或按允许范围修改 |
| 失败 | 显示失败原因、有效上游和重试入口 | 受控重试，不回滚审计事实 |
| stale | 说明页面/哈希/版本已变化 | 刷新后重新审核，旧提交返回 409 |
| 完成 | 显示当前批准结果和下一阶段影响 | 不重复提交旧批准 |

每种状态同时检查桌面宽度和浏览器 390px 响应式模式，确认标题、按钮、证据路径和影响说明不重叠、不截断。

## 七个 Gate 检查

| Gate | 运营要回答的问题 | 关键证据 |
| --- | --- | --- |
| Gate 1 参考片拆解 | 镜头切分和顺序是否可接受 | `recipe.json`、参考接触表 |
| Gate 2 复刻方案 | 内容基线与受控变更包是否批准 | `content_baseline.json`、`mutation_plan.json`、`shot_blueprint.json` |
| Gate 3 素材选配 | 每段素材、宽范围和源文字处理是否可用 | 候选、匹配结果、Gate 3 接触表 |
| Gate 3 证据闭环 | 每句口播是否有对应画面证据 | `script_evidence_matrix.json` |
| Gate 4 生成前 | 文案、音色、语速和画面预算是否批准 | 文案候选、`voice_preflight.json` |
| Gate 4 生成后 | 分段配音、停顿、边界和结尾是否可用 | voice manifest、时间轴、字幕 |
| Gate 5 成片终审 | 成片、字幕和交付报告是否通过 | MP4、SRT、最终校验、渲染报告、导入清单 |

每个 Gate 检查以下共同项：

- 页面只显示业务语言，不要求运营填写内部 hash、state revision 或 JSON。
- 关键图片、音频、短代理、字幕或成片可打开；缺失证据明确标红，不能静默跳过。
- 通过和驳回会绑定当前 session、actor、审核包哈希及 state revision。
- 要求修改先选择结构化类型和对象，再展示最早返回 Gate、失效 Gate、重生产物、是否需要 TTS/渲染和业务解释。
- 未二次确认前不执行修改；确认后显示 job id，并从权威状态刷新。
- 素材、范围、文案、声音、重录、边界、声明范围和结构修改均不得越过各自白名单。

## 冲突与恢复

在页面打开后让任务 revision 或审核包发生变化，再提交原页面决定。预期结果为 `409 review_conflict`，页面刷新当前权威视图，不写入旧决定。

registry 映射 stale 时不得自动修复。确认任务移动和冻结输入仍合法后显式执行：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-repair-run \
  --workspace-root . \
  --run-id <run-id> \
  --task-dir work/<moved-frozen-task> \
  --expected-registry-revision <revision> \
  --actor <operator-id> \
  --json
```

修改 job 失败时保留已提交事实、stale 状态和重试命令。只对显式登记且冻结哈希未漂移的 cold/hot run 执行：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-resume-change \
  --workspace-root . \
  --run-id <run-id> \
  --job-id <job-id> \
  --actor <operator-id> \
  --json
```

## 静态与 CLI 降级

页面或 API 不可用时生成确定性只读包：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-build-review \
  --task-dir work/<frozen-task> \
  --gate <gate-id> \
  --json
```

审核 `gate_review_packages/<gate-id>.review/snapshot.md`、`review.html` 和证据后，通过 CLI 创建同一 actor 的 session：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-open-session \
  --task-dir work/<frozen-task> \
  --gate <gate-id> \
  --actor <operator-id> \
  --role operator \
  --json
```

将返回的 `review_identity.review_package_hash`、`review_identity.state_revision` 和业务 scope 写入决定文件，再提交：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-decide \
  --task-dir work/<frozen-task> \
  --session-id <session-id> \
  --gate <gate-id> \
  --decision-file <decision.json> \
  --actor <operator-id> \
  --role operator \
  --json
```

CLI 降级 run 必须标记 `workbench_qualification=excluded`，不能计入 G-B 的真实工作台审核样本。

## 真实任务只读证明

2026-08-17 使用 `work/2026-08-16-gb-v2-cold` 重建 Gate 5 静态审核包。命令退出码为 0，仅更新：

- `gate_review_packages/gate5.review/gate_review_view.json`
- `gate_review_packages/gate5.review/gate_review_sheet.json`
- `gate_review_packages/gate5.review/snapshot.md`
- `gate_review_packages/gate5.review/review.html`

重建前后以下 SHA-256 完全一致：

| 文件 | SHA-256 |
| --- | --- |
| `pipeline_state.json` | `b739e8b65531ef230f3689601b47ae279e293caf3fe3c8261b897ccad276e87e` |
| `pipeline_events.jsonl` | `8d298633b5ac1bcb68e05a3873e8e4223055d55616c8ac59eb2b0b9803ac2fda` |
| `g_b_frozen_input_snapshot.json` | `3b7ab3f4d566c41fd1487214bce0bea4841682689dd963ad959eff88185ea391` |
| `remix.mp4` | `8ccf23fe802d22bbaa8cef39512566b7f3c5f614e4fddd16400c2958885b4a9d` |
| `captions.srt` | `83819f4dbcc9cde868dc7f9fe0b8043286f269f68a6f360962fd0f5c7f8cdcf4` |
| `final_validation_report.json` | `c3afab94c269d7a910f5e98aef9ed72dbddfbbb6032507ac2e21fc553ff7daf9` |
| `render_report.json` | `d2df6317ce26171fab9e32af72e15433e828d40150fede6430846f4d923dec45` |
| `jianying_import_manifest.json` | `31bcce693a99d4be40dcf5e5efc2fe968c876e1038f03e9d669bab513df0da65` |

该历史任务保留旧 blocker，静态视图建议驳回是正确行为；不能据此批准该任务。

## P0c 前剩余项

- 新建一对不复用审批的监督 cold/hot run。
- 两侧七个 Gate 全部通过真实工作台操作，采集可信 opened/evidence/active/heartbeat/decision/rework 事件。
- 人工完成六状态、七 Gate、桌面和 390px 页面走查并登记未决问题。
- 两侧 production audit 通过，生成质量、内容和过程快照。
- 形成 owner G-B 复核包并由 owner 明确批准或驳回。
- G-B 批准后仍需独立发布事务，不能由工作台自动解除普通 V2 production lock。
