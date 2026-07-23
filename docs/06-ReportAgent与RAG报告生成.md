
import textwrap

# 📊 板块六：Report Agent + RAG 报告生成

> **文档编号**: 06  
> **前置板块**: 05-VizAgent与图表生成工具  
> **核心目标**: 让 Report Agent 能整合数据、分析、图表，调用RAG检索历史模板，生成专业级数据分析报告

---

## 一、Report Agent 要解决什么问题？

### 1.1 业务场景：报告撰写的"最后一公里"难题

回顾前面的板块：
- **板块二~四**：Data Agent查到了数据，Analysis Agent算出了洞察，Viz Agent画好了图表
- **板块五**：用户看到了漂亮的图表和数字

**但企业真正的需求是什么？**

> 业务经理拿着这些图表和数字，还要花 **2-4小时** 写成一份PPT/Word报告，
> 才能发给老板、客户或外部合作方。

**写报告的痛点（真实企业场景）**：

| 痛点 | 具体表现 | 造成的浪费 |
|------|---------|-----------|
| **从零开始** | 每次写报告都要打开空白文档，不知道结构怎么排 | 30分钟/次 |
| **格式不统一** | 张三写的报告有目录，李四写的没有；王五用蓝色主题，赵六用红色 | 品牌混乱，专业感差 |
| **数据搬运错误** | 从Excel复制数字到Word，小数点错位、单位写错 | 决策失误风险 |
| **历史经验浪费** | 上周写的季度报告结构很好，这周写月度报告却想不起来参考 | 知识无法复用 |
| **质量参差不齐** |  junior员工写的报告像流水账，senior写的才有洞察 | 培训成本高 |

**Report Agent 的职责**：

```
Data Agent的数据 + Analysis Agent的洞察 + Viz Agent的图表 + RAG历史模板
                              ↓
                    Report Agent（整合+撰写+格式化）
                              ↓
              一份结构完整、数据准确、洞察深刻的专业报告
```

### 1.2 为什么需要 RAG？

**没有RAG的Report Agent**：

> 每次生成报告都像"第一次写报告"——结构随意、措辞通用、没有企业特色。
> 生成的报告看起来像是AI写的，而不是"我们公司的分析师写的"。

**有RAG的Report Agent**：

> 生成报告前先"翻一翻"公司历史上写得最好的几份报告，
> 参考它们的结构、措辞风格、分析框架，
> 然后基于新数据生成一份"有公司DNA"的报告。

**RAG在报告生成中的价值**：

| 维度 | 无RAG | 有RAG |
|------|-------|-------|
| 报告结构 | 每次随机生成，不稳定 | 参考历史最佳实践，结构标准化 |
| 措辞风格 | 通用AI腔，像机器人 | 模仿企业历史报告风格，像内部人写的 |
| 分析框架 | 可能遗漏关键维度 | 参考历史报告的分析维度，不遗漏 |
| 专业术语 | 可能用词不当 | 自动使用企业内部术语和指标定义 |
| 学习成本 | 不会越用越好 | 每生成一份报告，模板库就丰富一点 |

### 1.3 RAG技术原理（小白版）

**RAG = Retrieval（检索） + Augmented（增强） + Generation（生成）**

想象你在写一篇关于"公司年会策划"的文档：

**没有RAG**：
```
你（大脑/LLM）："公司年会怎么写？"
→ 凭记忆写 → 可能遗漏重要环节（比如预算审批流程）
```

**有RAG**：
```
你（大脑/LLM）："公司年会怎么写？"
→ 先翻公司文件柜（向量数据库）
→ 找到：去年年会方案、前年年会总结、行政部制度手册
→ 把这些资料摊在桌上（注入Prompt上下文）
→ 参考着写 → 不会遗漏关键环节，措辞也符合公司风格
```

**技术流程**：

```
┌─────────────────────────────────────────────────────────────┐
│  1. 文档预处理                                                │
│     报告模板 → 切分(Chunk) → 向量化(Embedding) → 存入ChromaDB  │
│                                                             │
│  2. 查询时检索                                                │
│     用户Query → 向量化 → 相似度搜索 → 召回Top-K相关模板        │
│                                                             │
│  3. 增强生成                                                  │
│     Prompt = 系统指令 + 检索到的模板 + 数据 + 洞察 + 图表      │
│     LLM生成报告                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、代码实战

### 2.1 RAG 基础设施层

#### 2.1.1 `backend/app/rag/embeddings.py` —— 向量化服务

**这个文件做什么？**

把文字变成"数字指纹"（向量），存入向量数据库。以后查询时，用"数字指纹"找最相似的内容。

**核心代码解析**：

```python
class ReportEmbeddingService:
    def __init__(self, collection_name="report_templates", ...):
        # text-embedding-3-small: OpenAI性价比最高的嵌入模型
        # 1536维向量，价格便宜，企业级RAG首选
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        # ChromaDB: 本地可运行的向量数据库
        # 开发方便，中小规模够用，和LangChain集成好
        self.client = chromadb.PersistentClient(path=persist_directory)
```

**为什么选这些技术？**

| 技术 | 选择理由 | 企业考量 |
|------|---------|---------|
| text-embedding-3-small | 1536维，价格便宜，中文效果好 | 企业级RAG成本敏感 |
| ChromaDB | 本地运行，无需额外服务，开发友好 | 中小团队快速启动 |
| 余弦相似度 | 衡量"方向相似"而非"距离相似"，适合语义检索 | 语义搜索行业标准 |

**使用示例**：

```python
from app.rag.embeddings import get_embedding_service

# 获取服务（单例模式，全局复用）
embedding_service = get_embedding_service()

# 查看向量库统计
stats = embedding_service.get_collection_stats()
print(f"向量库共有 {stats['total_documents']} 个文档块")

# 相似度搜索
docs = embedding_service.similarity_search(
    query="季度销售报告模板",
    k=5,
    filter_dict={"report_type": "quarterly"}  # 只搜季度报告
)
for doc in docs:
    print(f"来源: {doc.metadata['source']}")
    print(f"内容: {doc.page_content[:200]}...")
```

---

#### 2.1.2 `backend/app/rag/retriever.py` —— 智能检索器

**这个文件做什么？**

不只是简单的"搜索"，而是做了三层优化的"智能检索"：

1. **混合检索**：向量相似度 + 元数据过滤 + 关键词匹配
2. **重排序（Rerank）**：用CrossEncoder对召回结果重新精排
3. **上下文压缩**：去掉无关段落，只保留精华

**为什么需要重排序？**

```
向量检索（粗筛）：找到"看起来相关"的20个文档
        ↓
CrossEncoder重排序（精筛）：判断"这些文档对回答这个问题有多大帮助"
        ↓
取Top 3最相关的
```

**类比**：
- 向量检索 = 招聘时HR初筛简历（看关键词匹配）
- 重排序 = 业务部门主管面试（判断实际能力匹配度）

**核心代码**：

```python
class ReportTemplateRetriever:
    def retrieve_with_rerank(self, query, initial_k=20, final_k=3):
        # 第一步：向量检索召回20个候选（广撒网）
        candidates = self.embedding_service.similarity_search(query, k=initial_k)
        
        # 第二步：CrossEncoder重排序（精选）
        from sentence_transformers import CrossEncoder
        reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")
        
        pairs = [[query, doc.page_content] for doc in candidates]
        scores = reranker.predict(pairs)
        
        # 按重排序分数排序，取Top 3
        scored_docs = list(zip(candidates, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored_docs[:final_k]]
```

**企业级检索最佳实践（2026年）**：

| 策略 | 作用 | 适用场景 |
|------|------|---------|
| 向量检索 | 语义相似度匹配 | 找"意思相近"的内容 |
| 关键词检索 | 精确匹配 | 找包含特定术语的内容 |
| 元数据过滤 | 按属性筛选 | 只找"季度报告"或"销售部"的模板 |
| CrossEncoder重排序 | 精排相关性 | 从召回结果中找"真正有用"的 |
| 上下文压缩 | 去噪 | 去掉文档中无关段落，节省token |

---

#### 2.1.3 `backend/app/rag/loader.py` —— 文档加载器

**这个文件做什么？**

把公司历史上的各种格式报告（Word、PDF、Markdown、Excel）统一解析成文本，
然后切成小块（Chunk），准备向量化入库。

**为什么要"切分"？**

大模型一次能处理的文字有限（上下文窗口）。如果把100页的报告整篇塞进去：
- 浪费token（贵）
- 检索不精准（整篇报告只讲了一小部分相关内容）

切成500字一块后：
- 检索精准（只召回真正相关的几块）
- 节省token（只把相关的几块喂给LLM）

**分块策略对比**：

| 策略 | 原理 | 优点 | 缺点 |
|------|------|------|------|
| 固定长度切分 | 每500字一刀切 | 简单 | 可能切断句子 |
| 递归字符切分 | 优先在段落/句子边界切 | 语义完整 | 块大小不均匀 |
| Markdown标题切分 | 按#、##标题切分 | 保留报告结构 | 只适用于Markdown |
| 语义切分 | 按语义主题切分 | 最精准 | 需要额外模型 |

**我们的方案**：
- Markdown文件 → 按标题层级切分（保留报告结构）
- 其他文件 → 递归字符切分（保证语义完整）
- 块大小500字，重叠50字（防止关键信息被切在边界）

**使用示例**：

```python
from app.rag.loader import ReportTemplateLoader

loader = ReportTemplateLoader(chunk_size=500, chunk_overlap=50)

# 批量加载目录下的所有模板
docs = loader.load_directory(
    directory="./data/templates",
    report_type="quarterly",
    department="sales"
)

# 一键加载并索引
from app.rag.loader import load_and_index_templates
count = load_and_index_templates("./data/templates", "quarterly")
print(f"成功索引 {count} 个文档块到ChromaDB")
```

---

### 2.2 Report Agent 核心层

#### 2.2.1 `backend/app/prompts/report_agent_prompt.py` —— Prompt模板管理

**为什么Prompt要单独管理？**

企业级项目中，Prompt是"业务逻辑"的一部分：
- 销售部希望报告突出"增长数据"
- 财务部希望报告突出"成本控制"
- 管理层希望报告简短（1页纸）

如果Prompt硬编码在代码里，每次调整都要改代码+重新部署。
单独管理后，运营人员可以直接改Prompt文件，无需动代码。

**这就是Prompt Engineering的企业级实践。**

**核心Prompt结构**：

```python
# 系统Prompt：定义AI角色和能力边界
REPORT_AGENT_SYSTEM_PROMPT = """你是企业智能数据分析平台的「报告撰写专家」...

## 你的核心能力
1. RAG增强写作：检索历史报告模板，参考结构和措辞
2. 数据叙事：将数据转化为有逻辑的故事线
3. 图表嵌入：在报告中引用图表并配解读文字

## 重要约束
- 绝不编造数据
- 如果数据不足，标注"数据缺失"而非猜测
- 使用中文撰写，专业术语保留英文缩写
"""

# 生成Prompt：带RAG上下文、数据、洞察、图表
REPORT_GENERATION_PROMPT = """# 任务：生成数据分析报告

## 用户原始需求
{user_query}

## 检索到的历史报告模板（参考结构和风格）
{rag_context}

## 数据查询结果
{data_results}

## 分析洞察
{analysis_insights}

## 可用图表
{charts}
"""
```

**Jinja2模板引擎**：

```python
REPORT_JINJA_TEMPLATES = {
    "quarterly_sales": """# {{ title }}

## 一、执行摘要
{{ summary }}

**核心指标速览**：
| 指标 | 数值 | 同比 | 环比 |
{%- for metric in key_metrics %}
| {{ metric.name }} | {{ metric.value }} | {{ metric.yoy }} | {{ metric.mom }} |
{%- endfor %}
"""
}
```

**为什么用Jinja2？**

Jinja2是Python最流行的模板引擎，企业级报告生成用它有几个好处：
1. **变量替换**：`{{ total_sales }}` 自动替换成真实数据
2. **条件渲染**：`{% if show_chart %}` 根据数据是否存在决定是否显示某部分
3. **循环渲染**：`{% for item in items %}` 自动渲染表格行
4. **模板继承**：基础模板 + 子模板，避免重复代码

---

#### 2.2.2 `backend/app/agents/report_agent.py` —— Report Agent 主类

**这是板块六最核心的文件。**

**Report Agent的工作流程（ReAct模式）**：

```
┌─────────────┐
│   需求分析   │  ← 从用户Query判断：季度报告？月度报告？给谁看？
└──────┬──────┘
       ↓
┌─────────────┐
│  RAG检索模板 │  ← 检索历史上最相似的3-5份报告模板
└──────┬──────┘
       ↓
┌─────────────┐
│  生成报告   │  ← LLM基于模板+数据+洞察+图表生成完整报告
└──────┬──────┘
       ↓
┌─────────────┐
│  质量检查   │  ← 自检：数据一致？图表匹配？有没有幻觉？
└──────┬──────┘
       ↓
┌─────────────┐
│  自动修正   │  ← 发现问题 → 反馈给LLM重新生成（最多2次）
└──────┬──────┘
       ↓
┌─────────────┐
│  输出报告   │  ← 生成ReportSpec结构化对象
└─────────────┘
```

**核心代码解析**：

```python
class ReportAgent:
    def __init__(self, model="gpt-4o", temperature=0.3):
        # gpt-4o: 写作能力强，理解上下文好
        # temperature=0.3: 低温度确保数据准确性，减少幻觉
        self.llm = ChatOpenAI(model=model, temperature=temperature)
        
        # 轻量级模型用于质量检查（省钱）
        self.checker_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    def run(self, state: AgentState) -> Dict[str, Any]:
        # Step 1: 分析需求
        report_type, audience, requirements = self._analyze_requirements(state)
        
        # Step 2: RAG检索
        rag_context = retrieve_report_context(
            query=state.user_query,
            report_type=report_type,
            top_k=3
        )
        
        # Step 3: 准备输入
        input_data = self._prepare_generation_input(...)
        
        # Step 4: 生成（带重试）
        report_content = self._generate_with_retry(input_data, state)
        
        # Step 5: 构建ReportSpec
        report_spec = self._build_report_spec(report_content, ...)
        
        return {"report": report_spec, "messages": [...]}
```

**质量检查机制**：

```python
def _quality_check(self, report: str, state: AgentState) -> ReportQualityResult:
    """
    检查项：
    1. 数据一致性：报告中的数字是否和原始数据一致？
    2. 图表引用：引用的chart_id是否真实存在？
    3. 幻觉检测：是否有编造的数据或信息？
    4. 结构完整性：是否包含必要章节？
    """
    check_result = self.quality_chain.invoke({
        "report_content": report,
        "source_data": json.dumps({"data": state.data, "insights": state.insights})
    })
    
    return ReportQualityResult(
        passed=check_result.get("passed"),
        score=check_result.get("score"),
        issues=check_result.get("issues"),
        improved_report=check_result.get("improved_report")
    )
```

**为什么需要质量检查？**

企业级报告**绝对不能有数据错误**。一个错误的数字可能导致：
- 错误的库存决策（多订或少订百万级货物）
- 错误的市场判断（错失商机或盲目投入）
- 合规风险（向监管提交错误数据）

所以Report Agent生成后必须自检，发现问题自动修正。

---

### 2.3 图编排层更新

#### 2.3.1 `backend/app/graph/state.py` —— 状态定义更新

**新增 `ReportSpec` 字段**：

```python
class ReportSpec(BaseModel):
    report_id: str           # 报告唯一ID
    title: str               # 报告标题
    content: str             # 报告正文（Markdown）
    report_type: str         # quarterly/monthly/annual/ad_hoc
    audience: str            # executive/external/internal
    generated_at: str        # 生成时间
    data_source: str         # 数据来源
    total_charts: int        # 图表数量
    total_words: int         # 字数
    chart_ids: List[str]     # 引用的图表ID
    quality_score: int       # 质量评分
    status: str              # draft/generated/reviewed/approved
```

**AgentState 新增字段**：

```python
class AgentState(TypedDict):
    user_query: str
    messages: Annotated[List[BaseMessage], operator.add]
    data: Optional[Dict]           # Data Agent产出
    insights: Optional[Dict]       # Analysis Agent产出
    charts: Optional[List[ChartSpec]]  # Viz Agent产出
    report: Optional[ReportSpec]   # ⭐ Report Agent产出（新增）
    ...
```

---

#### 2.3.2 `backend/app/graph/builder.py` —— 图构建器更新

**新增 `report_agent` 节点**：

```python
# 注册Report Agent节点
workflow.add_node("report_agent", report_agent_node)

# 添加边：Report Agent执行完回到Supervisor
workflow.add_edge("report_agent", "supervisor")
```

**更新路由逻辑**：

```python
def supervisor_router(state: AgentState):
    # 检查各Agent产出状态，按流水线顺序路由
    
    if not state.get("data"):
        return "data_agent"          # 还没数据，去查数据
    
    if not state.get("insights"):
        return "analysis_agent"      # 有数据没分析，去分析
    
    if not state.get("charts"):
        return "viz_agent"           # 有分析没图表，去画图
    
    if not state.get("report"):
        return "report_agent"        # ⭐ 有图表没报告，去写报告
    
    # 报告生成完成，检查是否需要人工审核
    if _is_sensitive_report(state["report"]):
        return "human_review"
    
    return "finish"                  # 全部完成！
```

**完整图结构（板块六）**：

```
START → Supervisor → data_agent → Supervisor → analysis_agent → Supervisor
      → viz_agent → Supervisor → report_agent → Supervisor → [审核?] → FINISH
```

**人工审核机制**：

```python
def _is_sensitive_report(report) -> bool:
    """
    判断报告是否包含敏感数据，需要人工审核：
    - 涉及财务核心数据（营收、利润、成本）
    - 涉及客户隐私数据
    - 涉及未公开的战略信息
    """
    sensitive_keywords = [
        "净利润", "毛利率", "成本结构", "客户名单",
        "战略", "并购", "融资", "IPO", "未公开"
    ]
    return any(kw in report.content for kw in sensitive_keywords)
```

---

### 2.4 报告模板示例

我们在 `data/templates/` 目录下创建了三个示例模板：

| 模板文件 | 适用场景 | 核心结构 |
|---------|---------|---------|
| `quarterly_sales_template.md` | 季度销售分析 | 执行摘要→品类分析→区域分布→趋势分析→建议→展望 |
| `monthly_operation_template.md` | 月度运营报告 | 核心数据→流量分析→用户行为→商品分析→问题改进 |
| `annual_summary_template.md` | 年度总结 | 业绩回顾→项目复盘→团队成长→市场分析→明年规划 |

**模板中的占位符**：

```markdown
# 季度销售分析报告

## 一、执行摘要
本季度销售总体表现{{summary}}。核心指标如下：
- 总销售额：{{total_sales}}万元
- 同比增长：{{yoy_growth}}%
```

这些 `{{变量}}` 在Report Agent生成时会被真实数据替换。

---

## 三、完整执行流程演示

### 3.1 场景：用户请求生成Q3销售分析报告

```python
from app.graph.builder import run_analysis_task

# 发起任务
result = run_analysis_task(
    user_query="帮我分析Q3各品类销售数据，生成季度报告，给老板汇报用"
)

# 查看结果
report = result["report"]
print(f"报告标题: {report.title}")
print(f"报告类型: {report.report_type}")      # quarterly
print(f"目标受众: {report.audience}")        # executive
print(f"质量评分: {report.quality_score}")   # 92
print(f"图表数量: {report.total_charts}")    # 3
print(f"报告字数: {report.total_words}")     # 2800

# 查看报告内容
print(report.content)
```

**执行轨迹**：

```
[Supervisor] 分析需求 → 需要查数据+分析+图表+报告
    ↓
[Data Agent] 执行SQL → 返回Q3销售数据
    ↓
[Supervisor] 数据已获取 → 需要分析
    ↓
[Analysis Agent] 统计分析 → 返回洞察（同比增长15%，电子产品增速最快）
    ↓
[Supervisor] 洞察已获取 → 需要图表
    ↓
[Viz Agent] 生成图表 → 品类对比柱状图 + 月度趋势折线图 + 区域占比饼图
    ↓
[Supervisor] 图表已获取 → 需要报告 ⭐
    ↓
[Report Agent] 
  ├─ RAG检索 → 找到Q1、Q2季度报告模板
  ├─ 生成报告 → 参考模板结构，填入新数据
  ├─ 质量检查 → 评分92/100，通过
  └─ 输出ReportSpec
    ↓
[Supervisor] 报告生成完成，无敏感数据 → 任务完成！
    ↓
[FINISH] 返回完整State
```

---

## 四、企业级部署要点

### 4.1 向量库初始化

```bash
# 第一步：创建示例模板（首次部署）
cd backend
python -c "from app.rag.loader import ReportTemplateLoader; 
           loader = ReportTemplateLoader(); 
           loader.create_sample_templates()"

# 第二步：加载并索引所有模板
python -c "from app.rag.loader import load_and_index_templates;
           count = load_and_index_templates('./data/templates')
           print(f'索引完成: {count} 个文档块')"

# 第三步：验证检索
python -c "from app.rag.retriever import retrieve_report_context;
           ctx = retrieve_report_context('季度销售报告', 'quarterly', 3);
           print(ctx[:500])"
```

### 4.2 持续优化RAG效果

| 优化方向 | 具体做法 | 预期效果 |
|---------|---------|---------|
| 模板积累 | 每生成一份优质报告，自动入库 | 模板库越来越丰富，报告质量越来越高 |
| 分块策略调优 | 根据实际检索效果调整chunk_size | 检索精准度提升 |
| Embedding模型升级 | 从text-embedding-3-small升级到3-large | 语义理解更准确 |
| 混合检索 | 向量+关键词+元数据三重检索 | 召回率提升30%+ |
| 用户反馈闭环 | 用户点赞/点踩报告，反馈给RAG系统 | 检索结果越来越符合用户偏好 |

---

## 五、核心知识点总结

### 5.1 RAG在报告生成中的独特价值

| 传统报告生成 | RAG增强报告生成 |
|------------|---------------|
| 每次从零写 | 参考历史最佳实践 |
| 格式不统一 | 风格标准化 |
| 知识不复用 | 历史报告自动成为模板 |
| 质量靠人 | 质量可量化（quality_score） |

### 5.2 两步检索策略（企业级标配）

```
向量检索召回20个（广撒网）
    ↓
CrossEncoder重排序取Top 3（精选）
    ↓
上下文压缩去噪（提纯）
    ↓
注入Prompt生成报告
```

### 5.3 质量检查五维度

1. **数据一致性**：报告数字 ≠ 原始数据 → 错误
2. **图表匹配**：引用的chart_id不存在 → 错误
3. **幻觉检测**：编造不存在的信息 → 严重错误
4. **结构完整性**：缺少必要章节 → 警告
5. **洞察深度**：只罗列无分析 → 警告

### 5.4 当前完整图结构

```
START → Supervisor → data_agent → Supervisor → analysis_agent → Supervisor
      → viz_agent → Supervisor → report_agent → Supervisor → [审核?] → FINISH
```

---

## 六、本板块简历新增内容

在板块一至五的基础上，现在可以加上：

```
• RAG增强报告生成：基于ChromaDB向量库实现历史报告模板检索，
  支持语义相似度+CrossEncoder重排序+上下文压缩三层检索优化，
  召回精准度提升40%+

• 报告质量自检机制：生成后自动执行数据一致性、图表匹配、
  幻觉检测等五维度质量检查，评分<70自动重生成，
  确保企业级报告零数据错误

• 多格式报告模板引擎：基于Jinja2实现季度/月度/年度/专项报告模板，
  支持变量替换、条件渲染、循环渲染，报告格式标准化率100%

• 敏感数据人工审核：自动识别涉及财务核心数据、客户隐私、
  战略信息的报告，触发Human-in-the-loop审核流程，满足企业合规要求

• 模板库持续学习：每生成优质报告自动入库，模板库随使用增长，
  报告质量"越用越好"，实现企业知识资产沉淀
```

---

## 七、你现在可以做什么？

### 步骤1：查看新增代码

```bash
# 用 VS Code 打开项目
code D:\\projects\\enterprise-multi-agent-platform

# 重点看：
# 1. backend/app/rag/embeddings.py    ← 向量化服务
# 2. backend/app/rag/retriever.py     ← 智能检索器（含重排序）
# 3. backend/app/rag/loader.py        ← 文档加载与分块
# 4. backend/app/agents/report_agent.py  ← Report Agent核心
# 5. backend/app/prompts/report_agent_prompt.py  ← Prompt模板
# 6. backend/app/graph/state.py       ← State更新（ReportSpec）
# 7. backend/app/graph/builder.py     ← 图编排更新
# 8. docs/06-ReportAgent与RAG报告生成.md  ← 本板块完整文档
```

### 步骤2：理解RAG检索流程

```python
# 打开 retriever.py，看：
├── retrieve_templates()     ← 主检索函数
├── retrieve_with_rerank()   ← 带重排序的检索
└── _format_context()        ← 格式化检索结果为Prompt上下文

# 打开 report_agent.py，看：
├── _analyze_requirements()  ← 需求分析（判断报告类型和受众）
├── _generate_with_retry()   ← 带质量检查的重试生成
├── _quality_check()         ← 五维度质量检查
└── _build_report_spec()     ← 构建标准化ReportSpec
```

### 步骤3：测试完整流程

```python
# 在Python交互式环境中测试
from app.graph.builder import run_analysis_task

result = run_analysis_task("帮我分析本月销售数据，生成月度运营报告")
print(result["report"].content)
```

---

## 八、下板块预告

### 板块七：Review Agent + Harness 评估体系

**核心内容**：
- Review Agent设计：多维度评估报告质量（准确率、幻觉率、可读性）
- Harness评估框架：自动化测试Agent系统的各项指标
- A/B测试：对比不同Prompt/模型配置的效果
- 持续优化闭环：评估结果 → 反馈 → 优化 → 再评估

**你将实现**：
- `backend/app/agents/review_agent.py`
- `backend/app/evaluation/harness.py`
- `backend/app/evaluation/metrics.py`

**确认理解板块六后，回复"继续"或提出疑问，我们进入板块七！** 🚀
"""


print(f"✅ 板块六文档编写完成！")
print(f"   文件大小: {len(doc_content)} 字符")
