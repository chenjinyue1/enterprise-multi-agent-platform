
import os

"""
Viz Agent (agents/viz_agent.py)

职责：
1. 读取 Data Agent 的查询结果（State.data_results）
2. 读取 Analysis Agent 的分析结论（State.analysis_results）
3. 根据数据特征选择合适的图表类型
4. 生成 ECharts 图表配置
5. 将结果封装为 ChartSpec，写入 State.charts

设计要点：
=========
1. 使用 ReAct Agent：先思考需要什么图表，再调用工具生成
2. 工具选择：
   - recommend_chart_type：不确定时先获取建议
   - generate_chart：生成具体的 ECharts 配置
3. 输入：State.data_results.data + State.analysis_results
4. 输出：ChartSpec 列表（可生成多个图表）

图表生成策略：
==============
- 根据分析结果中的洞察类型选择图表：
  * trend（趋势）→ line 折线图
  * comparison（对比）→ bar 柱状图
  * summary（汇总）→ pie 饼图 或 table 表格
  * correlation（相关）→ scatter 散点图
  * anomaly（异常）→ bar 柱状图（标注异常点）

架构关系：
=========
Supervisor (分配可视化任务)
    ↓
Viz Agent (ReAct Agent)
    ↓ 读取 State.data_results / analysis_results
    ↓ 调用 Tools
Chart Tools (BaseTool)
    ↓ 调用 Python MCP Server
Python MCP Server
    ↓ 安全沙箱执行
生成 ECharts 配置
    ↓
ChartSpec（写入 State.charts）
"""

import json
import time
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate

from app.core.config import settings
from app.graph.state import AgentState, ChartSpec, TaskStatus, AnalysisInsight
from app.tools.chart_tool import get_chart_tools


# ============================================================
# 1. Viz Agent 系统提示词
# ============================================================

VIZ_AGENT_PROMPT = """你是企业智能数据分析平台的"可视化专家"（Viz Agent）。

## 你的职责
1. 根据数据特征和分析结论，选择合适的图表类型
2. 生成美观、清晰的 ECharts 图表配置
3. 确保图表能准确传达数据洞察

## 工作流程

### 步骤1：分析数据和洞察
- 查看 Data Agent 提供的原始数据（字段、类型、行数）
- 查看 Analysis Agent 的分析结论（洞察类型、关键发现）
- 判断需要生成哪些图表

### 步骤2：选择图表类型
根据数据特征和分析目标选择：
- 分类对比 → bar（柱状图）
- 时间趋势 → line（折线图）
- 占比构成 → pie（饼图）
- 变量关系 → scatter（散点图）
- 矩阵数据 → heatmap（热力图）
- 明细展示 → table（表格）

如果不确定，可以先调用 `recommend_chart_type` 获取建议。

### 步骤3：生成图表配置
调用 `generate_chart` 工具，传入：
- chart_type: 图表类型
- data_json: 数据（JSON 字符串）
- title: 图表标题（简洁明了）
- x_field/y_field 等字段映射

### 步骤4：输出结果
将生成的图表配置整理为 JSON 格式：
```json
{
  "charts": [
    {
      "chart_id": "唯一ID",
      "chart_type": "bar",
      "title": "图表标题",
      "data_source": "data_results",
      "x_field": "字段名",
      "y_field": "字段名",
      "config": {"echarts": {...}}
    }
  ]
}
```

## 图表设计规范

1. **标题**：简洁明了，说明图表内容
   - 好的："Q3 各品类销售额对比"
   - 差的："图表1"

2. **颜色**：使用企业品牌色，避免过于花哨
   - 主色：#5470c6（蓝色）
   - 辅色：#91cc75（绿色）、#fac858（黄色）、#ee6666（红色）

3. **标签**：关键数据点添加标签，便于阅读

4. **多图表**：如果数据维度多，可以生成多个图表
   - 例如：一个柱状图展示销售额，一个饼图展示占比

## 工具说明

你有以下工具可用：

{tools}

工具名称格式：
- 调用工具时，使用格式：
  ```
  Thought: 我需要推荐图表类型
  Action: recommend_chart_type
  Action Input: {"data_json": "...", "goal": "对比各品类销售额"}
  ```

## 当前任务

{input}

{agent_scratchpad}
"""


# ============================================================
# 2. 创建 Viz Agent
# ============================================================

def create_viz_agent():
    """创建 Viz Agent（ReAct Agent）"""
    
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0.2,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )
    
    tools = get_chart_tools()
    
    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=PromptTemplate.from_template(VIZ_AGENT_PROMPT),
    )
    
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=10,
        handle_parsing_errors=True,
        verbose=False,
    )
    
    return agent_executor


# ============================================================
# 3. Viz Agent 节点函数
# ============================================================

async def viz_agent_node(state: AgentState) -> dict:
    """
    Viz Agent 节点函数
    
    从 State 读取数据和分析结果，生成图表配置。
    """
    
    start_time = time.time()
    
    # 1. 读取数据和分析结果
    data_results = state.data_results
    analysis_results = state.analysis_results
    
    if not data_results or not data_results.data:
        error_msg = "Viz Agent 未收到数据"
        state.add_trace(
            agent="viz_agent",
            action="no_data",
            status=TaskStatus.FAILED,
            error_message=error_msg,
        )
        state.error_log.append(error_msg)
        return {"error_log": state.error_log, "active_agent": "supervisor"}
    
    # 2. 读取任务
    task = state.current_task
    if not task:
        task = "根据数据生成合适的可视化图表"
    
    # 3. 记录开始
    state.add_trace(
        agent="viz_agent",
        action="start_viz",
        input_summary=f"数据行数: {data_results.row_count}, 任务: {task[:100]}",
    )
    
    # 4. 准备输入
    data_json = json.dumps(data_results.data, ensure_ascii=False, default=str)
    
    # 构建 Agent 输入
    insights_summary = ""
    if analysis_results and analysis_results.insights:
        insights_summary = "\\n".join([
            f"- [{insight.type}] {insight.title}: {insight.description[:100]}"
            for insight in analysis_results.insights[:5]
        ])
    
    agent_input = f"""可视化任务：{task}

数据信息：
- 数据来源：{data_results.data_source}
- 数据行数：{data_results.row_count}
- 字段列表：{data_results.schema or list(data_results.data[0].keys()) if data_results.data else []}
- 查询 SQL：{data_results.query}

分析洞察：
{insights_summary or "无分析洞察"}

原始数据（前5行）：
{json.dumps(data_results.data[:5], ensure_ascii=False, default=str)}

请根据数据特征和洞察，生成合适的图表配置。
"""
    
    # 5. 创建并执行 Viz Agent
    try:
        agent_executor = create_viz_agent()
        
        result = await agent_executor.ainvoke({
            "input": agent_input,
            "agent_scratchpad": "",
        })
        
        output = result.get("output", "")
        
        # 6. 解析输出为 ChartSpec 列表
        charts = _parse_viz_output(output, data_results)
        
        # 7. 计算耗时
        duration_ms = (time.time() - start_time) * 1000
        
        # 8. 记录成功轨迹
        state.add_trace(
            agent="viz_agent",
            action="viz_complete",
            status=TaskStatus.SUCCESS,
            output_summary=f"生成 {len(charts)} 个图表",
            duration_ms=duration_ms,
        )
        
        # 9. 添加 Agent 消息
        charts_info = "\\n".join([
            f"- {chart.chart_type}: {chart.title}"
            for chart in charts
        ])
        
        state.add_message(
            role="agent",
            content=f"[Viz Agent] 图表生成完成。\\n\\n生成图表：\\n{charts_info}",
            agent_name="viz_agent",
        )
        
        # 10. 返回状态更新
        return {
            "charts": charts,  # LangGraph 会自动追加到 State.charts
            "task_status": TaskStatus.SUCCESS,
            "active_agent": "supervisor",
        }
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = f"Viz Agent 执行失败: {str(e)}"
        
        state.add_trace(
            agent="viz_agent",
            action="viz_error",
            status=TaskStatus.FAILED,
            error_message=error_msg,
            duration_ms=duration_ms,
        )
        
        state.error_log.append(error_msg)
        
        state.add_message(
            role="agent",
            content=f"[Viz Agent] 图表生成失败: {error_msg}",
            agent_name="viz_agent",
        )
        
        return {
            "error_log": state.error_log,
            "task_status": TaskStatus.FAILED,
            "active_agent": "supervisor",
        }


# ============================================================
# 4. 辅助函数：解析 Viz Agent 输出
# ============================================================

def _parse_viz_output(output: str, data_results) -> List[ChartSpec]:
    """
    解析 Viz Agent 的输出为 ChartSpec 列表
    
    尝试从输出中提取 JSON 格式的图表配置。
    """
    
    import re
    import uuid
    
    charts = []
    
    # 尝试1：提取 JSON 代码块
    json_patterns = [
        r"```json\\s*(.*?)\\s*```",
        r"```\\s*(\\{.*?\\})\\s*```",
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, output, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                
                if "charts" in data and isinstance(data["charts"], list):
                    for chart_data in data["charts"]:
                        charts.append(ChartSpec(
                            chart_id=chart_data.get("chart_id", f"chart_{uuid.uuid4().hex[:8]}"),
                            chart_type=chart_data.get("chart_type", "bar"),
                            title=chart_data.get("title", "未命名图表"),
                            data_source=chart_data.get("data_source", "data_results"),
                            x_field=chart_data.get("x_field"),
                            y_field=chart_data.get("y_field"),
                            config=chart_data.get("config", {}),
                        ))
                elif "chart_type" in data:
                    charts.append(ChartSpec(
                        chart_id=data.get("chart_id", f"chart_{uuid.uuid4().hex[:8]}"),
                        chart_type=data.get("chart_type", "bar"),
                        title=data.get("title", "未命名图表"),
                        data_source=data.get("data_source", "data_results"),
                        x_field=data.get("x_field"),
                        y_field=data.get("y_field"),
                        config=data.get("config", {}),
                    ))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    
    # 尝试2：直接解析整个输出
    try:
        data = json.loads(output)
        if "charts" in data and isinstance(data["charts"], list):
            for chart_data in data["charts"]:
                charts.append(ChartSpec(
                    chart_id=chart_data.get("chart_id", f"chart_{uuid.uuid4().hex[:8]}"),
                    chart_type=chart_data.get("chart_type", "bar"),
                    title=chart_data.get("title", "未命名图表"),
                    data_source="data_results",
                    config=chart_data.get("config", {}),
                ))
    except (json.JSONDecodeError, KeyError):
        pass
    
    # 兜底：如果没有任何图表，生成一个默认的柱状图
    if not charts and data_results and data_results.data:
        fields = list(data_results.data[0].keys())
        numeric_fields = [f for f in fields if isinstance(data_results.data[0].get(f), (int, float))]
        categorical_fields = [f for f in fields if f not in numeric_fields]
        
        if categorical_fields and numeric_fields:
            charts.append(ChartSpec(
                chart_id=f"chart_{uuid.uuid4().hex[:8]}",
                chart_type="bar",
                title="数据概览",
                data_source="data_results",
                x_field=categorical_fields[0],
                y_field=numeric_fields[0],
                config={},
            ))
    
    return charts


print("✅ backend/app/agents/viz_agent.py 创建完成")
