# 参考视频复刻 V2 新版本基线报告

更新时间：2026-08-16  
实现分支：`codex/remix-production-backend`  
Skill / contract：`2.0.0-alpha.1`  
基线任务：`work/2026-08-16-gb-pair-real-2/`

## 1. 结论先行

本报告把 2026-08-16 的真实 Native Runner cold/hot 配对定义为 **V2 可复现生产基线 v0**。以后代码、Skill、缓存和流程的改动，优先与这次基线比较，不再把无法按同一冻结输入重新执行的历史 V1 任务作为严格性能对照。

这次基线已经证明：

- cold 和 hot 都能从正式 CLI 进入真实 Native Registry，独立跑完 Gate 1–5；
- 使用了真实 `ffprobe`、`ffmpeg` 和豆包 TTS，产出可播放竖屏成片；
- 每次审批绑定各自任务的审核包哈希、`run_id` 和 `state_revision`，没有跨运行复用审批；
- Gate 3 宽范围、Voice Preflight、真实配音时长、精确裁点和最终渲染已经形成闭环；
- cold/hot 的最终技术校验均通过，成片规格符合 1080×1920、60fps、H.264/AAC；
- 机器/API 关键路径分别为 32.178 秒和 36.183 秒，远低于原设计的 cold 13 分钟、hot 8 分钟硬门槛。

这次基线还没有证明：

- V2 的五阶段业务质量分达到 88 分以上；当前没有完整 Track C 评分卡，质量分必须记为 `not_scored`；
- hot 的整条机器路径已经比 cold 更快。热索引步骤明显变快，但 TTS、渲染和其他波动使 hot 总关键路径暂时比 cold 长 4.005 秒；
- 一线运营从提交 Brief 到拿到预览的完整墙钟稳定低于一小时；本次人工等待、运营触达和返工没有被完整记录；
- 原设计中“V1/V2 同输入非回退”的严格 G-B 对照条件尚未满足。历史 V1 只能作为回溯背景，不作为本次严格比较对象。

因此当前发布结论是：**V2 新版本基线已建立，真实生产后端可用性已验证，G-B 仍为 `measured_pending_review`；普通 V2 生产、共享生产缓存和一线开放继续保持关闭。**

## 2. 为什么采用新版本作为基线

历史 V1 任务 `work/2026-08-11-douyin-tablemat-01/` 是人工路径形成的旧产物，缺少可重复的执行器、统一阶段计时、独立审批记录和严格的冷/热缓存定义。直接重新执行旧脚本会把新环境、新实现或新 API 状态混入 V1，生成一个表面可比、实际不可比的数字。

本报告采用的规则是：

1. 历史 V1 保留为 `retrospective_baseline`，只用于说明旧流程的问题和量级；
2. 本次真实 V2 配对作为 `measured_baseline_v0`，用于以后版本的前向回归；
3. 新版本后续每次比较必须复用同一冻结参考片、Brief、素材快照、文案、TTS 设置和输出规格；
4. cold 必须从空缓存开始，hot 只能复制声明的 cold 技术缓存，不能复制状态、审批、媒体或输出；
5. 两次运行都必须重新生成并批准自己的审核包，不能因为输入相同而复用另一运行的批准；
6. 质量分、机器时间、人工等待、运营触达、返工和 Gate 返回分别记录，不能用其中一项替代另一项。

这使基线从“旧系统和新系统的历史争论”变成“同一新系统的可重复回归测试”。它不能追溯性地让原 G-B 规则通过，但能为后续版本提供可靠的工程基准。

## 3. 基线输入与证据

### 3.1 运行身份

| 项目 | cold | hot |
|---|---|---|
| run_id | `gb-cold-1786867165` | `gb-hot-1786872405` |
| 任务目录 | `work/2026-08-16-gb-pair-real-2/cold/` | `work/2026-08-16-gb-pair-real-2/hot/` |
| state revision | 68 | 74 |
| Gate 1–5 | 全部 `approved` | 全部 `approved` |
| 归档 | 明确禁止 | 明确禁止 |
| production mode | `track-b-production` | `track-b-production` |

### 3.2 冻结输入

两侧均由各自的 `g_b_frozen_input_snapshot.json` 记录参考片、Brief、素材画像和源素材快照。hot 不读取 cold 的 `pipeline_state.json`、decisions、审核包、媒体输出或绝对源路径。

关键产物路径：

- 测量记录：[gb_measurement.json](/Users/yichen/Desktop/OntologyBrain/capcut_codex/work/2026-08-16-gb-pair-real-2/gb_measurement.json)
- cold 状态：[cold/pipeline_state.json](/Users/yichen/Desktop/OntologyBrain/capcut_codex/work/2026-08-16-gb-pair-real-2/cold/pipeline_state.json)
- hot 状态：[hot/pipeline_state.json](/Users/yichen/Desktop/OntologyBrain/capcut_codex/work/2026-08-16-gb-pair-real-2/hot/pipeline_state.json)
- cold 成片：[cold/remix.mp4](/Users/yichen/Desktop/OntologyBrain/capcut_codex/work/2026-08-16-gb-pair-real-2/cold/remix.mp4)
- hot 成片：[hot/remix.mp4](/Users/yichen/Desktop/OntologyBrain/capcut_codex/work/2026-08-16-gb-pair-real-2/hot/remix.mp4)

本次基线登记的关键 SHA-256：

| 产物 | SHA-256 |
|---|---|
| cold `pipeline_state.json` | `8d2d7278e107155521d093a3663d1ba064418c7a2f94f61a62251c0475b2ac13` |
| hot `pipeline_state.json` | `0e6f54fbcf91d946be1bcab776de663ead8c9c90ae5d4c944d6ff9c57e85d76f` |
| cold `remix.mp4` | `9c13763c64694e6199453791b68f504e9d7c5ac0aa657e5674cfab6c84d0e259` |
| hot `remix.mp4` | `2d0d4c9dcbf062b8db4807a4e9790ad8d9365f4212b673619c5785ffee4175d3` |
| cold/hot `final_validation_report.json` | `c3afab94c269d7a910f5e98aef9ed72dbddfbbb6032507ac2e21fc553ff7daf9` |

## 4. 真实生产结果

### 4.1 成片技术结果

| 指标 | cold | hot | 基线判断 |
|---|---:|---:|---|
| 最终时长 | 27.720s | 27.552s | 同一文案和设置下存在约 0.168s TTS/时间轴波动，均可接受 |
| 画面 | 1080×1920 | 1080×1920 | 通过 |
| 帧率 | 60fps | 60fps | 通过 |
| 视频编码 | H.264 | H.264 | 通过 |
| 音频编码 | AAC | AAC | 通过 |
| 最终校验 | `passed` | `passed` | 通过 |
| Gate 5 包 | 已生成并登记 | 已生成并登记 | 通过 |

### 4.2 素材与证据结果

- 11/11 个片段为 `matched`，没有用无关素材凑数；
- 当前候选置信度为 0.934。它只能证明匹配器的候选评分，不等价于视频质量分；
- `fragment05` 使用批准范围 7.3–8.8 秒，`fragment07` 使用批准范围 0–2.8 秒，均未越过源视频时长；
- 所有画面按审批保留源文字/水印，不做顶部或底部遮盖；
- `fragment03/04` 只承载已批准材质声明，`fragment08` 保持观察性表述，`fragment09` 保留完整保障条款；
- 全部片段播放速度为 1.0x，没有自动变速，也没有冻结尾帧补齐。

### 4.3 Voice Preflight 与时间轴结果

新链路固定为：

```text
Gate 3 宽范围
→ 画面时长预算
→ voice_preflight
→ Gate 4 生成前批准
→ TTS
→ 实测时长校验
→ 精确裁点与累计时间轴
→ Gate 4 生成后批准
→ 代理检查与正式渲染
```

本次 hot 的预检 11/11 通过；最紧的可比视频片段包括：

| 片段 | 画面预算 | 预估配音 | 预估余量 | 实测/结果 |
|---|---:|---:|---:|---|
| fragment05 | 1.500s | 1.437s | 0.063s | 1.464s，未越界 |
| fragment07 | 2.800s | 2.622s | 0.178s | 2.256s，未越界 |
| fragment11 | 3.100s | 3.057s | 0.043s | 通过 |

这证明“先检查画面预算，再调用 TTS”的约束已经进入真实 Runner，而不是只存在于设计文档中。

## 5. 效率基线

### 5.1 可确认的机器/API 时间

| 指标 | cold | hot | 解释 |
|---|---:|---:|---|
| machine/API critical path | 32.178s | 36.183s | 从阶段计时累加；不是 `gb_measurement.json` 写入命令本身的 1ms |
| 设计硬门槛 | ≤780s | ≤480s | 两者均通过 |
| 距离硬门槛余量 | 747.822s | 443.817s | 仅代表机器层余量 |
| Gate 返回 | 0 | 0 | 本次 invocation 无 Gate return |
| 受控返工 | 0s | 0s | 本次 invocation 无记录 |
| 审批等待 | 未测量 | 未测量 | 缺少可信 operator Gate 时间戳 |
| 运营触达 | 未测量 | 未测量 | 缺少操作日志 |

### 5.2 缓存结果的正确解读

本次 hot 使用了 cold 完成后的声明 SQLite cache，并且 cache 根目录与审批、状态、媒体输出隔离。`index-assets` 的阶段耗时由 cold 约 0.419s 降到 hot 约 0.006s，说明共享索引复制和增量索引路径可工作。

但不能把这一次写成“hot 整体提速”：

- stage metrics 中 hot 的 `index-assets` 仍记录为 `cache_status=miss`，说明缓存命中语义和汇总指标还需要统一；
- TTS、代理渲染和正式渲染具有外部服务/编码波动，hot 总关键路径比 cold 长 4.005s；
- 下一次基线应分别记录 `cache_hit_rate`、`index_reuse_seconds`、TTS、proxy、render 的耗时，不以单一总秒数判断热缓存收益。

### 5.3 完整墙钟的边界

按 `stage_metrics.jsonl` 的记录时间，本次从首次阶段记录到 Gate 5 包生成大约是 cold 79 分钟、hot 71 分钟；这不是可审计的完整运营墙钟，因为其中混有人工审批、网络重试、范围确认和未结构化的等待。Gate 5 决定本身也没有被写成完整 operator timing。

因此“一小时内生成”当前应拆为两个结论：

- **机器层：已达到**，cold/hot 均远低于 13/8 分钟门槛；
- **运营层：未完成验收**，还需要在真实一线操作中采集 Brief 提交、每次 Gate 展示、审批和最终预览的可信时间戳。

## 6. 五阶段效果评估

本次不生成虚假的 V2 质量分。按照当前评分契约，五阶段和视频总分均记为 `not_scored`，原因是 Track C 的逐项 `earned_points/max_points/evidence_paths/reason` 评分卡尚未由 owner 完成审核。

| 业务阶段 | 当前可确认事实 | 当前质量分状态 | 审批/流程状态 |
|---|---|---|---|
| Performance-proven Video | 参考片切分、关键帧、音轨和 recipe 真实生成，Gate 1 通过 | `not_scored` | `approved` |
| Blueprint | 目标结构、内容基线、声明边界和时长包络绑定 Gate 2 | `not_scored` | `approved` |
| Controlled Mutation | mutation、fallback、声明禁用和生产脚本候选被机器校验 | `not_scored` | Gate 2 契约已锁，Gate 4 生成前已通过 |
| Retrieval | 11/11 matched，证据闭环、宽范围、叠字策略和重复检查通过 | `not_scored` | Gate 3 两个子状态均 `approved` |
| Reconstruction | TTS、实测时间轴、SRT、代理、正式渲染和 Gate 5 包通过 | `not_scored` | Gate 4/5 均 `approved`，归档仍抑制 |
| 视频总分 | 无完整 Track C 评分卡 | `not_scored` | `review_required` |

这不是对视频效果的否定，而是对证据边界的准确记录：当前可以确认“生产完整性和技术约束通过”，不能据此推断播放量、转化率或爆款概率，也不能把 0.934 候选置信度换算成质量分。

## 7. 相对历史 V1 的可用信息

历史 V1 的 69 分、约 277 分钟回溯墙钟和各阶段回溯分继续保留，但统一标记为 `retrospective_baseline`。它们可用于解释优化方向：

- V1 的画面预算与真实配音时长约束发现偏晚；
- V1 缺少统一审批服务、状态 revision、缓存隔离和阶段计时；
- V1 的素材覆盖、声明边界和证据闭环依赖人工整理；
- V1 的媒体产出可以作为历史样片，但不能作为本次 V2 质量非回退的严格对照。

因此本报告不计算“V2 比 V1 提升了多少百分比”。这类百分比需要同一冻结输入下的可复现 V1 执行，当前没有该证据。

## 8. 当前风险与补齐项

### P0：影响 G-B/发布判断

1. 完成 Track C 五阶段逐项评分，生成合法的 `phase6_score_snapshot.json`；
2. 把 cold/hot 的人工等待、运营触达、TTS 重试、Gate 返回和返工时间写入可信事件；
3. 修正 `cache_status` 与 cache hit 汇总语义，补跑至少 3 次 cold/hot，报告中位数和离散度；
4. 修正 `gb_measurement.json` 的 `approvals_recorded=0` 汇总问题：两侧实际存在独立 Gate 决定文件，但测量摘要没有统计到它们；在修复前不得把该字段当作审批数量证据；
5. 由 owner 明确接受“新 V2 基线替代旧 V1 严格对照”的验收决定，并更新 G-B 判定记录。

### P1：影响一线可用性

1. 先做监督运营试用，再开放普通 V2 生产；
2. FastAPI/SSE 真实 optional-extra 路由测试补齐；
3. 将当前业务摘要、Gate 待办、缺素材和 voice_preflight 阻断原因接入 Backlot 式进度展示；
4. 把基线输入快照和运行摘要固化为 CLI 的 `baseline-check`/`compare` 只读命令，避免人工抄表。

### P2：影响长期质量评估

1. 固化镜头分类词典、素材时间段索引和证据矩阵的质量 rubric；
2. 采集运营首轮通过率、返工率、Gate 返回率和成片人工评分；
3. 以三次以上重复运行建立 TTS、FFmpeg 和缓存的正常波动区间。

## 9. 后续版本的比较协议

以后任何 Runner、adapter、TTS、渲染或缓存改动，都按以下顺序比较：

1. 读取本报告和 `gb_measurement.json`，确认输入快照完全一致；
2. cold 使用空缓存，hot 使用经验证的基线 cache snapshot；
3. 每个运行创建新的 `run_id`、state revision、审批包和输出目录；
4. 记录五类时间：机器/API、人工等待、运营触达、返工、网络重试；
5. 先比较硬门禁：Gate 顺序、审批隔离、哈希绑定、时间轴包含、媒体规格和归档抑制；
6. 再比较效率：P50/P95 阶段耗时、cache hit、TTS/渲染耗时和完整墙钟；
7. 最后比较质量：使用同一 rubric 的五阶段评分和人工审片结论；
8. 任一硬门禁失败时，即使总耗时更短，也判定为回归。

## 10. 最终状态

| 状态项 | 当前值 |
|---|---|
| V2 新版本基线 | `established_v0` |
| 真实 cold/hot 生产 | `passed` |
| 机器/API 13/8 分钟门槛 | `passed` |
| 五阶段质量分 | `not_scored` |
| hot 整体缓存提速 | `not_proven` |
| 一小时完整运营墙钟 | `not_measured` |
| G-B | `measured_pending_review` |
| 普通 V2 生产 | `locked` |
| 一线运营开放 | `blocked_until_supervised_trial` |

**建议 owner 现在批准的事项只有一个：接受本次 V2 真实配对作为后续回归基线。** 这项批准不等同于 G-B 通过，也不解除普通生产锁；质量评分、运营试用和缓存收益验证仍按上文补齐。
