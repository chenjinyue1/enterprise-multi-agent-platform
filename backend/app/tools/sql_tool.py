"""
SQL 工具封装 (tools/sql_tool.py)

职责：
1. 将 MCP 数据库操作封装为 LangChain Tool
2. 让 Data Agent 可以直接调用（符合 LangChain 接口规范）
3. 提供错误处理和重试机制

为什么需要这个封装？
====================
LangChain Agent 期望工具是特定的接口（BaseTool）。
MCP 是独立的协议层。
这个文件是"适配层"：把 MCP 调用适配成 LangChain Tool。

架构关系：
=========
Data Agent (LangChain Agent)
    ↓ 调用 Tool
SQL Tool (LangChain BaseTool)
    ↓ 调用 MCP Client
MCP Client (MCP 协议)
    ↓ JSON-RPC 2.0
MCP Server (db_server)
    ↓ SQLAlchemy
MySQL Database
"""

import asyncio
from typing import Optional, Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from app.mcp.client import execute_sql_via_mcp, get_schema_via_mcp, list_tables_via_mcp


# ============================================================
# 1. 输入参数模型（Pydantic）
# ============================================================
# 
# LangChain Tool 需要定义输入参数 Schema。
# LLM 根据这个 Schema 生成正确的参数。
# ============================================================

class ExecuteSQLInput(BaseModel):
    """execute_sql 工具的输入参数"""
    query: str = Field(
        description="SQL 查询语句（必须是 SELECT，禁止 DELETE/DROP/UPDATE）",
    )
    max_rows: int = Field(
        default=10000,
        description="最大返回行数（默认 10000，最大 50000）",
    )


class GetSchemaInput(BaseModel):
    """get_table_schema 工具的输入参数"""
    table_name: str = Field(
        description="表名（如 'sales', 'users', 'orders'）",
    )


class ListTablesInput(BaseModel):
    """list_tables 工具的输入参数（无参数）"""
    pass


# ============================================================
# 2. LangChain Tool 定义
# ============================================================

class ExecuteSQLTool(BaseTool):
    """
    执行 SQL 查询工具
    
    Data Agent 用这个工具查询数据库。
    底层通过 MCP Client 调用 db_server 的 execute_sql 工具。
    
    使用示例：
        tool = ExecuteSQLTool()
        result = await tool.ainvoke({"query": "SELECT * FROM sales LIMIT 10"})
    """
    
    name: str = "execute_sql"
    description: str = """
    执行 SQL SELECT 查询，返回查询结果。
    
    安全限制：
    - 只允许 SELECT 语句
    - 禁止 DELETE/DROP/TRUNCATE/UPDATE/INSERT/ALTER/CREATE
    - 查询超时 30 秒
    - 最多返回 10000 行（可调整）
    
    使用场景：
    - 查询销售数据、用户数据、订单数据
    - 聚合统计（SUM、COUNT、AVG）
    - 分组排序（GROUP BY、ORDER BY）
    
    示例：
    - "SELECT category, SUM(amount) FROM sales GROUP BY category"
    - "SELECT * FROM users WHERE created_at > '2024-01-01'"
    """
    
    args_schema: Type[BaseModel] = ExecuteSQLInput
    
    async def _arun(self, query: str, max_rows: int = 10000) -> str:
        """异步执行（LangChain 推荐）"""
        result = await execute_sql_via_mcp(query, max_rows)
        
        if not result.get("success"):
            error = result.get("error", "未知错误")
            return f"查询失败: {error}"
        
        # 格式化返回结果（给 LLM 看的文本格式）
        data = result.get("data", [])
        row_count = result.get("row_count", 0)
        columns = result.get("columns", [])
        
        if row_count == 0:
            return "查询成功，但返回 0 行数据。"
        
        # 构建 Markdown 表格
        lines = [
            f"查询成功！返回 {row_count} 行数据，耗时 {result.get('execution_time_ms', 0)}ms",
            "",
            "| " + " | ".join(columns) + " |",
            "| " + " | ".join(["---"] * len(columns)) + " |",
        ]
        
        for row in data[:20]:  # 最多显示 20 行给 LLM
            values = [str(row.get(col, "")) for col in columns]
            lines.append("| " + " | ".join(values) + " |")
        
        if row_count > 20:
            lines.append(f"")
            lines.append(f"... 还有 {row_count - 20} 行数据未显示")
        
        return "\\n".join(lines)
    
    def _run(self, query: str, max_rows: int = 10000) -> str:
        """同步执行（兼容 LangChain 同步接口）"""
        return asyncio.run(self._arun(query, max_rows))


class GetTableSchemaTool(BaseTool):
    """
    获取表结构工具
    
    Data Agent 在写 SQL 之前，先用这个工具了解表有哪些字段。
    """
    
    name: str = "get_table_schema"
    description: str = """
    获取指定表的字段结构信息（表名、字段名、字段类型、是否可空、注释）。
    
    使用场景：
    - 写 SQL 之前，先了解表结构
    - 确认字段名是否正确
    - 了解字段类型（避免类型不匹配的错误）
    
    示例：
    - get_table_schema("sales") → 返回 sales 表的所有字段
    """
    
    args_schema: Type[BaseModel] = GetSchemaInput
    
    async def _arun(self, table_name: str) -> str:
        result = await get_schema_via_mcp(table_name)
        
        if not result.get("success"):
            return f"获取表结构失败: {result.get('error', '未知错误')}"
        
        columns = result.get("columns", [])
        
        lines = [f"表 '{table_name}' 的字段结构：", ""]
        for col in columns:
            nullable = "可空" if col["nullable"] else "非空"
            comment = f" ({col['comment']})" if col["comment"] else ""
            lines.append(f"- {col['name']}: {col['type']} [{nullable}]{comment}")
        
        return "\\n".join(lines)
    
    def _run(self, table_name: str) -> str:
        return asyncio.run(self._arun(table_name))


class ListTablesTool(BaseTool):
    """
    列出所有表工具
    
    Data Agent 不知道有什么表时，先调用这个工具。
    """
    
    name: str = "list_tables"
    description: str = """
    列出当前数据库中的所有表名。
    
    使用场景：
    - 用户没有指定表名时，先查看有哪些表
    - 确认表名拼写是否正确
    
    无参数，直接调用即可。
    """
    
    args_schema: Type[BaseModel] = ListTablesInput
    
    async def _arun(self, **kwargs) -> str:
        result = await list_tables_via_mcp()
        
        if not result.get("success"):
            return f"获取表列表失败: {result.get('error', '未知错误')}"
        
        tables = result.get("tables", [])
        return "数据库中的表：\\n" + "\\n".join([f"- {t}" for t in tables])
    
    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))


# ============================================================
# 3. 工具集合（方便 Data Agent 一次性加载）
# ============================================================

def get_sql_tools() -> list:
    """
    获取所有 SQL 相关工具
    
    Data Agent 初始化时调用：
        tools = get_sql_tools()
        agent = create_react_agent(llm, tools)
    """
    return [
        ExecuteSQLTool(),
        GetTableSchemaTool(),
        ListTablesTool(),
    ]


print("✅ backend/app/tools/sql_tool.py 创建完成")
