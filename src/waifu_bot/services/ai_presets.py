"""Load and validate AI preset config from ai_presets.yaml."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, Field, model_validator

from waifu_bot.core.config import settings

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PRESETS_PATH = _ROOT / "config" / "ai_presets.yaml"

_cache_path: Path | None = None
_cache_mtime: float | None = None
_cache_config: AiPresetsConfig | None = None


class PresetDefaults(BaseModel):
    provider: str = "routerai"
    timeout_sec: float = 60.0
    max_tokens: int = 512
    temperature: float = 0.85


class SinglePreset(BaseModel):
    mode: Literal["single"] = "single"
    model: str
    fallback_model: str | None = None
    post_process: Literal["none", "rhythm_rewrite"] | None = None


class FusionPreset(BaseModel):
    mode: Literal["fusion"] = "fusion"
    parallel_experts: bool = True
    experts: list[str]
    judge: str
    judge_prompt: str = (
        "Сравни ответы экспертов. Выбери лучшее, исправь ошибки, верни финальный ответ."
    )
    fallback_model: str | None = None

    @model_validator(mode="after")
    def _non_empty_experts(self) -> FusionPreset:
        if not self.experts:
            raise ValueError("fusion preset requires at least one expert model")
        return self


class FusionRoleSpec(BaseModel):
    model: str
    system: str


class FusionRolesJudge(BaseModel):
    model: str
    system: str = "На основе мнений экспертов сформируй итоговое решение."


class FusionRolesPreset(BaseModel):
    mode: Literal["fusion_roles"] = "fusion_roles"
    roles: dict[str, FusionRoleSpec]
    judge: FusionRolesJudge
    fallback_model: str | None = None

    @model_validator(mode="after")
    def _non_empty_roles(self) -> FusionRolesPreset:
        if not self.roles:
            raise ValueError("fusion_roles preset requires at least one role")
        return self


PresetConfig = Annotated[
    Union[SinglePreset, FusionPreset, FusionRolesPreset],
    Field(discriminator="mode"),
]


class AiPresetsConfig(BaseModel):
    defaults: PresetDefaults = Field(default_factory=PresetDefaults)
    presets: dict[str, PresetConfig]

    @model_validator(mode="after")
    def _has_presets(self) -> AiPresetsConfig:
        if not self.presets:
            raise ValueError("ai_presets.yaml must define at least one preset")
        return self


def _resolve_presets_path(path: str | Path | None = None) -> Path:
    raw = path or getattr(settings, "ai_presets_path", None) or str(_DEFAULT_PRESETS_PATH)
    p = Path(raw)
    if not p.is_absolute():
        p = _ROOT / p
    return p


def load_ai_presets(path: str | Path | None = None, *, force_reload: bool = False) -> AiPresetsConfig:
    """Load ai_presets.yaml with mtime-based cache."""
    global _cache_path, _cache_mtime, _cache_config

    resolved = _resolve_presets_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"AI presets config not found: {resolved}")

    mtime = resolved.stat().st_mtime
    if (
        not force_reload
        and _cache_config is not None
        and _cache_path == resolved
        and _cache_mtime == mtime
    ):
        return _cache_config

    with open(resolved, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = AiPresetsConfig.model_validate(raw)
    _cache_path = resolved
    _cache_mtime = mtime
    _cache_config = config
    logger.debug("[ai_presets] loaded %d presets from %s", len(config.presets), resolved)
    return config


def resolve_preset(name: str, path: str | Path | None = None) -> tuple[PresetConfig, PresetDefaults]:
    """Return preset config merged with defaults."""
    config = load_ai_presets(path)
    key = (name or "").strip()
    if not key:
        key = getattr(settings, "ai_default_preset", "fast") or "fast"
    preset = config.presets.get(key)
    if preset is None:
        available = ", ".join(sorted(config.presets))
        raise KeyError(f"Unknown AI preset '{key}'. Available: {available}")
    return preset, config.defaults


def list_preset_names(path: str | Path | None = None) -> list[str]:
    return sorted(load_ai_presets(path).presets.keys())
