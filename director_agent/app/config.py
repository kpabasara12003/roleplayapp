from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    nats_url: str = ""
    nats_user: str = ""
    nats_password: str = ""
    log_level: str = "INFO"

    llm_api_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = 512
    llm_temperature: float = 0.75

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra="ignore"

settings = Settings()
