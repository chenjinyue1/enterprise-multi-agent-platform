# 🏢 企业智能数据分析多智能体平台
> Enterprise Multi-Agent Data Analysis Platform

基于 LangGraph + MCP + RAG 的企业级多智能体数据分析系统，实现从自然语言需求到数据查询、分析计算、可视化、报告生成的全流程自动化。

## 🎯 项目亮点

- **多智能体协作**：Supervisor 调度 5 个专业 Agent，各司其职
- **MCP 工具标准化**：工具与 Agent 解耦，支持热插拔
- **RAG 知识增强**：历史报告模板检索，输出标准化
- **人工审核介入**：关键节点支持人工确认，企业级安全
- **全链路可观测**：Redis + MySQL 持久化，执行轨迹可追溯
- **Harness 评估**：多维度质量评估，持续优化

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Vite + TypeScript |
| API 网关 | FastAPI + JWT |
| Agent 编排 | LangGraph + LangChain |
| 工具协议 | MCP (Model Context Protocol) |
| 向量数据库 | ChromaDB |
| 缓存/状态 | Redis |
| 关系数据库 | MySQL |
| 评估框架 | Harness |

## 📁 项目文档

| 序号 | 文档 | 内容 |
|------|------|------|
| 01 | [项目架构设计与环境搭建](docs/01-项目架构设计与环境搭建.md) | 架构选型、目录结构、环境配置 |
| 02 | [核心状态机State设计](docs/02-核心状态机State设计.md) | State定义、Annotated策略、RouteDecision、Supervisor |
| 03 | [DataAgent与MCP数据库工具](docs/03-DataAgent与MCP数据库工具.md) | Data Agent、MCP Server/Client、SQL Tool、ReAct Agent |
| 04 | [AnalysisAgent与Python计算工具](docs/04-AnalysisAgent与Python计算工具.md) | Analysis Agent、Python MCP Server、安全沙箱、ReAct Agent |
| 05 | [VizAgent与图表生成工具](docs/05-VizAgent与图表生成工具.md) | Viz Agent、图表生成工具、ECharts配置、图表推荐 |


## 🚀 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/chenjinyue1/enterprise-multi-agent-platform.git
cd enterprise-multi-agent-platform

# 2. 启动基础设施（MySQL + Redis + ChromaDB）
docker-compose up -d

# 3. 安装后端依赖
cd backend
pip install -e ".[dev]"

# 4. 复制环境变量
cp .env.example .env
# 编辑 .env 填入你的 OpenAI API Key

# 5. 启动后端
uvicorn app.main:app --reload

# 6. 启动前端（新终端）
cd frontend
npm install
npm run dev
```

## 📁 完整项目结构:
enterprise-multi-agent-platform/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI入口
│   │   ├── core/                # 配置、安全、模型
│   │   ├── api/v1/              # API路由
│   │   │   ├── chat.py          # 聊天/任务API
│   │   │   ├── reports.py       # 报告API
│   │   │   └── auth.py          # 认证API
│   │   ├── graph/               # LangGraph编排
│   │   │   ├── state.py         # 状态定义
│   │   │   ├── builder.py       # 图构建器
│   │   │   ├── nodes.py         # 节点定义
│   │   │   └── edges.py         # 边/路由
│   │   ├── agents/              # Agent定义
│   │   │   ├── supervisor.py
│   │   │   ├── data_agent.py
│   │   │   ├── analysis_agent.py
│   │   │   ├── viz_agent.py
│   │   │   ├── report_agent.py
│   │   │   └── review_agent.py
│   │   ├── tools/               # 工具封装
│   │   ├── mcp/                 # MCP协议层
│   │   ├── rag/                 # RAG知识库
│   │   ├── evaluation/          # Harness评估
│   │   ├── services/            # 业务服务
│   │   └── prompts/             # Prompt模板
│   ├── Dockerfile               # 后端Docker镜像
│   └── pyproject.toml           # Python依赖
├── frontend/
│   ├── src/
│   │   ├── components/          # 可复用组件
│   │   │   ├── ChatWindow.tsx   # 聊天主界面
│   │   │   ├── AgentStatus.tsx  # 执行状态面板
│   │   │   └── ReportViewer.tsx # 报告预览
│   │   ├── pages/               # 页面
│   │   ├── hooks/               # 自定义Hooks
│   │   │   └── useWebSocket.ts  # WebSocket管理
│   │   ├── services/            # API服务
│   │   │   └── api.ts           # Axios封装
│   │   ├── types/               # TypeScript类型
│   │   ├── App.tsx              # 应用入口
│   │   └── main.tsx             # 渲染入口
│   ├── Dockerfile               # 前端Docker镜像
│   ├── nginx.conf               # Nginx配置
│   └── vite.config.ts           # Vite配置
├── data/                        # 数据文件
│   └── templates/               # 报告模板
├── docs/                        # 项目文档
│   ├── 01-项目架构设计与环境搭建.md
│   ├── 02-核心状态机State设计.md
│   ├── 03-DataAgent与SQL查询工具.md
│   ├── 04-AnalysisAgent与Python计算工具.md
│   ├── 05-VizAgent与图表生成工具.md
│   ├── 06-ReportAgent与RAG报告生成.md
│   ├── 07-ReviewAgent与Harness评估体系.md
│   └── 08-前端集成与部署上线.md
├── docker-compose.yml           # 开发环境
├── docker-compose.prod.yml      # 生产环境
└── README.md                    # 项目说明


## 📄 License

MIT
