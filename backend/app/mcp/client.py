"""
MCP 客户端 (mcp/client.py)

职责：
1. 连接 MCP Server（STDIO 或 HTTP）
2. 发现 Server 提供的 Tools 和 Resources
3. 调用 Tools 执行动作
4. 读取 Resources 获取数据

为什么需要 Client？
==================
MCP 是"客户端-服务器"架构：
- Server：提供工具和资源（如数据库查询）
- Client：连接 Server，调用工具
- Host：管理多个 Client（如 Claude Desktop）

在我们的系统中：
- Data Agent 是 Host 的一部分
- 通过 MCP Client 连接 db_server
- 调用 execute_sql 工具查询数据库

两种连接方式：
================
1. STDIO（本地子进程）：
   - 启动 Server 作为子进程
   - 通过 stdin/stdout 通信
   - 适合开发调试、单机部署

2. HTTP（远程服务）：
   - 连接已运行的 HTTP Server
   - 通过 HTTP/WebSocket 通信
   - 适合企业分布式部署

使用方式：
=========
    async with MCPClient() as client:
        await client.connect_to_server("db")
        result = await client.call_tool("execute_sql", {"query": "SELECT * FROM sales"})
"""

import asyncio
import json
import subprocess
from typing import Any, Optional
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from app.core.config import settings


class MCPClient:
    """
    MCP 客户端
    
    封装了连接、发现、调用等操作，Data Agent 直接用这个类。
    """
    
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.server_params: Optional[StdioServerParameters] = None
        self._tools: list = []
        self._resources: list = []
    
    async def connect_to_server_stdio(self, server_script_path: str) -> None:
        """
        通过 STDIO 连接本地 MCP Server（子进程模式）
        
        参数：
            server_script_path: MCP Server 脚本路径
                如 "app/mcp/servers/db_server.py"
        
        使用场景：
        - 开发调试
        - 单机部署
        - Server 和 Agent 在同一台机器
        """
        
        # 配置 Server 启动参数
        self.server_params = StdioServerParameters(
            command="python",           # 启动命令
            args=["-m", server_script_path.replace("/", ".").replace(".py", "")],
            env=None,                   # 继承当前环境变量
        )
        
        # 建立 stdio 连接
        async with stdio_client(self.server_params) as (read, write):
            self.session = await ClientSession(read, write).__aenter__()
            
            # 初始化会话（握手）
            await self.session.initialize()
            
            # 发现可用工具
            tools = await self.session.list_tools()
            self._tools = tools.tools
            
            print(f"✅ 已连接 MCP Server (STDIO)，发现 {len(self._tools)} 个工具:")
            for tool in self._tools:
                print(f"   - {tool.name}: {tool.description[:50]}...")
    
    async def connect_to_server_http(self, url: str) -> None:
        """
        通过 HTTP 连接远程 MCP Server
        
        参数：
            url: Server URL，如 "http://localhost:8001"
        
        使用场景：
        - 企业分布式部署
        - Server 独立运行（如 Kubernetes 中）
        - 多个 Agent 共享同一个 Server
        """
        
        # 使用 SSE (Server-Sent Events) 传输
        # 注意：2026 年规范已推荐 Streamable HTTP，但 SDK 可能仍用 SSE
        async with sse_client(url) as (read, write):
            self.session = await ClientSession(read, write).__aenter__()
            await self.session.initialize()
            
            tools = await self.session.list_tools()
            self._tools = tools.tools
            
            print(f"✅ 已连接 MCP Server (HTTP {url})，发现 {len(self._tools)} 个工具")
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        调用 MCP Server 的工具
        
        参数：
            tool_name: 工具名称（如 "execute_sql"）
            arguments: 工具参数（如 {"query": "SELECT * FROM sales"}）
        
        返回：
            工具执行结果（dict）
        """
        if not self.session:
            raise RuntimeError("未连接 MCP Server，请先调用 connect_to_server")
        
        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            
            # 解析结果
            # MCP 返回的是 Content 对象列表，提取文本内容
            content = []
            for item in result.content:
                if hasattr(item, "text"):
                    content.append(item.text)
                elif hasattr(item, "data"):
                    content.append(item.data)
            
            # 尝试解析为 JSON
            if content:
                try:
                    return json.loads(content[0])
                except json.JSONDecodeError:
                    return {"result": content[0]}
            
            return {"result": None}
            
        except Exception as e:
            return {
                "success": False,
                "error": f"调用工具失败: {str(e)}",
            }
    
    async def read_resource(self, uri: str) -> str:
        """
        读取 MCP Server 的资源
        
        参数：
            uri: 资源 URI（如 "schema://sales"）
        
        返回：
            资源内容（字符串）
        """
        if not self.session:
            raise RuntimeError("未连接 MCP Server")
        
        try:
            result = await self.session.read_resource(uri)
            
            content = []
            for item in result.contents:
                if hasattr(item, "text"):
                    content.append(item.text)
            
            return "\\n".join(content) if content else ""
            
        except Exception as e:
            return f"读取资源失败: {str(e)}"
    
    async def list_tools(self) -> list:
        """列出所有可用工具"""
        if not self.session:
            return []
        
        tools = await self.session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
            for tool in tools.tools
        ]
    
    async def close(self) -> None:
        """关闭连接"""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()


# ============================================================
# 便捷函数：Data Agent 直接调用
# ============================================================

async def execute_sql_via_mcp(query: str, max_rows: int = 10000) -> dict:
    """
    通过 MCP 执行 SQL 查询（便捷函数）
    
    使用方式：
        result = await execute_sql_via_mcp("SELECT * FROM sales")
        print(result["data"])
    
    注意：每次调用会新建连接，适合低频查询。
    高频场景建议复用 MCPClient 实例。
    """
    async with MCPClient() as client:
        # 连接本地数据库 MCP Server
        await client.connect_to_server_stdio("app/mcp/servers/db_server")
        
        # 调用 execute_sql 工具
        result = await client.call_tool("execute_sql", {
            "query": query,
            "max_rows": max_rows,
        })
        
        return result


async def get_schema_via_mcp(table_name: str) -> dict:
    """通过 MCP 获取表结构"""
    async with MCPClient() as client:
        await client.connect_to_server_stdio("app/mcp/servers/db_server")
        return await client.call_tool("get_table_schema", {"table_name": table_name})


async def list_tables_via_mcp() -> dict:
    """通过 MCP 获取所有表"""
    async with MCPClient() as client:
        await client.connect_to_server_stdio("app/mcp/servers/db_server")
        return await client.call_tool("list_tables", {})


print("✅ backend/app/mcp/client.py 创建完成")
