# 余味 · 冰箱清库存厨师 v0.2

**LangChain + 真实 MCP + DeepSeek 官方 API** 的课程项目。仓库提供源码、依赖清单、自动化测试与技术文档。密钥、用户数据、原始照片和本机运行环境不随代码上传。

## 启动和体验

首次克隆请先按 [本地安装说明](docs/LOCAL_SETUP.md) 安装 Python/Node 依赖并构建网页。离线演示不需要 API key；GitHub 仓库链接本身不提供在线应用，公网服务尚未开通。

双击 **启动本地项目.cmd**，再打开 **http://127.0.0.1:8000**。关闭窗口或按 Ctrl+C 停止。默认离线模式，无需云服务，也不会因为填写了密钥就调用模型。

当前可体验 1–5 人、1–2 顿、每顿最多三道菜；自然语言确认卡片、手动盘点、真实 MCP 检查与离线重规划、实际用量确认、过程记录和手机界面。

首次使用点击“用三种食材体验一下”。自然语言离线规则可试“改成五个人吃，每顿45分钟”；五人库存不足时拒绝方案是正确行为。“手动核对剩余”会更新剩余数量，不会自动累加。拍照新增与冰箱盘点为两个入口，每批1–3张图片。

**真实Agent已通过“一人→五人→每顿20分钟”的连续变更测试：发现超时后修改方案，时间进一步缩短时返回无解。**修改后的照片提示已真实测试，能将后方不明瓶罐单列未知，但标签和品类仍有误判。配方与1–5人时间表目前都是开发示例，等待团队审核和实际做饭验证；真实试用和完整照片评价尚未完成。

最新检索优化在同一无解场景中从5次模型/3次检索降为1次模型/1次检索；只在MCP全库结果经宿主复核确实无可行单菜时终止。成功的重复工具结果仅在当前任务内复用，执行记录区分真实调用与缓存。三张新照片及一组双图也已测试，仍需人工核对种类和数量，详见最新实测报告。

## 文档

- [新版功能、接口与测试](docs/V2_GUIDE.md)
- [团队菜谱、照片、实做与试用准备](docs/TEAM_HANDOFF.md)
- [部署与备份恢复](docs/DEPLOYMENT.md)
- [当前进度与下一步](docs/STATUS.md)
- [正式评估协议与指标](docs/EVALUATION_PROTOCOL.md)
- [答辩演示脚本](docs/DEMO_RUNBOOK.md)
- [最终报告证据底稿](docs/REPORT_EVIDENCE.md)
- [照片种类确认实测与蛋盒计数修复](docs/LIVE_IDENTITY_TEST.md)
- [新版真实需求理解与五人规划测试](docs/LIVE_TEST_V2.md)
- [公开冰箱照片与单次视觉测试](docs/PHOTO_TEST.md)
- [修改后照片提示与连续需求变更实测](docs/LIVE_CHANGE_TEST.md)
- [检索优化与新照片测试批次](docs/AGENT_EFFICIENCY.md)
- [检索优化和新照片的真实结果](docs/LIVE_EFFICIENCY_TEST.md)
- [首次真实 Agent 测试原始记录](docs/LIVE_TEST.md)

## API 调用控制

密钥仅放本地 .env 或服务端环境变量。KITCHEN_ENABLE_LIVE 默认0；网页每次真实操作还需要单独确认。规划最多6次模型请求、12次工具调用、90秒；需求整理最多1次、每批照片最多1次，不自动重试。

网页服务默认全局最多2个同时执行的交互任务；每个厨房最多1个。每日每用户20次、全局100次模型请求尝试，UTC日期计数，写入SQLite后再发送请求。失败的请求也计数。真实测试、图片上传和收费部署均需事先明确授权。

## 技术与数据

React 手机网页 → FastAPI/SQLite → LangChain 主Agent → MCPAdapter/stdio → Kitchen MCP Server。DeepSeek提供理解与决策，程序计算库存和硬约束。检查工具没有库存修改权限。

任务状态、用户厨房、提案、确认回执、每日额度和完整任务版本在 data/kitchen.db；LangGraph执行检查点在 data/checkpoints.db。用户通过浏览器 HttpOnly Cookie 隔离，清除Cookie会失去原厨房凭据，第一版不做账号找回。

每次规划只注入当前已确认状态与上一版摘要，独立保存执行检查点；避免长期追加过期工具输出。原有1–2人数据可继续读取，数据库启动时增加新表及配方审核版本列，不清空现有库存。

团队审核独立于个人审核；菜谱改版后旧个人审核失效。库存变更会使旧计划要求重新核对，确认第一顿实际消耗后也会检查剩余餐次。配方审核、实做记录、用户反馈分别记录。

## 本地检查

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
.\.venv\Scripts\python.exe scripts\evaluate_offline.py --suite artifacts\benchmark-v2-contexts.json
```

后端测试、离线场景和浏览器测试均不调用真实API。浏览器测试使用独立无头Edge，启动测试服务前把 KITCHEN_DATA_DIR 指向 .tmp 内的专用目录，避免修改自己的厨房。截图和评估结果保存在 artifacts。

新克隆不包含 artifacts；先运行 `python scripts/freeze_benchmark.py` 生成离线场景。公开照片原图也未上传，需要图片的可选测试会跳过或提示缺少本地材料；固定响应夹具仅用于离线回归。

scripts/benchmark_live.py 默认dry-run；20个冻结场景的三组真实对照最多260次请求，需另行批准，不能把离线规则结果当作真实模型评估。详细用法见新版指南。

## 部署状态

Render配置与Dockerfile已准备，服务没有创建，容器构建待验证。云端使用单实例、单worker及持久磁盘；开通收费服务前另行确认。

不要把 .env、原始照片、数据库、运行环境或测试产物提交到仓库。技术文档中的历史测试摘要保留；其引用的本地原始产物不随仓库上传。

## 本轮交付完善

照片确认提供本地原图对照和逐项种类核对；不确定或矛盾的种类清空预选。确认前不入库，确认盘点不会重置页面用餐条件。浏览器连续流程使用模拟视觉和离线模型，真实MCP执行；不把该回归写成真实照片准确率或真人试用。

`python scripts/prepare_delivery.py` 生成队友工作包：可打印审核册、配方工作副本、空的照片/实做/试用记录以及仅源码ZIP；不会将配方自动标为审核。`python scripts/verify_container.py` 只检查Docker可用性，Docker启动后可用`--run`验证本地容器持久化。两者均不调用模型。
