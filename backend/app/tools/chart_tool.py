
import os

"""
图表生成工具封装 (tools/chart_tool.py)

职责：
1. 将数据转换为图表配置（ECharts/Plotly 格式）
2. 提供常用图表类型的生成函数
3. 通过 Python MCP Server 执行图表数据计算
4. 返回 ChartSpec 结构化配置

图表库选择：
============
前端使用 ECharts（百度开源，国内最流行）：
- 丰富的图表类型
- 良好的中文文档
- 与 React 集成成熟（echarts-for-react）
- 企业级项目广泛使用

Viz Agent 输出 ECharts 配置，前端直接渲染。
"""

import json
import asyncio
from typing import Optional, Type, Literal

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from app.mcp.client import MCPClient
from app.graph.state import ChartSpec


# ============================================================
# 1. 输入参数模型
# ============================================================

class GenerateChartInput(BaseModel):
    """generate_chart 工具的输入参数"""
    chart_type: Literal["bar", "line", "pie", "scatter", "heatmap", "table"] = Field(
        description="图表类型：bar(柱状图)、line(折线图)、pie(饼图)、scatter(散点图)、heatmap(热力图)、table(表格)"
    )
    data_json: str = Field(
        description="图表数据（JSON 数组字符串）",
    )
    title: str = Field(
        description="图表标题",
    )
    x_field: Optional[str] = Field(
        default=None,
        description="X轴字段名（bar/line/scatter 需要）",
    )
    y_field: Optional[str] = Field(
        default=None,
        description="Y轴字段名（bar/line/scatter 需要）",
    )
    category_field: Optional[str] = Field(
        default=None,
        description="分类字段名（pie 需要）",
    )
    value_field: Optional[str] = Field(
        default=None,
        description="数值字段名（pie 需要）",
    )
    series_field: Optional[str] = Field(
        default=None,
        description="系列字段名（多系列图表需要）",
    )


class RecommendChartTypeInput(BaseModel):
    """recommend_chart_type 工具的输入参数"""
    data_json: str = Field(description="数据样本（JSON 数组）")
    goal: str = Field(description="展示目标（如'对比各品类销售额'、'展示时间趋势'）")


# ============================================================
# 2. 图表配置生成器（Python 代码模板）
# ============================================================

CHART_CODE_TEMPLATES = {
    "bar": """
import json
import pandas as pd

data = json.loads(input_data)
df = pd.DataFrame(data)

categories = df[x_field].tolist()
values = df[y_field].tolist()

result = {
    "title": {"text": title, "left": "center"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": categories, "name": x_field},
    "yAxis": {"type": "value", "name": y_field},
    "series": [{
        "type": "bar",
        "data": values,
        "itemStyle": {"color": "#5470c6"}
    }],
    "grid": {"left": "10%", "right": "10%", "bottom": "15%", "top": "15%"}
}
""",

    "line": """
import json
import pandas as pd

data = json.loads(input_data)
df = pd.DataFrame(data)

categories = df[x_field].tolist()
values = df[y_field].tolist()

result = {
    "title": {"text": title, "left": "center"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": categories, "name": x_field, "boundaryGap": False},
    "yAxis": {"type": "value", "name": y_field},
    "series": [{
        "type": "line",
        "data": values,
        "smooth": True,
        "areaStyle": {"opacity": 0.3},
        "itemStyle": {"color": "#5470c6"}
    }],
    "grid": {"left": "10%", "right": "10%", "bottom": "15%", "top": "15%"}
}
""",

    "pie": """
import json
import pandas as pd

data = json.loads(input_data)
df = pd.DataFrame(data)

pie_data = [{"name": row[category_field], "value": row[value_field]} for _, row in df.iterrows()]

result = {
    "title": {"text": title, "left": "center"},
    "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
    "series": [{
        "type": "pie",
        "radius": ["40%", "70%"],
        "avoidLabelOverlap": False,
        "itemStyle": {"borderRadius": 10, "borderColor": "#fff", "borderWidth": 2},
        "label": {"show": True, "formatter": "{b}\\n{d}%"},
        "data": pie_data
    }]
}
""",

    "scatter": """
import json
import pandas as pd

data = json.loads(input_data)
df = pd.DataFrame(data)

scatter_data = [[row[x_field], row[y_field]] for _, row in df.iterrows()]

result = {
    "title": {"text": title, "left": "center"},
    "tooltip": {"trigger": "item"},
    "xAxis": {"type": "value", "name": x_field, "scale": True},
    "yAxis": {"type": "value", "name": y_field, "scale": True},
    "series": [{
        "type": "scatter",
        "data": scatter_data,
        "symbolSize": 15,
        "itemStyle": {"color": "#5470c6"}
    }],
    "grid": {"left": "10%", "right": "10%", "bottom": "15%", "top": "15%"}
}
""",

    "table": """
import json
import pandas as pd

data = json.loads(input_data)
df = pd.DataFrame(data)

result = {
    "columns": [{"field": col, "headerName": col} for col in df.columns],
    "data": df.head(100).to_dict("records"),
    "total": len(df)
}
""",
}


# ============================================================
# 3. LangChain Tool 定义
# ============================================================

class GenerateChartTool(BaseTool):
    """
    生成图表配置工具
    
    Viz Agent 用这个工具将数据转换为 ECharts 图表配置。
    支持 bar/line/pie/scatter/table 五种图表类型。
    
    使用示例：
        tool = GenerateChartTool()
        result = await tool.ainvoke({
            "chart_type": "bar",
            "data_json": '[{"category":"A","amount":100}]',
            "title": "各品类销售额",
            "x_field": "category",
            "y_field": "amount",
        })
    """
    
    name: str = "generate_chart"
    description: str = """
    将数据转换为 ECharts 图表配置。
    
    适用场景：
    - 需要可视化展示数据
    - 生成柱状图、折线图、饼图、散点图
    - 为报告生成配套图表
    
    参数说明：
    - chart_type: 图表类型（bar/line/pie/scatter/table）
    - data_json: 数据（JSON 数组字符串）
    - title: 图表标题
    - x_field: X轴字段（bar/line/scatter 需要）
    - y_field: Y轴字段（bar/line/scatter 需要）
    - category_field: 分类字段（pie 需要）
    - value_field: 数值字段（pie 需要）
    
    图表类型选择指南：
    - bar: 分类数据对比（如各品类销售额）
    - line: 时间序列趋势（如月度销售走势）
    - pie: 占比构成（如各品类销售占比）
    - scatter: 两个变量的关系（如价格 vs 销量）
    - table: 明细数据表格
    """
    
    args_schema: Type[BaseModel] = GenerateChartInput
    
    async def _arun(
        self,
        chart_type: str,
        data_json: str,
        title: str,
        x_field: Optional[str] = None,
        y_field: Optional[str] = None,
        category_field: Optional[str] = None,
        value_field: Optional[str] = None,
        series_field: Optional[str] = None,
    ) -> str:
        """异步执行"""
        
        code_template = CHART_CODE_TEMPLATES.get(chart_type)
        if not code_template:
            return f"不支持的图表类型: {chart_type}"
        
        # 构建完整的 Python 代码
        code_lines = [
            f'input_data = {repr(data_json)}',
            f'title = {repr(title)}',
            f'x_field = {repr(x_field or "")}',
            f'y_field = {repr(y_field or "")}',
            f'category_field = {repr(category_field or "")}',
            f'value_field = {repr(value_field or "")}',
            f'series_field = {repr(series_field or "")}',
            '',
            code_template,
        ]
        code = "\\n".join(code_lines)
        
        # 调用 Python MCP Server
        async with MCPClient() as client:
            await client.connect_to_server_stdio("app.mcp.servers.python_server")
            
            result = await client.call_tool("execute_python", {
                "code": code,
                "input_data": data_json,
                "timeout": 30,
            })
        
        if not result.get("success"):
            return f"图表生成失败: {result.get('error', '未知错误')}"
        
        exec_result = result.get("result")
        if not exec_result:
            return "图表生成成功，但无配置输出。"
        
        if isinstance(exec_result, dict):
            if "error" in exec_result:
                return f"图表生成错误: {exec_result['error']}"
            return json.dumps(exec_result, ensure_ascii=False, indent=2)
        
        return str(exec_result)
    
    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))


class RecommendChartTypeTool(BaseTool):
    """
    推荐图表类型工具
    
    根据数据特征和分析目标，推荐最适合的图表类型。
    """
    
    name: str = "recommend_chart_type"
    description: str = """
    根据数据特征推荐最适合的图表类型。
    
    适用场景：
    - 不确定用什么图表展示数据
    - 需要专业建议选择图表类型
    - 数据探索阶段
    
    返回：推荐的图表类型 + 理由 + 备选方案
    """
    
    args_schema: Type[BaseModel] = RecommendChartTypeInput
    
    async def _arun(self, data_json: str, goal: str) -> str:
        """基于规则推荐图表类型"""
        
        try:
            data = json.loads(data_json)
            if not data:
                return "数据为空，无法推荐图表类型。"
            
            sample = data[0]
            fields = list(sample.keys())
            numeric_fields = []
            categorical_fields = []
            datetime_fields = []
            
            for field in fields:
                val = sample[field]
                if isinstance(val, (int, float)):
                    numeric_fields.append(field)
                elif isinstance(val, str):
                    if any(kw in field.lower() for kw in ["date", "time", "month", "day", "year"]):
                        datetime_fields.append(field)
                    else:
                        categorical_fields.append(field)
            
            recommendations = []
            
            if "趋势" in goal or "走势" in goal or "时间" in goal:
                if datetime_fields and numeric_fields:
                    recommendations.append({
                        "type": "line",
                        "reason": "时间序列数据适合用折线图展示趋势变化",
                        "x_field": datetime_fields[0],
                        "y_field": numeric_fields[0],
                    })
            
            if "对比" in goal or "排名" in goal or "比较" in goal:
                if categorical_fields and numeric_fields:
                    recommendations.append({
                        "type": "bar",
                        "reason": "分类数据对比适合用柱状图",
                        "x_field": categorical_fields[0],
                        "y_field": numeric_fields[0],
                    })
            
            if "占比" in goal or "构成" in goal or "比例" in goal:
                if categorical_fields and numeric_fields:
                    recommendations.append({
                        "type": "pie",
                        "reason": "占比数据适合用饼图展示构成",
                        "category_field": categorical_fields[0],
                        "value_field": numeric_fields[0],
                    })
            
            if "关系" in goal or "相关" in goal or "分布" in goal:
                if len(numeric_fields) >= 2:
                    recommendations.append({
                        "type": "scatter",
                        "reason": "两个数值变量的关系适合用散点图",
                        "x_field": numeric_fields[0],
                        "y_field": numeric_fields[1],
                    })
            
            if not recommendations:
                if categorical_fields and numeric_fields:
                    recommendations.append({
                        "type": "bar",
                        "reason": "默认推荐柱状图，适合大多数分类对比场景",
                        "x_field": categorical_fields[0],
                        "y_field": numeric_fields[0],
                    })
                elif numeric_fields:
                    recommendations.append({
                        "type": "table",
                        "reason": "数据特征不明显，建议先用表格查看",
                    })
            
            lines = ["【图表类型推荐】", ""]
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"{i}. {rec['type']} 图")
                lines.append(f"   理由：{rec['reason']}")
                if "x_field" in rec:
                    lines.append(f"   X轴：{rec['x_field']}，Y轴：{rec['y_field']}")
                if "category_field" in rec:
                    lines.append(f"   分类：{rec['category_field']}，数值：{rec['value_field']}")
                lines.append("")
            
            return "\\n".join(lines)
            
        except Exception as e:
            return f"推荐失败: {str(e)}"
    
    def _run(self, data_json: str, goal: str) -> str:
        return asyncio.run(self._arun(data_json, goal))


# ============================================================
# 4. 便捷函数
# ============================================================

async def generate_chart_spec(
    chart_type: str,
    data: list,
    title: str,
    **kwargs
) -> ChartSpec:
    """直接生成 ChartSpec 对象"""
    
    import uuid
    
    tool = GenerateChartTool()
    result = await tool.ainvoke({
        "chart_type": chart_type,
        "data_json": json.dumps(data, ensure_ascii=False, default=str),
        "title": title,
        **kwargs,
    })
    
    try:
        echarts_config = json.loads(result)
    except json.JSONDecodeError:
        echarts_config = {}
    
    return ChartSpec(
        chart_id=f"chart_{uuid.uuid4().hex[:8]}",
        chart_type=chart_type,
        title=title,
        data_source="data_results",
        x_field=kwargs.get("x_field"),
        y_field=kwargs.get("y_field"),
        config={"echarts": echarts_config},
    )


# ============================================================
# 5. 工具集合
# ============================================================

def get_chart_tools() -> list:
    """获取所有图表生成相关工具"""
    return [
        GenerateChartTool(),
        RecommendChartTypeTool(),
    ]


print("✅ backend/app/tools/chart_tool.py 创建完成")
