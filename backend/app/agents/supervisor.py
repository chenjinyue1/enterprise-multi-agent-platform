"""
Supervisor Agent (agents/supervisor.py)

整个 Multi-Agent 系统的"项目经理"。

职责：
1. 理解用户需求（意图识别）
2. 拆解任务步骤（任务规划）
3. 决定下一个调用哪个 Agent(路由决策)
4. 判断任务是否完成（终止条件）
5. 决定是否需要人工审核（安全控制）

设计要点：
- 用结构化输出（Pydantic）替代字符串解析
- 提示词中嵌入当前状态，让决策有上下文
- 错误处理：LLM调用失败时返回安全默认值
"""

from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings
from app.graph.state import AgentState, RouteDecision, AgentType, TaskStatus


# ============================================================
# 1. 系统提示词（定义 Supervisor 的身份和行为边界）
# ============================================================
# 
# 提示词工程的核心原则：
# 1. 角色定义清楚：你是谁？能做什么？
# 2. 输入输出明确：给我什么？返回什么格式？
# 3. 边界约束：什么不能做？什么必须做？
# 4. 示例说明：给几个例子帮助理解
# ============================================================

SUPERVISOR_SYSTEM_PROMPT = """你是企业智能数据分析平台的"项目经理"（Supervisor Agent）。

## 你的职责
1. 分析用户的自然语言需求，判断需要哪些专业Agent协作
2. 按正确顺序调度Agent（先查数据→再分析→再可视化→最后写报告）
3. 判断任务是否完成，决定何时结束
4. 识别敏感操作，决定是否需要人工审核

## 可调度Agent说明

- **data_agent**：数据库查询专家
  - 能力：写SQL、查MySQL、理解表结构
  - 输入：自然语言查询需求
  - 输出：结构化数据（DataQueryResult）
  - 适用场景：用户需要"查数据"、"看销售额"、"统计订单"

- **analysis_agent**：数据分析专家
  - 能力：统计分析、趋势发现、异常检测、对比分析
  - 输入：DataQueryResult（原始数据）
  - 输出：分析结论（AnalysisResult）
  - 适用场景：用户需要"分析一下"、"有什么发现"、"趋势如何"
  - 依赖：必须先有 data_agent 的产出

- **viz_agent**：可视化专家
  - 能力：选择图表类型、配置图表参数
  - 输入：DataQueryResult 或 AnalysisResult
  - 输出：图表规格（ChartSpec）
  - 适用场景：用户需要"画图"、"图表"、"可视化"

- **report_agent**：报告撰写专家
  - 能力：整合数据、分析、图表，生成结构化报告
  - 输入：所有前置Agent的产出
  - 输出：报告章节（ReportSection）
  - 适用场景：用户需要"报告"、"总结"、"PPT"

- **review_agent**：质检专家
  - 能力：检查数据准确性、口径一致性、逻辑完整性
  - 输入：所有产出
  - 输出：审核结果（通过/不通过 + 修改建议）
  - 适用场景：涉及敏感数据、高价值决策前

- **FINISH**：任务完成，结束工作流

## 调度规则（必须遵守）

1. **顺序规则**：
   - 必须先调用 data_agent，才能调用 analysis_agent
   - analysis_agent 完成后，可以并行调用 viz_agent 和 report_agent
   - 如果用户明确要求"报告"，必须等 report_agent 完成后才能 FINISH

2. **审核规则**：
   - 涉及金额 > 100万的数据 → requires_review = true
   - 涉及客户隐私信息（姓名、电话、地址）→ requires_review = true
   - 删除/修改数据的操作 → requires_review = true
   - 常规查询 → requires_review = false

3. **终止规则**：
   - 用户说"谢谢"、"不用了"、"结束" → FINISH
   - 所有Agent都执行完毕且产出完整 → FINISH
   - 迭代次数接近上限 → FINISH（安全退出）

4. **错误处理**：
   - 如果某个Agent返回错误，可以决定重试（再次调用同Agent）或跳过
   - 重试不超过2次

## 输出格式

你必须返回 JSON 格式的决策，包含以下字段：
- next_agent：下一个Agent的名称（必须是上面列出的之一）
- reasoning：你的决策理由（1-2句话）
- task_for_next：给下一个Agent的具体任务指令（要详细、可执行）
- requires_review：是否需要人工审核（true/false）

## 示例

用户："查一下上季度各品类销售额"
→ next_agent: "data_agent"
→ reasoning: "用户需要查询销售数据，这是数据分析的第一步"
→ task_for_next: "查询上季度（Q3）各品类的销售额汇总数据，需要包含品类名称和销售额字段"
→ requires_review: false

用户："分析一下为什么Q3销售额下降了"
（已有 data_results）
→ next_agent: "analysis_agent"
→ reasoning: "已有原始数据，需要进行深入分析找出下降原因"
→ task_for_next: "分析Q3销售额下降的原因，从品类维度、时间维度、同比环比等角度进行拆解，找出主要影响因素"
→ requires_review: false
"""


# ============================================================
# 2. Supervisor Agent 创建函数
# ============================================================

def create_supervisor_agent():
    """
    创建 Supervisor Agent
    
    返回一个可调用对象，输入是消息列表，输出是 RouteDecision。
    
    为什么用 ChatOpenAI + structured_output？
    =========================================
    1. structured_output：强制 LLM 返回 JSON，而不是自由文本
       - 程序能可靠解析，不用写正则
       - Pydantic 自动校验字段类型
    
    2. temperature=0.1：低随机性
       - 调度决策要稳定，不能今天这样明天那样
       - 0.1 比 0 稍微灵活一点，但基本确定
    
    3. model：开发用 gpt-4o-mini（便宜、快）
       - Supervisor 主要是做决策，不需要最强模型
       - 生产环境可以升级到 gpt-4o
    """
    
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        temperature=0.1,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )
    
    # 绑定结构化输出：LLM 必须返回 RouteDecision 格式的 JSON
    structured_llm = llm.with_structured_output(RouteDecision)
    
    # 构建提示词模板
    # MessagesPlaceholder：动态插入对话历史
    prompt = ChatPromptTemplate.from_messages([
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
        ("human", """
当前任务状态：
- 已执行步骤数：{iteration_count}/{max_iterations}
- 已有数据：{has_data}
- 已有分析：{has_analysis}
- 已有图表：{chart_count} 张
- 已有报告章节：{section_count} 个
- 当前审核状态：{review_status}

请根据以上信息，做出路由决策。
"""),
    ])
    
    # 组合：提示词 → LLM → 结构化输出
    return prompt | structured_llm


# ============================================================
# 3. Supervisor 节点函数（LangGraph 节点）
# ============================================================
# 
# LangGraph 的每个节点都是一个函数：
#   输入：当前 State
#   处理：业务逻辑
#   输出：State 更新（dict 格式，只返回要修改的字段）
# 
# 为什么返回 dict 而不是直接修改 State？
# - LangGraph 内部做状态合并，避免副作用
# - 方便测试：输入 State → 得到更新 dict → 验证
# - 支持时间旅行调试：可以回放任何一步
# ============================================================

def supervisor_node(state: AgentState) -> dict:
    """
    Supervisor 节点函数
    
    这是 LangGraph 图中的一个节点。
    每次执行到 Supervisor 节点时，调用这个函数。
    
    参数：
        state: 当前系统状态（共享笔记本）
    
    返回：
        dict: 要更新的状态字段
        
    返回的 dict 会被 LangGraph 合并到原 State 中。
    """
    
    # 1. 准备状态摘要（给 LLM 看的上下文）
    has_data = state.data_results is not None
    has_analysis = state.analysis_results is not None
    
    # 2. 构建消息列表
    # 把 State 中的 messages 转换为 LangChain Message 对象
    messages = []
    for msg in state.messages:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "system":
            messages.append(SystemMessage(content=msg.content))
        else:
            # agent 角色的消息，加上前缀标识
            prefix = f"[{msg.agent_name}] " if msg.agent_name else "[Agent] "
            messages.append(HumanMessage(content=f"{prefix}{msg.content}"))
    
    # 3. 创建 Supervisor 并执行
    supervisor = create_supervisor_agent()
    
    try:
        # 调用 LLM 做决策
        decision = supervisor.invoke({
            "messages": messages,
            "iteration_count": state.iteration_count,
            "max_iterations": state.max_iterations,
            "has_data": "是" if has_data else "否",
            "has_analysis": "是" if has_analysis else "否",
            "chart_count": len(state.charts),
            "section_count": len(state.report_sections),
            "review_status": state.review_status.value,
        })
        
        # 4. 记录执行轨迹
        state.add_trace(
            agent="supervisor",
            action="route_decision",
            status=TaskStatus.SUCCESS,
            input_summary=state.current_task[:100],
            output_summary=f"决策: {decision.next_agent.value}, 理由: {decision.reasoning[:100]}",
        )
        
        # 5. 返回状态更新
        updates = {
            "active_agent": decision.next_agent,
            "next_agent": decision.next_agent,
            "current_task": decision.task_for_next,
            "iteration_count": state.iteration_count + 1,
        }
        
        # 如果需要审核，更新审核状态
        if decision.requires_review:
            updates["review_status"] = "pending"
        
        # 添加 Supervisor 的决策消息到对话历史
        state.add_message(
            role="agent",
            content=f"[决策] 下一步：{decision.next_agent.value}。理由：{decision.reasoning}",
            agent_name="supervisor",
        )
        
        return updates
        
    except Exception as e:
        # 6. 错误处理：LLM 调用失败时的安全回退
        error_msg = f"Supervisor 决策失败: {str(e)}"
        
        state.add_trace(
            agent="supervisor",
            action="route_decision",
            status=TaskStatus.FAILED,
            error_message=error_msg,
        )
        
        state.error_log.append(error_msg)
        
        # 安全回退：出错时直接结束，避免无限循环
        return {
            "active_agent": AgentType.FINISH,
            "error_log": state.error_log,
        }


print("✅ backend/app/agents/supervisor.py 创建完成")
