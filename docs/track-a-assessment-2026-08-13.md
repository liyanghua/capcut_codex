# Track A 阶段评估

日期：2026-08-13  
Skill：`remix-reference-video` `2.0.0-alpha.1`  
契约：`2.0.0-alpha.1`  
阶段：Track A 契约与 Gate 顺序迁移  
状态：`static_complete_g_a_awaiting_pilot_evidence`

## 结论

Track A 的跨文件契约迁移、版本边界、共同 artifact envelope、最小静态护栏和触发边界评测已经完成。纳入变更前媒体基线的 418 个 `work/` 媒体文件，收口时得到相同内容摘要。

这些结果只证明“规则已统一、关键静态矛盾可被阻断、Skill 触发边界在当前 12 条样例上正确、历史媒体基线未变化”。后续 pilot 已完成 Gate 1–5，但 G-A 因一次已撤销的 Gate 3 越权记录未通过；Track B/C 继续锁定。最终结论见 `docs/g-a-assessment-2026-08-15.md`。

## 已验证

| 检查项 | 结果 | 证据与边界 |
|---|---|---|
| 五阶段 ownership 与生产顺序 | 通过 | 优化方案、`AGENTS.md`、SOP、Skill 与 references 已统一 |
| Gate 3 双子状态 | 通过 | `gate3_material_selection` + `gate3_evidence_closure` |
| Gate 4 双子状态 | 通过 | `gate4_pre_generation` + `gate4_post_generation` |
| 宽范围与精确裁点分离 | 通过 | Gate 3 `fragment_plan.json` 不可变；Gate 4 `reconstruction_timeline.json` 只在宽范围内收窄 |
| TTS 唯一文本输入 | 通过 | `approved_production_script.json` |
| `recipe.json` 事实边界 | 通过 | V2 替换配音时长不回写参考事实层 |
| V1/V2 版本边界 | 通过 | Skill/contract `2.0.0-alpha.1`；V2 artifact `1.0.0`；历史 V1 `1.0` 只读 |
| Registry identity | 通过 | 25 个 active artifact 类型，路径与 schema ID 均唯一且由 `oneOf` 一一绑定 |
| YAML 可解析性 | 通过 | Brief 模板和 `agents/openai.yaml` 由 Ruby `YAML.safe_load` 实际解析 |
| 最小回归测试 | 通过 | 2/2：当前契约通过；重复 registry 路径被拒绝 |
| Trigger 前向评测 | 通过 | 独立评测 12/12：6/6 应触发、4/4 明确排除、2/2 near-neighbor 排除 |
| 历史媒体基线保护 | 通过 | 同一可复现命令前后摘要一致，覆盖 418 个指定扩展名文件 |
| Skill 基础格式 | 通过 | 官方 `quick_validate.py` 使用本机缓存 PyYAML 运行并返回 `Skill is valid!` |

## 可复现证据

静态检查：

```text
PASS: Track A static contract checks
manifest_sha256=aac405da9fa64b2a5a11f68302105a487d1f5ba1eff14c27cf38ba023b1a8b59
checked_files=14
registry_envelope=passed
brief_yaml_parse=passed
openai_yaml_parse=passed
trigger_fixture_structure=passed
trigger_behavior_evaluation=not_run
full_artifact_shape_validation=deferred_to_track_b
production_media_comparison=not_run
```

最后三行是静态检查器自身的边界，不代表独立评测没有运行。Trigger 行为与媒体比较由本报告单独记录。

最小测试：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s .agents/skills/remix-reference-video \
  -p 'track_a_static_check_test.py' -v
```

结果为 `Ran 2 tests ... OK`。没有扩展成大规模测试集。

媒体保护命令与结果：

```bash
find work -type f \( -name '*.mp4' -o -name '*.mp3' -o -name '*.wav' \
  -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' \) -print0 \
  | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256
```

变更前与收口时均为：

```text
d531a2a2ef5433524f98685ec32e25a46070749de049bdf91f531352692bd588  -
```

该结论只覆盖命令列出的媒体扩展名，不声称所有非媒体过程文件未变化。

## Trigger 评测明细

评测者只接收 `.agents/skills/remix-reference-video/trigger_smoke_cases.json` 中的 12 条运营原话，不接收期望答案：

| 组别 | 样例数 | 正确数 | 结果 |
|---|---:|---:|---|
| 明确应触发 | 6 | 6 | 均选择 `remix-reference-video` |
| 明确不应触发 | 4 | 4 | 均排除该 Skill |
| Near-neighbor | 2 | 2 | “详情页文案”和“无参考片剪辑”均判为边界外 |

这是当前夹具上的人工独立前向评测，不等同于未来所有自然语言触发都达到 100%。

## 未验证与延后项

| 项目 | 当前状态 | 后续归属 |
|---|---|---|
| 完整 artifact 字段级 schema | 未实现 | Track B 统一 validator |
| 真实 Gate 顺序有效性 | 未验证 | 唯一 `manual-contract-only` pilot / G-A |
| 真实任务提速 | 未测量 | G-A 只看顺序趋势；完整配对效率在 G-B |
| 五阶段视频质量分 | 未测量 | Track B 最小快照后，Track C 产品化 |
| 缓存、索引、增量重算 | 未实现 | G-A 通过后才启动 Track B |
| 完整评分卡与看板 | 未实现 | G-B 通过后才启动 Track C |

跨文件旧口径扫描只保留两类刻意出现：文档把 `v2-contract-alpha.1` 标记为禁用短别名；检查器主动拒绝 `workflow_contract` 和 `review.contract_version` 重复别名。它们不是 active contract 值。无依据的 `production_media_changed=false` 已从产物和报告中移除。

独立规格审查随后发现并修复了 pilot 前的语义冲突：`voice_script.json` 改为批准脚本的带源哈希只读投影；pilot 即使 Gate 5 通过也禁止归档；Gate 3 输入补齐 Gate 2 原子内容包与权威覆盖报告；候选、素材物化和成片校验拆成三份不可覆盖的报告；V2 审批只使用 `decisions[]`；manifest 增加单 pilot、非生产和不可归档机器边界。上述修订完成后重新运行本报告的静态检查、最小测试和媒体摘要核验。

## 当前状态

| 指标 | 当前值 | 状态 |
|---|---:|---|
| 静态契约护栏 | 通过 | measured |
| Trigger 夹具准确率 | 12/12 | measured_on_fixture |
| 媒体摘要一致性 | 一致 | measured_on_declared_scope |
| G-A | 未通过 | gate_overreach_recorded |
| Track B | 锁定 | locked_until_g_a |
| Track C | 锁定 | locked_until_g_b |

## G-A Pilot 要求

只允许一个 owner 指定的 `manual-contract-only` V2 pilot；不得启用 Track B 执行器，不得归档到 `final/`，不得复用其他任务的批准。每个 Gate 都必须展示产物并停止。

人工前向日志至少记录：

- `measurement_method=manual_forward_log`；
- `operator_touch_seconds`、`rework_seconds`、`gate_return_count`；
- 缺素材首次发现阶段；
- Gate 3 是否只批准宽范围；
- Gate 4 是否严格执行“生成前批准 → TTS → 实测时长 → 精确裁点/累计时间轴 → 生成后听审”；
- 真实配音后是否重做 Gate 3 精确时段；
- `net_time_delta_seconds`，但不把单案例墙钟差异全部归因于 Track A。

只有 pilot 没有 Gate 越权、没有因真实音频触发 Gate 3 精确时段重做，且静态检查仍通过，才能把 G-A 提交为 `passed`。在此之前不得启动 Track B。
