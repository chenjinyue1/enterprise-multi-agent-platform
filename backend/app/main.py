"""
FastAPI 应用入口 (app/main.py)

这是整个后端服务的"大门"。
所有HTTP请求都从这里进入，然后被路由到不同的处理函数。

启动命令：
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

访问文档：
    http://localhost:8000/docs  (Swagger UI，自动生成)
    http://localhost:8000/redoc (ReDoc，另一种文档风格)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


# ============================================================
# 生命周期管理（⭐企业级必备）
# ============================================================
# 
# 为什么需要 lifespan？
# - 应用启动时：连接数据库、加载模型、预热缓存
# - 应用关闭时：关闭连接、释放资源、保存状态
# 
# 不用 @app.on_event("startup") 的原因：
# - lifespan 是新版 FastAPI 推荐方式，支持异步上下文管理
# - 更优雅，资源自动清理
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    yield 之前：启动逻辑
    yield 之后：关闭逻辑
    """
    # ===== 启动阶段 =====
    print(f"🚀 启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"📍 环境: {settings.ENV}")
    print(f"🤖 LLM模型: {settings.OPENAI_MODEL}")

    # TODO: 后续板块会在这里添加：
    # - 连接MySQL
    # - 连接Redis
    # - 加载ChromaDB
    # - 初始化MCP客户端

    print("✅ 服务启动完成！")
    print(f"📖 API文档: http://{settings.HOST}:{settings.PORT}/docs")

    yield  # 应用运行期间

    # ===== 关闭阶段 =====
    print("🛑 服务正在关闭...")
    # TODO: 释放资源
    print("✅ 服务已安全关闭")


# ============================================================
# 创建 FastAPI 应用实例
# ============================================================
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="企业智能数据分析多智能体平台 API",
    # 文档配置
    docs_url="/docs" if not settings.is_production else None,  # 生产环境关闭文档
    redoc_url="/redoc" if not settings.is_production else None,
    # 生命周期
    lifespan=lifespan,
)

# ============================================================
# CORS 跨域配置（⭐前后端分离必备）
# ============================================================
# 
# 什么是 CORS？
# - 浏览器安全策略：默认不允许网页向不同域名发请求
# - 前端在 localhost:5173，后端在 localhost:8000 → 不同端口 = 跨域
# - 后端需要明确告诉浏览器："我允许这个前端访问我"
# 
# 为什么 allow_origins=["*"] 只在开发用？
# - 生产环境必须指定具体域名，否则任何网站都能调你的API
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else ["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],      # 允许所有HTTP方法
    allow_headers=["*"],      # 允许所有请求头
)


# ============================================================
# 根路由：健康检查
# ============================================================
@app.get("/", tags=["Health"])
async def root():
    """
    根路径 - 服务健康检查

    用途：
    - 浏览器访问 http://localhost:8000/ 看服务是否活着
    - 负载均衡器定时ping这个接口判断服务健康
    - Kubernetes readiness probe
    """
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENV,
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    详细健康检查

    企业级监控用这个接口：
    - 检查数据库连接是否正常
    - 检查Redis连接是否正常
    - 检查LLM API是否可用

    返回 200 = 全部正常
    返回 503 = 某个依赖挂了，触发告警
    """
    # TODO: 后续板块添加依赖检查
    return {
        "status": "healthy",
        "checks": {
            "api": "ok",
            "database": "pending",    # 待实现
            "redis": "pending",       # 待实现
            "llm": "pending",         # 待实现
        },
    }


# ============================================================
# TODO: 后续板块会在这里注册路由
# ============================================================
# from app.api.v1 import auth, chat, agent
# app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
# app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
# app.include_router(agent.router, prefix="/api/v1/agent", tags=["Agent"])


# 直接运行此文件时的调试入口
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development,  # 开发模式热重载
    )
