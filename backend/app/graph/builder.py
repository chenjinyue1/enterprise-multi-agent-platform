"""
LangGraph 图构建器 (graph/builder.py)

职责：把各个 Agent（节点）和路由逻辑（边）组装成一个完整的"工作流图"。

LangGraph 的核心概念：
===================
1. StateGraph：状态图，定义 State 类型
2. Node（节点）：每个 Agent 是一个节点，执行具体逻辑
3. Edge（边）：节点之间的连接，决定下一步去哪
4. Conditional Edge（条件边）：根据 State 的值动态决定路由

我们的图结构（Supervisor 模式）：
================================

        ┌─────────────┐
        │   START     │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  Supervisor │  ← 入口，所有请求先到这
        │   (调度器)   │
        └──────┬──────┘
               │
      ┌────────┼────────┬────────┬────────┐
      ▼        ▼        ▼        ▼        ▼
┌─────────┐ ┌─────┐ ┌──────┐ ┌──────┐ ┌──────┐
│  Data   │ │Analysis│ │ Viz  │ │Report│ │Review│
│  Agent  │ │ Agent │ │ Agent│ │ Agent│ │ Agent│
└────┬────┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘
     │         │        │        │        │
     └─────────┴────────┴────────┴────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  Supervisor │  ← 循环：做完后回到 Supervisor
                   └──────┬──────┘
                          │
                          ▼
                   ┌─────────────┐
                   │   FINISH    │  ← 结束
                   └─────────────┘

为什么这样设计？
================
- Supervisor 是中央调度器，所有路由决策集中管理
- 每个专业 Agent 只做一件事，解耦
- 循环结构：Agent 执行完后回到 Supervisor， Supervisor 决定下一步
- 可扩展：加新 Agent 只需在 Supervisor 里注册，不用改图结构
"""

from langgraph.graph import StateGraph, END

from app.graph.state import AgentState, AgentType
from app.agents.supervisor import supervisor_node


# ============================================================
# 1. 构建图
# ============================================================

def build_graph() -> StateGraph:
    """
    构建 Multi-Agent 工作流图
    
    返回一个编译好的 StateGraph，可以直接调用。
    
    使用方式：
        graph = build_graph()
        result = graph.invoke(initial_state)
    """
    
    # 1.1 创建 StateGraph
    # 参数：State 类型。LangGraph 用这个类型做状态校验和合并。
    workflow = StateGraph(AgentState)
    
    # 1.2 添加节点
    # 每个节点 = 一个 Agent 的执行函数
    # 参数：(节点名称, 节点函数)
    workflow.add_node("supervisor", supervisor_node)
    
    # TODO: 后续板块会添加更多节点

# 添加 Data Agent 节点（板块三新增）
    from app.agents.data_agent import data_agent_node
    workflow.add_node("data_agent", data_agent_node)
# 添加 Analysis Agent 节点（板块四新增）
    from app.agents.analysis_agent import analysis_agent_node
    workflow.add_node("analysis_agent", analysis_agent_node)
# 添加 Viz Agent 节点（板块五新增）
    from app.agents.viz_agent import viz_agent_node
    workflow.add_node("viz_agent", viz_agent_node)
    # workflow.add_node("report_agent", report_agent_node)
    # workflow.add_node("review_agent", review_agent_node)
    
    # 1.3 添加边（路由）
    
    # 入口：从 START 到 Supervisor
    workflow.set_entry_point("supervisor")
    
    # Supervisor 的条件路由
    # 根据 Supervisor 的决策，决定下一步去哪
    workflow.add_conditional_edges(
        "supervisor",           # 从 Supervisor 节点出发
        route_from_supervisor,  # 路由函数：返回下一个节点名称
    )
    
    # TODO: 后续板块添加 Agent 节点后，需要添加从 Agent 回到 Supervisor 的边

    # 添加 Data Agent 回到 Supervisor 的边（板块三新增）
    workflow.add_edge("data_agent", "supervisor")

    # 添加 Analysis Agent 回到 Supervisor 的边（板块四新增）
    workflow.add_edge("analysis_agent", "supervisor")

    # 添加 Viz Agent 回到 Supervisor 的边（板块五新增）
    workflow.add_edge("viz_agent", "supervisor")
    
    # TODO: 后续板块添加更多 Agent 节点后，添加对应边
    # for agent in ["data_agent", "analysis_agent", "viz_agent", "report_agent", "review_agent"]:
    #     workflow.add_edge(agent, "supervisor")
    
    # 1.4 编译图
    # compile() 会检查图的完整性：
    # - 所有节点是否都有入边和出边
    # - 是否有死胡同（除了 END）
    graph = workflow.compile()
    
    return graph


# ============================================================
# 2. 路由函数
# ============================================================
# 
# 条件边的核心：根据 State 的值决定下一步去哪。
# 返回的是节点名称字符串，LangGraph 根据这个字符串找对应的节点。
# ============================================================

def route_from_supervisor(state: AgentState) -> str:
    """
    Supervisor 的条件路由函数
    
    根据当前 State 中的 active_agent 字段，决定下一步走哪个节点。
    
    参数：
        state: 当前系统状态
    
    返回：
        str: 下一个节点的名称
    
    为什么需要这个函数？
    ==================
    Supervisor 节点已经做了决策（设置了 next_agent），
    但这个决策只是写到了 State 里，LangGraph 不知道下一步该执行哪个节点。
    
    这个函数就是"翻译器"：
        State.next_agent = "data_agent" → 返回 "data_agent"
        State.next_agent = "FINISH" → 返回 END（特殊常量，表示结束）
    """
    
    # 获取 Supervisor 决策的下一个 Agent
    next_agent = state.active_agent
    
    # 如果决定结束，返回 END 常量
    if next_agent == AgentType.FINISH:
        return END
    
    # 如果决定调用某个 Agent，返回对应的节点名称
    # 注意：返回的字符串必须和 add_node() 时用的名称一致
    return next_agent.value


# ============================================================
# 3. 图的可视化（调试用）
# ============================================================

def visualize_graph(graph: StateGraph, output_path: str = "graph.png") -> None:
    """
    可视化图结构
    
    生成一张 PNG 图片，展示图的节点和边。
    用于：
    - 文档配图
    - 面试展示
    - 团队沟通
    
    需要安装：pip install graphviz
    """
    try:
        from langchain_core.runnables.graph import CurveStyle, NodeColors
        
        graph.get_graph().draw_mermaid_png(
            output_file_path=output_path,
        )
        print(f"✅ 图已可视化保存到: {output_path}")
    except Exception as e:
        print(f"⚠️  可视化失败（可能需要安装 graphviz）: {e}")
        # 备用方案：输出 Mermaid 语法
        mermaid = graph.get_graph().draw_mermaid()
        print("Mermaid 语法（可粘贴到 https://mermaid.live 查看）：")
        print(mermaid)


print("✅ backend/app/graph/builder.py 创建完成")
