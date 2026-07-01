"""Import broker then register all actors."""
from __future__ import annotations

import waifu_bot.worker.broker  # noqa: F401

from waifu_bot.worker.actors import gameplay, llm  # noqa: F401
