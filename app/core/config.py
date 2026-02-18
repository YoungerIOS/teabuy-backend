from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TeaBuy API"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"
    supabase_db_url: str = ""
    database_url: str = ""
    jwt_secret: str = "change-me"
    jwt_access_expire_min: int = 30
    jwt_refresh_expire_days: int = 14
    payment_mode: str = "mock"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return self.supabase_db_url


settings = Settings()
