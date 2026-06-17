"""应用配置"""
import os
import warnings
from pydantic_settings import BaseSettings
from typing import List

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://erp_user:erp_password@localhost:3306/erp_db?charset=utf8mb4"
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "deepseek-chat"
    AI_BASE_URL: str = "https://api.deepseek.com/v1"
    AI_AGENT_ENABLED: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # ── 预测服务配置 ──
    FORECAST_ENABLED: bool = True
    FORECAST_HORIZON_DAYS: int = 30
    FORECAST_MIN_DATA_DAYS: int = 30
    FORECAST_CACHE_TTL_HOURS: int = 1
    FORECAST_MODEL: str = "auto"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = _env_path


settings = Settings()

if not settings.SECRET_KEY:
    warnings.warn(
        "SECRET_KEY 未设置！请在 .env 中配置 SECRET_KEY，否则 JWT 可被伪造。",
        stacklevel=2,
    )
