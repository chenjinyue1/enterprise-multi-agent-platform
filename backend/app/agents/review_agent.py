
# 4. 编写 Review Agent 核心代码
"""
Review Agent - 质量审核智能体

这是整个多智能体平台的"质量守门员"。
前面的Agent负责"生产"（查数据、做分析、画图表、写报告），
Review Agent负责"质检"——确保最终交付物达到企业级标准。

为什么需要Review Agent？
------------------------
1. **自动化质检**：不需要人工逐份审核，节省80%审核时间
2. **标准化评估**：消除"不同人审核标准不一致"的问题
3. **可追溯审计**：每份报告都有完整的质量评分记录
4. **持续改进**：评估结果反馈给前面的Agent，形成优化闭环

Review Agent vs Report Agent自检：
----------------------------------
- Report Agent自检：生成过程中的"自我检查"（快速、轻量）
- Review Agent审核：生成后的"独立第三方审核"（全面、严格）

类比：
- Report Agent自检 = 作者自己校对（容易漏掉问题）
- Review Agent审核 = 专业编辑审稿（更严格、更全面）
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import JsonOutputParser

from ..graph.state import AgentState, ReportSpec
from ..evaluation.metrics import ReportEvaluator, EvaluationReport, MetricRegistry
from ..evaluation.harness import quick_evaluate
from app.prompts.review_agent_prompt import build_review_prompt


# ============================================
# 审核结果模型
# ============================================
class ReviewStatus(Enum):
    """审核状态"""
    APPROVED = "approved"           # 通过，可直接发布
    NEEDS_REVISION = "needs_revision"  # 需要修改
    REJECTED = "rejected"           # 不通过，需要重写


class ReviewIssue:
    """审核发现的问题"""
    def __init__(
        self,
        severity: str,              # critical/high/medium/low
        category: str,              # data/logic/business/compliance/ux
        description: str,
        location: str = "",
        suggestion: str = ""
    ):
        self.severity = severity
        self.category = category
        self.description = description
        self.location = location
        self.suggestion = suggestion
    
    def to_dict(self) -> Dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "location": self.location,
            "suggestion": self.suggestion
        }


class ReviewResult:
    """
    审核结果
    
    这是Review Agent的最终输出，包含：
    - 综合评分和等级
    - 各维度评分
    - 发现的问题列表
    - 修改建议
    - 最终裁决
    """
    def __init__(
        self,
        report_id: str,
        overall_grade: str,
        overall_score: float,
        status: ReviewStatus,
        dimension_scores: Dict[str, Dict],
        issues: List[ReviewIssue],
        strengths: List[str],
        final_verdict: str,
        reviewed_at: str = None
    ):
        self.report_id = report_id
        self.overall_grade = overall_grade
        self.overall_score = overall_score
        self.status = status
        self.dimension_scores = dimension_scores
        self.issues = issues
        self.strengths = strengths
        self.final_verdict = final_verdict
        self.reviewed_at = reviewed_at or datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "overall_grade": self.overall_grade,
            "overall_score": round(self.overall_score, 2),
            "status": self.status.value,
            "dimension_scores": self.dimension_scores,
            "issues": [i.to_dict() for i in self.issues],
            "strengths": self.strengths,
            "final_verdict": self.final_verdict,
            "reviewed_at": self.reviewed_at
        }


# ============================================
# Review Agent 主类
# ============================================
class ReviewAgent:
    """
    质量审核Agent
    
    工作流程：
    ---------
    1. 自动化评估：运行所有注册指标（数据准确性、幻觉检测等）
    2. LLM深度审核：用GPT-4o做更深入的逻辑和业务合理性判断
    3. 综合裁决：结合自动化评分和LLM审核，给出最终裁决
    4. 反馈生成：生成修改建议，反馈给Report Agent
    
    企业场景：
    ---------
    报告生成后，Review Agent自动审核：
    - 通过（A/B级）→ 直接发布
    - 需修改（C级）→ 退回Report Agent，附带修改建议
    - 不通过（D/F级）→ 退回重写，记录问题
    """
    
    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.1,
        auto_threshold: float = 75.0,
        llm_threshold: float = 70.0
    ):
        """
        初始化Review Agent
        
        Args:
            model: 审核用LLM（需要强推理能力，用gpt-4o）
            temperature: 0.1（低温度确保审核标准一致）
            auto_threshold: 自动化评估通过阈值
            llm_threshold: LLM审核通过阈值
        """
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # 自动化评估器
        self.auto_evaluator = ReportEvaluator()
        
        # 审核Prompt
        self.review_prompt = build_review_prompt()
        self.review_chain = self.review_prompt | self.llm | JsonOutputParser()
        
        # 阈值
        self.auto_threshold = auto_threshold
        self.llm_threshold = llm_threshold
    
    def run(self, state: AgentState) -> Dict[str, Any]:
        """
        Agent主入口（LangGraph节点调用）
        
        Args:
            state: 当前状态，包含report、data、insights等
            
        Returns:
            更新后的state字段
        """
        print("\\n🔍 [Review Agent] 开始质量审核...")
        
        report = state.get("report")
        if not report:
            print("   ⚠️ 报告不存在，跳过审核")
            return {
                "review_result": None,
                "messages": state.messages + [
                    AIMessage(content="审核跳过：报告未生成")
                ]
            }
        
        # Step 1: 自动化评估
        print("   📊 执行自动化评估...")
        auto_eval = self._auto_evaluate(report, state)
        print(f"   自动化评分: {auto_eval.overall_score:.1f}/100 (等级: {auto_eval.grade})")
        
        # Step 2: LLM深度审核
        print("   🧠 执行LLM深度审核...")
        llm_review = self._llm_review(report, state, auto_eval)
        print(f"   LLM审核评分: {llm_review['overall_score']}/100 (等级: {llm_review['overall_grade']})")
        
        # Step 3: 综合裁决
        print("   ⚖️ 综合裁决...")
        review_result = self._adjudicate(auto_eval, llm_review, report)
        print(f"   最终裁决: {review_result.status.value.upper()} | 等级: {review_result.overall_grade}")
        
        # Step 4: 更新报告状态
        report.status = review_result.status.value
        report.quality_score = review_result.overall_score
        
        # Step 5: 生成反馈消息
        feedback_msg = self._generate_feedback_message(review_result)
        
        return {
            "review_result": review_result,
            "report": report,
            "messages": state.messages + [
                AIMessage(content=feedback_msg)
            ]
        }
    
    def _auto_evaluate(self, report: ReportSpec, state: AgentState) -> EvaluationReport:
        """
        自动化评估
        
        运行所有注册的指标检查，快速给出量化评分。
        这是"机器检查"，速度快、成本低、可重复。
        """
        state_data = {
            "data": state.data or {},
            "insights": state.insights or {},
            "charts": state.charts or []
        }
        
        return self.auto_evaluator.evaluate(
            report_content=report.content,
            state_data=state_data,
            report_id=report.report_id
        )
    
    def _llm_review(
        self,
        report: ReportSpec,
        state: AgentState,
        auto_eval: EvaluationReport
    ) -> Dict[str, Any]:
        """
        LLM深度审核
        
        用GPT-4o做更深入的逻辑判断，这是"专家审核"：
        - 判断业务合理性（机器无法判断"增长50%是否合理"）
        - 检查逻辑一致性（机器难以发现"数据说A，结论说B"）
        - 评估用户体验（机器难以判断"报告是否回答了用户问题"）
        """
        try:
            # 准备输入
            source_data = json.dumps(state.data or {}, ensure_ascii=False, indent=2)
            insights = json.dumps(state.insights or {}, ensure_ascii=False, indent=2)
            auto_eval_json = json.dumps(auto_eval.to_dict(), ensure_ascii=False, indent=2)
            
            # 截断报告内容（控制token消耗）
            report_content = report.content[:4000] if len(report.content) > 4000 else report.content
            
            review_input = {
                "user_query": state.user_query,
                "report_content": report_content,
                "source_data": source_data,
                "analysis_insights": insights,
                "auto_evaluation": auto_eval_json
            }
            
            result = self.review_chain.invoke(review_input)
            return result
            
        except Exception as e:
            print(f"   ⚠️ LLM审核异常: {e}")
            # LLM审核失败时，回退到自动化评估结果
            return {
                "overall_grade": auto_eval.grade,
                "overall_score": auto_eval.overall_score,
                "status": "approved" if auto_eval.overall_score >= 70 else "needs_revision",
                "dimension_scores": {},
                "issues": [],
                "strengths": [],
                "final_verdict": f"LLM审核失败，使用自动化评估结果: {auto_eval.grade}级"
            }
    
    def _adjudicate(
        self,
        auto_eval: EvaluationReport,
        llm_review: Dict[str, Any],
        report: ReportSpec
    ) -> ReviewResult:
        """
        综合裁决
        
        结合自动化评估和LLM审核，给出最终裁决。
        
        裁决规则：
        ---------
        1. 如果自动化评估有CRITICAL级别不通过 → 直接不通过
        2. 如果LLM审核发现数据错误或幻觉 → 直接不通过
        3. 综合得分 = 自动化得分 * 0.6 + LLM得分 * 0.4
        4. 根据综合得分确定等级和状态
        """
        
        # 提取LLM审核结果
        llm_score = llm_review.get("overall_score", auto_eval.overall_score)
        llm_grade = llm_review.get("overall_grade", auto_eval.grade)
        llm_status = llm_review.get("status", "approved")
        
        # 检查是否有严重问题
        has_critical = any(
            m.severity.value == "critical" and not m.passed
            for m in auto_eval.metrics
        )
        
        # 检查LLM是否发现严重问题
        llm_issues = llm_review.get("issues", [])
        has_critical_llm = any(
            i.get("severity") == "critical" for i in llm_issues
        )
        
        # 计算综合得分
        combined_score = auto_eval.overall_score * 0.6 + llm_score * 0.4
        
        # 确定等级
        grade = self._calculate_grade(combined_score)
        
        # 确定状态
        if has_critical or has_critical_llm:
            status = ReviewStatus.REJECTED
        elif combined_score >= 80:
            status = ReviewStatus.APPROVED
        elif combined_score >= 60:
            status = ReviewStatus.NEEDS_REVISION
        else:
            status = ReviewStatus.REJECTED
        
        # 构建问题列表
        issues = []
        
        # 添加自动化评估发现的问题
        for metric in auto_eval.metrics:
            if not metric.passed:
                issues.append(ReviewIssue(
                    severity="high" if metric.severity.value == "critical" else "medium",
                    category="data" if metric.metric_name == "data_accuracy" else "logic",
                    description=metric.details,
                    suggestion=metric.suggestions[0] if metric.suggestions else "请检查并修正"
                ))
        
        # 添加LLM审核发现的问题
        for issue in llm_issues:
            issues.append(ReviewIssue(
                severity=issue.get("severity", "medium"),
                category=issue.get("category", "logic"),
                description=issue.get("description", ""),
                location=issue.get("location", ""),
                suggestion=issue.get("suggestion", "")
            ))
        
        # 生成最终裁决
        if status == ReviewStatus.APPROVED:
            verdict = f"报告通过审核，等级{grade}（{combined_score:.1f}分），可直接发布。"
        elif status == ReviewStatus.NEEDS_REVISION:
            verdict = f"报告需要修改，等级{grade}（{combined_score:.1f}分）。请按以下建议修改后重新提交审核。"
        else:
            verdict = f"报告未通过审核，等级{grade}（{combined_score:.1f}分）。存在严重问题，建议重写。"
        
        return ReviewResult(
            report_id=report.report_id,
            overall_grade=grade,
            overall_score=combined_score,
            status=status,
            dimension_scores=llm_review.get("dimension_scores", {}),
            issues=issues,
            strengths=llm_review.get("strengths", []),
            final_verdict=verdict
        )
    
    def _calculate_grade(self, score: float) -> str:
        """计算等级"""
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
    
    def _generate_feedback_message(self, review_result: ReviewResult) -> str:
        """生成反馈消息"""
        status_map = {
            ReviewStatus.APPROVED: "✅ 审核通过",
            ReviewStatus.NEEDS_REVISION: "⚠️ 需要修改",
            ReviewStatus.REJECTED: "❌ 审核未通过"
        }
        
        msg = f"{status_map[review_result.status]} | 等级: {review_result.overall_grade} | 得分: {review_result.overall_score:.1f}\\n"
        msg += f"裁决: {review_result.final_verdict}\\n"
        
        if review_result.issues:
            msg += f"\\n发现 {len(review_result.issues)} 个问题:\\n"
            for i, issue in enumerate(review_result.issues[:5], 1):
                msg += f"{i}. [{issue.severity.upper()}] {issue.description}\\n"
        
        return msg


# ============================================
# LangGraph 节点函数
# ============================================
def review_agent_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph节点入口函数
    
    这是LangGraph调用Review Agent的入口。
    """
    try:
        agent = ReviewAgent()
        result = agent.run(state)
        return result
    except Exception as e:
        print(f"❌ [Review Agent] 执行失败: {e}")
        return {
            "review_result": None,
            "messages": state.messages + [
                AIMessage(content=f"审核执行失败: {str(e)}")
            ],
            "error": str(e)
        }


# ============================================
# 便捷函数
# ============================================
def review_report_direct(report: ReportSpec, state: AgentState) -> ReviewResult:
    """
    直接审核报告（用于测试或独立调用）
    
    使用示例：
    -------
    result = review_report_direct(report, state)
    if result.status == ReviewStatus.APPROVED:
        print("报告通过审核！")
    else:
        print(f"需要修改: {result.issues[0].suggestion}")
    """
    agent = ReviewAgent()
    result = agent.run(state)
    return result["review_result"]


print("✅ review_agent.py 编写完成")
