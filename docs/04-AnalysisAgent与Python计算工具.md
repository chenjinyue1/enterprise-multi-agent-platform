
# 板块四：Analysis Agent + Python 计算工具

> **文档编号**: 04  
> **前置板块**: 03-DataAgent与MCP数据库工具  
> **核心目标**: 让 Analysis Agent 能执行 Python 统计分析，从原始数据中提取洞察

---

## 📖 目录

1. [Analysis Agent 要解决什么问题？](#一analysis-agent-要解决什么问题)
2. [为什么需要 Python 计算工具？](#二为什么需要-python-计算工具)
3. [安全沙箱设计](#三安全沙箱设计)
4. [Python MCP Server](#四python-mcp-server)
5. [Python Tool（LangChain 封装）](#五python-toollangchain-封装)
6. [Analysis Agent](#六analysis-agent)
7. [图构建器更新](#七图构建器更新)
8. [本板块简历价值](#八本板块简历价值)
9. [下板块预告](#九下板块预告)

---

## 一、Analysis Agent 要解决什么问题？

### 1.1 业务场景

Data Agent 已经查到了原始数据：
```json
[
  {"category": "电子产品", "total": 1500000},
  {"category": "服装", "total": 800000},
  {"category": "食品", "total": 250000}
]
```

但用户要的不是原始数据，而是**洞察**：
- "哪个品类占比最高？"
- "各品类占比分别是多少？"
- "有没有异常数据？"
- "环比变化趋势如何？"

**Analysis Agent 的职责**：把原始数据 → 统计计算 → 分析洞察

### 1.2 为什么需要 Python 计算工具？

LLM 本身**不擅长精确计算**：
- 大数字乘法容易出错（1500000 + 800000 = ?）
- 百分比计算可能偏差（1500000 / 2550000 = ?）
- 统计分析需要专业库（pandas、numpy、scipy）

**解决方案**：让 LLM 生成 Python 代码，在安全的沙箱中执行，返回精确结果。

---

## 二、为什么需要 Python 计算工具？

### 2.1 LLM 的计算局限

| 计算类型 | LLM 能力 | 问题 |
|---------|---------|------|
| 简单加减 | ✅ 可以 | 偶尔出错 |
| 大数字运算 | ❌ 容易错 | 1500000 + 800000 = 2300000（可能错） |
| 百分比计算 | ❌ 容易错 | 占比计算精度问题 |
| 统计分析 | ❌ 不会 | 标准差、相关系数、回归分析 |
| 数据可视化 | ❌ 不会 | 生成图表配置 |

### 2.2 Python 工具的优势

```python
# LLM 可能算错
"电子产品占比 = 1500000 / (1500000 + 800000 + 250000) = 58.8%"
# 实际 = 1500000 / 2550000 = 58.82%（LLM 可能四舍五入不一致）

# Python 精确计算
import pandas as pd
df = pd.DataFrame(data)
total = df["total"].sum()
result = df.groupby("category")["total"].sum().apply(lambda x: round(x/total*100, 2))
# 结果精确到小数点后2位，100%一致
```

---

## 三、安全沙箱设计

### 3.1 Python 代码执行的风险

Python 代码执行是**高危操作**：
- `import os; os.system("rm -rf /")` → 系统被删
- `while True: pass` → CPU 占满
- 读取敏感文件 → 数据泄露
- 网络请求 → 外传数据

### 3.2 我们的安全策略（六层防护）

| 层级 | 措施 | 实现方式 |
|------|------|---------|
| **导入白名单** | 只允许 pandas、numpy 等 | `__import__` 自定义函数 |
| **黑名单拦截** | 禁止 os、sys、subprocess | 正则匹配危险代码模式 |
| **执行超时** | 代码执行不超过 30 秒 | `multiprocessing.Process` + `join(timeout)` |
| **资源限制** | 内存限制 512MB | `resource.setrlimit`（Linux） |
| **文件系统隔离** | 禁止访问 /etc、/home | 自定义 `open` 函数（未启用，子进程隔离） |
| **网络隔离** | 禁止网络请求 | 黑名单拦截 socket、urllib |

### 3.3 为什么用子进程？

```python
# 主进程
process = Process(target=_execute_code_in_process)
process.start()
process.join(timeout=30)  # 等待30秒

if process.is_alive():
    process.terminate()  # 超时强制终止
    process.kill()       # 还不行就强制杀死
```

**优势**：
- 超时控制：主进程可以强制终止子进程
- 内存限制：子进程独立设置资源限制
- 崩溃隔离：子进程崩溃不影响主进程
- 完全隔离：子进程有自己的内存空间

---

## 四、Python MCP Server

### 4.1 文件位置
`backend/app/mcp/servers/python_server.py`

### 4.2 两个核心工具

| 工具 | 作用 | 使用场景 |
|------|------|---------|
| `execute_python` | 执行自定义 Python 代码 | 复杂计算、自定义逻辑、数据转换 |
| `analyze_dataframe` | 快速数据分析（预置模板） | 快速统计、相关性、异常值、分布 |

### 4.3 execute_python 安全实现

```python
def _execute_with_timeout(code: str, input_data: str, timeout: int) -> dict:
    # 1. 检查危险代码（正则匹配）
    dangerous_patterns = [
        r"import\s+os", r"import\s+sys", r"os\.system",
        r"subprocess\.", r"socket\.", r"eval\s*\(", ...
    ]
    
    # 2. 子进程执行（隔离 + 超时）
    process = Process(target=_execute_code_in_process)
    process.start()
    process.join(timeout=timeout)
    
    if process.is_alive():
        process.terminate()
        process.kill()
        return {"error": "执行超时"}
    
    # 3. 受限全局命名空间
    restricted_globals = _create_restricted_globals()
    # 只允许安全内置函数
    # 自定义 __import__ 拦截危险导入
```

### 4.4 analyze_dataframe 预置分析

```python
@mcp.tool()
async def analyze_dataframe(data_json: str, analysis_type: str = "summary"):
    """
    分析类型：
    - "summary": 基础统计（计数、均值、标准差、最值）
    - "correlation": 相关性分析
    - "distribution": 分布分析（Shapiro-Wilk 正态性检验）
    - "outliers": 异常值检测（IQR 方法）
    """
```

**为什么预置分析？**
- 常见分析场景不需要写代码
- 结果格式统一，便于 LLM 解析
- 执行更快（不需要 LLM 生成代码）

---

## 五、Python Tool（LangChain 封装）

### 5.1 架构关系

```
Analysis Agent (ReAct Agent)
    ↓ 调用 LangChain Tool
Python Tool (BaseTool 适配层)
    ↓ 调用 MCP Client
MCP Client (JSON-RPC 2.0)
    ↓ STDIO / HTTP
MCP Server (python_server.py)
    ↓ 安全沙箱
Python 代码执行
```

### 5.2 两个工具

| 工具 | 输入 | 输出 |
|------|------|------|
| `execute_python` | `code`, `input_data`, `timeout` | 标准输出 + 执行结果 + 错误 |
| `analyze_dataframe` | `data_json`, `analysis_type` | 结构化分析结果 |

### 5.3 结果格式化

```python
# 将原始输出格式化为 LLM 友好的文本
lines = []

# 标准输出
if stdout.strip():
    lines.append("【标准输出】")
    lines.append(stdout)

# 执行结果（result 变量）
if exec_result is not None:
    lines.append("【执行结果】")
    lines.append(json.dumps(exec_result, indent=2))

# 标准错误（警告）
if stderr.strip():
    lines.append("【警告/提示】")
    lines.append(stderr)

return "\n".join(lines)
```

---

## 六、Analysis Agent

### 6.1 与 Data Agent 的区别

| 维度 | Data Agent | Analysis Agent |
|------|-----------|----------------|
| **输入** | 用户自然语言需求 | Data Agent 的查询结果 |
| **工具** | SQL 查询工具 | Python 计算工具 |
| **输出** | 原始数据 | 分析洞察和建议 |
| **核心能力** | 数据库查询 | 统计分析 |

### 6.2 分析流程（四步法）

```
步骤1：数据概览
  → analyze_dataframe(analysis_type="summary")
  → 了解数据量、类型、基础统计

步骤2：深入分析
  → 根据需求选择分析类型
  → correlation / outliers / distribution / execute_python

步骤3：生成洞察
  → 趋势洞察：上升/下降/平稳？
  → 对比洞察：差异、领先/落后？
  → 异常洞察：离群值、突变点？
  → 建议洞察：基于数据的业务建议

步骤4：输出结果
  → AnalysisResult JSON 格式
  → summary + insights + metrics + recommendations
```

### 6.3 系统提示词设计要点

```python
ANALYSIS_AGENT_PROMPT = """你是"数据分析专家"...

## 重要提示
1. 必须使用工具计算：不要凭 LLM 的"直觉"给出数字
2. 数据格式：input_data 变量传入 JSON 列表
3. 代码建议：import pandas as pd; df = pd.DataFrame(input_data)
4. 结果变量：代码中定义 result 变量作为返回值
5. 置信度：insights 中的 confidence（0-1），基于数据直接计算的设为 0.95+
"""
```

### 6.4 输出格式：AnalysisResult

```json
{
  "summary": "分析摘要（1-2句话）",
  "insights": [
    {
      "type": "trend/comparison/anomaly/correlation/summary",
      "title": "洞察标题",
      "description": "详细描述",
      "confidence": 0.95,
      "supporting_data": {"关键数据": "值"}
    }
  ],
  "metrics": {"自定义指标": "值"},
  "recommendations": ["建议1", "建议2"]
}
```

---

## 七、图构建器更新

### 7.1 当前图结构

```
        ┌─────────────┐
        │   START     │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  Supervisor │
        └──────┬──────┘
               │
        ┌──────┴──────┐
        ▼             ▼
┌─────────────┐  ┌─────────────┐
│  data_agent │  │   FINISH    │
│  (查询数据)  │  │   (结束)    │
└──────┬──────┘  └─────────────┘
       │
       ▼
┌─────────────┐
│  Supervisor │  ← 回到 Supervisor 决定下一步
└──────┬──────┘
       │
       ▼
┌─────────────┐
│analysis_agent│  ← 板块四新增
│  (分析数据)  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Supervisor │  ← 回到 Supervisor 决定下一步
└─────────────┘
```

### 7.2 更新内容

```python
# 添加 Analysis Agent 节点
workflow.add_node("analysis_agent", analysis_agent_node)
workflow.add_edge("analysis_agent", "supervisor")
```

---

## 八、本板块简历价值

### 8.1 新增可写内容

```markdown
• Python 安全沙箱：基于 multiprocessing 子进程 + 资源限制实现代码执行隔离，
  支持导入白名单（pandas/numpy/scipy）、危险代码正则拦截、执行超时（30秒）、
  内存限制（512MB），防止恶意代码执行和资源耗尽

• 预置分析模板：封装 analyze_dataframe 工具，支持 summary/correlation/
  distribution/outliers 四种分析模式，基于 scipy.stats 实现 Shapiro-Wilk
  正态性检验和 IQR 异常值检测

• 精确计算保障：Analysis Agent 通过 ReAct 模式调用 Python 工具执行统计计算，
  替代 LLM 直接计算，确保数值结果 100% 准确（占比、增长率、标准差等）

• 结构化洞察输出：定义 AnalysisInsight 模型（type/title/description/
  confidence/supporting_data），支持置信度评估和业务建议生成
```

### 8.2 面试高频问题

**Q1: 为什么不用 LLM 直接分析，而要调用 Python 工具？**
> "LLM 在精确计算上不可靠，大数字运算和百分比容易出错。我们的方案是让 LLM 生成分析思路，但具体的统计计算（均值、标准差、占比、回归系数）通过 Python 工具在沙箱中执行，确保结果 100% 准确。"

**Q2: Python 代码执行怎么保证安全？**
> "六层防护：1）正则黑名单拦截危险代码模式（import os、eval 等）；2）自定义 __import__ 函数实现导入白名单；3）子进程执行，主进程可强制终止；4）multiprocessing 超时控制（30秒）；5）Linux resource 模块限制内存（512MB）；6）受限的全局命名空间，只暴露安全的内置函数。"

**Q3: analyze_dataframe 和 execute_python 有什么区别？**
> "analyze_dataframe 是预置分析模板，适合常见场景（summary、correlation、outliers），执行快、结果格式统一。execute_python 是通用代码执行，适合复杂自定义逻辑（如增长率计算、预测模型），更灵活但需要 LLM 生成代码。"

**Q4: Analysis Agent 的洞察置信度怎么设定？**
> "confidence 字段表示 LLM 对洞察的信心。基于数据直接计算的（如占比 58.82%）设为 0.95+，需要推断或外推的（如'未来趋势'）设为 0.7-0.85。这个设计让最终报告可以区分'数据事实'和'分析推断'。"

---

## 九、下板块预告

### 板块五：Viz Agent + 图表生成工具

**核心内容**：
- Viz Agent 的设计：根据数据和分析结果生成图表配置
- 图表类型选择：柱状图、折线图、饼图、散点图、热力图
- 图表数据生成：通过 Python 工具生成图表数据（ECharts/Plotly 配置）
- 与 Analysis Agent 的衔接：读取 State.analysis_results 生成可视化

**你将实现**：
- `backend/app/agents/viz_agent.py`
- `backend/app/tools/chart_tool.py`

---

> **文档结束**  
> 如有疑问，随时提问。确认理解后，我们继续 **板块五：Viz Agent + 图表生成工具** 🚀


print("✅ docs/04-AnalysisAgent与Python计算工具.md 创建完成")
