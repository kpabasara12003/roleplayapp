import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    nats_url: str = ""
    nats_user: str = ""
    nats_password: str = ""
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra="ignore"

settings = Settings()
