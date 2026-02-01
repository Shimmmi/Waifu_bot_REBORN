from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


def _parse_int_list(v: str | list[int] | None) -> list[int]:
    if isinstance(v, list):
        return v
    if isinstance(v, int):
        return [v]
    if not v:
        return []
    return [int(x.strip()) for x in str(v).split(",") if x.strip()]


def _parse_access_levels(v: str | dict[int, int] | None) -> dict[int, int]:
    """Parse DEV_ACCESS_LEVELS: '123:4,456:2' -> {123: 4, 456: 2}."""
    if isinstance(v, dict):
        return v
    if not v:
        return {}
    result = {}
    for part in str(v).split(","):
        part = part.strip()
        if ":" in part:
            uid_s, level_s = part.split(":", 1)
            try:
                result[int(uid_s.strip())] = int(level_s.strip())
            except ValueError:
                pass
    return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore unknown env vars (e.g. TESTING_MODE; use APP_ENV=testing instead)
    )

    # infra
    app_name: str = "waifu_bot_reborn"
    environment: str = Field("dev", alias="APP_ENV", description="dev|stage|prod|testing")

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

    # dev/testing (only used when APP_ENV=testing)
    dev_user_ids: list[int] = Field(default_factory=list, alias="DEV_USER_IDS")
    # Один разработчик (альтернатива DEV_USER_IDS/DEV_ACCESS_LEVELS)
    dev_user_id: int | None = Field(None, alias="DEV_USER_ID")
    dev_access_level: int = Field(0, alias="DEV_ACCESS_LEVEL")
    # Сырая строка (формат "user_id:level,...") — парсится в property dev_access_levels
    dev_access_levels_raw: str = Field(default="", alias="DEV_ACCESS_LEVELS")
    # Разрешённые чаты для команд отладки (если задано — только в этих чатах). Пусто = любой чат.
    test_chat_ids: list[int] = Field(default_factory=list, alias="TEST_CHAT_IDS")
    # Один тестовый чат (альтернатива TEST_CHAT_IDS; поддерживает отрицательный id)
    test_chat_id: int | None = Field(None, alias="TEST_CHAT_ID")
    # GD: при True не требовать активность чата (4 msg/мин) и мин. кол-во игроков — для тестов
    gd_skip_activity_check: bool = Field(False, alias="GD_SKIP_ACTIVITY_CHECK")
    # GD dev: при True команды отладки (/gd_debug, /gd_test_start и т.д.) доступны только ADMIN_IDS в любом чате (без проверки TEST_CHAT_IDS)
    gd_dev_admin_any_chat: bool = Field(False, alias="GD_DEV_ADMIN_ANY_CHAT")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, v: str | list[int]) -> list[int]:
        return _parse_int_list(v)

    @field_validator("dev_user_ids", mode="before")
    @classmethod
    def _split_dev_user_ids(cls, v: str | list[int] | None) -> list[int]:
        return _parse_int_list(v)

    @field_validator("test_chat_ids", mode="before")
    @classmethod
    def _split_test_chat_ids(cls, v: str | list[int] | None) -> list[int]:
        return _parse_int_list(v)

    @property
    def dev_access_levels(self) -> dict[int, int]:
        """Парсинг DEV_ACCESS_LEVELS из строки формата 'user_id:level,...'."""
        return _parse_access_levels(getattr(self, "dev_access_levels_raw", None))

    @property
    def testing_mode(self) -> bool:
        """True when running in testing environment (dev commands allowed)."""
        return self.environment == "testing"

    def get_dev_access_level(self, user_id: int) -> int:
        """0 = no access, 1–4 = observer/test/dev/admin. Supports DEV_USER_ID/DEV_ACCESS_LEVEL."""
        allowed = set(self.dev_user_ids)
        if self.dev_user_id is not None:
            allowed.add(self.dev_user_id)
        if user_id not in allowed:
            return 0
        levels = self.dev_access_levels
        if levels:
            return levels.get(user_id, 2)
        if user_id == self.dev_user_id:
            return self.dev_access_level or 2
        return 2

    def _allowed_chat_ids(self) -> list[int]:
        """Merge TEST_CHAT_IDS and TEST_CHAT_ID (singular)."""
        ids = list(self.test_chat_ids)
        if self.test_chat_id is not None:
            ids.append(self.test_chat_id)
        return ids

    def is_test_chat_allowed(self, chat_id: int) -> bool:
        """True if dev commands are allowed in this chat. If no ids set — any chat.
        Accepts both full supergroup id (-100xxxxxxxxxx) and short form (xxxxxxxxxx).
        Supports TEST_CHAT_ID (singular) and TEST_CHAT_IDS."""
        allowed = self._allowed_chat_ids()
        if not allowed:
            return True
        if chat_id in allowed:
            return True
        # Telegram supergroup id -1004955648634 has "short" form 4955648634 in some UIs
        if chat_id < -1000000000000:
            short_id = abs(chat_id) - 1000000000000
            if short_id in allowed:
                return True
        return False

    def is_gd_dev_allowed_in_chat(self, user_id: int, chat_id: int) -> bool:
        """True if user can run GD dev commands in this chat.
        When GD_DEV_ADMIN_ANY_CHAT=True: admins can in any chat; otherwise TEST_CHAT_IDS applies."""
        if self.gd_dev_admin_any_chat and (self.admin_ids or []) and user_id in self.admin_ids:
            return True
        return self.is_test_chat_allowed(chat_id)


settings = Settings()

