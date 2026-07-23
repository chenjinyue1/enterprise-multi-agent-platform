
"""
Python 计算工具封装 (tools/python_tool.py)

职责：
1. 将 MCP Python 执行封装为 LangChain Tool
2. 提供数据分析专用工具（执行代码、快速分析）
3. 结果格式化：将原始输出转换为 LLM 友好的文本

架构关系：
=========
Analysis Agent (LangChain ReAct Agent)
    ↓ 调用 Tool（BaseTool 接口）
Python Tool（适配层）
    ↓ 调用 MCP Client
MCP Client (mcp/client.py)
    ↓ JSON-RPC 2.0
MCP Server (python_server.py)
    ↓ 安全沙箱执行
Python 代码执行
"""

import json
import asyncio
from typing import Optional, Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from app.mcp.client import MCPClient


# ============================================================
# 1. 输入参数模型
# ============================================================

class ExecutePythonInput(BaseModel):
    """execute_python 工具的输入参数"""
    code: str = Field(
        description="""
Python 代码字符串。建议定义 `result` 变量作为返回值。

可用库：pandas (pd), numpy (np), matplotlib, scipy, json, math 等
禁止：os, sys, subprocess, socket, 文件操作等

示例：
```python
import pandas as pd
df = pd.DataFrame(input_data)
result = {
    "mean": df["amount"].mean(),
    "std": df["amount"].std(),
}
```
""",
    )
    input_data: Optional[str] = Field(
        default=None,
        description="输入数据（JSON 字符串）。代码中可通过 `input_data` 变量访问。",
    )
    timeout: int = Field(
        default=30,
        description="执行超时时间（秒，默认 30，最大 120）",
    )


class AnalyzeDataframeInput(BaseModel):
    """analyze_dataframe 工具的输入参数"""
    data_json: str = Field(
        description="数据（JSON 数组字符串，如 [{\"category\":\"A\",\"amount\":100}, ...]）",
    )
    analysis_type: str = Field(
        default="summary",
        description="""
分析类型：
- "summary": 基础统计（计数、均值、标准差、最值）
- "correlation": 相关性分析
- "distribution": 分布分析（正态性检验）
- "outliers": 异常值检测（IQR 方法）
""",
    )


# ============================================================
# 2. LangChain Tool 定义
# ============================================================

class ExecutePythonTool(BaseTool):
    """
    执行 Python 数据分析代码工具
    
    Analysis Agent 用这个工具执行统计计算、数据转换、复杂分析。
    底层通过 MCP Client 调用 python_server 的 execute_python 工具。
    
    安全限制：
    - 只允许数据分析库（pandas, numpy, matplotlib, scipy）
    - 禁止系统/网络操作
    - 执行超时 30 秒
    - 内存限制 512MB
    
    使用示例：
        tool = ExecutePythonTool()
        result = await tool.ainvoke({
            "code": "import pandas as pd\\ndf = pd.DataFrame(input_data)\\nresult = df.groupby('category')['amount'].sum().to_dict()",
            "input_data": '[{"category":"A","amount":100}]',
        })
    """
    
    name: str = "execute_python"
    description: str = """
    在安全沙箱中执行 Python 代码进行数据分析计算。
    
    适用场景：
    - 复杂的统计计算（回归分析、假设检验）
    - 数据转换和清洗（pandas 操作）
    - 自定义计算逻辑（超出简单 SQL 的能力）
    - 生成计算中间结果（为图表做准备）
    
    可用库：pandas (pd), numpy (np), matplotlib, scipy, json, math 等
    禁止：os, sys, subprocess, socket, 文件操作等
    
    重要提示：
    - 代码中建议定义 `result` 变量作为返回值
    - input_data 参数传入 JSON 字符串，代码中通过 `input_data` 访问
    - 如果数据量大，建议先抽样或聚合
    
    示例：
    ```python
    import pandas as pd
    df = pd.DataFrame(input_data)
    # 计算各品类销售额占比
    total = df["amount"].sum()
    result = df.groupby("category")["amount"].sum().apply(lambda x: round(x/total*100, 2)).to_dict()
    ```
    """
    
    args_schema: Type[BaseModel] = ExecutePythonInput
    
    async def _arun(self, code: str, input_data: Optional[str] = None, timeout: int = 30) -> str:
        """异步执行"""
        async with MCPClient() as client:
            await client.connect_to_server_stdio("app.mcp.servers.python_server")
            
            result = await client.call_tool("execute_python", {
                "code": code,
                "input_data": input_data,
                "timeout": timeout,
            })
        
        if not result.get("success"):
            error = result.get("error", "未知错误")
            stderr = result.get("stderr", "")
            return f"代码执行失败: {error}\\n\\n标准错误输出:\\n{stderr}"
        
        # 格式化输出
        lines = []
        
        # 标准输出
        stdout = result.get("stdout", "")
        if stdout.strip():
            lines.append("【标准输出】")
            lines.append(stdout)
            lines.append("")
        
        # 执行结果
        exec_result = result.get("result")
        if exec_result is not None:
            lines.append("【执行结果】")
            if isinstance(exec_result, (dict, list)):
                lines.append(json.dumps(exec_result, ensure_ascii=False, indent=2))
            else:
                lines.append(str(exec_result))
            lines.append("")
        
        # 标准错误（如果有，但执行成功）
        stderr = result.get("stderr", "")
        if stderr.strip():
            lines.append("【警告/提示】")
            lines.append(stderr)
        
        return "\\n".join(lines) if lines else "代码执行成功，无输出。"
    
    def _run(self, code: str, input_data: Optional[str] = None, timeout: int = 30) -> str:
        return asyncio.run(self._arun(code, input_data, timeout))


class AnalyzeDataframeTool(BaseTool):
    """
    快速数据分析工具
    
    无需编写代码，直接对 JSON 数据进行常见统计分析。
    适合快速获取统计摘要、相关性、异常值等。
    
    使用示例：
        tool = AnalyzeDataframeTool()
        result = await tool.ainvoke({
            "data_json": '[{"category":"A","amount":100},{"category":"B","amount":200}]',
            "analysis_type": "summary",
        })
    """
    
    name: str = "analyze_dataframe"
    description: str = """
    对 JSON 数据进行快速统计分析，无需编写代码。
    
    适用场景：
    - 快速获取数据的基础统计指标（计数、均值、标准差、最值）
    - 检查数值列的相关性
    - 检测异常值（IQR 方法）
    - 分析数据分布特征（正态性检验）
    
    参数：
    - data_json: 数据（JSON 数组字符串）
    - analysis_type: 分析类型
      * "summary": 基础统计（默认）
      * "correlation": 相关性分析
      * "distribution": 分布分析（正态性检验）
      * "outliers": 异常值检测
    
    注意：数据必须是 JSON 数组格式，每个元素是一个对象（字典）。
    """
    
    args_schema: Type[BaseModel] = AnalyzeDataframeInput
    
    async def _arun(self, data_json: str, analysis_type: str = "summary") -> str:
        """异步执行"""
        async with MCPClient() as client:
            await client.connect_to_server_stdio("app.mcp.servers.python_server")
            
            result = await client.call_tool("analyze_dataframe", {
                "data_json": data_json,
                "analysis_type": analysis_type,
            })
        
        if not result.get("success"):
            return f"分析失败: {result.get('error', '未知错误')}"
        
        analysis = result.get("analysis", {})
        
        # 格式化输出
        lines = [f"【{analysis_type} 分析结果】", ""]
        lines.append(json.dumps(analysis, ensure_ascii=False, indent=2))
        
        return "\\n".join(lines)
    
    def _run(self, data_json: str, analysis_type: str = "summary") -> str:
        return asyncio.run(self._arun(data_json, analysis_type))


# ============================================================
# 3. 工具集合
# ============================================================

def get_python_tools() -> list:
    """
    获取所有 Python 计算相关工具
    
    Analysis Agent 初始化时调用：
        tools = get_python_tools()
        agent = create_react_agent(llm, tools)
    """
    return [
        ExecutePythonTool(),
        AnalyzeDataframeTool(),
    ]


print("✅ backend/app/tools/python_tool.py 创建完成")
