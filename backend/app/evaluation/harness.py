
# 2. 编写 Harness 评估框架
"""
Harness 评估框架

这是企业级Agent系统的"自动化测试平台"。

小白理解：
想象你是一家软件开发公司，每次发布新版本前都要做测试：
- 单元测试：测试每个函数是否正确
- 集成测试：测试多个模块协作是否正常
- 回归测试：确保新功能没破坏旧功能

Harness就是给AI Agent系统做的"自动化测试平台"，
它定义了测试用例、执行测试、收集结果、生成报告。

为什么叫Harness？
----------------
"Harness"原意是"马具/安全带"，在软件工程中引申为"测试框架"。
它把被测系统"套"起来，控制输入、观察输出、判断对错。

企业价值：
---------
1. 每次修改Prompt/模型后，自动跑一遍测试，确保没退化
2. 对比不同配置的效果（A/B测试），选择最优方案
3. 建立质量基线，量化Agent系统的改进
4. CI/CD集成：代码提交前自动评估，不通过不能合并
"""

import os
import json
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..graph.builder import run_analysis_task
from ..graph.state import AgentState
from .metrics import ReportEvaluator, EvaluationReport, MetricRegistry


# ============================================
# 测试用例定义
# ============================================
@dataclass
class TestCase:
    """
    单个测试用例
    
    类比单元测试的test case：
    - input: 测试输入（用户Query）
    - expected: 期望输出（可选，用于有明确答案的测试）
    - metadata: 测试用例的元数据（分类、标签等）
    """
    case_id: str
    name: str
    input_query: str
    expected_keywords: List[str] = field(default_factory=list)
    expected_sections: List[str] = field(default_factory=list)
    min_score: float = 70.0
    tags: List[str] = field(default_factory=list)
    description: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TestResult:
    """单个测试用例的执行结果"""
    case_id: str
    case_name: str
    status: str  # passed/failed/error/timeout
    duration_ms: float
    final_state: Optional[Dict] = None
    evaluation_report: Optional[EvaluationReport] = None
    error_message: Optional[str] = None
    trace_log: List[str] = field(default_factory=list)


# ============================================
# 测试数据集
# ============================================
DEFAULT_TEST_SUITE = [
    TestCase(
        case_id="TC001",
        name="季度销售分析",
        input_query="帮我分析Q3各品类销售数据，生成年季度报告",
        expected_keywords=["销售", "同比", "环比", "品类"],
        expected_sections=["摘要", "分析", "建议"],
        min_score=75.0,
        tags=["quarterly", "sales", "standard"],
        description="标准季度销售分析场景"
    ),
    TestCase(
        case_id="TC002",
        name="月度运营报告",
        input_query="生成本月运营报告，包含流量、转化、用户行为分析",
        expected_keywords=["流量", "转化", "用户", "运营"],
        expected_sections=["数据", "分析"],
        min_score=70.0,
        tags=["monthly", "operation", "standard"],
        description="月度运营报告场景"
    ),
    TestCase(
        case_id="TC003",
        name="高管简短汇报",
        input_query="老板要看Q3业绩，帮我写一份简短的执行摘要",
        expected_keywords=["摘要", "核心", "业绩"],
        expected_sections=["摘要"],
        min_score=80.0,
        tags=["executive", "brief", "high-stakes"],
        description="高管简短汇报场景（要求更高）"
    ),
    TestCase(
        case_id="TC004",
        name="异常数据检测",
        input_query="分析本月销售数据，找出异常波动并解释原因",
        expected_keywords=["异常", "波动", "原因", "分析"],
        expected_sections=["分析", "原因", "建议"],
        min_score=75.0,
        tags=["anomaly", "analysis", "advanced"],
        description="异常检测与根因分析场景"
    ),
    TestCase(
        case_id="TC005",
        name="多维度对比分析",
        input_query="对比Q2和Q3的销售数据，分析各区域、各品类的变化",
        expected_keywords=["对比", "Q2", "Q3", "区域", "品类"],
        expected_sections=["对比", "分析"],
        min_score=75.0,
        tags=["comparison", "multi-dimension", "advanced"],
        description="多维度对比分析场景"
    ),
]


# ============================================
# Harness 主类
# ============================================
class AgentHarness:
    """
    Agent评估Harness
    
    核心能力：
    1. 批量执行测试用例
    2. 收集执行轨迹（每个Agent的输入输出）
    3. 多维度评估结果
    4. 生成评估报告和对比分析
    5. A/B测试支持
    
    使用示例：
    -------
    harness = AgentHarness()
    
    # 运行完整测试套件
    results = harness.run_suite(DEFAULT_TEST_SUITE)
    
    # 生成报告
    report = harness.generate_report(results)
    print(report.summary)
    
    # A/B测试：对比两个Prompt版本
    comparison = harness.ab_test(
        config_a={"prompt_version": "v1"},
        config_b={"prompt_version": "v2"},
        test_cases=DEFAULT_TEST_SUITE[:3]
    )
    """
    
    def __init__(
        self,
        max_workers: int = 3,
        timeout_seconds: int = 120,
        enable_trace: bool = True
    ):
        """
        初始化Harness
        
        Args:
            max_workers: 并行执行的测试用例数
            timeout_seconds: 单个用例超时时间
            enable_trace: 是否收集详细执行轨迹
        """
        self.max_workers = max_workers
        self.timeout_seconds = timeout_seconds
        self.enable_trace = enable_trace
        self.evaluator = ReportEvaluator()
        
        # 执行历史（用于对比分析）
        self.execution_history: List[Dict] = []
    
    def run_suite(
        self,
        test_cases: List[TestCase],
        config: Optional[Dict] = None
    ) -> List[TestResult]:
        """
        运行测试套件
        
        Args:
            test_cases: 测试用例列表
            config: 运行配置（如Prompt版本、模型选择等）
            
        Returns:
            每个用例的执行结果
        """
        print(f"\\n🧪 [Harness] 开始运行测试套件: {len(test_cases)}个用例")
        print(f"   配置: {config or '默认配置'}")
        print(f"   并行度: {self.max_workers}")
        
        results = []
        
        # 并行执行测试用例
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_case = {
                executor.submit(self._run_single_case, case, config): case
                for case in test_cases
            }
            
            for future in as_completed(future_to_case):
                case = future_to_case[future]
                try:
                    result = future.result(timeout=self.timeout_seconds)
                    results.append(result)
                    status_icon = "✅" if result.status == "passed" else "❌"
                    print(f"   {status_icon} {case.case_id}: {case.name} ({result.duration_ms:.0f}ms)")
                except Exception as e:
                    results.append(TestResult(
                        case_id=case.case_id,
                        case_name=case.name,
                        status="error",
                        duration_ms=0,
                        error_message=str(e)
                    ))
                    print(f"   💥 {case.case_id}: {case.name} - 错误: {e}")
        
        # 保存到历史
        self.execution_history.append({
            "timestamp": datetime.now().isoformat(),
            "config": config,
            "results": [self._result_to_dict(r) for r in results]
        })
        
        return results
    
    def _run_single_case(
        self,
        test_case: TestCase,
        config: Optional[Dict]
    ) -> TestResult:
        """
        执行单个测试用例
        
        完整流程：
        1. 调用run_analysis_task执行完整Agent流程
        2. 检查输出是否包含期望关键词
        3. 用ReportEvaluator评估报告质量
        4. 判断是否通过
        """
        start_time = time.time()
        trace_log = []
        
        try:
            # Step 1: 执行Agent任务
            trace_log.append(f"[{test_case.case_id}] 开始执行: {test_case.input_query}")
            
            final_state = run_analysis_task(
                user_query=test_case.input_query,
                thread_id=f"harness_{test_case.case_id}_{uuid.uuid4().hex[:8]}"
            )
            
            trace_log.append(f"[{test_case.case_id}] Agent执行完成")
            
            # Step 2: 检查报告是否存在
            report = final_state.get("report")
            if not report:
                duration = (time.time() - start_time) * 1000
                return TestResult(
                    case_id=test_case.case_id,
                    case_name=test_case.name,
                    status="failed",
                    duration_ms=duration,
                    error_message="报告未生成",
                    trace_log=trace_log
                )
            
            # Step 3: 检查期望关键词
            report_content = report.content if hasattr(report, 'content') else str(report)
            missing_keywords = [
                kw for kw in test_case.expected_keywords
                if kw not in report_content
            ]
            
            if missing_keywords:
                trace_log.append(f"缺少关键词: {missing_keywords}")
            
            # Step 4: 评估报告质量
            state_data = {
                "data": final_state.get("data", {}),
                "insights": final_state.get("insights", {}),
                "charts": final_state.get("charts", [])
            }
            
            eval_report = self.evaluator.evaluate(
                report_content=report_content,
                state_data=state_data,
                report_id=report.report_id if hasattr(report, 'report_id') else test_case.case_id
            )
            
            trace_log.append(f"评估完成: 综合得分{eval_report.overall_score:.1f}, 等级{eval_report.grade}")
            
            # Step 5: 判断是否通过
            duration = (time.time() - start_time) * 1000
            
            # 通过条件：
            # 1. 综合得分 >= min_score
            # 2. 没有CRITICAL级别的不通过项
            # 3. 没有缺少关键关键词（可选）
            has_critical_fail = any(
                m.severity.value == "critical" and not m.passed
                for m in eval_report.metrics
            )
            
            if eval_report.overall_score >= test_case.min_score and not has_critical_fail:
                status = "passed"
            else:
                status = "failed"
                if has_critical_fail:
                    trace_log.append("存在严重问题，未通过")
            
            return TestResult(
                case_id=test_case.case_id,
                case_name=test_case.name,
                status=status,
                duration_ms=duration,
                final_state={
                    "report_id": report.report_id if hasattr(report, 'report_id') else None,
                    "report_title": report.title if hasattr(report, 'title') else None,
                    "total_words": report.total_words if hasattr(report, 'total_words') else 0,
                    "total_charts": report.total_charts if hasattr(report, 'total_charts') else 0,
                },
                evaluation_report=eval_report,
                trace_log=trace_log
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            trace_log.append(f"执行异常: {str(e)}")
            return TestResult(
                case_id=test_case.case_id,
                case_name=test_case.name,
                status="error",
                duration_ms=duration,
                error_message=str(e),
                trace_log=trace_log
            )
    
    def ab_test(
        self,
        config_a: Dict[str, Any],
        config_b: Dict[str, Any],
        test_cases: List[TestCase],
        name: str = "A/B Test"
    ) -> Dict[str, Any]:
        """
        A/B测试：对比两组配置的效果
        
        企业场景：
        ---------
        你想知道"用GPT-4o写报告"和"用Claude 3.5写报告"哪个更好？
        或者"Prompt版本A"和"Prompt版本B"哪个效果更好？
        
        A/B测试就是：用同样的测试用例，跑两组配置，对比结果。
        
        Args:
            config_a: A组配置（如{"model": "gpt-4o", "prompt_version": "v1"}）
            config_b: B组配置（如{"model": "claude-3.5", "prompt_version": "v1"}）
            test_cases: 测试用例（两组用同样的）
            name: 测试名称
            
        Returns:
            对比分析报告
        """
        print(f"\\n🆚 [Harness] 开始A/B测试: {name}")
        print(f"   A组: {config_a}")
        print(f"   B组: {config_b}")
        
        # 运行A组
        print("\\n   运行A组...")
        results_a = self.run_suite(test_cases, config_a)
        
        # 运行B组
        print("\\n   运行B组...")
        results_b = self.run_suite(test_cases, config_b)
        
        # 对比分析
        comparison = self._compare_results(results_a, results_b, config_a, config_b)
        
        return {
            "test_name": name,
            "config_a": config_a,
            "config_b": config_b,
            "comparison": comparison,
            "winner": comparison["winner"],
            "recommendation": comparison["recommendation"]
        }
    
    def _compare_results(
        self,
        results_a: List[TestResult],
        results_b: List[TestResult],
        config_a: Dict,
        config_b: Dict
    ) -> Dict:
        """对比两组结果"""
        
        # 计算平均分
        scores_a = [r.evaluation_report.overall_score for r in results_a if r.evaluation_report]
        scores_b = [r.evaluation_report.overall_score for r in results_b if r.evaluation_report]
        
        avg_a = sum(scores_a) / len(scores_a) if scores_a else 0
        avg_b = sum(scores_b) / len(scores_b) if scores_b else 0
        
        # 计算通过率
        pass_a = sum(1 for r in results_a if r.status == "passed") / len(results_a) if results_a else 0
        pass_b = sum(1 for r in results_b if r.status == "passed") / len(results_b) if results_b else 0
        
        # 计算平均耗时
        duration_a = sum(r.duration_ms for r in results_a) / len(results_a) if results_a else 0
        duration_b = sum(r.duration_ms for r in results_b) / len(results_b) if results_b else 0
        
        # 判断胜负
        score_diff = avg_b - avg_a
        pass_diff = pass_b - pass_a
        
        if score_diff > 5 and pass_diff >= 0:
            winner = "B"
            recommendation = f"推荐采用B组配置。综合得分提升{score_diff:.1f}分，通过率持平或提升。"
        elif score_diff < -5 and pass_diff <= 0:
            winner = "A"
            recommendation = f"推荐采用A组配置。综合得分比B组高{abs(score_diff):.1f}分。"
        else:
            winner = "tie"
            recommendation = "两组配置效果接近，建议根据其他因素（如成本、延迟）选择。"
        
        return {
            "avg_score_a": round(avg_a, 2),
            "avg_score_b": round(avg_b, 2),
            "pass_rate_a": round(pass_a * 100, 1),
            "pass_rate_b": round(pass_b * 100, 1),
            "avg_duration_a_ms": round(duration_a, 0),
            "avg_duration_b_ms": round(duration_b, 0),
            "score_diff": round(score_diff, 2),
            "winner": winner,
            "recommendation": recommendation,
            "case_details": [
                {
                    "case_id": a.case_id,
                    "case_name": a.case_name,
                    "score_a": a.evaluation_report.overall_score if a.evaluation_report else 0,
                    "score_b": b.evaluation_report.overall_score if b.evaluation_report else 0,
                    "winner": "A" if (a.evaluation_report.overall_score if a.evaluation_report else 0) > 
                                   (b.evaluation_report.overall_score if b.evaluation_report else 0) else "B"
                }
                for a, b in zip(results_a, results_b)
            ]
        }
    
    def generate_report(self, results: List[TestResult]) -> Dict[str, Any]:
        """
        生成测试报告
        
        输出格式适合：
        - 前端Dashboard展示
        - CI/CD流水线判断
        - 邮件通知
        """
        total = len(results)
        passed = sum(1 for r in results if r.status == "passed")
        failed = sum(1 for r in results if r.status == "failed")
        errors = sum(1 for r in results if r.status == "error")
        
        scores = [r.evaluation_report.overall_score for r in results if r.evaluation_report]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # 按标签分组统计
        tag_stats = {}
        for result in results:
            # 这里简化处理，实际应从test_case获取tags
            pass
        
        return {
            "summary": {
                "total_cases": total,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
                "avg_score": round(avg_score, 2),
                "grade": self._score_to_grade(avg_score),
                "total_duration_ms": sum(r.duration_ms for r in results)
            },
            "details": [self._result_to_dict(r) for r in results],
            "generated_at": datetime.now().isoformat()
        }
    
    def _result_to_dict(self, result: TestResult) -> Dict:
        """转换TestResult为字典"""
        return {
            "case_id": result.case_id,
            "case_name": result.case_name,
            "status": result.status,
            "duration_ms": round(result.duration_ms, 0),
            "final_state": result.final_state,
            "evaluation": result.evaluation_report.to_dict() if result.evaluation_report else None,
            "error": result.error_message,
            "trace": result.trace_log
        }
    
    def _score_to_grade(self, score: float) -> str:
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"


# ============================================
# 便捷函数
# ============================================
def quick_evaluate(report_content: str, state_data: Dict) -> EvaluationReport:
    """
    快速评估单个报告
    
    使用示例：
    -------
    result = quick_evaluate(report.content, {"data": state.data})
    print(f"得分: {result.overall_score}, 等级: {result.grade}")
    if result.status != "passed":
        print("需要修复的问题:", result.action_items)
    """
    evaluator = ReportEvaluator()
    return evaluator.evaluate(report_content, state_data)


def run_regression_test(config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    运行回归测试（使用默认测试套件）
    
    使用示例：
    -------
    # 修改了Prompt后，跑回归测试确保没退化
    result = run_regression_test({"prompt_version": "v2"})
    if result["summary"]["pass_rate"] < 80:
        print("⚠️ 回归测试未通过，请检查修改！")
    """
    harness = AgentHarness()
    results = harness.run_suite(DEFAULT_TEST_SUITE, config)
    return harness.generate_report(results)


print("✅ harness.py 编写完成")
