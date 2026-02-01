"""GD debug: log buffer, safe logger, snapshot manager. Used only in testing mode."""
from __future__ import annotations

import json
import logging
import os
import random
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# In-memory log buffer per chat_id (max N entries)
GD_DEBUG_LOG_MAX = 200
_gd_log_buffers: dict[int, deque[dict[str, Any]]] = {}

# Snapshot directory
SNAPSHOTS_DIR = Path(os.environ.get("GD_SNAPSHOTS_DIR", "snapshots")).resolve()
_snapshots: dict[str, dict] = {}


def push_gd_log(
    chat_id: int,
    event_type: str,
    message: str,
    *,
    user_id: int | None = None,
    **details: Any,
) -> None:
    """Append a safe log entry for this chat. user_id tags entry for /gd_logs filter."""
    if chat_id not in _gd_log_buffers:
        _gd_log_buffers[chat_id] = deque(maxlen=GD_DEBUG_LOG_MAX)
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "event": event_type,
        "message": message,
    }
    if user_id is not None:
        entry["user_id"] = user_id
    if details:
        entry["details"] = details
    _gd_log_buffers[chat_id].append(entry)


def get_gd_logs(
    chat_id: int,
    lines: int = 50,
    filter_level: str = "debug",
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Get last N log entries. filter_level: public, debug, verbose, internal.
    If user_id given, only entries where entry.get('user_id') == user_id (or no user_id tag).
    """
    buf = _gd_log_buffers.get(chat_id)
    if not buf:
        return []
    out = list(buf)[-lines:]
    if user_id is not None:
        out = [e for e in out if e.get("user_id") is None or e.get("user_id") == user_id]
    if filter_level == "public":
        out = [{k: v for k, v in e.items() if k in ("timestamp", "event", "message")} for e in out]
    return out


class SafeLogger:
    """Logger that filters output by access level (1–4)."""

    def __init__(self, user_id: int, access_level: int):
        self.user_id = user_id
        self.access_level = access_level

    def log_event(self, event_type: str, message: str, **details: Any) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "message": message,
        }
        if self.access_level >= 3:
            entry["details"] = details
        return entry


def snapshot_create(session_data: dict[str, Any], reason: str = "manual") -> str:
    """Create snapshot, return snapshot_id."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_id = f"snap_{int(time.time())}_{random.randint(1000, 9999)}"
    snap = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "session_data": session_data,
    }
    _snapshots[snapshot_id] = snap
    path = SNAPSHOTS_DIR / f"{snapshot_id}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Snapshot write failed: %s", e)
    return snapshot_id


def snapshot_list() -> list[dict[str, Any]]:
    """List available snapshots (id, timestamp, reason, size hint)."""
    result = []
    for sid, snap in _snapshots.items():
        result.append({
            "id": sid,
            "timestamp": snap.get("timestamp", ""),
            "reason": snap.get("reason", ""),
            "size_kb": round(len(json.dumps(snap)) / 1024, 1),
        })
    try:
        for p in SNAPSHOTS_DIR.glob("snap_*.json"):
            sid = p.stem
            if sid not in _snapshots:
                try:
                    with open(p, encoding="utf-8") as f:
                        snap = json.load(f)
                    _snapshots[sid] = snap
                    result.append({
                        "id": sid,
                        "timestamp": snap.get("timestamp", ""),
                        "reason": snap.get("reason", ""),
                        "size_kb": round(p.stat().st_size / 1024, 1),
                    })
                except Exception:
                    pass
    except Exception:
        pass
    result.sort(key=lambda x: x["timestamp"], reverse=True)
    return result


def snapshot_restore(snapshot_id: str) -> dict[str, Any] | None:
    """Load snapshot by id. Caller applies data to session."""
    if snapshot_id in _snapshots:
        return _snapshots[snapshot_id].get("session_data")
    path = SNAPSHOTS_DIR / f"{snapshot_id}.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                snap = json.load(f)
            _snapshots[snapshot_id] = snap
            return snap.get("session_data")
        except Exception:
            pass
    return None


def snapshot_delete(snapshot_id: str) -> bool:
    """Remove snapshot from memory and disk."""
    _snapshots.pop(snapshot_id, None)
    path = SNAPSHOTS_DIR / f"{snapshot_id}.json"
    if path.exists():
        try:
            path.unlink()
            return True
        except Exception:
            pass
    return False


def get_env_info() -> dict[str, Any]:
    """Return safe env info for /gd_env (L4)."""
    from waifu_bot.core.config import settings
    return {
        "APP_ENV": settings.environment,
        "testing_mode": settings.testing_mode,
        "dev_user_ids_count": len(settings.dev_user_ids),
        "test_chat_ids_count": len(settings.test_chat_ids),
    }
