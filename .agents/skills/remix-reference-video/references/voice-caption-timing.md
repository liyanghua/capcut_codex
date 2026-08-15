# 配音、字幕与时间轴规范

## 原则

- 文案来自已批准的目标蓝图和产品声明，不直接照搬参考片。
- 参考 ASR 只用于理解叙事、节奏和原意，必须人工精校。
- 已生成配音存在时，真实音频时长是画面和字幕的时间基准。
- 不通过配音变速、删字或自动填静音把语音强行拉回参考片时长。

## 文案生成与审计

TTS 文本唯一来自 Gate 4 生成前批准的 `approved_production_script.json`。`voice_script.json` 只是为 TTS 调用和字幕编排生成的确定性只读投影，必须记录 `source_approved_script_path` 与 `source_approved_script_sha256`；其文本、顺序和 span 必须与源脚本一致，哈希不匹配或投影被手改时立即停止。

`voice_script.json` 中每段必须记录：

- `fragment_id`；
- `text`；
- `approved_claim_ids`；
- `claim_evidence`；
- `forbidden_claim_hits`；
- `target_start_seconds`、`target_end_seconds`；
- `span_group_id`；
- `visual_status`；
- `review_status`。

生成前扫描 `project_brief.yaml.product.forbidden_claims`。命中任一禁用声明时，配音阶段必须停止。

不同视觉片段属于同一句完整语义时，使用同一 `span_group_id`。特别是图片与前后视频组成一句时，应先生成整句，再切分音频，不要把每个短片段合成为生硬的独立句。

## 豆包 TTS 配置

当前协议兼容实现优先支持：

1. V3 WebSocket：`DOUBAO_TTS_KEY`，资源 ID 默认 `seed-tts-2.0`。
2. 旧版 OpenSpeech：只在用户明确配置时使用 `cluster + voice_type`，凭证为 `DOUBAO_TTS_API_KEY` 或 `VOLCENGINE_TTS_APPID + VOLCENGINE_TTS_ACCESS_TOKEN`。

`DOUBAO_LITE_API_KEY` 不能自动代替 OpenSpeech 凭证。`DOUBAO_AUDIO` 可记录为 `requested_model`，但不得伪造成 `voice_type`、`speaker` 或旧协议不接受的字段。

生成前先执行预检：

- 凭证环境变量存在；
- endpoint/resource/cluster 与凭证类型兼容；
- 音色 ID 不为空；
- 语速在支持范围；
- 文案已通过 Gate 4 前的文本审核；
- 输出目录不会意外覆盖。

任一调用失败、返回空音频或输出损坏时，停止批处理，不生成不完整的 `final_voice.mp3`。错误报告不得包含凭证值。

## 分段、实测与拼接

- 默认每个独立语义段执行一次 TTS。
- 同一 `span_group_id` 只调用一次 TTS，解码为 PCM 后在低能量与零交叉附近切分。
- 组内切片无重叠、无间隙；重新拼接后应还原整句解码音频，误差不超过一个采样。
- 分段音频统一规格后再拼接。最终配音默认为 44.1kHz、双声道 MP3。
- 所有时长以 `ffprobe` 实测，`delta_seconds = actual_seconds - target_seconds`。
- `voice_manifest.json` 记录生成模式、文件哈希和 AI 生成声明。

## 时间轴重建

只有 `gate4_pre_generation=approved` 后才调用真实 TTS。TTS 完成并以 `ffprobe` 实测后，按 `fragment01 → fragmentNN` 的实际音频时长重建累计时间轴；这一步先于 `gate4_post_generation` 听审：

```text
fragment.start = previous_fragment.end
fragment.end = fragment.start + measured_audio_duration
```

不带独立语音的视觉分段必须属于已定义的 `span_group_id`，不能产生无来源的任意时长。精确裁点只能在 Gate 3 批准的 `approved_broad_range` 内收窄，并写入 `reconstruction_timeline.json`，不得修改 `fragment_plan.json` 或 `recipe.json`。用户提出删除片段时，必须返回 Gate 2 重新审核所在语义组的文案，不能只裁掉音频中间一段造成病句。

## 字幕

- 字幕文本来自 `approved_production_script.json` 的 canonical 文本；可以读取哈希匹配的 `voice_script.json` 投影，不再从 TTS 音频或旧 `script.txt` 重新猜测文案。
- 按语义断句，字数上限是上限而不是目标，避免 1–2 个字的孤立字幕。
- 每条 cue 不越过所属语义段的音频边界。
- 字幕时间单调、无重叠，使用 UTF-8 编码。
- V1/V2 默认都生成旁路 `captions.srt`，不烧录到视频，不添加字幕流；只有 Brief 和用户明确批准时才改变该策略。

## Gate 4 人工听审

运营至少检查：

- 开头是否被吞字；
- 产品名、数字、英文和专有名词发音；
- 跨片段语义是否自然；
- 最长停顿和最紧字幕边界；
- 句尾是否完整；
- 音色、语速和品牌调性。

首次确认只能将最终生产脚本、协议/模型、音色和语速状态设为 `script_approved`，此前不得调用真实 TTS。TTS 生成后，运营还必须确认实际音频、分段时长、累计时间轴、精确裁点、字幕边界、停顿和听审风险。两次决定都完成后，Gate 4 汇总状态才能为 `approved`。
