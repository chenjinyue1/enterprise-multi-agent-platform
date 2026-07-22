from app.graph.state import create_initial_state
from app.agents.data_agent import data_agent_node
import asyncio

async def test():
    state = create_initial_state("查一下Q3各品类销售额")
    
    # 模拟 Supervisor 已分配任务
    state.current_task = "查询Q3各品类销售额汇总，按销售额降序排列"
    
    # 执行 Data Agent
    updates = await data_agent_node(state)
    
    print("查询结果:")
    print(updates["data_results"])
    
    print("\\n执行轨迹:")
    for trace in state.execution_trace:
        print(f"  Step {trace.step}: {trace.agent} - {trace.action}")

asyncio.run(test())