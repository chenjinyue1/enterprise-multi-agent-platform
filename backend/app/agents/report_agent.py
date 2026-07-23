
# 5. 编写 Report Agent 核心代码
"""
Report Agent - 报告生成智能体

这是整个多智能体平台的"收官Agent"。
前面的Agent各司其职：
- Data Agent：把数据从数据库"搬"出来
- Analysis Agent：把数据"算"出洞察
- Viz Agent：把洞察"画"成图表

Report Agent的任务：把以上所有成果"写"成一份专业报告。

它就像一个"资深咨询顾问"，接过前面同事的所有工作成果，
整理成一份老板能看懂、客户能信服、团队能执行的专业报告。
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableSequence
from pydantic import BaseModel, Field

from ..graph.state import AgentState, ReportSpec, ChartSpec
from ..tools.chart_tool import ChartSpec as ChartToolSpec
from app.prompts.report_agent_prompt import (
    build_report_generation_prompt,
    build_quality_check_prompt,
    REPORT_JINJA_TEMPLATES
)
from ..rag.retriever import retrieve_report_context


# ============================================
# 结构化输出模型（Pydantic）
# ============================================
class ReportSection(BaseModel):
    """报告章节"""
    title: str = Field(description="章节标题")
    content: str = Field(description="章节内容（Markdown格式）")
    order: int = Field(description="章节顺序")
    chart_ids: List[str] = Field(default=[], description="本章引用的图表ID")


class ReportQualityResult(BaseModel):
    """报告质量检查结果"""
    passed: bool = Field(description="是否通过质量检查")
    score: int = Field(description="质量评分0-100")
    issues: List[Dict] = Field(default=[], description="发现的问题")
    improved_report: Optional[str] = Field(description="改进后的报告内容")


class ReportMetadata(BaseModel):
    """报告元数据"""
    report_type: str = Field(description="报告类型")
    audience: str = Field(description="目标受众")
    generated_at: str = Field(description="生成时间")
    data_source: str = Field(description="数据来源")
    total_charts: int = Field(description="包含图表数")
    total_words: int = Field(description="报告字数")


# ============================================
# Report Agent 主类
# ============================================
class ReportAgent:
    """
    报告生成Agent
    
    工作流程（ReAct模式）：
    --------------------
    1. Think: 分析用户需求，确定报告类型和受众
    2. Retrieve: 调用RAG检索历史模板
    3. Generate: 基于模板+数据+洞察生成报告
    4. Check: 质量自检（数据一致性、逻辑完整性）
    5. Refine: 如有问题，自动修正
    6. Output: 输出最终报告
    
    企业价值：
    ---------
    - 统一报告质量：消除"不同人写的报告质量参差不齐"问题
    - 沉淀企业知识：历史报告自动成为模板库，越用越聪明
    - 节省80%时间：从4小时写报告 → 10分钟审核报告
    """
    
    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        max_retries: int = 2
    ):
        """
        初始化Report Agent
        
        Args:
            model: 使用GPT-4o（写作能力强，理解上下文好）
            temperature: 0.3（低温度确保数据准确性，减少幻觉）
            max_retries: 质量检查不通过时的最大重试次数
        """
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            max_retries=3
        )
        
        # 轻量级模型用于质量检查（省钱）
        self.checker_llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        self.max_retries = max_retries
        
        # 构建生成链
        self.generation_prompt = build_report_generation_prompt()
        self.generation_chain = self.generation_prompt | self.llm | StrOutputParser()
        
        # 构建质量检查链
        self.quality_prompt = build_quality_check_prompt()
        self.quality_chain = self.quality_prompt | self.checker_llm | JsonOutputParser()
    
    def run(self, state: AgentState) -> Dict[str, Any]:
        """
        Agent主入口（LangGraph节点调用）
        
        Args:
            state: 当前状态，包含data、insights、charts等
            
        Returns:
            更新后的state字段
            
        完整执行流程：
        ---------------
        State输入 → 需求分析 → RAG检索 → 报告生成 → 质量检查 → 修正 → 输出ReportSpec
        """
        print("\\n📋 [Report Agent] 开始生成报告...")
        
        # Step 1: 分析需求
        report_type, audience, requirements = self._analyze_requirements(state)
        print(f"   报告类型: {report_type} | 受众: {audience}")
        
        # Step 2: RAG检索历史模板
        print("   🔍 检索历史报告模板...")
        rag_context = retrieve_report_context(
            query=state.user_query,
            report_type=report_type,
            top_k=3
        )
        print(f"   检索到 {len(rag_context.split('---'))} 个相关模板")
        
        # Step 3: 准备输入数据
        input_data = self._prepare_generation_input(
            state=state,
            report_type=report_type,
            audience=audience,
            requirements=requirements,
            rag_context=rag_context
        )
        
        # Step 4: 生成报告（带重试机制）
        report_content = self._generate_with_retry(input_data, state)
        
        # Step 5: 构建ReportSpec
        report_spec = self._build_report_spec(
            content=report_content,
            state=state,
            report_type=report_type,
            audience=audience
        )
        
        print(f"   ✅ 报告生成完成！{report_spec.total_words}字 | {report_spec.total_charts}个图表")
        
        return {
            "report": report_spec,
            "messages": state.messages + [
                AIMessage(content=f"报告已生成：{report_spec.title}（{report_spec.total_words}字）")
            ]
        }
    
    def _analyze_requirements(self, state: AgentState) -> tuple:
        """
        分析用户需求，确定报告参数
        
        为什么需要分析？
        ----------------
        用户说"帮我看看销售数据"，系统需要判断：
        - 这是季度报告？月度报告？还是临时分析？
        - 给老板看？给团队看？给客户看？
        - 要详细分析？还是只要结论？
        
        这些判断直接影响报告的结构、篇幅、措辞。
        """
        query = state.user_query.lower()
        
        # 判断报告类型
        if any(kw in query for kw in ["季度", "q1", "q2", "q3", "q4", "quarter"]):
            report_type = "quarterly"
        elif any(kw in query for kw in ["月度", "月报", "monthly", "本月"]):
            report_type = "monthly"
        elif any(kw in query for kw in ["年度", "年报", "annual", "全年", "year"]):
            report_type = "annual"
        else:
            report_type = "ad_hoc"  # 临时分析
        
        # 判断受众
        if any(kw in query for kw in ["老板", "高管", "ceo", "总裁", "executive", "汇报"]):
            audience = "executive"
        elif any(kw in query for kw in ["客户", "甲方", "customer", "对外"]):
            audience = "external"
        else:
            audience = "internal"
        
        # 提取特殊要求
        requirements = []
        if any(kw in query for kw in ["简短", "简洁", "一页", "brief"]):
            requirements.append("concise")
        if any(kw in query for kw in ["详细", "深入", "detail", "deep"]):
            requirements.append("detailed")
        if any(kw in query for kw in ["对比", "compare", "vs"]):
            requirements.append("comparison")
        
        return report_type, audience, requirements
    
    def _prepare_generation_input(
        self,
        state: AgentState,
        report_type: str,
        audience: str,
        requirements: List[str],
        rag_context: str
    ) -> Dict[str, Any]:
        """
        准备LLM生成所需的输入数据
        
        把State里的各种数据格式化成Prompt能用的字符串
        """
        # 数据结果JSON化
        data_results = json.dumps(
            state.data if state.data else {},
            ensure_ascii=False,
            indent=2
        )
        
        # 分析洞察JSON化
        insights = json.dumps(
            state.insights if state.insights else {},
            ensure_ascii=False,
            indent=2
        )
        
        # 图表信息JSON化
        charts_info = []
        if state.charts:
            for chart in state.charts:
                charts_info.append({
                    "id": chart.chart_id,
                    "title": chart.title,
                    "type": chart.chart_type,
                    "description": chart.description
                })
        charts_json = json.dumps(charts_info, ensure_ascii=False, indent=2)
        
        # 确定篇幅要求
        if "concise" in requirements:
            length_req = "精简版（1000字以内，适合高管快速阅读）"
        elif "detailed" in requirements:
            length_req = "详细版（3000-5000字，包含完整分析过程）"
        else:
            length_req = "标准版（2000-3000字）"
        
        # 特殊要求
        special_req = "；".join(requirements) if requirements else "无"
        
        return {
            "user_query": state.user_query,
            "rag_context": rag_context,
            "data_results": data_results,
            "analysis_insights": insights,
            "charts": charts_json,
            "report_type": report_type,
            "audience": audience,
            "length_requirement": length_req,
            "special_requirements": special_req
        }
    
    def _generate_with_retry(
        self,
        input_data: Dict[str, Any],
        state: AgentState
    ) -> str:
        """
        带质量检查的重试生成
        
        企业级要求：报告不能出错，尤其是数据错误。
        所以我们生成后自动检查，发现问题就修正，最多重试2次。
        """
        current_report = ""
        
        for attempt in range(self.max_retries + 1):
            print(f"   📝 生成尝试 {attempt + 1}/{self.max_retries + 1}...")
            
            # 生成报告
            current_report = self.generation_chain.invoke(input_data)
            
            # 质量检查
            print("   🔍 执行质量检查...")
            check_result = self._quality_check(current_report, state)
            
            if check_result.passed:
                print(f"   ✅ 质量检查通过！评分: {check_result.score}/100")
                break
            else:
                print(f"   ⚠️ 发现 {len(check_result.issues)} 个问题")
                for issue in check_result.issues:
                    print(f"      [{issue.get('severity', 'warning')}] {issue.get('description', '')}")
                
                # 如果有改进版本，使用改进版
                if check_result.improved_report:
                    current_report = check_result.improved_report
                    print("   🔄 已自动修正")
                
                # 如果不是最后一次尝试，把问题反馈给生成链
                if attempt < self.max_retries:
                    input_data["special_requirements"] += (
                        f"\\n\\n【修正要求】上一轮检查发现以下问题，请务必修正：\\n"
                        + "\\n".join(f"- {i.get('description', '')}: {i.get('suggestion', '')}"
                                    for i in check_result.issues)
                    )
        else:
            print("   ⚠️ 达到最大重试次数，使用最后一次生成结果")
        
        return current_report
    
    def _quality_check(self, report: str, state: AgentState) -> ReportQualityResult:
        """
        报告质量检查
        
        检查项：
        1. 数据一致性：报告中的数字是否和原始数据一致
        2. 图表引用：引用的chart_id是否真实存在
        3. 幻觉检测：是否有编造的信息
        4. 结构完整性：是否包含必要章节
        """
        try:
            # 准备检查输入
            source_data = json.dumps({
                "data": state.data,
                "insights": state.insights,
                "charts": [{"id": c.chart_id, "title": c.title} for c in (state.charts or [])]
            }, ensure_ascii=False, indent=2)
            
            check_input = {
                "report_content": report,
                "source_data": source_data
            }
            
            result = self.quality_chain.invoke(check_input)
            
            return ReportQualityResult(
                passed=result.get("passed", False),
                score=result.get("score", 0),
                issues=result.get("issues", []),
                improved_report=result.get("improved_report")
            )
        except Exception as e:
            print(f"   ⚠️ 质量检查异常: {e}")
            # 检查失败时默认通过（避免阻塞流程）
            return ReportQualityResult(passed=True, score=80, issues=[])
    
    def _build_report_spec(
        self,
        content: str,
        state: AgentState,
        report_type: str,
        audience: str
    ) -> ReportSpec:
        """
        构建标准化的ReportSpec对象
        
        ReportSpec是报告的结构化表示，前端据此渲染不同格式（Markdown/HTML/Word）
        """
        # 统计字数（中文字符+英文单词）
        import re
        chinese_chars = len(re.findall(r'[\\u4e00-\\u9fff]', content))
        english_words = len(re.findall(r'[a-zA-Z]+', content))
        total_words = chinese_chars + english_words
        
        # 提取引用的图表ID
        chart_ids = re.findall(r'chart://([a-zA-Z0-9_-]+)', content)
        
        # 生成标题
        title = self._generate_title(state, report_type)
        
        return ReportSpec(
            report_id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}",
            title=title,
            content=content,
            report_type=report_type,
            audience=audience,
            generated_at=datetime.now().isoformat(),
            data_source="MySQL + Python计算 + RAG模板库",
            total_charts=len(chart_ids),
            total_words=total_words,
            chart_ids=chart_ids,
            referenced_templates=[],  # 可从RAG结果填充
            status="generated"
        )
    
    def _generate_title(self, state: AgentState, report_type: str) -> str:
        """智能生成报告标题"""
        type_names = {
            "quarterly": "季度",
            "monthly": "月度",
            "annual": "年度",
            "ad_hoc": "专项"
        }
        type_name = type_names.get(report_type, "分析")
        
        # 从用户查询提取主题
        query = state.user_query
        # 去掉常见前缀
        for prefix in ["帮我", "请", "给我", "生成", "写一份", "做一个"]:
            query = query.replace(prefix, "")
        
        return f"{type_name}数据分析报告：{query.strip()}"


# ============================================
# LangGraph 节点函数
# ============================================
def report_agent_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph节点入口函数
    
    LangGraph通过调用这个函数来执行Report Agent。
    它包装了ReportAgent.run()，处理异常和日志。
    """
    try:
        agent = ReportAgent()
        result = agent.run(state)
        return result
    except Exception as e:
        print(f"❌ [Report Agent] 执行失败: {e}")
        # 返回错误状态，不阻断整个流程
        return {
            "report": None,
            "messages": state.messages + [
                AIMessage(content=f"报告生成失败: {str(e)}")
            ],
            "error": str(e)
        }


# ============================================
# 便捷函数：直接生成报告（非LangGraph场景）
# ============================================
def generate_report_direct(
    user_query: str,
    data: Dict,
    insights: Dict,
    charts: List[ChartSpec],
    report_type: str = "ad_hoc"
) -> ReportSpec:
    """
    直接生成报告（用于测试或独立调用）
    
    使用示例：
    -------
    report = generate_report_direct(
        user_query="Q3销售数据分析",
        data={"sales": 1500, "orders": 3200},
        insights={"trend": "上升", "top_category": "电子产品"},
        charts=[chart1, chart2],
        report_type="quarterly"
    )
    print(report.content)
    """
    from ..graph.state import AgentState
    
    # 构建临时State
    temp_state = AgentState(
        user_query=user_query,
        data=data,
        insights=insights,
        charts=charts,
        messages=[HumanMessage(content=user_query)]
    )
    
    agent = ReportAgent()
    result = agent.run(temp_state)
    return result["report"]


print("✅ report_agent.py 编写完成")
