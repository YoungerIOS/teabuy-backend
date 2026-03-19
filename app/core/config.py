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
    admin_api_key: str = "change-admin-key"
    mock_payment_callback_secret: str = "change-mock-secret"
    china_area_file: str = "app/data/area-full.json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def db_url(self) -> str:
        raw = self.database_url if self.database_url else self.supabase_db_url
        # Supabase dashboard often provides `postgresql://...`.
        # This project uses psycopg (SQLAlchemy dialect `postgresql+psycopg://`).
        if raw.startswith("postgresql://"):
            return raw.replace("postgresql://", "postgresql+psycopg://", 1)
        return raw


settings = Settings()
