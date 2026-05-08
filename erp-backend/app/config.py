"""应用配置"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://erp_user:erp_password@localhost:3306/erp_db?charset=utf8mb4"
    SECRET_KEY: str = "change-this-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4"
    AI_BASE_URL: str = "https://api.deepseek.com/v1"
    AI_AGENT_ENABLED: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
