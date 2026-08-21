# 参考视频复刻 Skill

这个 Skill 将完整参考视频、Brief 和 `assets/` 自有素材库转换为可审核的竖屏复刻成片。它包含五阶段业务模型、Gate 1–5、哈希绑定审批、Voice Preflight、Native Runner、真实 FFmpeg/TTS、缓存索引和只读审计。

## 当前版本边界

- Skill：`2.0.0-alpha.1`
- 产物：V2 使用 `schema_version=1.0.0`；历史 V1 产物保持 `schema_version=1.0`
- 当前已验证：真实 cold/hot Native Runner 端到端成片
- 当前未解锁：普通 V2 生产、共享生产缓存和一线无监督发布
- 当前唯一隔离新 case 入口：`gb-pair`

不要把历史 V1 的批准、状态或成片目录复制给 V2 任务。不要把 `gb-pair` 的测量结果当成 G-B 正式通过。

## 安装与检查

在仓库根目录执行：

```bash
cd .agents/skills/remix-reference-video
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python track_a_static_check.py
.venv/bin/python -m unittest discover -s tests -q
```

也可以直接使用项目内包装器：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py --help
```

## 历史 V1 流程

已经开始的 V1 任务按创建时契约续跑。使用原 V1 SOP 和原任务目录，不要用 V2 Runner 改写 `recipe.json`、审批或 `schema_version`。V1 默认交付 MP4、旁路 SRT、旧版校验报告、渲染报告和 `jianying_import_manifest.json`；没有专用适配器时不生成剪映加密草稿。

如果历史任务要迁移到 V2，必须单独生成旧/新阶段映射、输入哈希、失效 Gate 和重新确认清单；不能把迁移描述成自动兼容。

## 新 V2 case

新 case 先由 Skill 完成 Stage 0 输入预检和冻结输入准备。`gb-pair` 本身不会猜测产品事实、声明或素材哈希；进入配对前，冻结目录必须已经包含：

```text
frozen-root/
  reference-*.mp4
  project_brief.json
  asset_profiles.json
  g_b_frozen_input_snapshot.json
assets/
```

本机工作台已提供结构化初始化入口。启动 `workbench-serve` 后打开
`http://127.0.0.1:8765/workbench`，点击“新建项目”，即可选择参考视频和
素材目录、填写产品 Brief、执行 Stage 0、确认冻结输入并启动隔离 cold
到 Gate 1。macOS 使用原生文件/目录选择器；选择器不可用或取消时保留
手动绝对路径输入。Stage 0 只生成技术画像、Brief 草案和冻结候选，不生成
TTS、代理、字幕或成片。

Gate 2 后若技术画像缺少可审核的产品、语义、动作或叠字证据，creative
run 会暂停在“素材证据补充”，而不是伪造 Gate 3 审核包。运营在工作台
按真实画面填写并提交当前哈希绑定的证据后，runner 自动恢复到真正的
Gate 3；未补齐或哈希漂移继续阻断。

命令行或 Agent 交互仍保留为备用入口。如果只有参考视频、素材目录和产品信息，也可以在 Codex 新窗口发送下面的启动指令，让 Skill 补齐 Brief 草案、素材画像和冻结快照；缺少必要信息时它必须暂停并向运营提问：

```text
使用 $remix-reference-video 创建一个新的参考视频复刻任务。

参考视频：<绝对路径>
自有素材目录：<绝对路径>
产品和目标：<产品、平台、受众、已批准卖点、禁用声明>
任务名称：<英文短名称>

先完成 Stage 0，生成冻结输入草案并展示缺失项；不要编造产品事实、声明或素材。
当前普通 V2 production 仍受锁保护，准备完成后使用隔离 gb-pair。
从 Gate 1 开始逐 Gate 停止，等待我明确审批；不复用历史任务、cold/hot 或其他 case 的审批。
```

冻结输入经运营确认后，运行隔离 cold/hot 配对：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py gb-pair \
  --frozen-root <frozen-root> \
  --asset-root <assets> \
  --cold-task-dir <work>/<case>/cold \
  --hot-task-dir <work>/<case>/hot \
  --pair-root <work>/<case> \
  --doubao-client <path/to/doubao_client.py> \
  --json
```

不提供 `--decision-dir` 时，命令会在第一个需要人工确认的 Gate 停止；这是默认安全行为。由 Codex 交互运行时，应在每次用户批准后写入当前任务的决定文件，再用 `--resume-existing` 续跑。只有审核人已经为本次任务准备好全部结构化决定文件时，才传入 `--decision-dir <decision-dir>`，且每个文件仍会绑定当前审核包哈希和 `state_revision`，不能复用其他任务决定。

该命令会：

1. 为 cold/hot 创建独立任务、审批和缓存根目录；
2. 逐 Gate 生成审核包并等待当前任务的决定；
3. 只在 cold Gate 5 完成后复制声明的 SQLite 技术缓存；
4. 使用真实 `ffprobe`、`ffmpeg` 和 TTS 生成、检查并登记成片；
5. 输出 `gb_measurement.json`，记录机器时间、缓存、审批隔离和未测量项。

每个 Gate 的业务审批可以直接使用：

```text
Gate 1 通过，进入 Gate 2。
Gate 2 通过，进入 Gate 3 选材。
Gate 3 选材通过，进入证据闭环。
Gate 3 证据闭环通过，进入 Gate 4 生成前审核。
Gate 4 生成前通过，按当前文案、音色和语速生成。
Gate 4 生成后通过，进入正式渲染。
Gate 5 最终预览通过。
```

Gate 5 前的成片只能留在 `work/`；即使隔离配对完成，也不能将测量结果解释为 G-B 正式通过。

如果现有配对目录已通过部分 Gate，可显式续跑：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py gb-pair \
  --frozen-root <frozen-root> --asset-root <assets> \
  --cold-task-dir <work>/<case>/cold --hot-task-dir <work>/<case>/hot \
  --pair-root <work>/<case> --resume-existing --json
```

## 审批与只读检查

每个 Gate 都必须使用当前审核包哈希、当前 `run_id` 和 `state_revision` 批准。常用只读命令：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py production-status \
  --task-dir <task-dir> --json

python3 .agents/skills/remix-reference-video/scripts/remixctl.py production-audit \
  --task-dir <task-dir> --json
```

Gate 3 必须同时通过素材选择和证据闭环；Gate 4 必须先生成前批准，再真实 TTS，最后生成后听审。配音实际时长超出 Gate 3 宽范围时，必须返回受影响 Gate，不得变速或冻结尾帧补齐。


## 质量加固节点（V2 新任务）

`narrative_contract_v1` 只作用于冻结 Gate 2 内容基线携带该字段的新任务；在飞旧契约任务按旧 DAG 续跑（设计 §4.3），不会静默变轨。

- `build-narrative-coherence`（summarize-gate3 之后）：由冻结基线叙事元数据 + `continuity_lexicon_v1` 生成 `narrative_coherence_report.json`；`blocked`/`manual_review` 时阻止 `build-production-script`，并通过 Gate 4 生成前审核包暴露缺口。
- `validate-visual-layout`（materialize-approved-broad 之后）：按 `visual_layout_policy_v1` 生成 `visual_layout_report.json`。图片一律 `contain`、`crop_pixels=0`、放大不超过 `2.0x`；带源文字的视频仅在 overlay policy 为 `retain_source_text` 时 `contain`。`blocked` 时阻止 `voice-preflight`。
- 两份报告都是机器产物：`lifecycle_status` 只允许 `ready|stale`，不允许携带 Gate approval 字段；schema 注册在 `schemas/v2-alpha.registry.schema.json`。
- V2 文案修改请求必须携带 `edit_intent=bridge|rewrite`；`merge` 只属于结构修改并返回 Gate 2。V1 任务缺失 intent 由兼容层归一为 `rewrite`。

## 创意质量升级（Creative V2）

新建 creative run 在 Stage 0 冻结快照中明确写入 `creative_contract_version="creative_contract_v1"`，它才会选择 `creative_dag()`；没有该标记的历史 run 继续按 frozen legacy/hardened DAG 运行。creative DAG 不解除 `gb-pair` 隔离、Gate 审批或普通 V2 production lock。

- Gate 1 审核 `decomposition_bundle.json` 并选择一个 `selected_decomposition_id`；Gate 2 原子绑定 `creative_objective.json`、`remix_strategy_candidates.json`、内容基线、变更包和 coverage precheck；Gate 4 生成前只允许批准 `script_candidate_validation_report.json` 标记为 `passed` 的脚本候选。
- 工作台的阶段卡展示策略、候选版本、关键产物血缘、质量测量和结构化修改影响。`script_candidate_select` 只走 ChangeService 预览与二次确认，会使 Gate 4 及下游 stale，不会直接改写已批准成片。
- `validate-shot-quality` 缺失 required action 或代理证据时阻断；主观一致性/高光问题保持 `manual_review`。`build-final-content-diagnostic` 将前三秒、目标覆盖和确定性问题带入 Gate 5，不冒充 Track C L1 分数。
- 脚本候选 provider 必须显式传入。当前仅注册可复现的 `stub`，用于测试和契约验证；未接入受控生产 provider 前，creative run 会在候选生成环节停止，而不会静默回退为伪生成。
- `baseline_v0` 固定为 `gb-cold-1786890259`。用 `CreativeBaselineComparison` 创建 v0/v1 比较约束后，由 owner 按 [盲评模板](../../../docs/superpowers/blind-eval-template.md) 完成两份独立评价；只有真实 `baseline_v1` 通过全部 Gate 后才可计算比较结论。P3b 局部 AI 增强仍需先有 P3a 的重复、可修复问题监督证据。

## 本机审核工作台

P0b 提供 localhost-only 七 Gate 审核台。它只服务显式登记的冻结 `gb-pair` cold/hot run，不会按目录名猜测任务，也不会解除普通 V2 production、共享缓存、归档或发布锁。

安装 API 可选依赖并登记任务：

```bash
cd .agents/skills/remix-reference-video
python3 -m pip install -e '.[api,test]'
cd ../../..

python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-register-run \
  --workspace-root . \
  --task-dir work/<frozen-task> \
  --json
```

登记命令返回 `run_id`。使用固定本机审核身份启动服务：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-serve \
  --workspace-root . \
  --actor <operator-id> \
  --role operator \
  --host 127.0.0.1 \
  --port 8765
```

浏览器打开 `http://127.0.0.1:8765/workbench/runs/<run-id>`。页面可直接通过、驳回或要求修改；修改必须先生成服务端影响预览，再二次确认。旧页面、旧哈希、旧 revision、其他 actor/session 或另一侧 cold/hot 的提交会被拒绝。

工作台页面支持启动时灰度切换：

```bash
WORKBENCH_UI_MODE=workspace python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-serve \
  --workspace-root . --actor <operator-id> --host 127.0.0.1 --port 8765
```

`workspace` 模式显示故事板、未归类素材、中央预览、三轨只读时间线和五阶段决策助手；默认值和无效值均为 `legacy`，可用 `WORKBENCH_UI_MODE=legacy` 立即回退。时间线只能定位、播放和发起结构化修改，不能直接拖拽写入成片。工作区 `/api/v1/runs/<run-id>/workspace` 是只读业务投影，ETag 绑定当前 `state_revision`；媒体仍必须通过当前 run 的 allowlist 和 containment 校验。

如果页面不可用，先生成只读静态包：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-build-review \
  --task-dir work/<frozen-task> \
  --gate <gate-id> \
  --json
```

输出位于 `gate_review_packages/<gate-id>.review/`。API 完全不可用时，可用相同 actor 创建 CLI session，再提交绑定当前审核包的决定：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-open-session \
  --task-dir work/<frozen-task> \
  --gate <gate-id> \
  --actor <operator-id> \
  --role operator \
  --json

python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-decide \
  --task-dir work/<frozen-task> \
  --session-id <session-id> \
  --gate <gate-id> \
  --decision-file <decision.json> \
  --actor <operator-id> \
  --role operator \
  --json
```

修改恢复只允许冻结哈希仍匹配的已登记 run：

```bash
python3 .agents/skills/remix-reference-video/scripts/remixctl.py workbench-resume-change \
  --workspace-root . \
  --run-id <run-id> \
  --job-id <job-id> \
  --actor <operator-id> \
  --json
```

任务移动、registry revision 冲突或冻结输入漂移时不得自动修复。使用 `workbench-repair-run` 显式重绑并保留审计记录；仍冲突时重读 registry 和当前任务状态，不覆盖新条目。完整人工验收和七 Gate 检查表见项目根目录 `docs/review-workbench-manual-acceptance.md`。

## 产物位置

每次任务均在 `work/YYYY-MM-DD[-slug]/` 下保存。关键产物包括 `pipeline_state.json`、`recipe.json`、`shot_blueprint.json`、`content_baseline.json`、`mutation_plan.json`、`matches.json`、`fragment_plan.json`、`narrative_coherence_report.json`、`visual_layout_report.json`、`voice_preflight.json`、`reconstruction_timeline.json`、`captions.srt`、`remix.mp4` 和 Gate 5 校验报告。用户确认 Gate 5 后，普通任务才可归档到 `final/`；隔离 pilot 永远留在 `work/`。

完整契约和阶段说明见同目录 `references/`、项目根目录 `AGENTS.md` 与 `docs/remix-production-backend-implementation-status.md`。
