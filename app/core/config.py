from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # LLM 设置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    SILICONFLOW_VL_MODEL: str = "Qwen/Qwen3-VL-32B-Thinking"  # 默认视觉模型

    # 飞书设置
    FEISHU_APP_ID: Optional[str] = None
    FEISHU_APP_SECRET: Optional[str] = None
    FEISHU_ENCRYPT_KEY: Optional[str] = None
    FEISHU_VERIFICATION_TOKEN: Optional[str] = None
    FEISHU_BITABLE_APP_TOKEN: Optional[str] = None
    FEISHU_BITABLE_TABLE_ID: Optional[str] = None

    # 数据库设置
    DATABASE_URL: str = "sqlite+aiosqlite:///./sql_app.db"

    # 应用设置
    PORT: int = 8001
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "DEBUG"

    # Redis 设置
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
