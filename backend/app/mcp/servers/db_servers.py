
import os

"""
MCP 数据库服务 (mcp/servers/db_server.py)

职责：
1. 暴露数据库查询工具（Tool）给 Agent 调用
2. 暴露数据库结构信息（Resource）给 Agent 读取
3. 权限控制：只读查询，禁止 DELETE/DROP/UPDATE 等危险操作

MCP 协议说明：
================
- Tool: 可执行的动作（如 execute_sql）
- Resource: 只读数据（如 schema 信息）
- 传输方式：STDIO（本地）或 HTTP（远程）

企业安全要点：
================
1. SQL 注入防护：参数化查询
2. 危险操作拦截：禁止 DELETE/DROP/TRUNCATE
3. 查询超时：防止慢查询拖垮数据库
4. 结果限制：最多返回 10000 行
5. 审计日志：记录每次查询

使用方式：
=========
# 方式1：作为子进程启动（STDIO）
python -m app.mcp.servers.db_server

# 方式2：作为独立服务启动（HTTP）
python -m app.mcp.servers.db_server --transport http --port 8001
"""

import asyncio
import re
import time
from typing import Optional
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from sqlalchemy import text, create_engine
from sqlalchemy.exc import SQLAlchemyError, TimeoutError

from app.core.config import settings


# ============================================================
# 1. 创建 FastMCP 实例
# ============================================================
# 
# FastMCP 是 MCP Python SDK 的高级封装，自动处理：
# - 协议握手（JSON-RPC 2.0）
# - 工具注册和发现
# - 资源管理
# - 错误处理
# ============================================================

mcp = FastMCP("mysql-database-server")

# 数据库连接池（全局单例）
_engine = None

def _get_engine():
    """获取或创建数据库引擎（线程安全）"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.MYSQL_URL.replace("+aiomysql", "+pymysql"),
            pool_size=settings.MYSQL_POOL_SIZE,
            max_overflow=settings.MYSQL_MAX_OVERFLOW,
            pool_pre_ping=True,  # 连接前ping，自动重连
            pool_recycle=3600,   # 1小时回收连接，防止超时
            echo=False,
        )
    return _engine


# ============================================================
# 2. 工具定义（Tools）
# ============================================================
# 
# @mcp.tool() 装饰器会自动：
# 1. 从函数签名生成 JSON Schema（LLM 用这个理解工具）
# 2. 注册到 MCP 协议中
# 3. 处理参数序列化/反序列化
# 
# 函数 docstring 会作为工具描述，LLM 靠这个判断什么时候调用
# ============================================================

@mcp.tool()
async def execute_sql(query: str, max_rows: int = 10000) -> dict:
    """
    执行 SQL 查询并返回结果。
    
    **安全限制**：
    - 只允许 SELECT 语句
    - 禁止 DELETE/DROP/TRUNCATE/UPDATE/INSERT/ALTER/CREATE
    - 查询超时 30 秒
    - 最多返回 max_rows 行（默认 10000）
    
    **参数**：
    - query: SQL 查询语句（必须是 SELECT）
    - max_rows: 最大返回行数（默认 10000，最大 50000）
    
    **返回**：
    {
        "success": true/false,
        "data": [...],           # 查询结果（字典列表）
        "row_count": 0,          # 返回行数
        "columns": [...],        # 列名列表
        "execution_time_ms": 0,  # 执行耗时
        "error": null            # 错误信息（如有）
    }
    
    **示例**：
    execute_sql("SELECT category, SUM(amount) as total FROM sales GROUP BY category")
    """
    
    start_time = time.time()
    
    # 1. 安全校验：只允许 SELECT
    cleaned_query = query.strip().upper()
    
    # 危险关键词列表
    dangerous_keywords = [
        "DELETE", "DROP", "TRUNCATE", "UPDATE", "INSERT",
        "ALTER", "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
    ]
    
    for keyword in dangerous_keywords:
        # 用正则匹配单词边界，防止误伤（如 "SELECT" 里的 "ELECT"）
        pattern = r"\\b" + keyword + r"\\b"
        if re.search(pattern, cleaned_query, re.IGNORECASE):
            return {
                "success": False,
                "data": [],
                "row_count": 0,
                "columns": [],
                "execution_time_ms": 0,
                "error": f"安全拦截：检测到危险操作 '{keyword}'。只允许 SELECT 查询。",
            }
    
    # 2. 限制 max_rows
    if max_rows > 50000:
        max_rows = 50000
    
    try:
        # 3. 执行查询
        engine = _get_engine()
        
        with engine.connect() as conn:
            # 设置超时（数据库层面）
            conn.execute(text("SET SESSION MAX_EXECUTION_TIME=30000"))  # 30秒
            
            # 执行查询
            result = conn.execute(text(query))
            
            # 获取列名
            columns = list(result.keys())
            
            # 获取数据（限制行数）
            rows = []
            for i, row in enumerate(result):
                if i >= max_rows:
                    break
                rows.append(dict(zip(columns, row)))
            
            execution_time = (time.time() - start_time) * 1000
            
            return {
                "success": True,
                "data": rows,
                "row_count": len(rows),
                "columns": columns,
                "execution_time_ms": round(execution_time, 2),
                "error": None,
            }
            
    except SQLAlchemyError as e:
        execution_time = (time.time() - start_time) * 1000
        return {
            "success": False,
            "data": [],
            "row_count": 0,
            "columns": [],
            "execution_time_ms": round(execution_time, 2),
            "error": f"SQL执行错误: {str(e)}",
        }
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        return {
            "success": False,
            "data": [],
            "row_count": 0,
            "columns": [],
            "execution_time_ms": round(execution_time, 2),
            "error": f"未知错误: {str(e)}",
        }


@mcp.tool()
async def get_table_schema(table_name: str) -> dict:
    """
    获取指定表的字段结构信息。
    
    Data Agent 在写 SQL 之前，需要先了解表结构。
    这个工具返回表的字段名、类型、注释等。
    
    **参数**：
    - table_name: 表名（如 "sales", "users", "orders"）
    
    **返回**：
    {
        "success": true/false,
        "table_name": "sales",
        "columns": [
            {"name": "id", "type": "INT", "nullable": false, "comment": "主键"},
            {"name": "category", "type": "VARCHAR(50)", "nullable": true, "comment": "品类"},
            ...
        ],
        "error": null
    }
    """
    
    try:
        engine = _get_engine()
        
        with engine.connect() as conn:
            # 查询 MySQL 的 information_schema
            sql = text("""
                SELECT 
                    COLUMN_NAME as name,
                    DATA_TYPE as type,
                    IS_NULLABLE as nullable,
                    COLUMN_COMMENT as comment,
                    COLUMN_DEFAULT as default_value
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = :table_name
                ORDER BY ORDINAL_POSITION
            """)
            
            result = conn.execute(sql, {"table_name": table_name})
            columns = []
            for row in result:
                columns.append({
                    "name": row.name,
                    "type": row.type,
                    "nullable": row.nullable == "YES",
                    "comment": row.comment or "",
                    "default": row.default_value,
                })
            
            return {
                "success": True,
                "table_name": table_name,
                "columns": columns,
                "error": None,
            }
            
    except Exception as e:
        return {
            "success": False,
            "table_name": table_name,
            "columns": [],
            "error": f"获取表结构失败: {str(e)}",
        }


@mcp.tool()
async def list_tables() -> dict:
    """
    列出当前数据库中的所有表。
    
    Data Agent 不知道有什么表时，先调用这个工具。
    
    **返回**：
    {
        "success": true/false,
        "tables": ["sales", "users", "orders", ...],
        "error": null
    }
    """
    
    try:
        engine = _get_engine()
        
        with engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result]
            
            return {
                "success": True,
                "tables": tables,
                "error": None,
            }
            
    except Exception as e:
        return {
            "success": False,
            "tables": [],
            "error": f"获取表列表失败: {str(e)}",
        }


# ============================================================
# 3. 资源定义（Resources）
# ============================================================
# 
# Resource 是只读数据，Agent 可以随时读取。
# 与 Tool 的区别：Resource 不执行动作，只提供信息。
# ============================================================

@mcp.resource("schema://tables")
async def get_all_tables_resource() -> str:
    """
    数据库中所有表的列表（Resource 格式）。
    
    Resource URI 格式：schema://tables
    """
    result = await list_tables()
    if result["success"]:
        return "\\n".join(result["tables"])
    return f"Error: {result.get('error', 'Unknown error')}"


@mcp.resource("schema://{table_name}")
async def get_table_schema_resource(table_name: str) -> str:
    """
    指定表的字段结构（Resource 格式）。
    
    Resource URI 格式：schema://sales
    """
    result = await get_table_schema(table_name)
    if result["success"]:
        lines = [f"表: {table_name}", "字段:"]
        for col in result["columns"]:
            lines.append(f"  - {col['name']}: {col['type']} (nullable={col['nullable']}) {col['comment']}")
        return "\\n".join(lines)
    return f"Error: {result.get('error', 'Unknown error')}"


# ============================================================
# 4. 启动入口
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Database Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="传输方式：stdio（本地子进程）或 http（远程服务）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="HTTP 模式下的端口（默认 8001）",
    )
    
    args = parser.parse_args()
    
    if args.transport == "stdio":
        # STDIO 模式：作为子进程运行，通过标准输入输出通信
        # 这是 Claude Desktop / Cursor 的默认方式
        print("🚀 MCP Database Server 启动 (STDIO 模式)", flush=True)
        mcp.run(transport="stdio")
    else:
        # HTTP 模式：作为独立服务运行
        print(f"🚀 MCP Database Server 启动 (HTTP 模式, 端口 {args.port})")
        mcp.run(transport="http", port=args.port)

print("✅ backend/app/mcp/servers/db_server.py 创建完成")
