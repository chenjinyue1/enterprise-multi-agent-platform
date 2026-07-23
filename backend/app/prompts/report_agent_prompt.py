
# 4. 编写 Report Agent Prompt 模板
"""
Report Agent 提示词模板

为什么Prompt要单独管理？
-------------------------
企业级项目中，Prompt是"业务逻辑"的一部分，经常需要调整：
- 销售部希望报告突出"增长数据"
- 财务部希望报告突出"成本分析"
- 管理层希望报告简短（1页纸）

如果Prompt硬编码在Agent代码里，每次调整都要改代码+重新部署。
单独管理后，运营人员可以直接改Prompt文件，无需动代码。

这就是Prompt Engineering的企业级实践。
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage


# ============================================
# 系统提示词：定义Report Agent的角色和能力
# ============================================
REPORT_AGENT_SYSTEM_PROMPT = """你是企业智能数据分析平台的「报告撰写专家」。

## 你的职责
将Data Agent查询的数据、Analysis Agent的分析洞察、Viz Agent生成的图表，
整合成一份结构清晰、专业规范、可直接用于汇报的数据分析报告。

## 你的核心能力
1. **RAG增强写作**：你会先检索历史报告模板，参考其结构和措辞风格
2. **数据叙事**：将冰冷的数据转化为有逻辑的故事线
3. **图表嵌入**：在报告中合适的位置引用图表，并配上解读文字
4. **多格式输出**：支持Markdown、HTML、Word三种格式

## 报告质量标准
- 结构完整：执行摘要 → 数据分析 → 图表展示 → 洞察建议 → 附录
- 数据准确：所有数字必须与查询结果一致，不得编造
- 洞察深刻：不只罗列数据，要给出"为什么"和"怎么办"
- 语言专业：使用企业级商务用语，避免口语化

## 图表引用规范
当报告中需要引用图表时，使用以下格式：
```
![图表标题](chart://{chart_id})
```
其中chart_id是Viz Agent生成的图表唯一标识。

## 重要约束
- 绝不编造数据，所有数字必须来自State.data或State.insights
- 如果数据不足，明确标注"数据缺失"而非猜测
- 报告长度控制在2000-5000字（根据复杂度调整）
- 使用中文撰写，专业术语保留英文缩写（如GMV、DAU、ROI）
"""


# ============================================
# 报告生成主Prompt（带RAG上下文）
# ============================================
REPORT_GENERATION_PROMPT = """# 任务：生成数据分析报告

## 用户原始需求
{user_query}

## 检索到的历史报告模板（参考结构和风格）
{rag_context}

## 数据查询结果（来自Data Agent）
```json
{data_results}
```

## 分析洞察（来自Analysis Agent）
```json
{analysis_insights}
```

## 可用图表（来自Viz Agent）
```json
{charts}
```

## 报告要求
- 报告类型：{report_type}
- 目标受众：{audience}
- 篇幅要求：{length_requirement}
- 特殊要求：{special_requirements}

请生成完整的报告内容（Markdown格式）。报告结构：

1. **执行摘要**（200字以内，高管只看这部分）
2. **背景与目标**（为什么做这次分析）
3. **数据概览**（关键指标总览表格）
4. **详细分析**（分维度深入分析，每个维度配图表）
5. **关键发现**（3-5条核心洞察，用加粗标出）
6. **行动建议**（可落地的改进措施，带优先级）
7. **附录**（数据来源说明、术语表）

注意：
- 图表引用格式：`![描述](chart://chart_id)`
- 数据表格使用Markdown表格语法
- 关键数字用**加粗**标出
"""


# ============================================
# 报告质量自检Prompt
# ============================================
REPORT_QUALITY_CHECK_PROMPT = """# 报告质量检查

请对以下报告进行质量检查，输出检查报告：

## 待检查报告
{report_content}

## 原始数据
{source_data}

## 检查维度
1. **数据一致性**：报告中的数字是否与原始数据完全一致？
2. **逻辑完整性**：报告结构是否完整？是否有遗漏的重要分析维度？
3. **洞察深度**：是否只罗列数据，还是给出了有价值的洞察？
4. **图表匹配**：图表引用是否正确？图表与文字描述是否匹配？
5. ** hallucination（幻觉）**：是否有编造的数据或不存在的信息？

## 输出格式
```json
{{
    "passed": true/false,
    "score": 0-100,
    "issues": [
        {{
            "severity": "error/warning/info",
            "category": "data/logic/insight/chart/hallucination",
            "description": "问题描述",
            "suggestion": "修改建议"
        }}
    ],
    "improved_report": "如果未通过，输出修改后的报告；如果通过，此项为空"
}}
```
"""


# ============================================
# 报告模板引擎：Jinja2模板
# ============================================
REPORT_JINJA_TEMPLATES = {
    "quarterly_sales": """# {{ title }}

> **报告周期**：{{ period }}  
> **生成时间**：{{ generated_at }}  
> **数据来源**：{{ data_source }}

---

## 一、执行摘要

{{ summary }}

**核心指标速览**：

| 指标 | 数值 | 同比 | 环比 |
|------|------|------|------|
{%- for metric in key_metrics %}
| {{ metric.name }} | {{ metric.value }} | {{ metric.yoy }} | {{ metric.mom }} |
{%- endfor %}

---

## 二、详细分析

{{ detailed_analysis }}

---

## 三、图表展示

{%- for chart in charts %}
### {{ chart.title }}

{{ chart.description }}

![{{ chart.title }}](chart://{{ chart.id }})

{%- endfor %}

---

## 四、关键发现与建议

{{ insights }}

---

## 五、附录

**数据口径说明**：
{{ data_definitions }}

**术语表**：
{{ glossary }}
""",

    "monthly_operation": """# {{ title }}

> **报告月份**：{{ month }}  
> **生成时间**：{{ generated_at }}

---

## 一、本月核心数据

{{ monthly_summary }}

---

## 二、分项分析

{{ breakdown_analysis }}

---

## 三、问题与改进

{{ issues_and_actions }}
""",

    "executive_summary": """# {{ title }}

> **汇报对象**：{{ audience }}  
> **机密等级**：{{ confidentiality }}

---

## 核心结论（1分钟版）

{{ one_minute_summary }}

---

## 关键数据

{{ key_data }}

---

## 需要决策的事项

{{ decisions_needed }}
"""
}


# ============================================
# 构建LangChain Prompt对象
# ============================================
def build_report_generation_prompt() -> ChatPromptTemplate:
    """
    构建报告生成Prompt
    
    使用LangChain的ChatPromptTemplate，支持：
    - 系统消息：定义AI角色
    - 人类消息：输入具体任务
    - MessagesPlaceholder：支持多轮对话历史
    """
    return ChatPromptTemplate.from_messages([
        SystemMessage(content=REPORT_AGENT_SYSTEM_PROMPT),
        ("human", REPORT_GENERATION_PROMPT)
    ])


def build_quality_check_prompt() -> ChatPromptTemplate:
    """构建质量检查Prompt"""
    return ChatPromptTemplate.from_messages([
        SystemMessage(content="你是报告质量审核专家，严格检查数据准确性和逻辑完整性。"),
        ("human", REPORT_QUALITY_CHECK_PROMPT)
    ])


print("✅ report_agent_prompt.py 编写完成")
