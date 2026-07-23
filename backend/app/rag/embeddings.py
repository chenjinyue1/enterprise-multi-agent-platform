
# 1. 编写 RAG Embeddings 模块
"""
RAG 向量化模块
负责将文本转换为向量，存入 ChromaDB

小白理解：
想象你有一本很厚的公司制度手册，RAG就是给每页内容拍个"快照"（向量），
当有人问"年假怎么请"时，系统能快速找到最相关的那几页，而不是翻完整本书。
"""

import os
import hashlib
from typing import List, Dict, Optional
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
import chromadb


class ReportEmbeddingService:
    """
    报告模板向量化服务
    
    为什么需要这个类？
    ----------------
    企业里写报告最怕"每次从零开始"。上周写的季度报告、上个月的月度汇报，
    都是宝贵的"写作资产"。RAG就是把这些历史报告变成"可检索的记忆"，
    新报告自动生成时，自动参考历史模板的结构和措辞。
    
    技术原理（简单版）：
    ------------------
    1. 文本 → Embedding模型 → 向量（一串数字）
    2. 向量存入 ChromaDB（向量数据库）
    3. 查询时：问题 → 向量 → 找最相似的文档
    
    类比：就像给每本书贴上一个"DNA标签"，内容相似的书DNA也相似
    """
    
    def __init__(
        self,
        collection_name: str = "report_templates",
        persist_directory: str = "./data/chroma_db",
        embedding_model: str = "text-embedding-3-small"
    ):
        """
        初始化向量化服务
        
        Args:
            collection_name: ChromaDB集合名（类似MySQL的表名）
            persist_directory: 数据持久化目录（重启后数据不丢失）
            embedding_model: OpenAI嵌入模型，text-embedding-3-small性价比最高
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        
        # 初始化 Embedding 模型
        # text-embedding-3-small: 1536维，价格便宜，适合企业级RAG
        self.embeddings = OpenAIEmbeddings(
            model=embedding_model,
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # 确保目录存在
        os.makedirs(persist_directory, exist_ok=True)
        
        # 初始化 ChromaDB 客户端
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # 获取或创建集合
        try:
            self.collection = self.client.get_collection(collection_name)
        except Exception:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
            )
        
        # LangChain 封装的 Chroma 向量存储（用于高级检索）
        self.vector_store = Chroma(
            client=self.client,
            collection_name=collection_name,
            embedding_function=self.embeddings
        )
    
    def add_documents(
        self,
        documents: List[Document],
        batch_size: int = 100
    ) -> List[str]:
        """
        批量添加文档到向量库
        
        Args:
            documents: Document对象列表（包含page_content和metadata）
            batch_size: 每批处理的文档数，防止内存溢出
            
        Returns:
            文档ID列表
        """
        doc_ids = []
        
        # 分批处理，企业级数据量可能很大
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            
            # 为每个文档生成唯一ID（基于内容哈希，避免重复入库）
            ids = []
            for doc in batch:
                content_hash = hashlib.md5(
                    doc.page_content.encode("utf-8")
                ).hexdigest()[:16]
                doc_id = f"{doc.metadata.get('source', 'unknown')}_{content_hash}"
                ids.append(doc_id)
            
            # 添加到向量库
            self.vector_store.add_documents(documents=batch, ids=ids)
            doc_ids.extend(ids)
            
        return doc_ids
    
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_dict: Optional[Dict] = None
    ) -> List[Document]:
        """
        相似度检索：找到与查询最相关的文档
        
        Args:
            query: 用户查询（如"季度销售报告模板"）
            k: 返回最相关的k个文档
            filter_dict: 元数据过滤条件（如{"report_type": "quarterly"}）
            
        Returns:
            相关文档列表，按相似度排序
            
        企业场景：
        -------
        业务经理说"帮我写个季度汇报"，系统检索到：
        - Q1季度报告模板（相似度0.92）
        - Q2季度报告模板（相似度0.89）
        - 年度总结报告（相似度0.75）
        然后自动参考这些模板的结构和内容生成新报告
        """
        results = self.vector_store.similarity_search(
            query=query,
            k=k,
            filter=filter_dict
        )
        return results
    
    def delete_by_source(self, source: str) -> None:
        """
        按来源删除文档（用于更新模板时清理旧版本）
        
        企业场景：当报告模板更新后，需要删除旧版本，避免检索到过期内容
        """
        try:
            self.collection.delete(where={"source": source})
        except Exception as e:
            print(f"删除文档失败: {e}")
    
    def get_collection_stats(self) -> Dict:
        """获取向量库统计信息"""
        count = self.collection.count()
        return {
            "total_documents": count,
            "collection_name": self.collection_name,
            "persist_directory": self.persist_directory
        }


def get_embedding_service() -> ReportEmbeddingService:
    """
    工厂函数：获取Embedding服务单例
    
    为什么用单例？
    -------------
    Embedding模型加载很耗资源（内存+时间），整个应用只初始化一次，
    后续所有请求复用同一个实例。这是企业级应用的标准做法。
    """
    if not hasattr(get_embedding_service, "_instance"):
        get_embedding_service._instance = ReportEmbeddingService()
    return get_embedding_service._instance


print("✅ embeddings.py 编写完成")
