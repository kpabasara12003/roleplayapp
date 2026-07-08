from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    digitalocean_bge_key: str = ""
    digitalocean_bge_url: str = ""
    llm_api_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = 512
    llm_temperature: float = 0.75
    nats_url: str = ""
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
