# 受限试用部署与恢复

当前没有创建云服务。render.yaml 是待确认的配置：单个付费 Web Service、1GB持久磁盘、单实例、一个 Uvicorn worker。不要增加 worker：当前并发控制和后台任务运行于一个进程。

## 部署前

1. 完成真实模型和图片的小批联调、团队配方审核。
2. 验证 Docker 构建与容器启动。本轮检测到本机有 Docker CLI，但 Docker Desktop Linux 引擎未运行，尚未做容器验证。
3. 准备只含源码的私有仓库；.env、数据库、运行环境、原始照片、测试产物和本地文档不上传。不要直接上传整个工作文件夹。
4. 用户确认收费服务方案后，才在 Render 创建服务。密钥通过服务端环境变量配置。

## 配置

- KITCHEN_DATA_DIR=/var/data，挂载持久磁盘，保存业务数据库与检查点。
- KITCHEN_PUBLIC=1、KITCHEN_SECURE_COOKIE=1，并设置强随机 KITCHEN_ACCESS_CODE；缺少访问码或安全Cookie时公开模式拒绝启动。
- KITCHEN_ENABLE_LIVE 初始为0；用户另行批准试用预算后再开启。
- 默认每天每用户20次、全局100次模型请求尝试，UTC日期边界，重启不清零；按试用预算调整。
- 同一个服务提供静态网页与API。PORT 由平台注入；健康检查 /api/health。
- 修改访问码只影响新建会话，已有30天会话仍有效。结束试用时先关真实调用；需要撤销已有访问时停服务并由维护者清理相应会话，不把更改访问码当作强制退出。

上线验收：访问码错误不能进入；新浏览器厨房隔离；HTTPS手机访问；重启后库存与配方审核保留；进行中的任务变为中断且不自动重发；额度耗尽前阻止新请求；服务端密钥不出现在前端资源或响应中。确认无误后再发试用链接。

## 本地容器验收与源码打包

`python scripts/verify_container.py` 仅检查Docker是否可用；本轮仍返回engine未运行，未构建镜像。启动Docker Desktop的Linux引擎后，运行 `python scripts/verify_container.py --run` 执行隔离的本地构建和测试：访问码拒绝、库存写入后重启保留、新浏览器厨房隔离、真实调用关闭。默认使用本机8012端口；不注入.env或API密钥，不创建云服务。测试容器和临时卷自动清理，构建镜像留存，报告写入artifacts。此检查不替代公网HTTPS手机试用。

`python scripts/prepare_delivery.py` 还会生成source-only.zip和SHA-256清单。使用白名单收集源码、依赖清单、测试和文档，不含.env、数据库、原始照片、虚拟环境或评估产物。生成ZIP不是发布；仍需确认云服务后再上传。课程提交所需的去标识化实验记录另行整理，不能将源码包当成完整研究结果。

## 备份与恢复

先停止服务，确保两个数据库与业务状态一致。使用项目Python：

```powershell
.\.venv\Scripts\python.exe scripts\backup.py backup --source data --destination backups\snapshot-01 --service-stopped
.\.venv\Scripts\python.exe scripts\backup.py restore --source backups\snapshot-01 --destination data-restored --service-stopped
```

脚本调用SQLite backup API并检查完整性；目标已有数据库时拒绝覆盖。恢复到新目录后，将KITCHEN_DATA_DIR改为该目录，再启动并核对库存、记录与授权开关。不要删除原数据来试验恢复。

部署前、配方大改前、数据库变更前各保留一份备份。测试结束后保留去标识化评估数据，原始照片和试用数据由团队按参与者意愿管理。原图默认不在服务端保存。
