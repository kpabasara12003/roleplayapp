from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://localhost:5432/roleplay"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    digitalocean_bge_key: str = ""
    digitalocean_bge_url: str = "https://inference.do-ai.run/v1/embeddings"
    llm_api_url: str = "https://inference.do-ai.run/v1/chat/completions"
    llm_api_key: str = ""
    llm_model: str = "kimi-k2.6"
    llm_max_tokens: int = 512
    llm_temperature: float = 0.75
    nats_url: str = "nats://localhost:4222"
    nats_user: str = ""
    nats_password: str = ""
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    @property
    def cors_list(self) -> List[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
