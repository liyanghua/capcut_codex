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

新 case 需要准备：

```text
frozen-root/
  reference-*.mp4
  project_brief.yaml
  asset_profiles.json
  g_b_frozen_input_snapshot.json
assets/
```

冻结输入必须包含参考片、Brief、素材画像和源素材快照。运行隔离 cold/hot 配对：

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

该命令会：

1. 为 cold/hot 创建独立任务、审批和缓存根目录；
2. 逐 Gate 生成审核包并等待当前任务的决定；
3. 只在 cold Gate 5 完成后复制声明的 SQLite 技术缓存；
4. 使用真实 `ffprobe`、`ffmpeg` 和 TTS 生成、检查并登记成片；
5. 输出 `gb_measurement.json`，记录机器时间、缓存、审批隔离和未测量项。

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

## 产物位置

每次任务均在 `work/YYYY-MM-DD[-slug]/` 下保存。关键产物包括 `pipeline_state.json`、`recipe.json`、`shot_blueprint.json`、`content_baseline.json`、`mutation_plan.json`、`matches.json`、`fragment_plan.json`、`voice_preflight.json`、`reconstruction_timeline.json`、`captions.srt`、`remix.mp4` 和 Gate 5 校验报告。用户确认 Gate 5 后，普通任务才可归档到 `final/`；隔离 pilot 永远留在 `work/`。

完整契约和阶段说明见同目录 `references/`、项目根目录 `AGENTS.md` 与 `docs/remix-production-backend-implementation-status.md`。
