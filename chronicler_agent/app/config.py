import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://localhost:5432/roleplay"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    digitalocean_bge_key: str = ""
    digitalocean_bge_url: str = "https://inference.do-ai.run/v1/embeddings"
    nats_url: str = "nats://localhost:4222"
    nats_user: str = ""
    nats_password: str = ""
    log_level: str = "INFO"
    summarize_every_n: int = 10  # Summarize every N messages

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
