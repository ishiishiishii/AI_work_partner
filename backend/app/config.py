from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = "http://host.docker.internal:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = (
        "postgresql://postgres:postgres@host.docker.internal:54322/postgres"
    )
    api_cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


settings = Settings()
