
"""
Analysis Agent (agents/analysis_agent.py)

职责：
1. 读取 Data Agent 的查询结果（State.data_results）
2. 分析数据特征、趋势、异常、相关性
3. 生成业务洞察和行动建议
4. 将结果封装为 AnalysisResult，写入 State

设计要点：
=========
1. 使用 ReAct Agent：先思考分析思路，再调用工具执行
2. 工具选择：
   - analyze_dataframe：快速统计（无需写代码）
   - execute_python：复杂分析（自定义代码）
3. 输入：State.data_results.data（原始数据）
4. 输出：AnalysisResult（结构化分析结论）

分析维度：
=========
- 描述性统计：计数、均值、标准差、最值、分位数
- 趋势分析：时间序列变化、增长率
- 对比分析：同比环比、品类对比、区域对比
- 异常检测：离群值、突变点
- 相关性分析：变量间关系
- 分布分析：正态性、偏度、峰度
- 业务洞察：基于数据的业务建议

架构关系：
=========
Supervisor (分配分析任务)
    ↓
Analysis Agent (ReAct Agent)
    ↓ 读取 State.data_results
    ↓ 调用 Tools
Python Tools (LangChain BaseTool)
    ↓ 调用 MCP Client
MCP Client
    ↓ JSON-RPC 2.0
MCP Server (python_server.py)
    ↓ 安全沙箱执行
Python 计算（pandas, numpy, scipy）
    ↓
AnalysisResult（结构化输出）
"""

import json
import time
from typing import Optional, List

from langchain_openai import ChatOpenAI
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.graph.state import (
    AgentState, AnalysisResult, AnalysisInsight, 
    TaskStatus, DataQueryResult
)
from app.tools.python_tool import get_python_tools


# ============================================================
# 1. Analysis Agent 系统提示词
# ============================================================
# 
# 这是 Analysis Agent 的"身份卡"，告诉 LLM：
# - 你是数据分析专家
# - 你的输入是原始数据（JSON格式）
# - 你的输出是结构化的分析结论
# - 你必须使用工具进行精确计算
# ============================================================

ANALYSIS_AGENT_PROMPT = """你是企业智能数据分析平台的"数据分析专家"（Analysis Agent）。

## 你的职责
1. 接收 Supervisor 分配的数据分析任务
2. 读取 Data Agent 提供的原始数据
3. 使用 Python 工具进行精确的统计分析
4. 生成结构化的分析结论和业务洞察

## 分析流程（必须执行）

### 步骤1：数据概览
先调用 `analyze_dataframe` 工具，使用 `analysis_type="summary"` 获取数据基础统计。
了解：
- 数据量（行数、列数）
- 各列的数据类型
- 基础统计指标（均值、标准差、最值）
- 缺失值情况

### 步骤2：深入分析
根据任务需求，选择合适的分析类型：
- 需要了解变量关系 → `analyze_dataframe` 用 `correlation`
- 需要检查数据质量 → `analyze_dataframe` 用 `outliers`
- 需要了解分布特征 → `analyze_dataframe` 用 `distribution`
- 需要复杂计算（如占比、增长率、预测）→ `execute_python` 编写自定义代码

### 步骤3：生成洞察
基于统计结果，生成业务洞察：
- 趋势洞察：数据上升/下降/平稳？变化幅度？
- 对比洞察：各品类/区域差异？领先/落后的是？
- 异常洞察：有无异常值？可能原因？
- 建议洞察：基于数据，给出业务建议

### 步骤4：输出结果
将分析结果整理为 JSON 格式：
```json
{
  "summary": "分析摘要（1-2句话概括核心发现）",
  "insights": [
    {
      "type": "trend/comparison/anomaly/correlation/summary",
      "title": "洞察标题",
      "description": "详细描述",
      "confidence": 0.95,
      "supporting_data": {"关键数据": "值"}
    }
  ],
  "metrics": {
    "自定义指标": "值"
  },
  "recommendations": [
    "基于数据的行动建议1",
    "基于数据的行动建议2"
  ]
}
```

## 工具说明

你有以下工具可用：

{tools}

工具名称格式：
- 调用工具时，使用格式：
  ```
  Thought: 我需要了解数据基础统计
  Action: analyze_dataframe
  Action Input: {{"data_json": "...", "analysis_type": "summary"}}
  ```

## 重要提示

1. **必须使用工具计算**：不要凭 LLM 的"直觉"给出数字，所有统计结论必须通过工具计算验证。
2. **数据格式**：原始数据通过 `input_data` 变量传入 Python 代码，格式是 JSON 列表。
3. **代码建议**：使用 `execute_python` 时，建议先 `import pandas as pd`，然后 `df = pd.DataFrame(input_data)`。
4. **结果变量**：代码中定义 `result` 变量作为返回值，会被提取到输出中。
5. **置信度**：insights 中的 confidence 字段（0-1），表示你对这个洞察的信心程度。基于数据直接计算的设为 0.95+，需要推断的设为 0.7-0.85。

## 当前任务

{input}

{agent_scratchpad}
"""


# ============================================================
# 2. 创建 Analysis Agent
# ============================================================

def create_analysis_agent():
    """
    创建 Analysis Agent（ReAct Agent）
    
    与 Data Agent 的区别：
    - Data Agent 的工具是 SQL 查询（查数据库）
    - Analysis Agent 的工具是 Python 计算（做分析）
    - Analysis Agent 的输入是 Data Agent 的产出（原始数据）
    """
    
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0.2,  # 稍高一点点，分析需要一定灵活性
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )
    
    tools = get_python_tools()
    
    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=PromptTemplate.from_template(ANALYSIS_AGENT_PROMPT),
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
# 3. Analysis Agent 节点函数
# ============================================================

async def analysis_agent_node(state: AgentState) -> dict:
    """
    Analysis Agent 节点函数
    
    从 State 读取 data_results，进行分析，写入 analysis_results。
    """
    
    start_time = time.time()
    
    # 1. 读取数据
    data_results = state.data_results
    
    if not data_results or not data_results.data:
        error_msg = "Analysis Agent 未收到数据，请先执行 Data Agent"
        state.add_trace(
            agent="analysis_agent",
            action="no_data",
            status=TaskStatus.FAILED,
            error_message=error_msg,
        )
        state.error_log.append(error_msg)
        
        state.add_message(
            role="agent",
            content=f"[Analysis Agent] 错误：{error_msg}",
            agent_name="analysis_agent",
        )
        
        return {
            "error_log": state.error_log,
            "active_agent": "supervisor",
        }
    
    # 2. 读取任务
    task = state.current_task
    if not task:
        task = "对数据进行全面的统计分析，生成洞察和建议"
    
    # 3. 记录开始
    state.add_trace(
        agent="analysis_agent",
        action="start_analysis",
        input_summary=f"数据行数: {data_results.row_count}, 任务: {task[:100]}",
    )
    
    # 4. 准备输入
    # 将数据转换为 JSON 字符串，作为工具的 input_data
    data_json = json.dumps(data_results.data, ensure_ascii=False, default=str)
    
    # 构建 Agent 输入：任务描述 + 数据信息
    agent_input = f"""分析任务：{task}

数据信息：
- 数据来源：{data_results.data_source}
- 查询 SQL：{data_results.query}
- 数据行数：{data_results.row_count}
- 执行耗时：{data_results.execution_time_ms}ms
- 字段列表：{data_results.schema or "未知"}

原始数据（JSON格式，可作为 input_data 传入工具）：
{data_json[:5000]}  // 截断显示，完整数据通过工具参数传递

请对数据进行深入分析，生成统计洞察和业务建议。
"""
    
    # 5. 创建并执行 Analysis Agent
    try:
        agent_executor = create_analysis_agent()
        
        result = await agent_executor.ainvoke({
            "input": agent_input,
            "agent_scratchpad": "",
        })
        
        output = result.get("output", "")
        
        # 6. 解析输出为 AnalysisResult
        analysis_result = _parse_analysis_output(output, data_results)
        
        # 7. 计算耗时
        duration_ms = (time.time() - start_time) * 1000
        
        # 8. 记录成功轨迹
        state.add_trace(
            agent="analysis_agent",
            action="analysis_complete",
            status=TaskStatus.SUCCESS,
            output_summary=f"生成 {len(analysis_result.insights)} 条洞察, {len(analysis_result.recommendations)} 条建议",
            duration_ms=duration_ms,
        )
        
        # 9. 添加 Agent 消息
        insights_summary = "\\n".join([
            f"- [{insight.type}] {insight.title} (置信度: {insight.confidence})"
            for insight in analysis_result.insights[:5]
        ])
        
        state.add_message(
            role="agent",
            content=f"""[Analysis Agent] 分析完成。

核心发现：
{analysis_result.summary}

洞察（前5条）：
{insights_summary}

建议：
{chr(10).join(analysis_result.recommendations[:3])}
""",
            agent_name="analysis_agent",
        )
        
        # 10. 返回状态更新
        return {
            "analysis_results": analysis_result,
            "task_status": TaskStatus.SUCCESS,
            "active_agent": "supervisor",
        }
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = f"Analysis Agent 执行失败: {str(e)}"
        
        state.add_trace(
            agent="analysis_agent",
            action="analysis_error",
            status=TaskStatus.FAILED,
            error_message=error_msg,
            duration_ms=duration_ms,
        )
        
        state.error_log.append(error_msg)
        
        state.add_message(
            role="agent",
            content=f"[Analysis Agent] 分析失败: {error_msg}",
            agent_name="analysis_agent",
        )
        
        # 返回错误结果（不中断流程）
        return {
            "analysis_results": AnalysisResult(
                summary="分析失败",
                insights=[],
                metrics={},
                recommendations=["请检查数据格式或重试分析"],
            ),
            "error_log": state.error_log,
            "task_status": TaskStatus.FAILED,
            "active_agent": "supervisor",
        }


# ============================================================
# 4. 辅助函数：解析 Agent 输出
# ============================================================

def _parse_analysis_output(output: str, data_results: DataQueryResult) -> AnalysisResult:
    """
    解析 Analysis Agent 的输出为 AnalysisResult
    
    尝试从输出中提取 JSON 格式的分析结果。
    如果提取失败，则基于输出文本构造一个基本的 AnalysisResult。
    """
    
    import re
    
    # 尝试1：提取 JSON 代码块
    json_patterns = [
        r"```json\\s*(.*?)\\s*```",
        r"```\\s*(\\{.*?\\})\\s*```",
    ]
    
    for pattern in json_patterns:
        match = re.search(pattern, output, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                
                # 解析 insights
                insights = []
                for ins in data.get("insights", []):
                    insights.append(AnalysisInsight(
                        type=ins.get("type", "summary"),
                        title=ins.get("title", "未命名洞察"),
                        description=ins.get("description", ""),
                        confidence=ins.get("confidence", 0.8),
                        supporting_data=ins.get("supporting_data"),
                    ))
                
                return AnalysisResult(
                    summary=data.get("summary", output[:200]),
                    insights=insights,
                    metrics=data.get("metrics", {}),
                    recommendations=data.get("recommendations", []),
                )
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    
    # 尝试2：直接解析整个输出
    try:
        data = json.loads(output)
        if isinstance(data, dict) and ("summary" in data or "insights" in data):
            insights = []
            for ins in data.get("insights", []):
                insights.append(AnalysisInsight(
                    type=ins.get("type", "summary"),
                    title=ins.get("title", "未命名洞察"),
                    description=ins.get("description", ""),
                    confidence=ins.get("confidence", 0.8),
                    supporting_data=ins.get("supporting_data"),
                ))
            
            return AnalysisResult(
                summary=data.get("summary", output[:200]),
                insights=insights,
                metrics=data.get("metrics", {}),
                recommendations=data.get("recommendations", []),
            )
    except json.JSONDecodeError:
        pass
    
    # 兜底：基于文本构造基本结果
    # 提取关键句子作为洞察
    sentences = [s.strip() for s in output.split(".") if len(s.strip()) > 10]
    
    insights = []
    for i, sentence in enumerate(sentences[:5]):
        insights.append(AnalysisInsight(
            type="summary",
            title=f"洞察 {i+1}",
            description=sentence,
            confidence=0.7,
        ))
    
    return AnalysisResult(
        summary=output[:300] if output else "分析完成，但无法提取结构化结果",
        insights=insights,
        metrics={"data_rows": data_results.row_count},
        recommendations=["请查看详细分析输出"],
    )


print("✅ backend/app/agents/analysis_agent.py 创建完成")
