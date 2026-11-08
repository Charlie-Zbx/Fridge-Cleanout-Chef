# 克隆后在本地试用

仓库为私有，需维护者授予访问权限后才能克隆。仅上传源码和技术资料，不包含维护者的密钥、库存、原始照片或运行环境。当前没有在线服务，队友可以先在本机运行离线模式。

## Windows / PowerShell

准备 Python 3.12 和 Node.js 24（包含 npm），在你选择的目录执行：

```powershell
git clone https://github.com/Charlie-Zbx/Fridge-Cleanout-Chef.git
Set-Location Fridge-Cleanout-Chef
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock.txt -e '.[dev]'
New-Item -ItemType Directory -Path .tmp -Force | Out-Null
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Push-Location frontend
npm ci
npm run build
Pop-Location
$env:KITCHEN_ENABLE_LIVE = '0'
.\.venv\Scripts\python.exe -m kitchen
```

打开 http://127.0.0.1:8000，点击“用三种食材体验一下”。关闭终端或按Ctrl+C结束。之后可双击根目录启动脚本；更新前端后再次运行 npm run build。维护者自己的 scripts/build.ps1 使用其本地 .tools 运行时，普通克隆请使用上面的 npm 命令。

离线模式仍运行LangChain与真实MCP，决策使用可重复的模拟模型；不会因创建.env或启动服务而自动调用DeepSeek。照片识别需真实模型，因此离线试用使用手动盘点。

## 检查

在另一个终端的项目根目录执行：

```powershell
$env:KITCHEN_ENABLE_LIVE = '0'
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = (Resolve-Path .tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\freeze_benchmark.py
.\.venv\Scripts\python.exe scripts\evaluate_offline.py --suite artifacts\benchmark-v2-contexts.json
```

测试默认关闭真实调用。原始公开照片未包含在仓库；依赖这些原图的独立实验需要另行准备，不能将缺失的照片替换成私人图片后直接上传。浏览器回归使用Microsoft Edge和隔离测试数据库，详见README。

## 真实试用

只有在维护者明确批准调用预算后，才在自己的本地.env或服务器环境变量中配置密钥并开启真实调用。密钥不要写进React代码、Git提交、Issue、截图或聊天。`.env.example`仅保留空值与示例配置。

源码仓库和云服务独立；不要直接根据render.yaml开通收费服务。团队共同在线试用需要维护者另行完成部署、访问限制与预算配置。
