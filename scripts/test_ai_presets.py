#!/usr/bin/env python3
"""Smoke-test AI presets against RouterAI (requires ROUTERAI_API_KEY)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from waifu_bot.services.ai_presets import list_preset_names, resolve_preset  # noqa: E402
from waifu_bot.services.ai_service import generate as ai_generate  # noqa: E402
from waifu_bot.services.llm_client import has_text_llm_configured  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    if args.list:
        for name in list_preset_names():
            print(name)
        return 0

    if not has_text_llm_configured():
        print("ROUTERAI_API_KEY is not configured", file=sys.stderr)
        return 1

    preset_name = args.preset
    preset, defaults = resolve_preset(preset_name)
    print(f"preset={preset_name} mode={preset.mode} timeout={defaults.timeout_sec}s")

    text = await ai_generate(
        args.prompt,
        preset=preset_name,
        caller=f"test-ai-presets-{preset_name}",
        timeout_sec=args.timeout,
        post_process_rhythm=False,
    )
    if not text:
        print("FAIL: empty response", file=sys.stderr)
        return 1

    print("OK:", text[:500].replace("\n", " "))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default="fast", help="Preset name to test")
    parser.add_argument("--prompt", default="Ответь одним предложением: что такое fusion?")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--list", action="store_true", help="List available presets")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
