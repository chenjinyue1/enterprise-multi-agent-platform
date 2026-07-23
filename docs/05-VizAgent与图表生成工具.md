
import os

# 板块五：Viz Agent + 图表生成工具

> **文档编号**: 05  
> **前置板块**: 04-AnalysisAgent与Python计算工具  
> **核心目标**: 让 Viz Agent 能根据数据生成图表配置，前端据此渲染可视化

---

## 📖 目录

1. [Viz Agent 要解决什么问题？](#一viz-agent-要解决什么问题)
2. [为什么需要专门的 Viz Agent？](#二为什么需要专门的-viz-agent)
3. [图表类型选择策略](#三图表类型选择策略)
4. [图表工具（Chart Tool）](#四图表工具chart-tool)
5. [Viz Agent](#五viz-agent)
6. [图构建器更新](#六图构建器更新)
7. [本板块简历价值](#七本板块简历价值)
8. [下板块预告](#八下板块预告)

---

## 一、Viz Agent 要解决什么问题？

### 1.1 业务场景

Data Agent 查到了数据，Analysis Agent 做了分析，但用户最终看到的是**文字和数字**。对于业务人员来说，一张图表比十行文字更直观。

**Viz Agent 的职责**：把数据 → 图表配置 → 前端渲染

### 1.2 为什么需要专门的 Viz Agent？

**直接让 LLM 生成图表的问题**：
- LLM 不知道前端用什么图表库（ECharts？Plotly？D3？）
- LLM 生成的图表配置可能语法错误
- 图表类型选择需要专业知识（什么数据适合什么图？）

**我们的方案**：
- Viz Agent 专门负责"数据 → 图表配置"的转换
- 使用 Python 工具生成标准化的图表数据
- 输出 `ChartSpec` 结构化配置，前端统一解析

---

## 二、为什么需要专门的 Viz Agent？

### 2.1 可视化是独立的专业领域

| 维度 | Data Agent | Analysis Agent | Viz Agent |
|------|-----------|----------------|-----------|
| **核心能力** | 数据库查询 | 统计分析 | 可视化设计 |
| **输出** | 原始数据 | 分析洞察 | 图表配置 |
| **工具** | SQL | Python 计算 | 图表生成 |
| **专业知识** | SQL 语法 | 统计学 | 图表设计原则 |

### 2.2 图表设计原则

```
好的图表 = 正确的图表类型 + 清晰的数据映射 + 美观的样式
```

| 原则 | 说明 | 示例 |
|------|------|------|
| **正确性** | 图表类型匹配数据特征 | 时间趋势用折线图，分类对比用柱状图 |
| **清晰性** | 数据映射明确 | X轴、Y轴、系列字段清晰标注 |
| **美观性** | 配色协调、标签清晰 | 企业品牌色、关键数据点加标签 |
| **简洁性** | 不堆砌图表 | 一个图表传达一个核心信息 |

---

## 三、图表类型选择策略

### 3.1 洞察类型 → 图表类型映射

| 洞察类型 | 推荐图表 | 原因 |
|---------|---------|------|
| trend（趋势） | line 折线图 | 展示随时间变化的趋势 |
| comparison（对比） | bar 柱状图 | 分类数据的大小对比 |
| summary（汇总） | pie 饼图 / table 表格 | 占比构成或明细展示 |
| correlation（相关） | scatter 散点图 | 两个变量的关系 |
| anomaly（异常） | bar 柱状图 | 标注异常值 |

### 3.2 数据特征 → 图表类型映射

| 数据特征 | 推荐图表 | 场景 |
|---------|---------|------|
| 分类 + 数值 | bar | 各品类销售额对比 |
| 时间 + 数值 | line | 月度销售趋势 |
| 分类 + 占比 | pie | 各品类销售占比 |
| 数值 + 数值 | scatter | 价格 vs 销量 |
| 矩阵数据 | heatmap | 区域 × 品类 销售矩阵 |
| 明细记录 | table | 订单明细 |

---

## 四、图表工具（Chart Tool）

### 4.1 文件位置
`backend/app/tools/chart_tool.py`

### 4.2 两个核心工具

| 工具 | 作用 | 使用场景 |
|------|------|---------|
| `generate_chart` | 生成具体图表的 ECharts 配置 | 已知图表类型和数据 |
| `recommend_chart_type` | 根据数据特征推荐图表类型 | 不确定用什么图表 |

### 4.3 图表配置模板

每种图表类型对应一段 Python 代码模板，生成 ECharts 配置：

```python
CHART_CODE_TEMPLATES = {
    "bar": """
import json, pandas as pd
data = json.loads(input_data)
df = pd.DataFrame(data)
result = {
    "title": {"text": title, "left": "center"},
    "xAxis": {"type": "category", "data": df[x_field].tolist()},
    "yAxis": {"type": "value", "name": y_field},
    "series": [{"type": "bar", "data": df[y_field].tolist()}]
}
""",
    "line": "...",
    "pie": "...",
    "scatter": "...",
    "table": "...",
}
```

**为什么用代码模板而不是硬编码？**
- 灵活：可以处理任意字段名
- 可扩展：添加新图表类型只需加模板
- 可维护：图表逻辑集中管理

### 4.4 ECharts 配置输出

```json
{
  "title": {"text": "Q3 各品类销售额", "left": "center"},
  "tooltip": {"trigger": "axis"},
  "xAxis": {"type": "category", "data": ["电子产品", "服装", "食品"]},
  "yAxis": {"type": "value", "name": "销售额"},
  "series": [{
    "type": "bar",
    "data": [1500000, 800000, 250000],
    "itemStyle": {"color": "#5470c6"}
  }]
}
```

前端拿到这个配置，直接传给 ECharts 渲染即可。

---

## 五、Viz Agent

### 5.1 与 Data/Analysis Agent 的区别

| 维度 | Data Agent | Analysis Agent | Viz Agent |
|------|-----------|----------------|-----------|
| **输入** | 用户自然语言 | Data Agent 结果 | Data + Analysis 结果 |
| **工具** | SQL | Python 计算 | 图表生成 |
| **输出** | 原始数据 | 分析洞察 | 图表配置 |

### 5.2 工作流程

```
步骤1：分析数据和洞察
  → 查看 data_results（字段、类型、行数）
  → 查看 analysis_results（洞察类型、关键发现）
  → 判断需要生成哪些图表

步骤2：选择图表类型
  → 根据洞察类型选择（trend→line, comparison→bar）
  → 不确定时调用 recommend_chart_type

步骤3：生成图表配置
  → 调用 generate_chart 生成 ECharts 配置
  → 传入 chart_type, data_json, title, 字段映射

步骤4：输出结果
  → ChartSpec 列表（可生成多个图表）
```

### 5.3 输出格式：ChartSpec

```python
class ChartSpec(BaseModel):
    chart_id: str           # 唯一ID
    chart_type: str         # bar/line/pie/scatter/heatmap/table
    title: str              # 图表标题
    data_source: str        # 数据来源
    x_field: Optional[str]  # X轴字段
    y_field: Optional[str]  # Y轴字段
    config: dict            # ECharts 配置
```

### 5.4 多图表生成

一个分析任务可能需要多个图表：
- 柱状图：各品类销售额对比
- 饼图：各品类销售占比
- 折线图：月度销售趋势

Viz Agent 可以生成多个 ChartSpec，都追加到 `State.charts` 中。

---

## 六、图构建器更新

### 6.1 当前图结构

```
START → Supervisor → data_agent → Supervisor → analysis_agent → Supervisor → viz_agent → Supervisor → FINISH
```

### 6.2 更新内容

```python
# 添加 Viz Agent 节点
workflow.add_node("viz_agent", viz_agent_node)
workflow.add_edge("viz_agent", "supervisor")
```

---

## 七、本板块简历价值

### 7.1 新增可写内容

```markdown
• 可视化 Agent 设计：基于数据特征和洞察类型自动选择图表类型，
  支持 bar/line/pie/scatter/table 五种图表，输出标准化 ECharts 配置

• 图表配置生成：通过 Python 代码模板动态生成 ECharts 配置，
  支持任意字段映射，前端直接渲染无需二次处理

• 图表推荐引擎：基于数据特征（分类/数值/时间）和分析目标（对比/趋势/占比）
  智能推荐最适合的图表类型，降低用户选择成本

• 多图表支持：单个任务可生成多个图表（对比图+占比图+趋势图），
  全面展示数据洞察
```

### 7.2 面试高频问题

**Q1: 为什么需要单独的 Viz Agent，而不是让 Analysis Agent 顺便生成图表？**
> "可视化是独立的专业领域，需要专门的图表设计知识（什么数据适合什么图、配色原则、标签设计）。单独一个 Viz Agent 可以：1）专注于可视化逻辑；2）复用给不同的上游 Agent（Data Agent 和 Analysis Agent 都可以调用）；3）独立迭代优化图表生成策略。"

**Q2: 图表配置为什么用 ECharts？**
> "ECharts 是百度开源的图表库，在国内企业级项目中使用率最高。选择它的原因：1）丰富的图表类型和交互能力；2）完善的中文文档和社区支持；3）与 React 集成成熟（echarts-for-react）；4）企业品牌色定制方便。"

**Q3: 怎么保证生成的图表配置是正确的？**
> "三层保障：1）Python 代码模板经过测试，确保生成的 JSON 结构正确；2）Pydantic 模型（ChartSpec）校验字段类型；3）前端渲染时如果出错，会回退到表格展示。"

---

## 八、下板块预告

### 板块六：Report Agent + RAG 报告生成

**核心内容**：
- Report Agent 的设计：整合数据、分析、图表，生成结构化报告
- RAG 知识库：检索历史报告模板，提升生成质量
- 报告模板引擎：Jinja2 模板，统一格式
- 与 Viz Agent 的衔接：读取 State.charts 嵌入报告

**你将实现**：
- `backend/app/agents/report_agent.py`
- `backend/app/rag/retriever.py`
- `backend/app/rag/embeddings.py`

---

> **文档结束**  
> 如有疑问，随时提问。确认理解后，我们继续 **板块六：Report Agent + RAG 报告生成** 🚀


print("✅ docs/05-VizAgent与图表生成工具.md 创建完成")
