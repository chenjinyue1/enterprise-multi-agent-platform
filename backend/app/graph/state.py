
import os


ROOT = "D:\CampuslQ09\enterprise-multi-agent-platform\backend\app\graph\state.py"

"""
核心状态机定义 (graph/state.py)

这是整个 Multi-Agent 系统的"共享笔记本"。
所有 Agent 通过读写这个 State 来协作。

设计哲学：
- 每个字段都有明确的目的和生命周期
- 用 Pydantic 保证类型安全
- 用 Annotated 控制更新行为
- 预留可观测性和人工介入的字段

面试重点：
- 为什么用 Annotated[List, "append"]？
- State 怎么实现持久化？
- 人工介入点怎么设计？
"""

from typing import Annotated, Any, List, Optional, Literal
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


# ============================================================
# 1. 枚举定义（状态值的标准化）
# ============================================================
# 
# 为什么用 Enum 而不是字符串？
# - 防止拼写错误："data_agent" vs "data_agnet"
# - IDE 自动补全：输入 AgentType. 就弹出选项
# - 类型检查：mypy 能发现非法赋值
# ============================================================

class AgentType(str, Enum):
    """Agent 类型枚举"""
    SUPERVISOR = "supervisor"
    DATA = "data_agent"
    ANALYSIS = "analysis_agent"
    VIZ = "viz_agent"
    REPORT = "report_agent"
    REVIEW = "review_agent"
    HUMAN = "human"           # 人工节点
    FINISH = "FINISH"         # 结束


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    SUCCESS = "success"       # 成功
    FAILED = "failed"         # 失败
    RETRYING = "retrying"     # 重试中


class ReviewStatus(str, Enum):
    """审核状态枚举"""
    NOT_REQUIRED = "not_required"  # 不需要审核
    PENDING = "pending"            # 等待审核
    APPROVED = "approved"          # 已通过
    REJECTED = "rejected"          # 已拒绝


# ============================================================
# 2. 子模型定义（State 的组成部分）
# ============================================================
# 
# 把复杂字段拆成子模型的好处：
# - 清晰：一眼看出这个字段包含什么
# - 复用：多个 State 可以共用子模型
# - 校验：子模型内部可以做更细粒度的校验
# ============================================================

class Message(BaseModel):
    """
    对话消息
    
    为什么不用简单的 dict？
    - Pydantic 自动校验：role 必须是 "user" 或 "assistant"
    - timestamp 自动记录：不用手动传
    """
    role: Literal["user", "assistant", "system", "agent"] = Field(
        description="消息角色"
    )
    content: str = Field(description="消息内容")
    agent_name: Optional[str] = Field(
        default=None,
        description="哪个Agent发的（agent角色时必填）"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="消息时间戳"
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="附加信息（如token用量、耗时等）"
    )


class DataQueryResult(BaseModel):
    """
    数据查询结果
    
    Data Agent 查询数据库后的产出，会被 Analysis Agent 消费
    """
    query: str = Field(description="执行的SQL或查询语句")
    data: List[dict] = Field(default_factory=list, description="查询结果数据")
    row_count: int = Field(default=0, description="返回行数")
    execution_time_ms: float = Field(default=0.0, description="执行耗时(毫秒)")
    data_source: str = Field(default="mysql", description="数据来源")
    schema: Optional[List[str]] = Field(default=None, description="字段名列表")
    
    @field_validator("data")
    @classmethod
    def validate_data_not_too_large(cls, v: List[dict]) -> List[dict]:
        """
        校验数据量不能太大
        
        为什么需要？
        - LLM 上下文有限，数据太多会截断
        - 企业里可能一次查出百万行，直接塞给LLM会崩
        - 这里做保护，超限报错，让Agent改查询条件
        """
        MAX_ROWS = 10000  # 最多1万行
        if len(v) > MAX_ROWS:
            raise ValueError(f"查询结果超过{MAX_ROWS}行，请添加WHERE条件缩小范围")
        return v


class AnalysisInsight(BaseModel):
    """分析洞察（单条）"""
    type: Literal["trend", "anomaly", "comparison", "correlation", "summary"] = Field(
        description="洞察类型"
    )
    title: str = Field(description="洞察标题")
    description: str = Field(description="洞察描述")
    confidence: float = Field(
        default=0.8,
        ge=0.0, le=1.0,
        description="置信度（0-1）"
    )
    supporting_data: Optional[dict] = Field(
        default=None,
        description="支撑数据"
    )


class AnalysisResult(BaseModel):
    """
    分析计算结果
    
    Analysis Agent 的产出，会被 Viz Agent 和 Report Agent 消费
    """
    summary: str = Field(default="", description="分析摘要")
    insights: List[AnalysisInsight] = Field(
        default_factory=list,
        description="关键洞察列表"
    )
    metrics: dict = Field(default_factory=dict, description="计算指标")
    recommendations: List[str] = Field(
        default_factory=list,
        description="行动建议"
    )


class ChartSpec(BaseModel):
    """
    图表规格
    
    Viz Agent 的产出，前端根据这个配置渲染图表
    """
    chart_id: str = Field(description="图表唯一ID")
    chart_type: Literal["line", "bar", "pie", "scatter", "heatmap", "table"] = Field(
        description="图表类型"
    )
    title: str = Field(description="图表标题")
    data_source: str = Field(description="数据来源（关联data_results）")
    x_field: Optional[str] = Field(default=None, description="X轴字段")
    y_field: Optional[str] = Field(default=None, description="Y轴字段")
    config: dict = Field(default_factory=dict, description="图表配置（颜色、大小等）")
    

class ReportSection(BaseModel):
    """
    报告章节
    
    Report Agent 的产出，最终整合成完整报告
    """
    section_id: str = Field(description="章节ID")
    title: str = Field(description="章节标题")
    content: str = Field(description="章节内容（Markdown格式）")
    chart_refs: List[str] = Field(
        default_factory=list,
        description="引用的图表ID列表"
    )
    data_refs: List[str] = Field(
        default_factory=list,
        description="引用的数据源列表"
    )
    order: int = Field(default=0, description="章节顺序")


class ExecutionTrace(BaseModel):
    """
    执行轨迹记录
    
    可观测性的核心！记录每一步谁做了什么、花了多久。
    企业审计、故障排查、性能优化都靠它。
    """
    step: int = Field(description="步骤序号")
    agent: str = Field(description="执行Agent")
    action: str = Field(description="执行动作")
    input_summary: Optional[str] = Field(default=None, description="输入摘要")
    output_summary: Optional[str] = Field(default=None, description="输出摘要")
    status: TaskStatus = Field(default=TaskStatus.SUCCESS, description="执行状态")
    duration_ms: Optional[float] = Field(default=None, description="耗时(毫秒)")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="记录时间"
    )
    error_message: Optional[str] = Field(default=None, description="错误信息")


class ReviewRecord(BaseModel):
    """
    审核记录
    
    人工审核的完整记录，用于审计和合规。
    """
    reviewer: Optional[str] = Field(default=None, description="审核人")
    status: ReviewStatus = Field(description="审核结果")
    feedback: Optional[str] = Field(default=None, description="审核意见")
    reviewed_at: Optional[datetime] = Field(default=None, description="审核时间")
    checkpoints: List[str] = Field(
        default_factory=list,
        description="检查点（如\'数据准确\'、\'口径一致\'）"
    )


# ============================================================
# 3. 核心 State 定义
# ============================================================
# 
# 这是整个系统最重要的类！所有 Agent 共享这一个 State。
# 
# 设计要点：
# 1. 字段分组：按功能分组，注释标明
# 2. 默认值：每个字段都有默认值，防止None导致的bug
# 3. 可空性：明确哪些字段可为None（Optional），哪些必须存在
# 4. 更新策略：用 Annotated 控制字段更新方式
# ============================================================

class AgentState(BaseModel):
    """
    Multi-Agent 系统的共享状态（核心中的核心）
    
    类比：这是一个"超级笔记本"，所有Agent都能读写，
    LangGraph 会自动保存每一页，服务重启后能从上次继续。
    
    使用方式：
        from app.graph.state import AgentState
        state = AgentState()
        state.messages.append(Message(role="user", content="查一下销售额"))
    """
    
    # --------------------------------------------------------
    # 3.1 对话与任务（基础信息）
    # --------------------------------------------------------
    
    messages: Annotated[List[Message], "append"] = Field(
        default_factory=list,
        description="""
        对话历史。
        
        为什么用 Annotated[List, "append"]？
        - LangGraph 的 State 更新是"合并"机制
        - 默认行为：新值覆盖旧值
        - "append" 行为：新消息追加到列表末尾
        - 这样对话历史不会丢，所有Agent都能看到完整上下文
        """
    )
    
    current_task: str = Field(
        default="",
        description="当前任务描述。Supervisor 从这里读取要做什么。"
    )
    
    task_status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="当前任务状态，前端用此展示进度"
    )
    
    # --------------------------------------------------------
    # 3.2 Agent 调度（路由信息）
    # --------------------------------------------------------
    
    active_agent: AgentType = Field(
        default=AgentType.SUPERVISOR,
        description="""
        当前活跃的Agent。
        
        前端用此值展示：
        - "Supervisor 正在分析需求..."
        - "Data Agent 正在查询数据库..."
        - "Analysis Agent 正在计算..."
        """
    )
    
    next_agent: Optional[AgentType] = Field(
        default=None,
        description="下一个要调用的Agent（由Supervisor决定）"
    )
    
    # --------------------------------------------------------
    # 3.3 各 Agent 产出（数据流转）
    # --------------------------------------------------------
    # 
    # 这是 Agent 之间协作的关键！
    # Data Agent 产出 → Analysis Agent 消费
    # Analysis Agent 产出 → Viz Agent + Report Agent 消费
    
    data_results: Optional[DataQueryResult] = Field(
        default=None,
        description="Data Agent 查询到的原始数据。Analysis Agent 会读取这个字段。"
    )
    
    analysis_results: Optional[AnalysisResult] = Field(
        default=None,
        description="Analysis Agent 的分析结论。Viz Agent 和 Report Agent 会读取这个字段。"
    )
    
    charts: List[ChartSpec] = Field(
        default_factory=list,
        description="Viz Agent 生成的图表规格列表。Report Agent 会引用这些图表。"
    )
    
    report_sections: List[ReportSection] = Field(
        default_factory=list,
        description="Report Agent 写的报告章节。最终整合成完整报告。"
    )
    
    # --------------------------------------------------------
    # 3.4 最终产出
    # --------------------------------------------------------
    
    final_report: Optional[str] = Field(
        default=None,
        description="最终整合后的报告（Markdown/HTML格式）"
    )
    
    # --------------------------------------------------------
    # 3.5 审核与质量（企业级安全）
    # --------------------------------------------------------
    # 
    # 为什么必须设计审核机制？
    # - 财务数据不能出错：必须人工确认
    # - 合规要求：某些操作必须留痕
    # - 责任归属：出了问题知道谁审核的
    
    review_status: ReviewStatus = Field(
        default=ReviewStatus.NOT_REQUIRED,
        description="""
        审核状态。
        
        流转过程：
        not_required → pending → approved/rejected
        
        触发条件（在 Supervisor 中配置）：
        - 涉及金额 > 100万 → 必须审核
        - 涉及客户隐私数据 → 必须审核
        - 删除操作 → 必须审核
        """
    )
    
    review_record: Optional[ReviewRecord] = Field(
        default=None,
        description="审核记录详情"
    )
    
    # --------------------------------------------------------
    # 3.6 可观测性（企业级必备）
    # --------------------------------------------------------
    # 
    # 没有可观测性 = 盲人摸象
    # 出了bug不知道哪步错了，性能瓶颈不知道在哪
    
    execution_trace: List[ExecutionTrace] = Field(
        default_factory=list,
        description="""
        执行轨迹。
        
        记录内容示例：
        Step 1: Supervisor 解析需求 → 分配给 Data Agent
        Step 2: Data Agent 执行SQL → 返回1000行数据
        Step 3: Analysis Agent 分析 → 发现3个异常
        Step 4: Viz Agent 生成图表 → 2张图表
        Step 5: Report Agent 写报告 → 5个章节
        Step 6: Review Agent 检查 → 通过
        
        用途：
        - 调试：哪步出错了？
        - 审计：这个数字怎么来的？
        - 优化：哪步最慢？
        - 复盘：为什么这次结果不好？
        """
    )
    
    error_log: List[str] = Field(
        default_factory=list,
        description="错误日志。非致命错误记录在这里，不中断流程。"
    )
    
    # --------------------------------------------------------
    # 3.7 迭代控制（防止死循环）
    # --------------------------------------------------------
    # 
    # 为什么需要迭代控制？
    # - LLM 可能陷入循环："再查一下"→"再分析一下"→"再查一下"...
    # - 企业资源有限，不能无限跑
    # - 超时保护：用户等不了10分钟
    
    iteration_count: int = Field(
        default=0,
        description="当前迭代次数。每经过一个Agent节点+1。"
    )
    
    max_iterations: int = Field(
        default=15,
        description="最大迭代次数。超过则强制结束，防止死循环。"
    )
    
    # --------------------------------------------------------
    # 3.8 元数据（扩展字段）
    # --------------------------------------------------------
    
    session_id: str = Field(
        default="",
        description="会话ID。用于关联一次完整的对话流程。"
    )
    
    user_id: Optional[str] = Field(
        default=None,
        description="用户ID。用于权限控制、审计。"
    )
    
    metadata: dict = Field(
        default_factory=dict,
        description="扩展字段。用于存放业务特定的数据。"
    )
    
    # ============================================================
    # 4. 业务方法
    # ============================================================
    
    def add_message(self, role: str, content: str, agent_name: Optional[str] = None) -> None:
        """
        添加消息到对话历史
        
        为什么封装成方法？
        - 保证格式统一
        - 自动填充时间戳
        - 方便后续扩展（如记录token用量）
        """
        self.messages.append(Message(
            role=role,  # type: ignore
            content=content,
            agent_name=agent_name,
        ))
    
    def add_trace(
        self,
        agent: str,
        action: str,
        status: TaskStatus = TaskStatus.SUCCESS,
        input_summary: Optional[str] = None,
        output_summary: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """添加执行轨迹"""
        self.execution_trace.append(ExecutionTrace(
            step=len(self.execution_trace) + 1,
            agent=agent,
            action=action,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            error_message=error_message,
        ))
    
    def should_stop(self) -> bool:
        """
        判断是否该停止
        
        停止条件（满足任一）：
        1. 迭代次数超过上限
        2. 任务已完成（FINISH）
        3. 审核被拒绝
        """
        if self.iteration_count >= self.max_iterations:
            self.error_log.append(f"达到最大迭代次数限制({self.max_iterations})")
            return True
        
        if self.active_agent == AgentType.FINISH:
            return True
        
        if self.review_status == ReviewStatus.REJECTED:
            return True
        
        return False
    
    def get_summary(self) -> dict:
        """
        获取状态摘要（用于日志和调试）
        
        不返回完整State（可能很大），只返回关键信息
        """
        return {
            "session_id": self.session_id,
            "active_agent": self.active_agent.value,
            "task_status": self.task_status.value,
            "iteration": f"{self.iteration_count}/{self.max_iterations}",
            "has_data": self.data_results is not None,
            "has_analysis": self.analysis_results is not None,
            "chart_count": len(self.charts),
            "section_count": len(self.report_sections),
            "review_status": self.review_status.value,
            "trace_count": len(self.execution_trace),
        }


# ============================================================
# 5. 路由决策模型
# ============================================================
# 
# Supervisor Agent 的输出格式。
# 用 Pydantic 模型强制 LLM 返回结构化数据。
# ============================================================

class RouteDecision(BaseModel):
    """
    Supervisor 的路由决策
    
    为什么用 Pydantic 模型作为 LLM 输出？
    ===================================
    传统做法（字符串解析）：
        LLM输出："下一步调用 data_agent，因为需要查询数据"
        程序：用正则提取 "data_agent" → 容易出错！
    
    我们的做法（结构化输出）：
        LLM输出JSON：{"next_agent": "data_agent", "reasoning": "..."}
        程序：直接解析为 Pydantic 对象 → 类型安全！
    
    LangChain 的 with_structured_output 帮我们做了这件事。
    """
    
    next_agent: AgentType = Field(
        description="下一个应该调用的Agent"
    )
    
    reasoning: str = Field(
        description="决策理由。用于日志记录、调试、向用户解释。"
    )
    
    task_for_next: str = Field(
        description="分配给下一个Agent的具体任务描述。要清晰、具体、可执行。"
    )
    
    requires_review: bool = Field(
        default=False,
        description="此步骤是否需要人工审核。涉及敏感操作时设为true。"
    )
    
    @field_validator("task_for_next")
    @classmethod
    def validate_task_not_empty(cls, v: str) -> str:
        """任务描述不能为空"""
        if not v or not v.strip():
            raise ValueError("任务描述不能为空")
        return v.strip()


# ============================================================
# 6. 辅助函数
# ============================================================

def create_initial_state(user_message: str, user_id: Optional[str] = None) -> AgentState:
    """
    创建初始状态
    
    每次用户发起新对话时调用。
    生成唯一的 session_id，初始化所有字段。
    """
    import uuid
    
    state = AgentState(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        current_task=user_message,
        task_status=TaskStatus.PENDING,
    )
    
    # 添加用户第一条消息
    state.add_message(role="user", content=user_message)
    
    # 记录启动轨迹
    state.add_trace(
        agent="system",
        action="session_started",
        input_summary=user_message[:100],  # 只记录前100字符
    )
    
    return state

print("✅ backend/app/graph/state.py 创建完成")
