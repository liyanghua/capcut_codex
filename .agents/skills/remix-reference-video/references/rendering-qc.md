# 渲染、字幕与成片验收

## 输入前置条件

正式渲染前必须满足：

- `gate_status.gate1`、`gate_status.gate2`、`gate3_material_selection`、`gate3_evidence_closure`、`gate4_pre_generation` 和 `gate4_post_generation` 均对当前输入哈希为 `approved`，且 `stages.reference_split.status`、`stages.content_blueprint.status` 均为 `approved`；Gate 3/Gate 4 汇总状态不得由单个子状态伪造，也不得用手工 Gate 映射绕过 Gate 1/2 业务阶段汇总；
- `fragment_plan.json` 中没有 `missing_material`，且 `reconstruction_timeline.json` 的精确裁点全部 containment 在 Gate 3 批准宽范围内；
- 所有生产素材位于 `material/fragmentNN/`；
- `material_manifest.json` 已记录物理复制/导出和副本 SHA；
- 每份素材路径、SHA-256 和时段范围验证通过；
- 叠字、品牌、水印已有 `keep`、`crop`、`cover` 或 `replace` 决定；
- 使用配音时，`approved_production_script.json`、`final_voice.mp3` 和实测时间轴已通过验证；V2 不从 `recipe.json` 读取替换配音时间轴。

审核占位模式只能在用户明确要求时开启，输出必须带有 `review_with_placeholders` 状态，不得进入 `final/`。

## 视觉时间轴

- 配音存在时，使用配音实测时长；否则使用已批准蓝图时长。
- 将累计时间边界转为目标帧，不对每段独立四舍五入。
- 视频定格、裁切和采样不得越过源媒体真实范围。
- 视频播放速度默认 `1.00x`。
- 素材短于所需时长时，先在已批准的同源范围内扩展；仍不足则返回 Gate 3。
- 禁止使用长时间尾帧冻结隐藏素材不足。仅允许不超过 2 帧的编码/舍入补齐。

## 画面处理

- 默认输出 9:16、1080×1920、60fps；单次 Brief 可覆盖。
- 视频和图片按「保持比例缩放 + 裁切或填充」适配，不拉伸主体。
- 图片默认使用稳定静帧，不使用 `zoompan` 或逐帧浮点缩放，避免内嵌文字和产品边缘抖动。
- 一张静态图或同一感知哈希内容不得重复承载多个卖点，除非用户明确批准。
- 默认使用硬切。只有边界 QA 确认存在跳变或卡顿感时，才对该边界使用 2–3 帧短叠化。
- 输出统一为 BT.709 和单一最终 H.264 编码链，避免分段独立编码导致颜色和时基跳变。

## 音频与字幕

- 去除生产素材的原音轨，除非 Brief 明确要求保留环境声。
- 最终视频仅保留一条视频流和一条音频流。
- 最终音频默认 AAC、44.1kHz、双声道。
- 视频和音频播放时长差应不超过一帧；报告应区分编码器尾部 padding 与真实时间轴错误。
- 字幕保存为 UTF-8 `captions.srt`，不烧录，不嵌入字幕流。

## `render_report.json`

报告至少包含：

- 输入文件路径和 SHA-256；
- 帧率、分辨率、帧数、编码和色彩参数；
- 音频采样率、声道和编码；
- 片段时间轴和每个边界的转场决定；
- 源叠字/品牌清单；
- 重复素材和重复卖点检查；
- 占位、缺素材和过期产物状态；
- 自动验收结果与待人工审核项。

同一轮还必须生成 `final_validation_report.json`，作为 Gate 5 硬门禁的不可变结果；它不得覆盖 Gate 3 的 `match_validation_report.json` 或素材物化后的 `material_validation_report.json`。

正式输出原子提升后，适配器必须更新 `pipeline_state.json`：登记 `remix.mp4`、`final_validation_report.json`、`render_report.json`、`jianying_import_manifest.json` 的 SHA-256，把 `current_stage` 设为 `final_review`、`stages.render.status` 与 `stages.final_review.status` 设为 `awaiting_user`，并保持 `gate_status.gate5=awaiting_user`。状态回写失败时清理本轮新文件并恢复原状态；`pipeline_state.json` 未登记时不得提交 Gate 5 审核包。

## `jianying_import_manifest.json`

V1/V2 的默认交付都用导入清单代替不可靠的加密草稿伪造；只有专用适配器和用户明确要求时才生成可编辑草稿。清单记录：

- 画布、帧率和总时长；
- 每个视觉片段的素材路径、源时段和目标时段；
- 配音和 SRT 路径；
- 轨道顺序、转场和裁切方式；
- 文件哈希和人工导入检查项。

清单必须声明 `editable_draft_generated=false`。只有真实通过剪映打开验证的新建可编辑草稿，才能将该值改为 `true`。

## Gate 5 审片清单

运营必须检查：

- 开头钩子和结尾 CTA 是否完整；
- 产品、卖点和动作是否一致；
- 是否出现重复静态图、重复房间或重复卖点；
- 图片是否抖动；
- 边界是否卡顿、闪黑或色彩跳变；
- 音画、字幕和口播是否对齐；
- 源叠字和品牌是否按决定处理；
- 成片中是否存在任何未批准声明。

普通生产任务通过 Gate 5 后才能归档。`manual-contract-only` pilot 即使 Gate 5 通过也只保留在 `work/` 作为 G-A 证据，不进入 `final/`。返工时必须回到最早的受影响阶段，例如素材问题回 Gate 3，文案/发音问题回 Gate 4；需要删并段、改声明或重排时回 Gate 2。
