# 7-Agent

基于 Python、FastAPI、Next.js 和 Electron 的 AI Agent 项目，提供 Web 对话界面、可扩展工具与技能，以及飞书桌面执行能力。

> 当前为开发版本。仓库尚未包含所有本地技能模块，首次部署前请先阅读下方的「已知限制」。本文描述已提交代码，不代表本地尚未提交的开发功能。

## 功能概览

- **多模型对话**：Web 后端支持 DeepSeek、Kimi 和 OpenAI 兼容接口；独立命令行入口使用 Anthropic。
- **工具与技能**：提供文件操作、浏览器自动化、代码执行、文档处理等能力，并可加载 Markdown 技能。
- **MCP 扩展**：连接外部 MCP 服务，扩展 Agent 可调用的工具。
- **会话与知识管理**：提供会话、记忆、知识库、定时任务和技能管理接口。
- **账户系统**：邮箱验证码注册与登录，用户信息保存在 MySQL。
- **飞书集成**：通过 Lark CLI 处理消息、文档、日历和任务；桌面客户端可连接后端执行 CLI 请求。

部分工具依赖第三方服务、额外授权或特定操作系统，配置模型密钥并不意味着所有工具都能直接使用。

## 项目结构

```text
agent/                     Agent 核心、模型适配、工具、技能及 MCP 客户端
backend/                   FastAPI 服务、认证、存储和业务路由
frontend/                  Next.js Web 界面
desktop/                   Electron 客户端及 Lark CLI 运行环境
tests/                     Python 测试
docs/                      部署和实现说明
main.py                    独立命令行对话入口
.env.example               本地后端配置模板
.env.server.example        Docker 服务端配置模板
docker-compose.server.yml  Web、API 及数据库服务编排
```

Web 与 Electron 使用同一个 API 服务。模型调用及数据库访问在后端完成；桌面客户端通过 WebSocket 连接 API，承担客户端侧的飞书 CLI 执行。

## 环境准备

仓库 Docker 配置使用 Python 3.13 和 Node.js 22，可按相同版本准备本地环境。

| 依赖 | 用途 |
| --- | --- |
| Python 与 pip | Agent、API 与 Python 测试 |
| Node.js 与 npm | Web 前端及 Electron |
| MongoDB | 会话及业务数据 |
| MySQL | 用户、认证及飞书账户数据 |
| Redis | 定时任务服务 |
| Playwright Chromium | 浏览器自动化工具 |
| SMTP 服务 | 注册验证码邮件 |

Compose 中对应的数据库镜像为 MongoDB 8、MySQL 8.4、Redis 7。使用本地开发方式时，需要自行启动数据库服务。

## 本地开发

以下命令以 PowerShell 为例，除注明目录外均在项目根目录执行。复制配置模板仅用于首次初始化，不要覆盖已有配置。

### 1. 安装后端依赖

```powershell
git clone https://github.com/zihao0727/7-agent.git
cd 7-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

在 `.env` 中替换占位值，按实际使用的能力配置：

| 配置项 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY`、`KIMI_API_KEY`、`SEVNX_API_KEY` | 对应 Web 模型供应商的密钥 |
| 对应的 `*_BASE_URL`、`*_MODEL` | 接口地址与账户可用的模型名称 |
| `ANTHROPIC_API_KEY` | 仅在使用独立 `main.py` 入口时需要 |
| `MONGODB_URL`、`MONGODB_DB` | 默认地址为 `mongodb://localhost:27017`，库名为 `7_agent` |
| `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE` | MySQL 连接参数 |
| `REDIS_URL` | 默认地址为 `redis://localhost:6379/0` |
| `SMTP_HOST`、`SMTP_PORT`、`SMTP_SENDER`、`SMTP_PASSWORD` | 注册邮件所需的 SMTP 配置 |
| `TAVILY_API_KEY` | 网络搜索工具使用 |
| `CREDENTIAL_ENCRYPTION_KEY` | 飞书凭据存储使用的 Fernet 加密密钥 |
| `CORS_ORIGINS` | 允许访问 API 的前端来源，格式为 JSON 数组 |

模型名与服务权限应以自己的供应商账户为准。未使用的供应商密钥可留空，不要将模板占位值当成有效凭据。

后端启动时初始化数据库表。若 MySQL 数据库不存在，初始化过程会尝试创建它；也可提前创建数据库，并为应用用户配置所需的访问和建表权限。

### 2. 启动 API

先处理「已知限制」中的缺失技能模块，再执行：

```powershell
python -m uvicorn backend.app:app --host 127.0.0.1 --port 6868 --workers 1
```

健康检查地址为 `http://localhost:6868/api/health`，API 文档地址为 `http://localhost:6868/docs`。

### 3. 启动 Web

在另一个终端执行：

```powershell
cd frontend
npm ci
Copy-Item .env.local.example .env.local
```

将 `frontend/.env.local` 中的 `NEXT_PUBLIC_API_URL` 改为 `http://localhost:6868`，再运行：

```powershell
npm run dev
```

打开 `http://localhost:7878`。注册需要已配置且可用的 SMTP 服务。前后端默认使用不同端口，修改前端地址时也需检查后端 `CORS_ORIGINS`。

### 4. 可选：桌面客户端

先启动 API 和 Web，然后在新终端执行：

```powershell
cd desktop
npm ci
npm start
```

开发环境默认连接本地 `7878` 和 `6868` 端口，也可通过 `AGENT7_APP_URL`、`AGENT7_API_URL` 指定地址。部署配置及 Windows 安装包构建方法见 [部署说明](docs/deployment.md)。

### 5. 可选：独立命令行

配置 `ANTHROPIC_API_KEY` 后，在项目根目录运行：

```powershell
python main.py
python main.py --help
```

该入口与 Web 服务独立，不需要先启动 Next.js。

## Docker 部署

Compose 同时启动 API、Web、MongoDB、MySQL 和 Redis；缺失技能模块的限制同样适用。

1. 将 `.env.server.example` 复制为 `.env.server`，替换密钥、密码和域名占位值。
2. 配置 `PUBLIC_API_URL` 和 `CORS_ORIGINS`，生产环境通过 HTTPS 反向代理访问。
3. 生成并妥善保管 `CREDENTIAL_ENCRYPTION_KEY`，不要提交到仓库：

   ```powershell
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. 启动服务：

   ```powershell
   docker compose --env-file .env.server -f docker-compose.server.yml up -d --build
   docker compose --env-file .env.server -f docker-compose.server.yml ps
   ```

默认 API 端口为 `6868`，Web 端口为 `7878`。数据库不发布宿主机端口。反向代理需支持 `/api/client-runtime/ws` 的 WebSocket 连接。

前端 API 地址在构建时注入；修改 `PUBLIC_API_URL` 后需重新构建 Web 镜像。升级前请备份数据库及应用数据卷。更完整的配置说明见 [docs/deployment.md](docs/deployment.md)。

## 开发检查

在项目根目录安装测试依赖并运行 Python 测试：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

`pytest.ini` 默认排除标记为 `integration` 的测试。需要外部服务的测试应在配置好依赖后单独运行；未标记测试的环境依赖仍需根据具体测试检查。

前端检查在 `frontend` 目录执行：

```powershell
npm run lint
npm run build
```

## 安全与已知限制

- **缺失的本地技能**：`backend/state.py` 引用了 `agent.skills.notary_business_analysis` 和 `agent.skills.skill_creator_skill`，但这两个模块未纳入当前仓库。新克隆环境导入后端时会失败。需要由维护者提供经过审查、不含私有配置的模块，或调整对应的导入和技能注册后再部署。
- **桌面测试未收录**：当前已提交版本的 `desktop/package.json` 定义了测试命令，但对应的 `desktop/test` 文件尚未纳入版本控制。
- **单进程部署**：桌面连接状态保存在内存中，API 使用一个 worker；不要在未改造连接协调机制前直接增加 worker 或副本数。
- **不是安全沙箱**：代码执行、文件操作、浏览器及 CLI 工具具备实际操作能力，应限制访问范围，并使用独立账户或容器隔离。
- **凭据管理**：真实密钥只放在本地环境文件或部署密钥系统中，不要写入代码、示例、日志或 `NEXT_PUBLIC_*` 变量。开发环境未配置加密密钥时，部分凭据存储会退回明文；生产环境必须配置加密密钥。
- **历史清理不等于凭据失效**：清理仓库历史不能撤销其他克隆、缓存或备份中的副本。
