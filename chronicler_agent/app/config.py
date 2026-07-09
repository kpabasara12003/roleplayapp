import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    digitalocean_bge_key: str = ""
    digitalocean_bge_url: str = ""
    nats_url: str = ""
    nats_user: str = ""
    nats_password: str = ""
    log_level: str = "INFO"
    summarize_every_n: int = 10  # Summarize every N messages

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra="ignore"

settings = Settings()
