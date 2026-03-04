from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    archer_base_url: str = "https://api.archeraffiliates.com"
    archer_username: str = ""
    archer_password: str = ""
    archer_api_key: str = ""
    archer_reports_endpoint: str = ""  # blank = auto-discover

    google_ads_customer_id: str = ""
    database_url: str = "sqlite:///./ads_dashboard.db"
    backend_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
