# Fast Path v0 操作与验证

## 定位

Fast Path v0 是五阶段外部的实验执行层，不是第六个业务阶段。它负责按已声明的 argv 顺序执行机器步骤、检查人工 Gate、记录实耗时、验证产物哈希、从有效缓存续跑，并为 `assets/` 建立共享技术索引。

它不生成业务判断，也不自动批准 Gate。Track B 另有 native adapter runner：当前已接入真实参考视频切分并提供受 manifest 锁保护的 `init/run/stage/resume` 开发入口，其余阶段 adapter 已有独立契约测试，但尚未形成可对一线开放的完整 registry。只有隔离端到端 Gate fixture、G-B 冻结配对和监督运营试用全部通过后，才能验证完整视频是否达到一小时目标。

## 五阶段对应关系

| 业务阶段 | Fast Path v0 的作用 | 主要提速点 |
| --- | --- | --- |
| Performance-proven Video | 执行探测/拆镜命令，缓存参考片输入指纹和产物哈希 | 参考片未变时不重复拆解 |
| Blueprint | Gate 1 批准后才执行蓝图命令 | 相同事实、Brief 和配置复用结果 |
| Controlled Mutation | 与 Gate 2 依赖绑定，输入变化时缓存失效 | 防止误用旧变更包 |
| Retrieval | Gate 2 后执行；读取共享 SQLite 技术索引 | 未变素材不重复哈希和 FFprobe |
| Reconstruction | Gate 3/4 满足后执行配音、时间轴和渲染命令 | 失败后保留有效上游并续跑 |

## 运行边界

- 单机、单任务、标准库 Python；不包含队列、FastAPI、SSE 或前端。
- `pipeline_state.json` 仍是 Gate 状态权威；Fast Path 只增加 `fast_path.stage_status` 和 `fast_path.stage_cache`。
- 计划只接受 argv 数组，不接受 shell 字符串；任务输入/输出必须位于声明的任务目录内。
- 每个新执行步骤都要声明输入、输出、前置 Gate、完成后 Gate、超时和是否允许缓存。
- 任何阶段失败、超时、缺产物、输入被改写或输出路径逃逸都会停止。
- 阶段命令在独立进程组运行；超时会清理整个进程组，未使用的 stdout/stderr 不在内存中累积。
- 状态、事件、指标和锁文件拒绝 symlink；严格 JSON 读取拒绝重复键和无效 UTF-8。
- 素材文件读取失败会按路径持久记录并在恢复后清除；FFprobe 缺失属于可重试环境失败，不缓存成素材损坏。
- 当前 `manual-contract-only` pilot 只允许 `status` 和 `audit`；`fast`、`resume` 必须无写入拒绝。
- `init/run/stage/resume` 在检查 manifest 锁之前不得创建任务目录、状态、锁、缓存或媒体。当前 manifest 仍关闭普通 V2 production，因此这些命令只在临时隔离测试中验证，不存在用户侧绕过参数。

### WP-A2 G-A Evidence Harness

G-A 前唯一允许写入 pilot 的入口是三条证据工具。它们只处理任务内既有文件和结构化人工决定，不执行 stage、媒体、缓存或归档：

```text
remixctl ga-prepare-review --task-dir <pilot> --gate <gate_id> --artifact <path>...
remixctl ga-record-decision --task-dir <pilot> --gate <gate_id> \
  --review-package gate_review_packages/<gate_id>.json \
  --decision-file <decision.json> --actor <owner>
remixctl ga-audit --task-dir <pilot>
```

审核包先绑定任务 `run_id` 和输入 SHA-256；决定时重新校验哈希并由工具生成可信时间戳。Gate 3 的删段、并段、重排只能作为请求返回 Gate 2，不能由此工具批准。`ga-audit` 完全只读，发现输入变化、审批复用、顺序错误或结构越权即失败。pilot 即使 Gate 5 通过也只能留在 `work/`，不得迁移到 `final/`。
- Fast Path v0 不改变 `manifest.json` 的 Track B 锁和 `v2_production_enabled=false`。

## 命令

在 Skill 目录执行：

```bash
uv run python scripts/remixctl.py fast \
  --workspace-root /absolute/project/root \
  --plan /absolute/project/root/fast-path-plan.json

uv run python scripts/remixctl.py resume \
  --workspace-root /absolute/project/root \
  --plan /absolute/project/root/fast-path-plan.json

uv run python scripts/remixctl.py status \
  --task-dir /absolute/project/root/work/YYYY-MM-DD-slug

uv run python scripts/remixctl.py audit \
  --task-dir /absolute/project/root/work/YYYY-MM-DD-slug

uv run python scripts/remixctl.py index-assets \
  --assets-root /absolute/project/root/assets \
  --database /absolute/project/root/.cache/remix-reference-video/assets.sqlite3
```

Track B native runner 的开发命令形态如下；当前生产锁开启时会在任何写入前退出：

```bash
uv run python scripts/remixctl.py init \
  --workspace-root /absolute/project/root \
  --task-dir /absolute/project/root/work/YYYY-MM-DD-slug \
  --reference /absolute/project/root/inbox/reference.mp4

uv run python scripts/remixctl.py run \
  --task-dir /absolute/project/root/work/YYYY-MM-DD-slug \
  --reference /absolute/project/root/work/YYYY-MM-DD-slug/reference.mp4

uv run python scripts/remixctl.py stage \
  --task-dir /absolute/project/root/work/YYYY-MM-DD-slug \
  --reference /absolute/project/root/work/YYYY-MM-DD-slug/reference.mp4 \
  --stage split-reference

uv run python scripts/remixctl.py resume \
  --task-dir /absolute/project/root/work/YYYY-MM-DD-slug \
  --reference /absolute/project/root/work/YYYY-MM-DD-slug/reference.mp4
```

每个命令均可增加 `--json`，供后续 FastAPI 或自动化调用。

## 运行产物

| 路径 | 用途 |
| --- | --- |
| `<task>/pipeline_state.json` | Gate 权威状态及 Fast Path 缓存登记 |
| `<task>/pipeline_events.jsonl` | 单调 sequence 的执行与审计事件 |
| `<task>/stage_metrics.jsonl` | 每次机器尝试的实测耗时和 cache hit |
| `<task>/.fast_path.lock` | 同任务写入互斥锁 |
| `<workspace>/.cache/.../assets.sqlite3` | 素材路径与内容分离的共享技术索引 |

人的审核等待不写成 `0` 秒。v0 只记录实际机器尝试耗时；端到端墙钟需要在外部用 Gate 到达和批准时间计算。

## 退出码

| 退出码 | 含义 | 运营动作 |
| ---: | --- | --- |
| `0` | 成功或全部缓存命中 | 查看结果或进入下一工作项 |
| `2` | 参数、计划或路径契约错误 | 修正配置后重试 |
| `3` | 到达人工 Gate | 审核当前 Gate，不要重复启动 |
| `4` | 策略阻塞 | 查看任务模式或阻塞原因 |
| `5` | 阶段执行或审计失败 | 处理错误后运行 `resume`/`audit` |

## 隔离 fixture

`tests/fixtures/fast_path_plan.json` 配合 `tests/fixtures/fast_path_task/` 验证：

```text
fast
→ fixture-reference-split
→ Gate 1 awaiting_user
→ 显式把 fixture 的 gate1 标记为 approved
→ resume
→ fixture-blueprint succeeded
→ resume
→ 两阶段 cache_hit
```

fixture 只能复制到临时 workspace 运行，不能直接在 Skill 安装目录生成状态和产物。

## 实测记录

最近测量日期：`2026-08-15`。本节只记录命令实测，不使用估算替代验收。

| 验证项 | 实测结果 |
| --- | --- |
| Fast Path 新测试 | `75/75` 通过；`ResourceWarning` 作为错误时仍通过 |
| 隔离 fixture | `fast=awaiting_user` → 明确批准 Gate 1 → `resume=succeeded` → 再次 `resume=cache_hit` |
| 现有回归 | Track A 2、matcher 46、Gate 4 6、时间轴 1、Gate 5 2、字幕叠层 2，共 `59/59` 通过 |
| `assets/` 冷索引 | 7 个支持文件，7 次哈希、7 次 FFprobe、0 个不可读，`0.485973s` |
| `assets/` 暖索引 | 7/7 cache hit，0 次哈希、0 次 FFprobe、`0.004557s` |
| pilot 只读状态 | `final_review`，`gate5=approved`；pilot 即使完成且 G-A 已由独立 clean harness 通过，仍保持 `manual-contract-only`、不归档且只允许只读 `status/audit` |
| pilot 全文件摘要 | `status/audit` 前后均为 `480eb3dc6415d1ffd7c44c5bafbf12a937cd1d78fba1aa9718b2d52b7c03fd7b` |
| Skill 包校验 | 官方 `quick_validate.py` 返回 `Skill is valid!` |

`2026-08-15` 加固覆盖：Gate 批准重新绑定当前产物哈希；上游变化会撤销下游缓存、标记后续 Gate 为 `stale` 并移除已声明的旧下游输出；人工 `blocked/failed/stale` 不会被非缓存重跑覆盖；缓存指纹包含可执行文件和脚本内容；任务根目录替换为 symlink 时在控制文件写入前拒绝；FFprobe 超时作为可重试索引错误；`audit` 检查批准闭环和事件 revision 单调性。

以上只证明执行、Gate 停止、恢复、缓存、技术索引和只读保护生效。真实五阶段机器时间、人工等待、完整视频质量和“一小时完成复刻”仍未验证；必须先接入五阶段通用命令，再用冻结标准任务测量。
