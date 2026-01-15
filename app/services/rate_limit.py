from __future__ import annotations

import time
from datetime import datetime, timezone

import redis


KEY_NEXT_ALLOWED = "whatsapp:next_allowed_at"  # unix timestamp seconds


def get_next_allowed(r: redis.Redis) -> int:
    raw = r.get(KEY_NEXT_ALLOWED)
    return int(raw) if raw else 0


def set_next_allowed(r: redis.Redis, unix_ts: int) -> None:
    r.set(KEY_NEXT_ALLOWED, str(unix_ts))


def wait_for_slot(r: redis.Redis, min_interval_seconds: int) -> None:
    while True:
        now = int(datetime.now(timezone.utc).timestamp())
        next_allowed = get_next_allowed(r)
        if now >= next_allowed:
            return
        sleep_for = max(1, next_allowed - now)
        time.sleep(sleep_for)
