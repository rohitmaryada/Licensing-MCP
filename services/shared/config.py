from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    LICENSING_PG_URL: str
    SERVICE_NAME: str = "UNKNOWN"
    LOG_LEVEL: str = "INFO"


settings = Settings()
