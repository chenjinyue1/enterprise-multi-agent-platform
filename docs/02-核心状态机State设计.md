
doc02_content = '''# 板块二：核心状态机 State 设计

> **文档编号**: 02  
> **前置板块**: 01-项目架构设计与环境搭建  
> **编写日期**: 2026-07-18  
> **目标读者**: 已理解 Multi-Agent 概念，想深入 State 设计的开发者

---

## 📖 目录

1. [什么是 State？](#一什么是-state)
2. [为什么 State 是 Multi-Agent 的灵魂？](#二为什么-state-是-multi-agent-的灵魂)
3. [State 设计原则](#三state-设计原则)
4. [代码实战：AgentState 完整定义](#四代码实战agentstate-完整定义)
5. [Annotated 与 State 更新策略](#五annotated-与-state-更新策略)
6. [结构化输出：RouteDecision](#六结构化输出routedecision)
7. [Supervisor Agent 设计](#七supervisor-agent-设计)
8. [LangGraph 图构建器骨架](#八langgraph-图构建器骨架)
9. [运行验证](#九运行验证)
10. [本板块简历价值](#十本板块简历价值)
11. [下板块预告](#十一下板块预告)

---

## 一、什么是 State？

### 1.1 一句话定义

> **State = Multi-Agent 系统的"共享笔记本"**

所有 Agent 都能读写这个笔记本，LangGraph 会自动保存每一页，服务重启后能从上次继续。

### 1.2 用生活例子理解

想象你在**餐厅当经理**：

**没有 State（混乱模式）**：
- 你脑子里记住：A桌点了牛排、B桌要加辣、C桌在等汤...
- 突然停电了 → 来电后全忘了 → 重新问一遍客人
- 厨师问"刚才那桌牛排要几分熟？"→ 你说"我忘了" → 客人发火

**有 State（有序模式）**：
- 你有一个**共享笔记本**（State），每桌的点单都写上去
- 厨师、服务员、收银员都能看到
- 停电了 → 来电后翻开笔记本继续 → nothing lost
- 老板问"3号桌消费了多少钱？"→ 翻笔记本就知道

**在 Multi-Agent 系统里**：
- **笔记本 = State**
- **经理 = Supervisor Agent**
- **厨师/服务员 = 各专业 Agent**
- **停电 = 服务重启**
- **老板查账 = 审计追踪**

### 1.3 State 在 LangGraph 中的三大超能力

```
┌─────────────────────────────────────────────────────────────┐
│                     LangGraph State 三大特性                  │
├─────────────────────────────────────────────────────────────┤
│ 1. 共享性：所有 Agent 都能读写同一个 State                    │
│    → Data Agent 查到数据 → Analysis Agent 自动能看到         │
├─────────────────────────────────────────────────────────────┤
│ 2. 持久化：自动保存到 Redis/数据库                           │
│    → 服务重启 → 从上次断点继续 → 不用从头来                  │
├─────────────────────────────────────────────────────────────┤
│ 3. 可观测性：每一步 State 变化都被记录                         │
│    → 老板问"这个数字怎么来的？"→ 看执行轨迹就知道             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、为什么 State 是 Multi-Agent 的灵魂？

### 2.1 真实生产事故

> 某公司的 AI 客服系统，用户问"我上周的订单怎么还没发货？"
> - Agent A 查了订单状态 → "已发货"
> - Agent B 去查物流 → 但不知道 Agent A 已经查过了 → 又查了一遍
> - Agent C 想回复用户 → 但看不到 A 和 B 的结果 → 回复"请稍等"
> - 用户等了5分钟 → 愤怒投诉

**根因**：没有统一的 State，Agent 之间信息不共享。

### 2.2 我们的方案

所有 Agent 共用一本"笔记本"，写上去的东西大家都能看到：

```
Data Agent 查询结果 ──→ State.data_results
                              ↓
Analysis Agent 读取 State.data_results ──→ 分析结论 ──→ State.analysis_results
                                                          ↓
                              ┌───────────────────────────┘
                              ↓
                    Viz Agent 读取 → 生成图表 → State.charts
                    Report Agent 读取 → 写报告 → State.report_sections
```

---

## 三、State 设计原则

设计 State 之前，先回答三个问题：

| 问题 | 答案 | 对应代码 |
|------|------|---------|
| **哪些数据需要共享？** | 查询结果、分析结论、图表配置、报告内容 | `data_results`, `analysis_results`, `charts`, `report_sections` |
| **哪些数据需要持久化？** | 全部！用户对话、执行轨迹、错误日志 | 整个 `AgentState` |
| **哪些节点需要人工介入？** | 涉及敏感数据、高价值操作 | `review_status` 字段 |

### 3.1 字段分组设计

我们的 State 分为 8 组：

```
AgentState
├── 1. 对话与任务（messages, current_task, task_status）
├── 2. Agent 调度（active_agent, next_agent）
├── 3. 各 Agent 产出（data_results, analysis_results, charts, report_sections）
├── 4. 最终产出（final_report）
├── 5. 审核与质量（review_status, review_record）
├── 6. 可观测性（execution_trace, error_log）
├── 7. 迭代控制（iteration_count, max_iterations）
└── 8. 元数据（session_id, user_id, metadata）
```

---

## 四、代码实战：AgentState 完整定义

### 4.1 枚举定义（状态值标准化）

```python
from enum import Enum

class AgentType(str, Enum):
    """Agent 类型枚举"""
    SUPERVISOR = "supervisor"
    DATA = "data_agent"
    ANALYSIS = "analysis_agent"
    VIZ = "viz_agent"
    REPORT = "report_agent"
    REVIEW = "review_agent"
    HUMAN = "human"
    FINISH = "FINISH"
```

**为什么用 Enum 而不是字符串？**
- 防止拼写错误：`"data_agent"` vs `"data_agnet"`
- IDE 自动补全：输入 `AgentType.` 就弹出选项
- 类型检查：mypy 能发现非法赋值

### 4.2 子模型定义（模块化）

```python
class DataQueryResult(BaseModel):
    """数据查询结果"""
    query: str                    # 执行的SQL
    data: List[dict]              # 查询结果
    row_count: int                # 返回行数
    execution_time_ms: float      # 执行耗时
    data_source: str = "mysql"    # 数据来源
    
    @field_validator("data")
    @classmethod
    def validate_data_not_too_large(cls, v: List[dict]) -> List[dict]:
        MAX_ROWS = 10000
        if len(v) > MAX_ROWS:
            raise ValueError(f"查询结果超过{MAX_ROWS}行")
        return v
```

**为什么拆成子模型？**
- 清晰：一眼看出这个字段包含什么
- 复用：多个 State 可以共用子模型
- 校验：子模型内部可以做更细粒度的校验

**`validate_data_not_too_large` 的作用**：
- LLM 上下文有限，数据太多会截断
- 企业里可能一次查出百万行，直接塞给 LLM 会崩
- 这里做保护，超限报错，让 Agent 改查询条件

### 4.3 核心 AgentState 定义

```python
class AgentState(BaseModel):
    """Multi-Agent 系统的共享状态"""
    
    # --- 对话与任务 ---
    messages: Annotated[List[Message], "append"] = Field(default_factory=list)
    current_task: str = ""
    task_status: TaskStatus = TaskStatus.PENDING
    
    # --- Agent 调度 ---
    active_agent: AgentType = AgentType.SUPERVISOR
    next_agent: Optional[AgentType] = None
    
    # --- 各 Agent 产出 ---
    data_results: Optional[DataQueryResult] = None
    analysis_results: Optional[AnalysisResult] = None
    charts: List[ChartSpec] = Field(default_factory=list)
    report_sections: List[ReportSection] = Field(default_factory=list)
    
    # --- 最终产出 ---
    final_report: Optional[str] = None
    
    # --- 审核与质量 ---
    review_status: ReviewStatus = ReviewStatus.NOT_REQUIRED
    review_record: Optional[ReviewRecord] = None
    
    # --- 可观测性 ---
    execution_trace: List[ExecutionTrace] = Field(default_factory=list)
    error_log: List[str] = Field(default_factory=list)
    
    # --- 迭代控制 ---
    iteration_count: int = 0
    max_iterations: int = 15
    
    # --- 元数据 ---
    session_id: str = ""
    user_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
```

---

## 五、Annotated 与 State 更新策略

### 5.1 核心问题：LangGraph 怎么更新 State？

LangGraph 的 State 更新是**合并机制**：
- 每个节点返回一个 `dict`，表示要更新的字段
- LangGraph 把这个 `dict` 合并到原 State 中

**问题来了**：列表字段怎么更新？

### 5.2 默认行为 vs Append 行为

```python
# 默认行为：新值覆盖旧值
messages: List[Message] = Field(default_factory=list)
# 节点返回：{"messages": [new_msg]}
# 结果：messages = [new_msg]  （旧消息丢了！）

# Append 行为：新值追加到列表
messages: Annotated[List[Message], "append"] = Field(default_factory=list)
# 节点返回：{"messages": [new_msg]}
# 结果：messages = [old_msg1, old_msg2, new_msg]  （保留了历史）
```

**为什么对话历史必须用 append？**
- 每个 Agent 都可能产生消息
- 如果覆盖，就只能看到最后一条
- 用 append，完整对话历史保留，所有 Agent 都能看到上下文

### 5.3 哪些字段用 append？

| 字段 | 更新策略 | 原因 |
|------|---------|------|
| `messages` | append | 对话历史不能丢 |
| `execution_trace` | append | 轨迹要完整记录 |
| `error_log` | append | 错误日志累积 |
| `charts` | append | 可能生成多张图表 |
| `report_sections` | append | 可能多个章节 |
| `data_results` | 覆盖 | 一次查询只有一个结果 |
| `analysis_results` | 覆盖 | 一次分析只有一个结论 |
| `final_report` | 覆盖 | 最终报告只有一个 |

---

## 六、结构化输出：RouteDecision

### 6.1 为什么需要结构化输出？

**传统做法（字符串解析）**：
```
LLM 输出："下一步调用 data_agent，因为需要查询数据"
程序：用正则提取 "data_agent" → 容易出错！
      如果 LLM 说"调用数据Agent"→ 正则匹配失败！
```

**我们的做法（结构化输出）**：
```python
class RouteDecision(BaseModel):
    next_agent: AgentType      # 枚举类型，只能是预设值
    reasoning: str             # 决策理由
    task_for_next: str         # 具体任务
    requires_review: bool      # 是否需要审核

# LLM 输出 JSON：
# {"next_agent": "data_agent", "reasoning": "...", "task_for_next": "...", "requires_review": false}
# 程序：直接解析为 Pydantic 对象 → 类型安全！
```

### 6.2 LangChain 的 with_structured_output

```python
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

# 绑定结构化输出：LLM 必须返回 RouteDecision 格式的 JSON
structured_llm = llm.with_structured_output(RouteDecision)

# 调用时，LLM 会自动输出 JSON，然后被解析为 RouteDecision 对象
decision = structured_llm.invoke("用户想查销售额")
print(decision.next_agent)  # AgentType.DATA
```

**面试话术**：
> "我用 LangChain 的 with_structured_output 实现 LLM 的结构化输出。这样做的好处是：LLM 返回的是 JSON，程序直接解析为 Pydantic 对象，不用写正则提取，类型安全，且 Pydantic 会自动校验字段合法性。"

---

## 七、Supervisor Agent 设计

### 7.1 Supervisor 的职责

Supervisor 是整个系统的"项目经理"：

```
用户输入："查一下上季度各品类销售额"
        ↓
[Supervisor] 解析需求 → 需要查数据
        ↓
决策：next_agent = data_agent
      task_for_next = "查询上季度各品类销售额..."
      requires_review = false
```

### 7.2 提示词工程（Prompt Engineering）

```python
SUPERVISOR_SYSTEM_PROMPT = """你是企业智能数据分析平台的"项目经理"...

## 可调度Agent说明
- data_agent：数据库查询专家...
- analysis_agent：数据分析专家...
...

## 调度规则（必须遵守）
1. 顺序规则：必须先 data_agent，再 analysis_agent...
2. 审核规则：涉及金额>100万 → requires_review = true...
3. 终止规则：用户说"谢谢" → FINISH...
"""
```

**提示词设计要点**：
1. **角色定义清楚**：你是谁？能做什么？
2. **输入输出明确**：给我什么？返回什么格式？
3. **边界约束**：什么不能做？什么必须做？
4. **示例说明**：给几个例子帮助理解

### 7.3 节点函数设计

```python
def supervisor_node(state: AgentState) -> dict:
    """
    Supervisor 节点函数
    
    LangGraph 的每个节点都是一个函数：
      输入：当前 State
      处理：业务逻辑
      输出：State 更新（dict 格式，只返回要修改的字段）
    """
    # 1. 准备上下文
    has_data = state.data_results is not None
    
    # 2. 调用 LLM 做决策
    decision = supervisor.invoke({...})
    
    # 3. 记录执行轨迹
    state.add_trace(agent="supervisor", action="route_decision", ...)
    
    # 4. 返回状态更新（只返回要修改的字段）
    return {
        "active_agent": decision.next_agent,
        "current_task": decision.task_for_next,
        "iteration_count": state.iteration_count + 1,
    }
```

**为什么返回 dict 而不是直接修改 State？**
- LangGraph 内部做状态合并，避免副作用
- 方便测试：输入 State → 得到更新 dict → 验证
- 支持时间旅行调试：可以回放任何一步

---

## 八、LangGraph 图构建器骨架

### 8.1 图结构

```
        ┌─────────────┐
        │   START     │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  Supervisor │  ← 入口 + 循环回到这里
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
                   │  Supervisor │
                   └──────┬──────┘
                          │
                          ▼
                   ┌─────────────┐
                   │   FINISH    │
                   └─────────────┘
```

### 8.2 代码骨架

```python
from langgraph.graph import StateGraph, END
from app.graph.state import AgentState

def build_graph() -> StateGraph:
    # 1. 创建 StateGraph
    workflow = StateGraph(AgentState)
    
    # 2. 添加节点
    workflow.add_node("supervisor", supervisor_node)
    # TODO: 添加其他 Agent 节点
    
    # 3. 添加边
    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges("supervisor", route_from_supervisor)
    
    # 4. 编译
    return workflow.compile()

def route_from_supervisor(state: AgentState) -> str:
    """根据 State 决定下一步去哪"""
    if state.active_agent == AgentType.FINISH:
        return END
    return state.active_agent.value
```

---

## 九、运行验证

### 9.1 测试 State 创建

```python
# 在 Python 交互式环境中测试
from app.graph.state import create_initial_state, AgentType

# 创建初始状态
state = create_initial_state("查一下上季度销售额", user_id="user_001")

print(f"Session ID: {state.session_id}")
print(f"Current Task: {state.current_task}")
print(f"Active Agent: {state.active_agent.value}")
print(f"Messages: {len(state.messages)}")
print(f"Trace: {len(state.execution_trace)}")

# 输出：
# Session ID: a1b2c3d4-...
# Current Task: 查一下上季度销售额
# Active Agent: supervisor
# Messages: 1
# Trace: 1
```

### 9.2 测试 State 更新

```python
from app.graph.state import DataQueryResult

# 模拟 Data Agent 查询结果
state.data_results = DataQueryResult(
    query="SELECT category, SUM(amount) FROM sales WHERE quarter='Q3' GROUP BY category",
    data=[{"category": "电子产品", "amount": 1500000}, {"category": "服装", "amount": 800000}],
    row_count=2,
    execution_time_ms=45.2,
)

# 添加轨迹
state.add_trace(
    agent="data_agent",
    action="execute_query",
    output_summary="返回2行数据",
    duration_ms=45.2,
)

print(state.get_summary())
# {
#   'session_id': 'a1b2c3d4-...',
#   'active_agent': 'supervisor',
#   'has_data': True,
#   'has_analysis': False,
#   'chart_count': 0,
#   'section_count': 0,
#   'trace_count': 2
# }
```

---

## 十、本板块简历价值

### 10.1 新增可写内容

在板块一的基础上，增加：

```markdown
• 状态机设计：设计 AgentState 共享状态机，包含 8 组 20+ 字段，
  覆盖对话历史、Agent调度、数据流转、审核状态、执行轨迹、迭代控制等维度，
  支持全链路可观测和故障恢复

• 结构化输出：基于 Pydantic + LangChain with_structured_output 实现
  Supervisor 路由决策的结构化输出，替代字符串解析，提升系统可靠性

• 安全设计：内置审核状态机（not_required → pending → approved/rejected），
  支持敏感操作自动触发人工审核，满足企业合规要求

• 防御性编程：数据量校验（防止百万行数据拖垮LLM）、迭代次数上限（防止死循环）、
  错误安全回退（LLM调用失败时优雅退出）
```

### 10.2 面试高频问题

**Q1: 为什么用 Pydantic 定义 State？**
> "Pydantic 提供类型安全和自动校验。在 Multi-Agent 系统中，State 被多个 Agent 读写，类型错误会导致难以排查的bug。Pydantic 在运行时自动校验，早发现早解决。"

**Q2: Annotated[List, 'append'] 是什么意思？**
> "这是 LangGraph 的状态更新策略。默认情况下，节点返回的新值会覆盖旧值。但对于 messages、execution_trace 等列表字段，我们需要保留历史，所以用 append 策略，新值追加到列表末尾。"

**Q3: 怎么防止 Agent 死循环？**
> "我在 State 中设计了 iteration_count 和 max_iterations 字段。每经过一个节点，iteration_count +1。Supervisor 每次决策前检查，如果超过上限则强制 FINISH。同时，should_stop() 方法还检查审核被拒绝的情况，多重保护。"

**Q4: 人工审核怎么实现？**
> "State 中有 review_status 字段，流转过程是 not_required → pending → approved/rejected。Supervisor 在决策时判断是否需要审核（如涉及金额>100万），需要则设为 pending，前端检测到 pending 状态后弹出审核界面，用户确认后再继续。"

---

## 十一、下板块预告

### 板块三：Data Agent + MCP 数据库工具

**你将学到**：
- Data Agent 的设计：如何把自然语言转成 SQL？
- MCP 协议实战：封装数据库查询为 MCP Server
- 工具调用：LangChain Tool 的使用方式
- 错误处理：SQL 执行失败怎么办？

**代码实战**：
- 创建 `data_agent.py`
- 创建 `mcp/servers/db_server.py`
- 打通 Supervisor → Data Agent → 返回结果的完整链路

---

> **文档结束**  
> 如有疑问，随时提问。确认理解后，我们继续 **板块三：Data Agent + MCP 数据库工具** 🚀
'''

with open(f"{ROOT}/docs/02-核心状态机State设计.md", "w", encoding="utf-8") as f:
    f.write(doc02_content)

print("✅ docs/02-核心状态机State设计.md 创建完成")
