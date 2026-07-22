"""
Data Agent (agents/data_agent.py)

职责：
1. 接收 Supervisor 分配的数据查询任务
2. 分析数据库结构（调用 list_tables / get_table_schema）
3. 将自然语言需求转换为 SQL
4. 执行 SQL 查询（通过 MCP + SQL Tool）
5. 将结果封装为 DataQueryResult，写入 State

设计要点：
=========
1. 使用 LangChain ReAct Agent：先思考（Thought），再行动（Action），再观察（Observation）
2. 工具调用链：list_tables → get_table_schema → execute_sql
3. 错误处理：SQL 执行失败时重试或返回错误
4. 结果格式化：将工具返回的文本转换为 DataQueryResult 对象

为什么用 ReAct Agent？
=====================
ReAct = Reasoning + Acting
- Reasoning（思考）："用户要查销售额，我需要先知道有哪些表"
- Acting（行动）：调用 list_tables 工具
- Observation（观察）：看到 sales 表存在
- 循环直到完成任务

这比直接让 LLM 写 SQL 更可靠，因为 LLM 可以：
1. 先探索数据库结构
2. 确认字段名正确
3. 发现错误后修正 SQL

架构关系：
=========
Supervisor (分配任务)
    ↓
Data Agent (ReAct Agent)
    ↓ 调用 Tools
SQL Tools (LangChain BaseTool)
    ↓ 调用 MCP Client
MCP Client (MCP 协议)
    ↓ JSON-RPC 2.0
MCP Server (db_server)
    ↓ SQLAlchemy
MySQL Database
"""

import json
import time
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage

from app.core.config import settings
from app.graph.state import AgentState, DataQueryResult, TaskStatus
from app.tools.sql_tool import get_sql_tools


# ============================================================
# 1. Data Agent 系统提示词
# ============================================================
# 
# 这是 Data Agent 的"身份卡"，告诉 LLM：
# - 你是谁？（数据库查询专家）
# - 你能做什么？（查表、看结构、执行 SQL）
# - 你不能做什么？（DELETE/DROP 等危险操作）
# - 你的输出格式？（DataQueryResult JSON）
# ============================================================

DATA_AGENT_PROMPT = """你是企业智能数据分析平台的"数据查询专家"（Data Agent）。

## 你的职责
1. 理解 Supervisor 分配的数据查询任务
2. 探索数据库结构（有哪些表、字段）
3. 编写正确的 SQL 查询语句
4. 执行查询并返回结构化结果

## 工作流程（必须按顺序执行）

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

## 工具说明

你有以下工具可用：

{tools}

工具名称格式：
- 调用工具时，使用格式：
  ```
  Thought: 我需要查看表结构
  Action: get_table_schema
  Action Input: {{"table_name": "sales"}}
  ```

## 输出格式

最终输出必须是 JSON 格式：
```json
{{
  "query": "执行的SQL语句",
  "data": [{{"字段1": "值1", "字段2": "值2"}}, ...],
  "row_count": 10,
  "execution_time_ms": 45.2,
  "success": true,
  "error": null
}}
```

## 当前任务

{input}

{agent_scratchpad}
"""


# ============================================================
# 2. 创建 Data Agent
# ============================================================

def create_data_agent():
    """
    创建 Data Agent（ReAct Agent）
    
    ReAct Agent 的工作流程：
    1. Thought：LLM 思考下一步该做什么
    2. Action：选择工具并调用
    3. Observation：观察工具返回的结果
    4. 循环直到任务完成或达到最大步数
    
    为什么选 ReAct？
    - 适合需要多步推理的任务（先查表结构，再写 SQL）
    - 有明确的思考过程，便于调试
    - 错误时可以自我修正（重试）
    """
    
    # 初始化 LLM
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0.1,  # 低温度，SQL 要准确
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )
    
    # 获取工具
    tools = get_sql_tools()
    
    # 创建 ReAct Agent
    # create_react_agent 会自动处理 Thought/Action/Observation 循环
    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=PromptTemplate.from_template(DATA_AGENT_PROMPT),
    )
    
    # 创建执行器
    # max_iterations：最多执行多少步（防止无限循环）
    # handle_parsing_errors：解析错误时自动重试
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=10,           # 最多 10 步
        handle_parsing_errors=True,  # 解析错误时重试
        verbose=False,               # 不打印详细日志（生产环境）
    )
    
    return agent_executor


# ============================================================
# 3. Data Agent 节点函数（LangGraph 节点）
# ============================================================

async def data_agent_node(state: AgentState) -> dict:
    """
    Data Agent 节点函数
    
    LangGraph 执行到这个节点时，调用此函数。
    
    参数：
        state: 当前系统状态
    
    返回：
        dict: 状态更新（data_results、messages、execution_trace 等）
    
    执行流程：
    1. 从 State 读取任务描述
    2. 创建 Data Agent 并执行
    3. 解析 Agent 输出为 DataQueryResult
    4. 更新 State（写入 data_results、添加轨迹等）
    5. 返回更新 dict
    """
    
    start_time = time.time()
    
    # 1. 读取任务
    task = state.current_task
    if not task:
        # 如果没有任务，返回错误
        error_msg = "Data Agent 未收到任务描述"
        state.add_trace(
            agent="data_agent",
            action="no_task",
            status=TaskStatus.FAILED,
            error_message=error_msg,
        )
        return {
            "error_log": state.error_log + [error_msg],
            "active_agent": "supervisor",  # 回到 Supervisor
        }
    
    # 2. 记录开始执行
    state.add_trace(
        agent="data_agent",
        action="start_query",
        input_summary=task[:100],
    )
    
    # 3. 创建并执行 Data Agent
    try:
        agent_executor = create_data_agent()
        
        # 执行 Agent
        # invoke 是同步的，但 LangGraph 节点可以是 async 的
        result = await agent_executor.ainvoke({
            "input": task,
            "agent_scratchpad": "",  # 初始为空，Agent 会填充
        })
        
        # 4. 解析输出
        # ReAct Agent 的输出在 result["output"] 中
        output = result.get("output", "")
        
        # 尝试从输出中提取 JSON
        data_result = _parse_agent_output(output, task)
        
        # 5. 计算耗时
        duration_ms = (time.time() - start_time) * 1000
        
        # 6. 记录成功轨迹
        state.add_trace(
            agent="data_agent",
            action="query_complete",
            status=TaskStatus.SUCCESS,
            output_summary=f"返回 {data_result.row_count} 行数据",
            duration_ms=duration_ms,
        )
        
        # 7. 添加 Agent 消息到对话历史
        state.add_message(
            role="agent",
            content=f"[Data Agent] 查询完成。SQL: {data_result.query}，返回 {data_result.row_count} 行数据。",
            agent_name="data_agent",
        )
        
        # 8. 返回状态更新
        return {
            "data_results": data_result,
            "task_status": TaskStatus.SUCCESS,
            "active_agent": "supervisor",  # 执行完回到 Supervisor
        }
        
    except Exception as e:
        # 9. 错误处理
        duration_ms = (time.time() - start_time) * 1000
        error_msg = f"Data Agent 执行失败: {str(e)}"
        
        state.add_trace(
            agent="data_agent",
            action="query_error",
            status=TaskStatus.FAILED,
            error_message=error_msg,
            duration_ms=duration_ms,
        )
        
        state.error_log.append(error_msg)
        
        state.add_message(
            role="agent",
            content=f"[Data Agent] 查询失败: {error_msg}",
            agent_name="data_agent",
        )
        
        # 返回错误结果（不中断流程，让 Supervisor 决定下一步）
        return {
            "data_results": DataQueryResult(
                query="",
                data=[],
                row_count=0,
                execution_time_ms=duration_ms,
                error=error_msg,
            ),
            "error_log": state.error_log,
            "task_status": TaskStatus.FAILED,
            "active_agent": "supervisor",
        }


# ============================================================
# 4. 辅助函数：解析 Agent 输出
# ============================================================

def _parse_agent_output(output: str, task: str) -> DataQueryResult:
    """
    解析 Data Agent 的输出为 DataQueryResult
    
    Data Agent 的输出可能包含：
    1. JSON 格式的结果（理想情况）
    2. Markdown 格式的表格 + 说明（需要解析）
    3. 纯文本描述（需要提取）
    
    这个函数尝试多种解析方式，确保能提取到有效数据。
    """
    
    # 尝试1：从输出中提取 JSON 代码块
    import re
    
    # 匹配 ```json ... ``` 或 ``` ... ``` 中的 JSON
    json_patterns = [
        r"```json\\s*(.*?)\\s*```",
        r"```\\s*(\\{.*?\\})\\s*```",
    ]
    
    for pattern in json_patterns:
        match = re.search(pattern, output, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return DataQueryResult(
                    query=data.get("query", ""),
                    data=data.get("data", []),
                    row_count=data.get("row_count", len(data.get("data", []))),
                    execution_time_ms=data.get("execution_time_ms", 0),
                    data_source=data.get("data_source", "mysql"),
                    schema=data.get("columns", []),
                )
            except json.JSONDecodeError:
                continue
    
    # 尝试2：直接解析整个输出为 JSON
    try:
        data = json.loads(output)
        if isinstance(data, dict) and "data" in data:
            return DataQueryResult(
                query=data.get("query", ""),
                data=data.get("data", []),
                row_count=data.get("row_count", 0),
                execution_time_ms=data.get("execution_time_ms", 0),
            )
    except json.JSONDecodeError:
        pass
    
    # 尝试3：从 Markdown 表格解析
    # 简单实现：提取 | 开头的行
    lines = output.strip().split("\\n")
    table_lines = [l for l in lines if l.strip().startswith("|")]
    
    if len(table_lines) >= 3:  # 表头 + 分隔线 + 至少一行数据
        # 解析表头
        header_line = table_lines[0]
        headers = [h.strip() for h in header_line.split("|")[1:-1]]
        
        # 解析数据（跳过分隔线）
        data_rows = []
        for line in table_lines[2:]:
            values = [v.strip() for v in line.split("|")[1:-1]]
            if len(values) == len(headers):
                data_rows.append(dict(zip(headers, values)))
        
        if data_rows:
            return DataQueryResult(
                query="从输出解析的查询",
                data=data_rows,
                row_count=len(data_rows),
                execution_time_ms=0,
                schema=headers,
            )
    
    # 兜底：返回原始输出作为文本
    return DataQueryResult(
        query="",
        data=[{"output": output}],
        row_count=1,
        execution_time_ms=0,
        error="无法解析结构化数据，返回原始输出",
    )

print("✅ backend/app/agents/data_agent.py 创建完成")
