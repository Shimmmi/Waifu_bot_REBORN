#!/usr/bin/env python3
"""Generate content via AI architect preset (RouterAI fusion_roles)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from waifu_bot.core.config import settings  # noqa: E402
from waifu_bot.services.ai_service import generate as ai_generate  # noqa: E402
from waifu_bot.services.llm_client import has_text_llm_configured  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    if not has_text_llm_configured():
        print("ROUTERAI_API_KEY is not configured", file=sys.stderr)
        return 1

    if args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read()
    else:
        print("Provide --file or pipe prompt via stdin", file=sys.stderr)
        return 1

    prompt = prompt.strip()
    if not prompt:
        print("Empty prompt", file=sys.stderr)
        return 1

    preset = args.preset or settings.ai_preset_architect
    text = await ai_generate(
        prompt,
        preset=preset,
        caller="ai-architect-cli",
        timeout_sec=args.timeout,
        max_tokens=args.max_tokens,
        post_process_rhythm=False,
    )
    if not text:
        print("Generation failed", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=None, help="Input prompt file")
    parser.add_argument("--output", type=Path, default=None, help="Write result to file")
    parser.add_argument("--preset", default=None, help="Override preset (default: architect)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
