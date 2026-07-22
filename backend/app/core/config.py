"""
配置管理模块 (core/config.py)

为什么需要这个文件？
===================
企业级项目里，配置分散在各处是灾难：
- 数据库密码写在代码里 → 提交Git泄露
- 开发用localhost，上线忘改 → 服务崩了
- 不同环境配置不一样 → 每次部署手动改

解决方案：
- 所有配置集中在这里
- 从环境变量读取（.env文件）
- 支持多环境（开发/测试/生产）
- 类型安全（Pydantic校验）

使用方式：
    from app.core.config import settings
    print(settings.DATABASE_URL)
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用配置类

    继承 BaseSettings 的好处：
    1. 自动从环境变量读取
    2. 自动类型转换和校验
    3. 缺失必填项时启动报错（早发现早解决）
    """

    # Pydantic V2 配置方式
    model_config = SettingsConfigDict(
        env_file=".env",           # 从 .env 文件加载
        env_file_encoding="utf-8",
        case_sensitive=False,       # 环境变量不区分大小写
        extra="ignore",             # 忽略未知配置项（不报错）
    )

    # ============================================================
    # 应用基础配置
    # ============================================================
    APP_NAME: str = Field(default="Multi-Agent Platform", description="应用名称")
    APP_VERSION: str = Field(default="0.1.0", description="应用版本")
    DEBUG: bool = Field(default=False, description="调试模式")
    ENV: str = Field(default="development", description="运行环境")

    # ============================================================
    # API服务配置
    # ============================================================
    HOST: str = Field(default="0.0.0.0", description="监听地址")
    PORT: int = Field(default=8000, description="监听端口")

    # ============================================================
    # 安全配置（⭐面试常问）
    # ============================================================
    # JWT密钥：用于签名令牌，泄露则任何人可伪造身份
    SECRET_KEY: str = Field(
        default="change-me-in-production",
        description="JWT签名密钥",
    )
    # 令牌过期时间：太短用户体验差，太长安全性低
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="JWT令牌过期时间(分钟)",
    )

    # ============================================================
    # LLM配置
    # ============================================================
    OPENAI_API_KEY: str = Field(description="OpenAI API密钥")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="默认模型")
    OPENAI_BASE_URL: Optional[str] = Field(
        default=None,
        description="API基础地址（用于代理或国产模型）",
    )

    # ============================================================
    # 数据库配置
    # ============================================================
    MYSQL_URL: str = Field(description="MySQL连接URL")
    MYSQL_POOL_SIZE: int = Field(default=10, description="连接池大小")
    MYSQL_MAX_OVERFLOW: int = Field(default=20, description="连接池溢出上限")

    # ============================================================
    # Redis配置
    # ============================================================
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis连接URL")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis密码")

    # ============================================================
    # ChromaDB配置
    # ============================================================
    CHROMA_PERSIST_DIR: str = Field(
        default="./data/chroma",
        description="ChromaDB持久化目录",
    )
    CHROMA_COLLECTION_NAME: str = Field(
        default="report_templates",
        description="向量集合名称",
    )

    # ============================================================
    # MCP配置
    # ============================================================
    MCP_DB_SERVER_PORT: int = Field(default=8001, description="数据库MCP服务端口")
    MCP_PYTHON_SERVER_PORT: int = Field(default=8002, description="Python MCP服务端口")

    # ============================================================
    # 校验器（⭐Pydantic的强大之处）
    # ============================================================
    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """
        校验JWT密钥强度

        为什么需要？
        - 开发环境可能用弱密钥
        - 上线前必须提醒更换
        """
        if v == "change-me-in-production":
            # 不是报错，是警告（开发环境允许）
            import warnings
            warnings.warn(
                "⚠️  你正在使用默认JWT密钥！生产环境必须更换！",
                RuntimeWarning,
            )
        if len(v) < 32:
            raise ValueError("JWT密钥长度必须至少32位")
        return v

    @field_validator("ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        """校验环境名称"""
        allowed = {"development", "testing", "production", "staging"}
        if v not in allowed:
            raise ValueError(f"ENV必须是以下之一: {allowed}")
        return v

    @property
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self.ENV == "production"

    @property
    def is_development(self) -> bool:
        """是否为开发环境"""
        return self.ENV == "development"


# ============================================================
# 单例模式：整个应用共享同一个配置实例
# 
# 为什么用 @lru_cache？
# - 配置读取一次就够了，不用每次都读文件
# - 保证全局唯一，避免不同地方配置不一致
# ============================================================
@lru_cache
def get_settings() -> Settings:
    """获取配置实例（单例）"""
    return Settings()


# 全局导出：其他地方直接 import settings 使用
settings = get_settings()


# 调试输出（直接运行此文件时）
if __name__ == "__main__":
    print(f"应用名称: {settings.APP_NAME}")
    print(f"应用版本: {settings.APP_VERSION}")
    print(f"运行环境: {settings.ENV}")
    print(f"调试模式: {settings.DEBUG}")
    print(f"API端口: {settings.PORT}")
    print(f"LLM模型: {settings.OPENAI_MODEL}")
    print(f"是否为生产环境: {settings.is_production}")
