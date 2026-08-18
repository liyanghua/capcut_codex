# 业务视频工作区人工验收记录

日期：2026-08-18  
实现分支：`codex/business-video-workbench`  
当前默认模式：`legacy`  
工作区模式：`WORKBENCH_UI_MODE=workspace`

## 验收范围

- 页面结构：故事板、关键元素、分镜、音频、未归类素材、中央预览、三轨时间线、五阶段决策助手。
- 状态：加载中、缺失、阻塞、等待审核、完成、revision 更新和 legacy 回退。
- 决策：通过、驳回原因、要求修改、影响预览和当前 run/revision 绑定。
- 安全：工作区媒体 allowlist、路径 containment、ETag/304、生产锁和审批权威不变。

## 自动化证据

- workspace projection/schema：通过（9 项 focused tests）。
- API、媒体边界、ETag/304、页面模式：通过（FastAPI TestClient 8 项）。
- 决策守卫：通过（通过阻塞、驳回原因、幂等和冲突测试）。
- JavaScript：`node --check` 通过。
- Skill 全量：待最终合并前执行。

## 1440px 桌面

状态：`awaiting_manual_operator`

操作：启动服务后将浏览器窗口设为 1440px 宽，打开 `/workbench/runs/<run-id>`，逐项核对：

1. 三列布局无横向滚动；左侧故事板卡片可选中。
2. 选中分镜后，中央媒体和底部画面轨同步变化。
3. 预览播放、暂停、时间线定位可用；时间线没有拖拽写入能力。
4. 右侧五阶段进度、依据、风险、下一步和三个决策按钮完整可见。
5. 阻塞时“通过”禁用；驳回无原因不能提交；要求修改必须先显示影响预览。

记录：

- 结果：待运营手动确认
- 备注：

## 390px 窄屏

状态：`awaiting_manual_operator`

操作：将浏览器窗口设为 390px 宽，重复桌面检查，并额外核对：

1. 故事板、预览、决策区按纵向顺序显示，正文无溢出遮挡。
2. 分镜标题、风险和按钮文字均在容器内换行。
3. 时间线可横向查看但不改变任何事实产物。
4. 对话框在视口内，原因和影响预览可读。

记录：

- 结果：待运营手动确认
- 备注：

## 回退验证

使用 `WORKBENCH_UI_MODE=legacy` 重启服务，页面应加载独立的 `review_workbench_legacy.js` 和 `review_workbench_legacy.css`，原有七 Gate DOM 和决策 API 保持可用。回退不应修改 `pipeline_state.json`、审批、缓存或生产锁。

当前结论：自动化实现已完成；在运营完成上述两个视口的人工记录前，不切换默认模式到 `workspace`。
