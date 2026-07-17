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
    # Подробные логи: webhook → update → исходящие ответы (диагностика «бот молчит в группе»). В prod можно выключить.
    telegram_trace_log: bool = Field(True, alias="TELEGRAM_TRACE_LOG")
    # Дублировать каждую команду (/...) в ЛС админам (и опционально автору) — см. TELEGRAM_COMMAND_DEBUG_DM_INCLUDE_SENDER
    telegram_command_debug_dm: bool = Field(False, alias="TELEGRAM_COMMAND_DEBUG_DM")
    telegram_command_debug_dm_include_sender: bool = Field(True, alias="TELEGRAM_COMMAND_DEBUG_DM_INCLUDE_SENDER")
    # Базовый URL Bot API через Cloudflare Worker (путь включает секретный префикс). Имеет приоритет над TELEGRAM_BOT_PROXY.
    # Пример: https://my-worker.xxx.workers.dev/myRandomPrefix
    telegram_api_base_url: str | None = Field(None, alias="TELEGRAM_API_BASE_URL")
    # JWKS для Armory OIDC login; если не задан — берётся TELEGRAM_API_BASE_URL/oauth/.well-known/jwks.json
    telegram_oidc_jwks_url: str | None = Field(None, alias="TELEGRAM_OIDC_JWKS_URL")
    # Исходящие запросы Bot API только через прокси (SOCKS5/HTTP). Пример: socks5://user:pass@host:1080
    telegram_bot_proxy: str | None = Field(None, alias="TELEGRAM_BOT_PROXY")
    # Абсолютный потолок (с) на скачивание одного файла (tavern BGM); per-chunk read — ниже.
    telegram_file_download_timeout: int = Field(600, alias="TELEGRAM_FILE_DOWNLOAD_TIMEOUT")
    telegram_file_download_read_timeout: int = Field(60, alias="TELEGRAM_FILE_DOWNLOAD_READ_TIMEOUT")
    webhook_drop_pending: bool = Field(True, alias="WEBHOOK_DROP_PENDING")
    telegram_update_mode: str = Field("webhook", alias="TELEGRAM_UPDATE_MODE",
                                       description="webhook|polling — polling bypasses VPS inbound network issues")
    webapp_menu_button_text: str = Field("Играть", alias="WEBAPP_MENU_BUTTON_TEXT")

    # db / cache
    postgres_dsn: str = Field(..., alias="POSTGRES_DSN")
    db_pool_size: int = Field(5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(10, alias="DB_MAX_OVERFLOW")
    db_pool_pre_ping: bool = Field(True, alias="DB_POOL_PRE_PING")
    redis_url: str = Field(..., alias="REDIS_URL")
    # inline = asyncio loops in API; worker = Dramatiq+scheduler only; dual = both (shadow)
    background_mode: str = Field("inline", alias="BACKGROUND_MODE")
    # Process role for LLM offload: api | gameplay | llm
    worker_role: str = Field("api", alias="WORKER_ROLE")
    llm_worker_enabled: bool = Field(False, alias="LLM_WORKER_ENABLED")
    # Debounce PlayerTelegramActivityMiddleware DB writes (seconds).
    player_activity_debounce_seconds: int = Field(300, alias="PLAYER_ACTIVITY_DEBOUNCE_SECONDS")
    # Log P50/P95 for group_message_damage and LLM (Stage 1 baseline; see docs/STAGE1_INFRA.md).
    perf_metrics_enabled: bool = Field(False, alias="PERF_METRICS_ENABLED")

    # --- OpenRouter: текстовые модели (OPENROUTER_MODEL, OPENROUTER_MODEL_HIRE); image → ROUTERAI_MODEL_IMAGE ---
    openrouter_api_key: str | None = Field(None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field("https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_model: str = Field("openrouter/healer-alpha", alias="OPENROUTER_MODEL")
    openrouter_model_hire: str | None = Field(None, alias="OPENROUTER_MODEL_HIRE")
    # Legacy; image generation uses ROUTERAI_MODEL_IMAGE only (see get_image_model in llm_client).
    openrouter_model_image: str = Field("sourceful/riverflow-v2-fast", alias="OPENROUTER_MODEL_IMAGE")

    # RouterAI: primary text provider + fallback при HTTP 402 от OpenRouter (OpenAI-compatible API)
    routerai_api_key: str | None = Field(None, alias="ROUTERAI_API_KEY")
    routerai_base_url: str = Field("https://routerai.ru/api/v1", alias="ROUTERAI_BASE_URL")
    routerai_model: str | None = Field(None, alias="ROUTERAI_MODEL")
    routerai_model_image: str = Field(
        "google/gemini-3.1-flash-lite-image",
        alias="ROUTERAI_MODEL_IMAGE",
    )

    # AI presets (RouterAI fusion)
    ai_presets_path: str = Field("config/ai_presets.yaml", alias="AI_PRESETS_PATH")
    ai_default_preset: str = Field("fast", alias="AI_DEFAULT_PRESET")
    ai_preset_narrative: str = Field("fast", alias="AI_PRESET_NARRATIVE")
    ai_preset_gd: str = Field("gd_narrative", alias="AI_PRESET_GD")
    ai_preset_balance: str = Field("expert", alias="AI_PRESET_BALANCE")
    ai_preset_architect: str = Field("architect", alias="AI_PRESET_ARCHITECT")

    # Image API (опционально; альтернатива OpenRouter для портретов наёмниц)
    together_api_key: str | None = Field(None, alias="TOGETHER_API_KEY")
    replicate_api_token: str | None = Field(None, alias="REPLICATE_API_TOKEN")

    # networking
    host: str = Field("0.0.0.0", alias="HOST")
    port: int = Field(8000, alias="PORT")

    # Absolute repo root for admin writes to static/ (optional; see waifu_bot.paths.repository_root)
    repo_root: str | None = Field(None, alias="REPO_ROOT")

    # Browser dev bypass: when DEV_BROWSER_TOKEN is set, ?devPlayerId=N&devToken=<token> works in any APP_ENV.
    dev_browser_token: str | None = Field(None, alias="DEV_BROWSER_TOKEN")

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
    # Legacy GD (удалён): переменные оставлены, чтобы старые .env не ломали загрузку настроек
    gd_skip_activity_check: bool = Field(False, alias="GD_SKIP_ACTIVITY_CHECK")
    gd_dev_admin_any_chat: bool = Field(False, alias="GD_DEV_ADMIN_ANY_CHAT")

    # Armory web portal (browser, not Telegram WebApp)
    armory_session_secret: str | None = Field(None, alias="ARMORY_SESSION_SECRET")
    armory_cookie_domain: str | None = Field(None, alias="ARMORY_COOKIE_DOMAIN")
    armory_public_origin: str = Field("https://shimmirpgbot.ru", alias="ARMORY_PUBLIC_ORIGIN")
    armory_oidc_redirect_uri: str | None = Field(None, alias="ARMORY_OIDC_REDIRECT_URI")
    bot_username: str | None = Field(None, alias="BOT_USERNAME")
    telegram_oidc_client_id: str | None = Field(None, alias="TELEGRAM_OIDC_CLIENT_ID")


    # Desktop Electron interim auth (email/Telegram JWT via X-Desktop-Session)
    desktop_session_secret: str | None = Field(None, alias="DESKTOP_SESSION_SECRET")
    desktop_oidc_redirect_uri: str | None = Field(None, alias="DESKTOP_OIDC_REDIRECT_URI")
    desktop_session_ttl_days: int = Field(30, alias="DESKTOP_SESSION_TTL_DAYS")

    # Mobile Google Sign-In (activity client)
    google_client_id: str | None = Field(None, alias="GOOGLE_CLIENT_ID")

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

    def is_admin(self, tg_id: int) -> bool:
        """Check if Telegram user id is an administrator."""
        legacy_admin = 305174198
        return tg_id in self.admin_ids or tg_id == legacy_admin

    @property
    def armory_session_key(self) -> str:
        """Secret for Armory JWT sessions; falls back to webhook_secret in dev."""
        if self.armory_session_secret:
            return self.armory_session_secret
        if self.environment in ("dev", "testing"):
            return self.webhook_secret
        raise ValueError("ARMORY_SESSION_SECRET is required in production")
    @property
    def desktop_session_key(self) -> str:
        """Secret for desktop Electron JWT sessions (X-Desktop-Session)."""
        if self.desktop_session_secret:
            return self.desktop_session_secret
        if self.armory_session_secret:
            return self.armory_session_secret
        if self.environment in ("dev", "testing", "stage"):
            return self.webhook_secret
        raise ValueError("DESKTOP_SESSION_SECRET is required in production")



settings = Settings()

