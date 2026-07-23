
# 1. 编写评估指标模块 metrics.py
"""
评估指标模块
定义多维度评估指标，用于量化Agent系统输出质量

小白理解：
想象你是一家餐厅的老板，你怎么知道厨师做的菜好不好？
- 看卖相（外观指标）
- 尝味道（口感指标）
- 问顾客（满意度指标）
- 算成本（效率指标）

评估指标就是给AI系统做的"体检项目"，从不同维度打分，
确保它输出的报告是准确、有用、可信的。
"""

import os
import re
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser


# ============================================
# 评估结果数据类
# ============================================
class MetricSeverity(Enum):
    """指标严重级别"""
    CRITICAL = "critical"      # 严重：必须修复，否则不能上线
    HIGH = "high"              # 高：影响用户体验，建议修复
    MEDIUM = "medium"          # 中：有优化空间
    LOW = "low"                # 低：锦上添花
    INFO = "info"              # 信息：仅供参考


@dataclass
class MetricScore:
    """
    单个指标的评分结果
    
    为什么用dataclass？
    -----------------
    评估结果需要结构化存储，方便：
    - 存入数据库（MySQL/Redis）
    - 序列化为JSON（API返回给前端）
    - 生成评估报告（可视化图表）
    """
    metric_name: str                    # 指标名称
    score: float                        # 分数 0-100
    weight: float                       # 权重（用于加权计算总分）
    severity: MetricSeverity            # 严重级别
    passed: bool                        # 是否通过阈值
    threshold: float                    # 通过阈值
    details: str                        # 详细说明
    evidence: List[str] = field(default_factory=list)  # 证据（具体哪里扣分了）
    suggestions: List[str] = field(default_factory=list)  # 改进建议


@dataclass  
class EvaluationReport:
    """
    完整评估报告
    
    这是Review Agent的最终输出，包含所有维度的评分。
    """
    report_id: str                      # 被评估的报告ID
    evaluated_at: str                   # 评估时间
    overall_score: float                # 综合得分（加权平均）
    grade: str                          # 等级: A/B/C/D/F
    status: str                         # 状态: passed/failed/warning
    metrics: List[MetricScore]          # 各维度评分详情
    summary: str                        # 评估总结
    action_items: List[str]             # 必须修复的问题
    improvements: List[str]             # 优化建议
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于JSON序列化）"""
        return {
            "report_id": self.report_id,
            "evaluated_at": self.evaluated_at,
            "overall_score": round(self.overall_score, 2),
            "grade": self.grade,
            "status": self.status,
            "metrics": [
                {
                    "name": m.metric_name,
                    "score": round(m.score, 2),
                    "weight": m.weight,
                    "severity": m.severity.value,
                    "passed": m.passed,
                    "threshold": m.threshold,
                    "details": m.details,
                    "evidence": m.evidence,
                    "suggestions": m.suggestions
                }
                for m in self.metrics
            ],
            "summary": self.summary,
            "action_items": self.action_items,
            "improvements": self.improvements
        }


# ============================================
# 指标注册表（装饰器模式）
# ============================================
class MetricRegistry:
    """
    指标注册表
    
    设计模式：装饰器注册
    使用方式：
        @register_metric("data_accuracy", weight=0.3, threshold=85)
        def check_data_accuracy(report, state):
            ...
    
    为什么用注册表？
    ----------------
    企业级评估需要"可插拔"的指标：
    - 今天评估5个维度，明天可能需要加第6个
    - 不同业务线（销售/财务/运营）关注不同指标
    - 用注册表可以动态加载指标，不用改核心代码
    """
    
    _metrics: Dict[str, Dict] = {}
    
    @classmethod
    def register(cls, name: str, weight: float = 1.0, threshold: float = 70.0):
        """
        注册指标的装饰器
        
        Args:
            name: 指标唯一名称
            weight: 权重（0-1，所有指标权重之和应为1）
            threshold: 通过阈值（低于此值算不通过）
        """
        def decorator(func: Callable):
            cls._metrics[name] = {
                "func": func,
                "weight": weight,
                "threshold": threshold,
                "name": name
            }
            return func
        return decorator
    
    @classmethod
    def get_metric(cls, name: str) -> Optional[Dict]:
        """获取单个指标"""
        return cls._metrics.get(name)
    
    @classmethod
    def get_all_metrics(cls) -> Dict[str, Dict]:
        """获取所有已注册指标"""
        return cls._metrics.copy()
    
    @classmethod
    def list_metrics(cls) -> List[str]:
        """列出所有指标名称"""
        return list(cls._metrics.keys())


# 便捷装饰器
register_metric = MetricRegistry.register


# ============================================
# 核心评估指标实现
# ============================================

@register_metric("data_accuracy", weight=0.25, threshold=85.0)
def check_data_accuracy(report_content: str, state_data: Dict) -> MetricScore:
    """
    数据准确性检查
    
    核心逻辑：
    1. 从报告中提取所有数字
    2. 和原始数据（state.data）对比
    3. 检查是否有：数字错误、单位不一致、计算错误
    
    企业价值：
    ---------
    这是最重要的指标。报告中的数字错了，
    可能导致错误的商业决策（如库存误判、预算偏差）。
    """
    issues = []
    suggestions = []
    score = 100.0
    
    # 从报告中提取所有数字（包括百分比、金额等）
    # 匹配模式：1500、1,234、15.5%、1.5万、¥1500等
    number_patterns = [
        r'\\b\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?\\b',  # 1,234 或 1,234.56
        r'\\b\\d+\\.\\d+\\b',                           # 15.5
        r'\\b\\d+\\b',                                   # 1500
        r'\\b\\d+\\.\\d+%',                            # 15.5%
        r'\\b\\d+万\\b',                                 # 1500万
        r'\\b\\d+亿\\b',                                 # 1.5亿
    ]
    
    found_numbers = []
    for pattern in number_patterns:
        matches = re.findall(pattern, report_content)
        found_numbers.extend(matches)
    
    # 检查state_data中的关键数字是否在报告中正确呈现
    if state_data:
        data_json = json.dumps(state_data, ensure_ascii=False)
        
        # 提取state_data中的数字
        state_numbers = re.findall(r'\\b\\d+(?:\\.\\d+)?\\b', data_json)
        
        # 检查报告中的数字是否和数据源一致
        # 简化版：检查关键数字是否出现（实际项目中需要更复杂的映射逻辑）
        missing_numbers = []
        for num in state_numbers[:10]:  # 只检查前10个关键数字
            if num not in report_content and f"{float(num):.1f}" not in report_content:
                missing_numbers.append(num)
        
        if missing_numbers:
            issues.append(f"报告中可能遗漏了关键数据: {missing_numbers}")
            score -= len(missing_numbers) * 5
    
    # 检查是否有明显的计算错误（如同比计算）
    # 简单启发式：如果报告提到"同比增长"，检查是否有百分比
    if "同比" in report_content or "增长" in report_content:
        if not re.search(r'\\d+\\.\\d*%|\\d+%', report_content):
            issues.append("提到增长但未给出具体百分比")
            score -= 10
    
    score = max(0, min(100, score))
    passed = score >= 85
    
    return MetricScore(
        metric_name="data_accuracy",
        score=score,
        weight=0.25,
        severity=MetricSeverity.CRITICAL if not passed else MetricSeverity.LOW,
        passed=passed,
        threshold=85.0,
        details="检查报告中的数字是否与原始数据一致" if passed else "发现数据一致性问题",
        evidence=issues,
        suggestions=suggestions if suggestions else ["建议增加数据校验环节"]
    )


@register_metric("hallucination_check", weight=0.25, threshold=90.0)
def check_hallucination(report_content: str, state_data: Dict) -> MetricScore:
    """
    幻觉检测
    
    核心逻辑：
    1. 检查报告中是否有"编造"的信息
    2. 检查是否有state_data中不存在的声明
    3. 检查是否有无法验证的断言
    
    什么是幻觉？
    -----------
    LLM"一本正经地胡说八道"——生成看起来合理但实际不存在的信息。
    在企业报告中，这是致命问题。
    
    检测方法：
    ---------
    - 规则匹配：检查常见幻觉模式（"根据数据显示"但无数据支撑）
    - LLM-as-Judge：用另一个LLM判断每个声明是否有依据
    - 事实核查：关键声明与数据源交叉验证
    """
    issues = []
    score = 100.0
    
    # 规则1：检查"无中生有"的断言
    hallucination_patterns = [
        r"根据.*?报告显示",  # "根据XX报告显示"但无引用
        r"研究表明",         # "研究表明"但无来源
        r"众所周知",         # "众所周知"（模糊引用）
        r"行业平均",         # "行业平均"（无具体来源）
    ]
    
    for pattern in hallucination_patterns:
        matches = re.findall(pattern, report_content)
        if matches:
            issues.append(f"发现无来源断言: {matches[0]}...")
            score -= 15
    
    # 规则2：检查是否有state_data中不存在的指标被提及
    if state_data:
        data_keys = set(str(k).lower() for k in state_data.keys())
        # 常见指标关键词
        common_metrics = ["销售额", "订单量", "用户数", "转化率", "客单价", "gmv", "dau"]
        mentioned_metrics = []
        
        for metric in common_metrics:
            if metric in report_content:
                mentioned_metrics.append(metric)
        
        # 如果提到了数据源中没有的指标，可能是幻觉
        # 简化版：实际项目中需要更复杂的映射
    
    # 规则3：检查极端数值（可能是编造）
    extreme_numbers = re.findall(r'\\b999[\\d,]+\\b|\\b1000[\\d,]+\\b', report_content)
    if extreme_numbers:
        issues.append(f"发现异常数值，需核实: {extreme_numbers}")
        score -= 10
    
    score = max(0, min(100, score))
    passed = score >= 90
    
    return MetricScore(
        metric_name="hallucination_check",
        score=score,
        weight=0.25,
        severity=MetricSeverity.CRITICAL if not passed else MetricSeverity.HIGH,
        passed=passed,
        threshold=90.0,
        details="未检测到明显幻觉" if passed else "发现疑似幻觉内容",
        evidence=issues,
        suggestions=["建议增加数据来源引用", "对关键声明添加脚注说明"]
    )


@register_metric("structure_completeness", weight=0.15, threshold=70.0)
def check_structure(report_content: str, state_data: Dict) -> MetricScore:
    """
    结构完整性检查
    
    检查报告是否包含必要的章节：
    - 执行摘要
    - 数据分析
    - 图表展示
    - 洞察建议
    - 附录
    
    企业场景：
    ---------
    不同级别的报告有不同的结构要求：
    - 高管汇报：必须有"执行摘要"（他们只看这部分）
    - 详细分析：必须有"方法论"和"数据来源"
    - 对外报告：必须有"免责声明"
    """
    required_sections = {
        "执行摘要": ["执行摘要", "摘要", "概述", "总结"],
        "数据分析": ["分析", "数据", "趋势"],
        "洞察建议": ["建议", "洞察", "发现", "结论"],
        "图表": ["图", "chart", "表格"],
    }
    
    missing_sections = []
    score = 100.0
    
    for section_name, keywords in required_sections.items():
        found = any(kw in report_content for kw in keywords)
        if not found:
            missing_sections.append(section_name)
            score -= 15
    
    score = max(0, min(100, score))
    passed = score >= 70
    
    return MetricScore(
        metric_name="structure_completeness",
        score=score,
        weight=0.15,
        severity=MetricSeverity.HIGH if not passed else MetricSeverity.LOW,
        passed=passed,
        threshold=70.0,
        details="报告结构完整" if passed else f"缺少必要章节: {missing_sections}",
        evidence=[f"缺少: {s}" for s in missing_sections],
        suggestions=[f"建议添加'{s}'章节" for s in missing_sections]
    )


@register_metric("chart_reference_accuracy", weight=0.15, threshold=80.0)
def check_chart_references(report_content: str, state_data: Dict) -> MetricScore:
    """
    图表引用准确性
    
    检查：
    1. 报告中引用的chart_id是否真实存在
    2. 图表描述是否与文字内容匹配
    3. 是否有图表但未引用，或有引用但无图表
    """
    issues = []
    score = 100.0
    
    # 提取所有图表引用
    chart_refs = re.findall(r'chart://([a-zA-Z0-9_-]+)', report_content)
    
    # 检查state中是否有这些图表
    charts = state_data.get("charts", []) if isinstance(state_data, dict) else []
    available_chart_ids = set()
    
    if charts:
        for chart in charts:
            if hasattr(chart, 'chart_id'):
                available_chart_ids.add(chart.chart_id)
            elif isinstance(chart, dict):
                available_chart_ids.add(chart.get("chart_id", ""))
    
    # 检查引用的图表是否存在
    invalid_refs = [ref for ref in chart_refs if ref not in available_chart_ids]
    if invalid_refs:
        issues.append(f"引用了不存在的图表: {invalid_refs}")
        score -= len(invalid_refs) * 10
    
    # 检查是否有图表未被引用
    if available_chart_ids:
        unreferenced = available_chart_ids - set(chart_refs)
        if unreferenced:
            issues.append(f"有图表未被引用: {unreferenced}")
            score -= len(unreferenced) * 5
    
    score = max(0, min(100, score))
    passed = score >= 80
    
    return MetricScore(
        metric_name="chart_reference_accuracy",
        score=score,
        weight=0.15,
        severity=MetricSeverity.HIGH if not passed else MetricSeverity.LOW,
        passed=passed,
        threshold=80.0,
        details="图表引用准确" if passed else "发现图表引用问题",
        evidence=issues,
        suggestions=["确保所有图表都有对应的引用", "删除不存在的图表引用"]
    )


@register_metric("readability", weight=0.10, threshold=60.0)
def check_readability(report_content: str, state_data: Dict) -> MetricScore:
    """
    可读性检查
    
    检查：
    1. 段落长度是否合适（不超过300字）
    2. 是否有大段无格式文本
    3. 专业术语是否有解释
    4. 句子长度是否适中
    """
    issues = []
    score = 100.0
    
    # 检查段落长度
    paragraphs = report_content.split("\\n\\n")
    long_paragraphs = [p for p in paragraphs if len(p) > 300]
    if long_paragraphs:
        issues.append(f"有{len(long_paragraphs)}个段落超过300字，建议拆分")
        score -= len(long_paragraphs) * 3
    
    # 检查句子长度（简单版：按句号分割）
    sentences = re.split(r'[。！？]', report_content)
    long_sentences = [s for s in sentences if len(s) > 100]
    if len(long_sentences) > 5:
        issues.append(f"有{len(long_sentences)}个长句子，建议拆分")
        score -= 5
    
    # 检查是否有专业术语未解释（简单启发式）
    professional_terms = ["GMV", "DAU", "ROI", "LTV", "CPC", "CPA", "ARR", "MRR"]
    for term in professional_terms:
        if term in report_content:
            # 检查术语附近是否有解释
            term_positions = [m.start() for m in re.finditer(term, report_content)]
            for pos in term_positions:
                context = report_content[max(0, pos-50):min(len(report_content), pos+50)]
                if "（" not in context and "(" not in context and "称为" not in context:
                    issues.append(f"术语'{term}'可能缺少解释")
                    score -= 2
                    break
    
    score = max(0, min(100, score))
    passed = score >= 60
    
    return MetricScore(
        metric_name="readability",
        score=score,
        weight=0.10,
        severity=MetricSeverity.MEDIUM if not passed else MetricSeverity.LOW,
        passed=passed,
        threshold=60.0,
        details="可读性良好" if passed else "可读性有优化空间",
        evidence=issues,
        suggestions=["拆分长段落", "为专业术语添加解释"]
    )


@register_metric("insight_depth", weight=0.10, threshold=65.0)
def check_insight_depth(report_content: str, state_data: Dict) -> MetricScore:
    """
    洞察深度检查
    
    检查报告是否只是"罗列数据"，还是提供了有价值的洞察：
    1. 是否有"为什么"的分析（因果推断）
    2. 是否有"怎么办"的建议（行动导向）
    3. 是否有对比分析（同比、环比、对标）
    4. 是否有异常识别和解释
    """
    issues = []
    score = 100.0
    
    # 检查是否有因果分析
    causal_markers = ["因为", "由于", "导致", "原因", "归因于", "驱动力"]
    has_causal = any(m in report_content for m in causal_markers)
    if not has_causal:
        issues.append("缺少因果分析（为什么数据会这样？）")
        score -= 15
    
    # 检查是否有行动建议
    action_markers = ["建议", "措施", "行动", "优化", "改进", "策略"]
    has_action = any(m in report_content for m in action_markers)
    if not has_action:
        issues.append("缺少行动建议（怎么办？）")
        score -= 15
    
    # 检查是否有对比分析
    comparison_markers = ["同比", "环比", "对比", "vs", "相较", "相比"]
    has_comparison = any(m in report_content for m in comparison_markers)
    if not has_comparison:
        issues.append("缺少对比分析")
        score -= 10
    
    # 检查是否有异常识别
    anomaly_markers = ["异常", "波动", "突增", "骤降", "值得关注", "警惕"]
    has_anomaly = any(m in report_content for m in anomaly_markers)
    if not has_anomaly:
        issues.append("缺少异常识别")
        score -= 5
    
    score = max(0, min(100, score))
    passed = score >= 65
    
    return MetricScore(
        metric_name="insight_depth",
        score=score,
        weight=0.10,
        severity=MetricSeverity.MEDIUM if not passed else MetricSeverity.LOW,
        passed=passed,
        threshold=65.0,
        details="洞察深度足够" if passed else "洞察深度不足",
        evidence=issues,
        suggestions=["增加因果分析", "提供具体行动建议", "加入对比分析"]
    )


# ============================================
# 评估器类
# ============================================
class ReportEvaluator:
    """
    报告评估器
    
    这是Harness的核心组件，负责：
    1. 执行所有已注册的指标检查
    2. 计算加权总分
    3. 生成评估报告
    
    使用示例：
    -------
    evaluator = ReportEvaluator()
    result = evaluator.evaluate(report_content, state_data)
    print(f"综合得分: {result.overall_score}")
    print(f"等级: {result.grade}")
    """
    
    def __init__(self, custom_metrics: Optional[List[str]] = None):
        """
        初始化评估器
        
        Args:
            custom_metrics: 指定要运行的指标列表（None=运行所有）
        """
        self.metrics_to_run = custom_metrics or MetricRegistry.list_metrics()
    
    def evaluate(
        self,
        report_content: str,
        state_data: Dict,
        report_id: str = "unknown"
    ) -> EvaluationReport:
        """
        执行完整评估
        
        Args:
            report_content: 报告正文
            state_data: 原始状态数据（用于对比验证）
            report_id: 报告ID
            
        Returns:
            EvaluationReport对象
        """
        metrics_results = []
        total_weight = 0
        weighted_score = 0
        action_items = []
        
        # 执行每个指标
        for metric_name in self.metrics_to_run:
            metric_def = MetricRegistry.get_metric(metric_name)
            if not metric_def:
                continue
            
            try:
                result = metric_def["func"](report_content, state_data)
                metrics_results.append(result)
                
                # 计算加权分
                weighted_score += result.score * result.weight
                total_weight += result.weight
                
                # 收集必须修复的问题
                if result.severity == MetricSeverity.CRITICAL and not result.passed:
                    action_items.append(f"[严重] {result.metric_name}: {result.details}")
                
            except Exception as e:
                # 指标执行失败，记录但不阻断
                metrics_results.append(MetricScore(
                    metric_name=metric_name,
                    score=0,
                    weight=metric_def["weight"],
                    severity=MetricSeverity.CRITICAL,
                    passed=False,
                    threshold=metric_def["threshold"],
                    details=f"评估执行失败: {str(e)}",
                    evidence=[str(e)],
                    suggestions=["检查评估逻辑"]
                ))
        
        # 计算综合得分
        overall_score = weighted_score / total_weight if total_weight > 0 else 0
        
        # 确定等级
        grade = self._calculate_grade(overall_score)
        
        # 确定状态
        has_critical = any(
            m.severity == MetricSeverity.CRITICAL and not m.passed 
            for m in metrics_results
        )
        status = "failed" if has_critical else ("warning" if overall_score < 75 else "passed")
        
        # 生成总结
        summary = self._generate_summary(metrics_results, overall_score, grade)
        
        return EvaluationReport(
            report_id=report_id,
            evaluated_at=datetime.now().isoformat(),
            overall_score=overall_score,
            grade=grade,
            status=status,
            metrics=metrics_results,
            summary=summary,
            action_items=action_items,
            improvements=[s for m in metrics_results for s in m.suggestions]
        )
    
    def _calculate_grade(self, score: float) -> str:
        """根据分数计算等级"""
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
    
    def _generate_summary(
        self, 
        metrics: List[MetricScore], 
        overall: float,
        grade: str
    ) -> str:
        """生成评估总结"""
        passed_count = sum(1 for m in metrics if m.passed)
        total_count = len(metrics)
        
        summary = f"综合评分: {overall:.1f}/100 (等级: {grade})。"
        summary += f"共检查{total_count}个维度，{passed_count}个通过。"
        
        # 找出最弱的维度
        weakest = min(metrics, key=lambda m: m.score)
        summary += f"最需要改进的维度: {weakest.metric_name}({weakest.score:.1f}分)。"
        
        return summary


# ============================================
# LLM-as-Judge 高级评估
# ============================================
class LLMJudgeEvaluator:
    """
    LLM-as-Judge 评估器
    
    用另一个LLM（Judge）来评估报告质量。
    这是2026年最主流的评估方法，比规则匹配更灵活、更准确。
    
    为什么需要LLM-as-Judge？
    ------------------------
    规则匹配只能检查"硬指标"（如数字是否一致、结构是否完整），
    但无法评估"软指标"（如洞察是否有价值、措辞是否专业、逻辑是否通顺）。
    
    LLM-as-Judge就是让另一个"更聪明"的LLM来当评委，
    像人类专家一样阅读报告并打分。
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(
            model=model,
            temperature=0,
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
    
    def evaluate_with_llm(
        self,
        report_content: str,
        user_query: str,
        criteria: List[str] = None
    ) -> Dict[str, Any]:
        """
        使用LLM评估报告
        
        Args:
            report_content: 报告内容
            user_query: 用户原始需求
            criteria: 评估维度列表
            
        Returns:
            LLM的评估结果
        """
        criteria = criteria or [
            "数据准确性",
            "逻辑连贯性", 
            "洞察深度",
            "语言专业性",
            "用户满意度（是否回答了用户的问题）"
        ]
        
        prompt = f"""你是一位资深的数据分析总监，负责审核下属提交的数据分析报告。

## 用户原始需求
{user_query}

## 待评估报告
{report_content[:3000]}...（报告截断，仅评估前3000字）

## 评估维度
请对每个维度给出评分（0-100）和简要评价：
{chr(10).join(f"{i+1}. {c}" for i, c in enumerate(criteria))}

## 输出格式
请以JSON格式输出：
{{
    "overall_score": 85,
    "dimension_scores": {{
        "数据准确性": {{"score": 90, "comment": "..."}},
        ...
    }},
    "strengths": ["优点1", "优点2"],
    "weaknesses": ["不足1", "不足2"],
    "verdict": "通过/需修改/不通过"
}}
"""
        
        try:
            response = self.llm.invoke(prompt)
            # 尝试解析JSON
            content = response.content
            # 提取JSON部分
            json_match = re.search(r'\\{.*\\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {"error": "无法解析评估结果", "raw": content}
        except Exception as e:
            return {"error": str(e), "overall_score": 0}

print("✅ metrics.py 编写完成")
