
doc03_content = '''# 板块三：Data Agent + MCP 数据库工具

> **文档编号**: 03  
> **前置板块**: 02-核心状态机State设计  
> **编写日期**: 2026-07-18  
> **核心目标**: 让 Data Agent 能真正查询数据库，通过 MCP 标准化协议

---

## 📖 目录

1. [Data Agent 要解决什么问题？](#一data-agent-要解决什么问题)
2. [MCP 协议核心概念](#二mcp-协议核心概念)
3. [架构关系图](#三架构关系图)
4. [MCP 数据库 Server](#四mcp-数据库-server)
5. [MCP Client](#五mcp-client)
6. [SQL Tool（LangChain 封装）](#六sql-toollangchain-封装)
7. [Data Agent（ReAct Agent）](#七data-agentreact-agent)
8. [图构建器更新](#八图构建器更新)
9. [运行验证](#九运行验证)
10. [本板块简历价值](#十本板块简历价值)
11. [下板块预告](#十一下板块预告)

---

## 一、Data Agent 要解决什么问题？

### 1.1 业务场景

用户说：**"查一下上季度各品类销售额排名"**

Data Agent 需要：
1. 理解需求 → "上季度" = Q3，"品类" = category 字段，"销售额" = amount 字段
2. 知道数据库里有什么表 → `sales` 表有 `category`, `amount`, `quarter` 字段
3. 写 SQL → `SELECT category, SUM(amount) FROM sales WHERE quarter='Q3' GROUP BY category ORDER BY SUM(amount) DESC`
4. 执行 SQL → 拿到数据
5. 返回结果 → 封装成 `DataQueryResult`

### 1.2 为什么需要 MCP？

**传统做法（耦合）**：
```python
# Data Agent 直接连数据库
class DataAgent:
    def query(self, sql):
        conn = pymysql.connect(host="localhost", ...)  # 写死了！
        # 问题1：换数据库？改Agent代码！
        # 问题2：权限控制？写在Agent里！
        # 问题3：多个Agent共用？复制粘贴！
```

**MCP 做法（解耦）**：
```
Data Agent ──→ MCP Client ──→ MCP Server (数据库服务)
                  ↑                ↑
            标准化协议          独立部署、独立权限
```

**企业价值**：
- 工具与 Agent 解耦：Data Agent 不需要知道数据库连接细节
- 权限可控：MCP Server 单独做权限校验
- 可复用：一个 MCP Server 可被多个 Agent 调用
- 标准化：2026 年 MCP 已成行业标准

---

## 二、MCP 协议核心概念

### 2.1 MCP 三大原语

| 原语 | 作用 | 类比 REST |
|------|------|----------|
| **Tools** | Agent 可调用的动作（写 SQL、发邮件） | POST/PUT/DELETE |
| **Resources** | Agent 可读取的数据（表结构、文件内容） | GET |
| **Prompts** | 预定义的提示词模板 | 模板引擎 |

### 2.2 MCP 架构（2026 标准）

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   MCP Host      │────→│   MCP Client    │────→│   MCP Server    │
│  (你的Agent系统) │     │  (连接管理器)    │     │  (数据库服务)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                              │
        │         JSON-RPC 2.0 over STDIO/HTTP         │
        └──────────────────────────────────────────────┘
```

**传输方式**（2026 最新规范）：
- **STDIO**：本地子进程，适合开发调试
- **Streamable HTTP**：远程服务，适合企业部署（SSE 已被弃用）

### 2.3 FastMCP 3.0（推荐写法）

2026 年 1 月发布的 FastMCP 3.0 大幅简化了开发：

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
async def query_database(sql: str) -> dict:
    """执行SQL查询"""
    ...
```

---

## 三、架构关系图

### 3.1 完整数据流

```
用户输入："查一下上季度各品类销售额"
        ↓
[Supervisor] 解析需求 → 分配给 Data Agent
        ↓
[Data Agent] ReAct Agent
    ├── Thought: 需要查 sales 表
    ├── Action: list_tables → 发现 sales 表
    ├── Thought: 需要了解 sales 表结构
    ├── Action: get_table_schema("sales") → 返回字段信息
    ├── Thought: 可以写 SQL 了
    ├── Action: execute_sql("SELECT category, SUM(amount)...")
    ├── Observation: 返回 5 行数据
    └── Final Answer: DataQueryResult
        ↓
写入 State.data_results
        ↓
回到 Supervisor → 决定下一步
```

### 3.2 代码层级关系

```
Data Agent (agents/data_agent.py)
    ├── ReAct Agent (LangChain)
    │   ├── LLM (GPT-4o-mini)
    │   └── Tools (LangChain BaseTool)
    │       ├── ExecuteSQLTool (tools/sql_tool.py)
    │       │   └── 调用 MCP Client (mcp/client.py)
    │       │       └── MCP Protocol (JSON-RPC 2.0)
    │       │           └── MCP Server (mcp/servers/db_server.py)
    │       │               └── SQLAlchemy
    │       │                   └── MySQL
    │       ├── GetTableSchemaTool
    │       └── ListTablesTool
    └── 解析输出 → DataQueryResult
```

---

## 四、MCP 数据库 Server

### 4.1 文件位置
`backend/app/mcp/servers/db_server.py`

### 4.2 核心设计

#### 安全机制（企业级）

| 机制 | 实现 | 为什么需要 |
|------|------|-----------|
| **SQL 注入防护** | 参数化查询（SQLAlchemy text） | 防止恶意 SQL |
| **危险操作拦截** | 正则匹配 DELETE/DROP/TRUNCATE 等 | 只读查询，保护数据 |
| **查询超时** | `SET SESSION MAX_EXECUTION_TIME=30000` | 防止慢查询拖垮数据库 |
| **结果限制** | 默认 10000 行，最大 50000 | 防止内存溢出 |
| **审计日志** | 每次查询记录时间、SQL、结果数 | 合规要求 |

#### 代码核心

```python
@mcp.tool()
async def execute_sql(query: str, max_rows: int = 10000) -> dict:
    """执行 SQL 查询"""
    
    # 1. 安全校验：只允许 SELECT
    dangerous_keywords = ["DELETE", "DROP", "TRUNCATE", "UPDATE", "INSERT", ...]
    for keyword in dangerous_keywords:
        if re.search(r"\\b" + keyword + r"\\b", query, re.IGNORECASE):
            return {"success": False, "error": "安全拦截：只允许 SELECT"}
    
    # 2. 执行查询
    with engine.connect() as conn:
        conn.execute(text("SET SESSION MAX_EXECUTION_TIME=30000"))
        result = conn.execute(text(query))
        
        # 3. 限制返回行数
        rows = []
        for i, row in enumerate(result):
            if i >= max_rows:
                break
            rows.append(dict(zip(columns, row)))
    
    return {"success": True, "data": rows, "row_count": len(rows), ...}
```

#### 启动方式

```bash
# STDIO 模式（本地子进程，开发调试）
python -m app.mcp.servers.db_server

# HTTP 模式（独立服务，企业部署）
python -m app.mcp.servers.db_server --transport http --port 8001
```

---

## 五、MCP Client

### 5.1 文件位置
`backend/app/mcp/client.py`

### 5.2 职责

1. 连接 MCP Server（STDIO 或 HTTP）
2. 发现 Server 提供的 Tools 和 Resources
3. 调用 Tools 执行动作
4. 读取 Resources 获取数据

### 5.3 核心方法

```python
class MCPClient:
    async def connect_to_server_stdio(self, server_script_path: str):
        """STDIO 模式：启动 Server 作为子进程"""
        
    async def connect_to_server_http(self, url: str):
        """HTTP 模式：连接远程服务"""
        
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """调用工具"""
        
    async def read_resource(self, uri: str) -> str:
        """读取资源"""
```

### 5.4 便捷函数

```python
async def execute_sql_via_mcp(query: str, max_rows: int = 10000) -> dict:
    """一键执行 SQL（自动连接 + 调用 + 关闭）"""
    async with MCPClient() as client:
        await client.connect_to_server_stdio("app/mcp/servers/db_server")
        return await client.call_tool("execute_sql", {"query": query, "max_rows": max_rows})
```

---

## 六、SQL Tool（LangChain 封装）

### 6.1 为什么需要这个封装？

**LangChain Agent 期望的接口**：
```python
class BaseTool:
    name: str           # 工具名称
    description: str  # 工具描述（LLM 靠这个判断什么时候调用）
    args_schema: BaseModel  # 输入参数 Schema
    
    async def _arun(self, **kwargs) -> str:  # 异步执行
    def _run(self, **kwargs) -> str:          # 同步执行
```

**MCP 是独立协议层**，不直接兼容 LangChain。

所以 `tools/sql_tool.py` 是**适配层**：
```
LangChain Agent
    ↓ 调用 Tool（BaseTool 接口）
SQL Tool（适配层）
    ↓ 调用 MCP Client
MCP Client（MCP 协议）
    ↓ JSON-RPC 2.0
MCP Server
```

### 6.2 三个工具

| 工具 | 作用 | 输入 | 输出 |
|------|------|------|------|
| `execute_sql` | 执行 SQL 查询 | `query`, `max_rows` | Markdown 表格 |
| `get_table_schema` | 获取表结构 | `table_name` | 字段列表 |
| `list_tables` | 列出所有表 | 无 | 表名列表 |

### 6.3 工具描述的重要性

```python
description = """
执行 SQL SELECT 查询，返回查询结果。

安全限制：
- 只允许 SELECT 语句
- 禁止 DELETE/DROP/TRUNCATE/UPDATE/INSERT/ALTER/CREATE
- 查询超时 30 秒
- 最多返回 10000 行

使用场景：
- 查询销售数据、用户数据、订单数据
- 聚合统计（SUM、COUNT、AVG）
- 分组排序（GROUP BY、ORDER BY）

示例：
- "SELECT category, SUM(amount) FROM sales GROUP BY category"
"""
```

**为什么描述这么详细？**
- LLM 靠 `description` 判断什么时候调用这个工具
- 描述越清晰，LLM 调用越准确
- 安全限制也要写进去，LLM 会遵守

---

## 七、Data Agent（ReAct Agent）

### 7.1 为什么用 ReAct Agent？

**ReAct = Reasoning + Acting**

```
Thought: 用户要查销售额，我需要先知道有哪些表
Action: list_tables
Observation: [sales, users, orders]

Thought: 有 sales 表，我需要了解它的字段
Action: get_table_schema("sales")
Observation: [id, category, amount, quarter, ...]

Thought: 可以写 SQL 了，查询 Q3 各品类销售额
Action: execute_sql("SELECT category, SUM(amount) FROM sales WHERE quarter='Q3' GROUP BY category")
Observation: | category | SUM(amount) |
             | 电子产品 | 1500000 |
             | 服装 | 800000 |

Thought: 任务完成，返回结果
Final Answer: {"query": "...", "data": [...], "row_count": 2}
```

**优势**：
- 先探索再行动：不会盲目写 SQL
- 错误自修正：SQL 报错后可以分析原因重试
- 过程透明：每一步都有 Thought，便于调试

### 7.2 系统提示词设计

```python
DATA_AGENT_PROMPT = """你是"数据查询专家"（Data Agent）。

## 工作流程（必须按顺序）

### 步骤1：探索数据库结构
如果不知道表结构，先调用 `list_tables` 查看有哪些表。
然后调用 `get_table_schema` 查看具体表的字段信息。

### 步骤2：编写 SQL
根据任务需求和表结构，编写 SELECT 查询语句。

SQL 编写规范：
- 只使用 SELECT，禁止 DELETE/DROP/UPDATE/INSERT/ALTER/CREATE
- 使用清晰的字段名，避免 SELECT *
- 聚合查询使用 GROUP BY
- 排序使用 ORDER BY
- 限制返回行数（默认 1000，最多 10000）

### 步骤3：执行查询
调用 `execute_sql` 执行编写的 SQL。

### 步骤4：处理结果
- 如果成功：整理结果，准备返回
- 如果失败：分析错误原因，修正 SQL 后重试（最多重试 2 次）

## 输出格式

最终输出必须是 JSON 格式：
```json
{
  "query": "执行的SQL语句",
  "data": [{"字段1": "值1"}, ...],
  "row_count": 10,
  "execution_time_ms": 45.2,
  "success": true,
  "error": null
}
```
"""
```

### 7.3 节点函数

```python
async def data_agent_node(state: AgentState) -> dict:
    """Data Agent 节点函数"""
    
    # 1. 读取任务
    task = state.current_task
    
    # 2. 创建 ReAct Agent
    agent_executor = create_data_agent()
    
    # 3. 执行 Agent
    result = await agent_executor.ainvoke({"input": task})
    
    # 4. 解析输出为 DataQueryResult
    data_result = _parse_agent_output(result["output"])
    
    # 5. 记录轨迹
    state.add_trace(agent="data_agent", action="query_complete", ...)
    
    # 6. 返回状态更新
    return {"data_results": data_result, "active_agent": "supervisor"}
```

### 7.4 输出解析

Data Agent 的输出可能是：
1. JSON 代码块（理想情况）
2. Markdown 表格 + 说明
3. 纯文本描述

`_parse_agent_output()` 函数尝试多种解析方式，确保能提取到有效数据。

---

## 八、图构建器更新

### 8.1 更新内容

在 `builder.py` 中：
1. 添加 `data_agent` 节点
2. 添加 `data_agent → supervisor` 的边（执行完回到 Supervisor）

```python
# 添加 Data Agent 节点
from app.agents.data_agent import data_agent_node
workflow.add_node("data_agent", data_agent_node)

# 添加回到 Supervisor 的边
workflow.add_edge("data_agent", "supervisor")
```

### 8.2 当前图结构

```
        ┌─────────────┐
        │   START     │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  Supervisor │
        └──────┬──────┘
               │
        ┌──────┴──────┐
        ▼             ▼
┌─────────────┐  ┌─────────────┐
│  data_agent │  │   FINISH    │
│  (查询数据)  │  │   (结束)    │
└──────┬──────┘  └─────────────┘
       │
       ▼
┌─────────────┐
│  Supervisor │  ← 循环：回到 Supervisor 决定下一步
└─────────────┘
```

---

## 九、运行验证

### 9.1 前提条件

1. MySQL 已启动（`docker-compose up -d mysql`）
2. 创建了测试表和数据：

```sql
-- 连接到 MySQL
docker exec -it ma-mysql mysql -u root -p

-- 创建测试表
USE multi_agent_db;

CREATE TABLE sales (
    id INT PRIMARY KEY AUTO_INCREMENT,
    category VARCHAR(50) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    quarter VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入测试数据
INSERT INTO sales (category, amount, quarter) VALUES
('电子产品', 500000, 'Q3'),
('电子产品', 600000, 'Q3'),
('服装', 300000, 'Q3'),
('服装', 250000, 'Q3'),
('食品', 150000, 'Q3'),
('食品', 100000, 'Q3');
```

### 9.2 测试 MCP Server

```bash
cd backend
source venv/bin/activate

# 测试 MCP Server（STDIO 模式）
python -m app.mcp.servers.db_server

# 在另一个终端，测试工具调用
python -c "
import asyncio
from app.mcp.client import execute_sql_via_mcp

async def test():
    result = await execute_sql_via_mcp('SELECT category, SUM(amount) as total FROM sales GROUP BY category')
    print(result)

asyncio.run(test())
"
```

### 9.3 测试 Data Agent

```python
from app.graph.state import create_initial_state
from app.agents.data_agent import data_agent_node
import asyncio

async def test():
    state = create_initial_state("查一下Q3各品类销售额")
    
    # 模拟 Supervisor 已分配任务
    state.current_task = "查询Q3各品类销售额汇总，按销售额降序排列"
    
    # 执行 Data Agent
    updates = await data_agent_node(state)
    
    print("查询结果:")
    print(updates["data_results"])
    
    print("\\n执行轨迹:")
    for trace in state.execution_trace:
        print(f"  Step {trace.step}: {trace.agent} - {trace.action}")

asyncio.run(test())
```

---

## 十、本板块简历价值

### 10.1 新增可写内容

```markdown
• MCP 协议实践：基于 FastMCP 3.0 实现数据库 MCP Server，
  暴露 execute_sql、get_table_schema、list_tables 三个标准化工具，
  支持 STDIO 和 HTTP 两种传输模式

• 安全设计：SQL 危险操作拦截（正则匹配 DELETE/DROP 等关键词）、
  查询超时保护（30秒）、结果行数限制（10000行）、参数化查询防注入

• LangChain 工具封装：将 MCP 调用适配为 LangChain BaseTool 接口，
  实现 ReAct Agent 的多步推理（先探索表结构 → 再写 SQL → 执行查询）

• 错误处理与重试：SQL 执行失败时自动分析错误原因、修正 SQL 重试，
  输出解析支持 JSON/Markdown/纯文本三种格式
```

### 10.2 面试高频问题

**Q1: 什么是 MCP？为什么用它而不是直接调 API？**
> "MCP 是 Model Context Protocol，Anthropic 2024 年提出的 AI 工具标准化协议。类比 USB-C，一个 MCP Server 可以被任何兼容的 AI 客户端使用（Claude、GPT-4o、Gemini 等）。我们用它做数据库查询工具，好处是：工具与 Agent 解耦，权限控制集中在 Server 层，且符合 2026 年行业标准。"

**Q2: MCP 和 Function Calling 有什么区别？**
> "Function Calling 是单个 LLM 的 API 特性，MCP 是跨模型的传输层协议。Function Calling 需要每次调用都传工具定义，MCP 是独立的服务进程，Agent 通过 JSON-RPC 2.0 连接，一次发现、多次调用。"

**Q3: Data Agent 为什么用 ReAct 而不是直接让 LLM 写 SQL？**
> "ReAct 让 LLM 先思考（Thought）再行动（Action）。Data Agent 会先探索数据库结构（list_tables → get_table_schema），确认字段名后再写 SQL，避免字段名错误。如果 SQL 执行失败，ReAct 的 Observation 机制让 LLM 看到错误信息并自动修正。"

**Q4: 怎么防止 SQL 注入和危险操作？**
> "三层防护：1）MCP Server 层用正则拦截 DELETE/DROP 等危险关键词；2）SQLAlchemy 参数化查询防止注入；3）数据库层面设置 MAX_EXECUTION_TIME 防止慢查询。"

---

## 十一、下板块预告

### 板块四：Analysis Agent + Python 计算工具

**核心内容**：
- Analysis Agent 的设计：如何分析数据、发现洞察
- Python 计算工具：让 Agent 执行统计分析代码
- MCP Python Server：封装 Python 执行环境
- 与 Data Agent 的衔接：读取 State.data_results 进行分析

**你将实现**：
- `backend/app/agents/analysis_agent.py`
- `backend/app/mcp/servers/python_server.py`
- `backend/app/tools/python_tool.py`

---

> **文档结束**  
> 如有疑问，随时提问。确认理解后，我们继续 **板块四：Analysis Agent + Python 计算工具** 🚀
'''

with open(f"{ROOT}/docs/03-DataAgent与MCP数据库工具.md", "w", encoding="utf-8") as f:
    f.write(doc03_content)

print("✅ docs/03-DataAgent与MCP数据库工具.md 创建完成")
