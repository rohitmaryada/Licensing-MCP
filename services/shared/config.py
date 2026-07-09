from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    LICENSING_PG_URL: str
    SERVICE_NAME: str = "UNKNOWN"
    LOG_LEVEL: str = "INFO"
    # Entitlement's E1 -> Activation call (the one sanctioned cross-service
    # call, B2-READS-PLAN.md §3). Docker-compose service name by default;
    # override for local (non-compose) runs.
    ACTIVATION_SERVICE_URL: str = "http://activation:8000"


settings = Settings()
