
# 🔍 板块七：Review Agent + Harness 评估体系

> **文档编号**: 07  
> **前置板块**: 06-ReportAgent与RAG报告生成  
> **核心目标**: 建立多维度质量评估体系，实现Agent系统的自动化测试、A/B对比和持续优化闭环

---

## 一、Review Agent + Harness 要解决什么问题？

### 1.1 业务场景：AI系统的"质量危机"

前面的板块搭建了一个完整的多智能体平台：
- Data Agent查数据 → Analysis Agent做分析 → Viz Agent画图表 → Report Agent写报告

**但企业上线前必须回答一个问题：这个系统生成的报告，质量够吗？**

**真实痛点**：

| 痛点 | 具体表现 | 风险等级 |
|------|---------|---------|
| **数据错误** | 报告中的数字和数据库不一致 | 🔴 致命 |
| **AI幻觉** | 报告编造了不存在的数据或结论 | 🔴 致命 |
| **逻辑矛盾** | 数据说"下降"，结论说"增长" | 🟠 严重 |
| **结构缺失** | 高管汇报缺少"执行摘要" | 🟡 中等 |
| **质量波动** | 今天生成的报告90分，明天60分 | 🟡 中等 |
| **无法量化** | "感觉报告还行"→无法衡量改进 | 🟢 轻微 |

**如果没有评估体系**：
- 你改了Prompt，不知道效果变好了还是变差了
- 你换了模型，不知道新模型更适合还是更不适合
- 用户投诉报告质量差，但你不知道具体问题在哪
- 系统上线后，质量持续退化却无人察觉

### 1.2 我们的解决方案

**三层质量保障体系**：

```
┌─────────────────────────────────────────────────────────────┐
│  第一层：Report Agent 自检（生成过程中）                         │
│  • 快速检查：数据一致性、图表引用、结构完整性                     │
│  • 特点：速度快、成本低、覆盖基础问题                            │
├─────────────────────────────────────────────────────────────┤
│  第二层：Review Agent 审核（生成后）                             │
│  • 深度审核：自动化指标 + LLM-as-Judge深度判断                   │
│  • 特点：全面、严格、可追溯                                      │
├─────────────────────────────────────────────────────────────┤
│  第三层：Harness 回归测试（持续集成）                           │
│  • 批量测试：用标准测试套件定期跑一遍                            │
│  • A/B对比：对比不同配置的效果                                   │
│  • 特点：系统化、可量化、可对比                                  │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 为什么需要专门的评估体系？

**传统软件测试 vs AI Agent测试**：

| 维度 | 传统软件 | AI Agent |
|------|---------|---------|
| 输出确定性 | 相同输入 → 相同输出 | 相同输入 → 可能不同输出 |
| 正确性判断 | 结果 == 预期值 | 结果"好不好"是主观的 |
| 测试范围 | 功能是否工作 | 质量是否达标（多维度） |
| 回归风险 | 改A功能不影响B功能 | 改Prompt可能影响所有输出 |
| 评估方法 | 单元测试断言 | LLM-as-Judge + 规则匹配 |

**企业级AI系统必须有评估体系，否则就是"盲人骑瞎马"。**

---

## 二、代码实战

### 2.1 评估指标层

#### 2.1.1 `backend/app/evaluation/metrics.py` —— 多维度评估指标

**这个文件做什么？**

定义了6个核心评估指标，每个指标负责检查报告的一个维度：

| 指标名称 | 权重 | 阈值 | 检查内容 | 严重级别 |
|---------|------|------|---------|---------|
| **data_accuracy** | 0.25 | 85 | 报告数字是否与原始数据一致 | CRITICAL |
| **hallucination_check** | 0.25 | 90 | 是否有编造的信息 | CRITICAL |
| **structure_completeness** | 0.15 | 70 | 是否包含必要章节 | HIGH |
| **chart_reference_accuracy** | 0.15 | 80 | 图表引用是否正确 | HIGH |
| **readability** | 0.10 | 60 | 可读性（段落长度、术语解释） | MEDIUM |
| **insight_depth** | 0.10 | 65 | 是否有因果分析、行动建议 | MEDIUM |

**装饰器注册模式**：

```python
@register_metric("data_accuracy", weight=0.25, threshold=85.0)
def check_data_accuracy(report_content: str, state_data: Dict) -> MetricScore:
    # 检查逻辑...
    return MetricScore(score=95, passed=True, ...)
```

**为什么用装饰器注册？**

企业级评估需要"可插拔"的指标：
- 今天评估6个维度，明天可能需要加第7个（如"合规性检查"）
- 不同业务线关注不同指标（销售部关注"洞察深度"，财务部关注"数据准确性"）
- 用注册表可以动态加载指标，不用改核心代码

**使用示例**：

```python
from app.evaluation.metrics import ReportEvaluator, MetricRegistry

# 查看所有已注册指标
print(MetricRegistry.list_metrics())
# ['data_accuracy', 'hallucination_check', 'structure_completeness', ...]

# 执行完整评估
evaluator = ReportEvaluator()
result = evaluator.evaluate(
    report_content=report.content,
    state_data={"data": state.data, "charts": state.charts},
    report_id=report.report_id
)

print(f"综合得分: {result.overall_score}")  # 87.5
print(f"等级: {result.grade}")              # B
print(f"状态: {result.status}")             # passed

# 查看各维度评分
for metric in result.metrics:
    print(f"{metric.metric_name}: {metric.score}/100 {'✅' if metric.passed else '❌'}")
```

---

#### 2.1.2 `LLM-as-Judge` 高级评估

**什么是LLM-as-Judge？**

用另一个LLM（"评委"）来评估报告质量。

**为什么需要？**

规则匹配只能检查"硬指标"（数字是否一致、结构是否完整），
但无法评估"软指标"（洞察是否有价值、措辞是否专业、逻辑是否通顺）。

LLM-as-Judge就是让另一个"更聪明"的LLM来当评委，
像人类专家一样阅读报告并打分。

**使用示例**：

```python
from app.evaluation.metrics import LLMJudgeEvaluator

judge = LLMJudgeEvaluator(model="gpt-4o-mini")
result = judge.evaluate_with_llm(
    report_content=report.content,
    user_query="帮我分析Q3销售数据",
    criteria=["数据准确性", "逻辑连贯性", "洞察深度", "语言专业性"]
)

print(result["overall_score"])  # 88
print(result["verdict"])      # "通过"
```

---

### 2.2 Harness 评估框架

#### 2.2.1 `backend/app/evaluation/harness.py` —— 自动化测试平台

**这个文件做什么？**

这是企业级Agent系统的"自动化测试平台"，核心能力：

1. **批量执行测试用例**：一次跑5-10个场景，覆盖不同业务场景
2. **收集执行轨迹**：记录每个Agent的输入输出、执行时间
3. **多维度评估结果**：对每个输出执行6个指标检查
4. **A/B对比测试**：对比两组配置的效果
5. **生成测试报告**：适合CI/CD流水线判断

**测试用例设计**：

```python
DEFAULT_TEST_SUITE = [
    TestCase(
        case_id="TC001",
        name="季度销售分析",
        input_query="帮我分析Q3各品类销售数据，生成年季度报告",
        expected_keywords=["销售", "同比", "环比", "品类"],
        min_score=75.0,
        tags=["quarterly", "sales", "standard"]
    ),
    TestCase(
        case_id="TC003",
        name="高管简短汇报",
        input_query="老板要看Q3业绩，帮我写一份简短的执行摘要",
        expected_keywords=["摘要", "核心", "业绩"],
        min_score=80.0,
        tags=["executive", "brief", "high-stakes"]
    ),
    # ... 更多用例
]
```

**为什么需要测试套件？**

- **覆盖不同场景**：季度报告、月度报告、高管汇报、异常分析...
- **防止回归**：改了Prompt后，确保所有场景都没退化
- **量化改进**：从"感觉变好了"到"平均分从75提升到82"

**使用示例**：

```python
from app.evaluation.harness import AgentHarness, DEFAULT_TEST_SUITE

# 初始化Harness
harness = AgentHarness(max_workers=3, timeout_seconds=120)

# 运行完整测试套件
results = harness.run_suite(DEFAULT_TEST_SUITE)

# 生成报告
report = harness.generate_report(results)
print(f"通过率: {report['summary']['pass_rate']}%")
print(f"平均分: {report['summary']['avg_score']}")
print(f"等级: {report['summary']['grade']}")
```

---

#### 2.2.2 A/B 测试

**企业场景**：

你想知道"用GPT-4o写报告"和"用Claude 3.5写报告"哪个更好？
或者"Prompt版本A"和"Prompt版本B"哪个效果更好？

A/B测试就是：用同样的测试用例，跑两组配置，对比结果。

**使用示例**：

```python
# A/B测试：对比两个模型
comparison = harness.ab_test(
    config_a={"model": "gpt-4o", "prompt_version": "v1"},
    config_b={"model": "claude-3.5-sonnet", "prompt_version": "v1"},
    test_cases=DEFAULT_TEST_SUITE[:3],
    name="GPT-4o vs Claude-3.5"
)

print(f"A组平均分: {comparison['comparison']['avg_score_a']}")
print(f"B组平均分: {comparison['comparison']['avg_score_b']}")
print(f"胜出方: {comparison['winner']}")
print(f"建议: {comparison['recommendation']}")
```

**输出示例**：
```
A组平均分: 82.5
B组平均分: 79.3
胜出方: A
建议: 推荐采用A组配置。综合得分提升3.2分，通过率持平。
```

---

### 2.3 Review Agent 核心层

#### 2.3.1 `backend/app/agents/review_agent.py` —— 质量审核Agent

**Review Agent vs Report Agent自检**：

| 维度 | Report Agent自检 | Review Agent审核 |
|------|---------------|----------------|
| 角色 | 作者自己校对 | 专业编辑审稿 |
| 深度 | 快速、轻量 | 全面、严格 |
| 方法 | 规则匹配 | 规则 + LLM-as-Judge |
| 独立性 | 自己检查自己 | 独立第三方 |
| 结果 | 修正小问题 | 裁决是否通过 |

**Review Agent 工作流程**：

```
┌─────────────┐
│ 自动化评估   │  ← 运行6个指标检查，快速量化评分
└──────┬──────┘
       ↓
┌─────────────┐
│ LLM深度审核 │  ← GPT-4o做逻辑判断、业务合理性评估
└──────┬──────┘
       ↓
┌─────────────┐
│  综合裁决   │  ← 结合两者，给出最终裁决
└──────┬──────┘
       ↓
┌─────────────┐
│  反馈生成   │  ← 生成修改建议，反馈给Report Agent
└─────────────┘
```

**审核等级标准**：

| 等级 | 分数 | 状态 | 处理方式 |
|------|------|------|---------|
| A | 90-100 | approved | 直接发布 |
| B | 80-89 | approved | 建议微调后发布 |
| C | 70-79 | needs_revision | 必须修改后重新审核 |
| D | 60-69 | rejected | 严重问题，需要重写 |
| F | <60 | rejected | 不合格，不能发布 |

**裁决规则**：
1. 自动化评估有CRITICAL级别不通过 → 直接不通过
2. LLM审核发现数据错误或幻觉 → 直接不通过
3. 综合得分 = 自动化得分 * 0.6 + LLM得分 * 0.4
4. 根据综合得分确定等级和状态

**使用示例**：

```python
from app.agents.review_agent import ReviewAgent, review_report_direct

# 审核报告
result = review_report_direct(report, state)

print(f"审核等级: {result.overall_grade}")      # B
print(f"审核得分: {result.overall_score}")      # 85.5
print(f"审核状态: {result.status.value}")       # approved

if result.status.value == "needs_revision":
    print("需要修改的问题:")
    for issue in result.issues:
        print(f"  - [{issue.severity}] {issue.description}")
        print(f"    建议: {issue.suggestion}")
```

---

### 2.4 图编排层更新

#### 2.4.1 完整图结构（板块七）

```
START → Supervisor → data_agent → Supervisor → analysis_agent → Supervisor
      → viz_agent → Supervisor → report_agent → Supervisor → review_agent → Supervisor
      → [审核通过?] → FINISH
      → [需修改?] → report_agent（重新生成）
      → [敏感数据?] → human_review
```

**路由逻辑更新**：

```python
def supervisor_router(state: AgentState):
    # ... 前面的检查 ...
    
    # 检查审核结果
    review_result = state.get("review_result")
    if review_result:
        status = review_result.status
        
        if status == "approved":
            return "finish"           # 审核通过，任务完成
        elif status == "needs_revision":
            return "report_agent"     # 需要修改，退回重新生成
        elif status == "rejected":
            return "finish"           # 不通过，结束并返回错误
    
    # 按流水线顺序路由
    if not state.get("data"): return "data_agent"
    if not state.get("insights"): return "analysis_agent"
    if not state.get("charts"): return "viz_agent"
    if not state.get("report"): return "report_agent"
    if not state.get("review_result"): return "review_agent"  # ⭐
    
    return "finish"
```

---

## 三、完整执行流程演示

### 3.1 场景：用户请求生成Q3销售分析报告（含审核）

```python
from app.graph.builder import run_analysis_task

# 发起任务
result = run_analysis_task(
    user_query="帮我分析Q3各品类销售数据，生成季度报告，给老板汇报用"
)

# 查看审核结果
review = result.get("review_result")
if review:
    print(f"审核等级: {review.overall_grade}")      # B
    print(f"审核得分: {review.overall_score}")      # 86.5
    print(f"审核状态: {review.status}")             # approved
    print(f"裁决: {review.final_verdict}")
    
    if review.issues:
        print(f"\\n发现 {len(review.issues)} 个问题:")
        for issue in review.issues:
            print(f"  [{issue.severity}] {issue.description}")

# 查看报告
report = result.get("report")
if report:
    print(f"\\n报告标题: {report.title}")
    print(f"报告字数: {report.total_words}")
    print(f"图表数量: {report.total_charts}")
```

**执行轨迹**：

```
[Supervisor] 分析需求 → 需要查数据+分析+图表+报告+审核
    ↓
[Data Agent] 执行SQL → 返回Q3销售数据
    ↓
[Analysis Agent] 统计分析 → 返回洞察
    ↓
[Viz Agent] 生成图表 → 返回3个图表配置
    ↓
[Report Agent] 生成报告 → 参考RAG模板，填入数据
    ↓
[Review Agent]
  ├─ 自动化评估 → 综合得分82.5（B级）
  ├─ LLM深度审核 → 得分90.5（A级）
  ├─ 综合裁决 → 86.5分，B级，approved
  └─ 发现2个minor问题（段落过长、术语未解释）
    ↓
[Supervisor] 审核通过 → 任务完成！
    ↓
[FINISH] 返回完整State
```

---

## 四、企业级部署要点

### 4.1 CI/CD 集成

```yaml
# .github/workflows/agent-eval.yml
name: Agent Evaluation

on: [pull_request]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run Harness Test Suite
        run: |
          cd backend
          python -m pytest tests/test_harness.py -v
      
      - name: Check Pass Rate
        run: |
          PASS_RATE=$(python -c "from app.evaluation.harness import run_regression_test; 
                                  r=run_regression_test(); 
                                  print(r['summary']['pass_rate'])")
          if (( $(echo "$PASS_RATE < 80" | bc -l) )); then
            echo "❌ 回归测试通过率低于80%，阻止合并"
            exit 1
          fi
          echo "✅ 回归测试通过，通过率: $PASS_RATE%"
```

### 4.2 持续优化闭环

```
评估结果 → 发现问题 → 定位原因 → 优化Prompt/模型 → 重新评估 → 验证改进
    ↑                                                                    ↓
    └──────────────────────────────────────────────────────────────────────┘
```

**优化方向**：

| 问题类型 | 优化手段 | 预期效果 |
|---------|---------|---------|
| 数据准确性低 | 增强数据校验逻辑 | 准确率提升20% |
| 幻觉率高 | 增强RAG上下文、降低temperature | 幻觉率降低30% |
| 洞察深度不足 | 优化Report Agent Prompt | 洞察得分提升15% |
| 可读性差 | 增加段落拆分逻辑 | 可读性得分提升10% |

---

## 五、核心知识点总结

### 5.1 三层质量保障体系

| 层级 | 组件 | 方法 | 覆盖问题 |
|------|------|------|---------|
| 第一层 | Report Agent自检 | 规则匹配 | 数据一致性、图表引用 |
| 第二层 | Review Agent审核 | 规则 + LLM-as-Judge | 逻辑一致性、业务合理性 |
| 第三层 | Harness回归测试 | 批量测试 + A/B对比 | 回归检测、配置优化 |

### 5.2 六维度评估指标

| 指标 | 权重 | 阈值 | 检查方法 |
|------|------|------|---------|
| data_accuracy | 25% | 85 | 数字提取+对比 |
| hallucination_check | 25% | 90 | 规则匹配+LLM判断 |
| structure_completeness | 15% | 70 | 章节关键词匹配 |
| chart_reference_accuracy | 15% | 80 | chart_id验证 |
| readability | 10% | 60 | 段落长度+术语检查 |
| insight_depth | 10% | 65 | 因果/建议/对比关键词 |

### 5.3 A/B测试价值

- **模型选型**：GPT-4o vs Claude-3.5，用数据说话
- **Prompt优化**：版本A vs 版本B，量化改进效果
- **成本权衡**：质量 vs 成本，找到最优平衡点

### 5.4 当前完整图结构

```
START → Supervisor → data_agent → Supervisor → analysis_agent → Supervisor
      → viz_agent → Supervisor → report_agent → Supervisor → review_agent → Supervisor
      → [审核通过] → FINISH
      → [需修改] → report_agent（循环）
```

---

## 六、本板块简历新增内容

在板块一至六的基础上，现在可以加上：

```markdown
• 多维度质量评估体系：设计6维度评估指标（数据准确性、幻觉检测、结构完整性、
  图表引用、可读性、洞察深度），权重化评分+阈值判定，实现报告质量量化管理

• LLM-as-Judge深度审核：引入GPT-4o作为"智能评委"，评估逻辑一致性、
  业务合理性、用户体验等"软指标"，与规则化评估互补，审核覆盖率100%

• Harness自动化测试框架：构建5场景标准测试套件，支持并行执行、
  执行轨迹收集、批量评估，CI/CD集成实现"代码提交即测试"

• A/B测试与持续优化：实现Prompt版本/模型配置的A/B对比测试，
  量化评估不同方案效果，建立"评估→发现→优化→验证"持续改进闭环

• 质量门禁机制：审核等级A/B直接发布，C级退回修改，D/F级拒绝发布，
  确保上线报告质量稳定可控，企业级零事故交付
```

---

## 七、你现在可以做什么？

### 步骤1：查看新增代码

```bash
# 重点看：
# 1. backend/app/evaluation/metrics.py      ← 6维度评估指标
# 2. backend/app/evaluation/harness.py      ← 自动化测试框架
# 3. backend/app/agents/review_agent.py     ← Review Agent核心
# 4. backend/app/prompts/review_agent_prompt.py  ← 审核Prompt
# 5. backend/app/graph/state.py             ← State更新（ReviewResultSpec）
# 6. backend/app/graph/builder.py           ← 图编排更新
# 7. docs/07-ReviewAgent与Harness评估体系.md  ← 本板块完整文档
```

### 步骤2：理解评估流程

```python
# 打开 metrics.py，看：
├── @register_metric装饰器        ← 指标注册机制
├── check_data_accuracy()         ← 数据准确性检查
├── check_hallucination()         ← 幻觉检测
└── ReportEvaluator.evaluate()    ← 综合评估器

# 打开 harness.py，看：
├── TestCase                      ← 测试用例定义
├── AgentHarness.run_suite()      ← 批量测试执行
├── AgentHarness.ab_test()        ← A/B对比测试
└── generate_report()             ← 测试报告生成

# 打开 review_agent.py，看：
├── _auto_evaluate()              ← 自动化评估
├── _llm_review()                 ← LLM深度审核
├── _adjudicate()                 ← 综合裁决
└── ReviewResult                  ← 审核结果模型
```

### 步骤3：测试评估功能

```python
# 快速评估单个报告
from app.evaluation.harness import quick_evaluate

result = quick_evaluate(report.content, {"data": state.data})
print(f"得分: {result.overall_score}, 等级: {result.grade}")

# 运行回归测试
from app.evaluation.harness import run_regression_test
report = run_regression_test()
print(f"通过率: {report['summary']['pass_rate']}%")

# A/B测试
from app.evaluation.harness import AgentHarness, DEFAULT_TEST_SUITE
harness = AgentHarness()
comparison = harness.ab_test(
    config_a={"model": "gpt-4o"},
    config_b={"model": "gpt-4o-mini"},
    test_cases=DEFAULT_TEST_SUITE[:2]
)
print(f"胜出: {comparison['winner']}")
```

---

## 八、项目全景回顾

经过板块一至七，我们搭建了一个完整的企业级多智能体数据分析平台：

```
┌─────────────────────────────────────────────────────────────────┐
│                     企业智能数据分析多智能体平台                    │
├─────────────────────────────────────────────────────────────────┤
│  板块一：项目架构设计    → 技术选型、目录结构、环境搭建            │
│  板块二：State状态机     → 共享状态、数据流转、持久化             │
│  板块三：Data Agent      → SQL查询、数据获取                      │
│  板块四：Analysis Agent  → 统计分析、洞察提取                     │
│  板块五：Viz Agent       → 图表生成、ECharts配置                  │
│  板块六：Report Agent    → RAG增强、报告生成、质量自检             │
│  板块七：Review Agent    → 多维度评估、Harness测试、A/B对比       │
├─────────────────────────────────────────────────────────────────┤
│  技术栈：FastAPI + LangChain + LangGraph + MCP + ChromaDB       │
│          + Redis + MySQL + React + Vite + TypeScript             │
└─────────────────────────────────────────────────────────────────┘
```

**整个链路运行流程**：

```
用户提问 → Supervisor拆解任务 → Data Agent查数据 → Analysis Agent做分析
→ Viz Agent画图表 → Report Agent写报告（RAG增强）→ Review Agent质量审核
→ 通过 → 返回报告
→ 不通过 → 退回修改 → 重新生成 → 再审核
```

---

## 九、下板块预告

### 板块八：前端集成 + 部署上线

**核心内容**：
- 前端Chat UI对接后端API
- WebSocket实时推送Agent执行进度
- 报告预览与导出（Markdown/HTML/PDF）
- Docker容器化部署
- 生产环境配置（MySQL/Redis/ChromaDB）

**你将实现**：
- `frontend/src/components/ChatWindow.tsx`
- `frontend/src/components/AgentStatus.tsx`
- `frontend/src/components/ReportViewer.tsx`
- `docker-compose.prod.yml`
- `backend/Dockerfile`

**确认理解板块七后，回复"继续"或提出疑问，我们进入板块八（最终板块）！** 🚀


print(f"✅ 板块七文档编写完成！")
print(f"   文件大小: {len(doc_content)} 字符")
