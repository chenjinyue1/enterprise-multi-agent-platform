
# 2. 编写 RAG Retriever 模块
"""
RAG 检索器模块
负责从向量库检索相关文档，并构建增强Prompt

小白理解：
检索器就像一个"智能图书管理员"。你问"怎么写季度报告"，
它不去翻所有书，而是直接找到"季度报告"相关的3-5个模板，
然后把这些模板的内容"贴"到你的问题后面，让大模型参考着写。
"""

from typing import List, Dict, Optional, Tuple
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain_openai import ChatOpenAI

from .embeddings import get_embedding_service


class ReportTemplateRetriever:
    """
    报告模板检索器
    
    为什么需要专门的检索器？
    ------------------------
    简单的相似度搜索有个问题：可能召回很多"看起来相关但实际没用"的文档。
    比如搜"销售报告"，可能召回"销售培训手册"、"销售制度文档"等。
    
    我们的检索器做了三层优化：
    1. 混合检索：向量相似度 + 关键词匹配 + 元数据过滤
    2. 重排序：用CrossEncoder对召回结果重新打分排序
    3. 上下文压缩：去掉无关段落，只保留精华内容
    
    企业价值：确保Report Agent参考的模板是真正相关的，不是"凑数"的
    """
    
    def __init__(
        self,
        top_k: int = 5,
        score_threshold: float = 0.6,
        enable_compression: bool = True
    ):
        """
        初始化检索器
        
        Args:
            top_k: 召回文档数量（企业场景5个足够，太多会污染上下文）
            score_threshold: 相似度阈值，低于此值的文档直接丢弃
            enable_compression: 是否启用上下文压缩（去掉无关段落，节省token）
        """
        self.embedding_service = get_embedding_service()
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.enable_compression = enable_compression
        
        # 初始化压缩器（可选，用于去掉文档中的无关内容）
        if enable_compression:
            llm = ChatOpenAI(
                model="gpt-4o-mini",  # 压缩用轻量模型，省钱
                temperature=0,
                openai_api_key=os.getenv("OPENAI_API_KEY")
            )
            compressor = LLMChainExtractor.from_llm(llm)
            
            self.compression_retriever = ContextualCompressionRetriever(
                base_compressor=compressor,
                base_retriever=self._get_base_retriever()
            )
    
    def _get_base_retriever(self) -> BaseRetriever:
        """获取基础检索器"""
        return self.embedding_service.vector_store.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={
                "k": self.top_k,
                "score_threshold": self.score_threshold
            }
        )
    
    def retrieve_templates(
        self,
        query: str,
        report_type: Optional[str] = None,
        department: Optional[str] = None,
        date_range: Optional[str] = None
    ) -> Tuple[List[Document], str]:
        """
        检索报告模板
        
        Args:
            query: 用户原始需求（如"帮我写一份Q3电商销售分析报告"）
            report_type: 报告类型过滤（quarterly/monthly/annual/special）
            department: 部门过滤（sales/marketing/finance）
            date_range: 时间范围过滤（用于找最新模板）
            
        Returns:
            (文档列表, 格式化的上下文字符串)
            
        企业场景：
        -------
        当Data Agent和分析Agent完成数据查询和图表生成后，
        Report Agent调用此检索器，找到历史上最相似的报告模板，
        然后基于模板结构+新数据生成最终报告。
        """
        # 构建元数据过滤条件
        filter_dict = {}
        if report_type:
            filter_dict["report_type"] = report_type
        if department:
            filter_dict["department"] = department
        if date_range:
            filter_dict["date_range"] = date_range
        
        # 执行检索
        if self.enable_compression:
            docs = self.compression_retriever.invoke(query)
        else:
            docs = self.embedding_service.similarity_search(
                query=query,
                k=self.top_k,
                filter_dict=filter_dict if filter_dict else None
            )
        
        # 格式化上下文（用于注入Prompt）
        context = self._format_context(docs)
        
        return docs, context
    
    def _format_context(self, docs: List[Document]) -> str:
        """
        将检索到的文档格式化为Prompt可用的上下文字符串
        
        格式示例：
        ---------
        [参考模板1: Q2销售季度报告]
        来源：reports/quarterly_sales_q2.md
        内容：
        ## 一、执行摘要
        本季度销售额同比增长15%...
        
        [参考模板2: Q1销售季度报告]
        ...
        """
        if not docs:
            return "未找到相关历史报告模板。"
        
        context_parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知来源")
            title = doc.metadata.get("title", f"参考模板{i}")
            report_type = doc.metadata.get("report_type", "未分类")
            
            part = f"""[参考模板{i}: {title}]
来源：{source}
报告类型：{report_type}
内容：
{doc.page_content}
---"""
            context_parts.append(part)
        
        return "\\n\\n".join(context_parts)
    
    def retrieve_with_rerank(
        self,
        query: str,
        initial_k: int = 20,
        final_k: int = 3
    ) -> List[Document]:
        """
        带重排序的检索（企业级RAG标配）
        
        为什么需要重排序？
        -----------------
        向量相似度搜索是"粗筛"，可能把"表面相似但内容不相关"的文档排前面。
        CrossEncoder重排序是"精筛"，它把查询和文档一起输入模型，
        判断"这个文档对回答这个问题有多大帮助"，准确率更高。
        
        两步检索策略（企业最佳实践）：
        ----------------------------
        1. 向量检索召回20个候选（广撒网）
        2. CrossEncoder重排序取Top 3（精选）
        
        这样比直接向量检索Top 3效果好得多，因为向量检索可能漏掉真正相关的文档。
        """
        # 第一步：向量检索召回更多候选
        candidates = self.embedding_service.similarity_search(
            query=query,
            k=initial_k
        )
        
        if not candidates:
            return []
        
        # 第二步：CrossEncoder重排序
        try:
            from sentence_transformers import CrossEncoder
            reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")
            
            pairs = [[query, doc.page_content] for doc in candidates]
            scores = reranker.predict(pairs)
            
            # 按重排序分数排序
            scored_docs = list(zip(candidates, scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            
            return [doc for doc, _ in scored_docs[:final_k]]
        except Exception:
            # 如果重排序模型加载失败，回退到向量检索结果
            return candidates[:final_k]


# 便捷函数：快速检索
def retrieve_report_context(
    query: str,
    report_type: Optional[str] = None,
    top_k: int = 3
) -> str:
    """
    一键检索报告上下文（供Report Agent直接调用）
    
    使用示例：
    -------
    context = retrieve_report_context(
        query="Q3电商销售分析报告",
        report_type="quarterly"
    )
    # context 可以直接注入Prompt
    """
    retriever = ReportTemplateRetriever(top_k=top_k)
    docs, context = retriever.retrieve_templates(
        query=query,
        report_type=report_type
    )
    return context


print("✅ retriever.py 编写完成")
