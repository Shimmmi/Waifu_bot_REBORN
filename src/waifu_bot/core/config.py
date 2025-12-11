from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # infra
    app_name: str = "waifu_bot_reborn"
    environment: str = Field("dev", alias="APP_ENV", description="dev|stage|prod")

    # telegram
    bot_token: str = Field(..., alias="BOT_TOKEN")
    webhook_secret: str = Field(..., alias="WEBHOOK_SECRET")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")
    public_base_url: AnyHttpUrl = Field(..., alias="PUBLIC_BASE_URL")

    # db / cache
    postgres_dsn: str = Field(..., alias="POSTGRES_DSN")
    redis_url: str = Field(..., alias="REDIS_URL")

    # networking
    host: str = Field("0.0.0.0", alias="HOST")
    port: int = Field(8000, alias="PORT")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, list):
            return v
        if isinstance(v, int):
            return [v]
        if not v:
            return []
        return [int(x.strip()) for x in v.split(",") if x.strip()]


settings = Settings()

