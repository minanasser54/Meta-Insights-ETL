from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from utils.logging import logger

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class FailedFetch:
    table: str
    entity_id: str
    since: str | None = None
    until: str | None = None
    error: str = ""
    attempts: int = 1
    first_failed_at: str = field(default_factory=_now)
    last_attempt_at: str = field(default_factory=_now)

    @property
    def key(self) -> tuple[str, str, str | None, str | None]:
        return (self.table, str(self.entity_id), self.since, self.until)


class RetryQueue:
    def __init__(self, path: str | Path = "retry_queue.txt", max_attempts: int = 5) -> None:
        self.path = Path(path)
        self.dead_path = self.path.with_name(self.path.stem + ".dead" + self.path.suffix)
        self.max_attempts = max_attempts
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ io
    def _read(self, path: Path | None = None) -> list[FailedFetch]:
        path = path or self.path
        if not path.exists():
            return []
        items: list[FailedFetch] = []
        with path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(FailedFetch(**json.loads(line)))
                except (ValueError, TypeError):
                    # A corrupt line must not block the whole queue.
                    logger.warning("Skipping unreadable retry-queue line %d in %s", number, path)
        return items

    def _write(self, items: Iterable[FailedFetch], path: Path | None = None) -> None:
        path = path or self.path
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(asdict(item), ensure_ascii=True) + "\n")
        os.replace(tmp, path)  # atomic on Windows and POSIX

    # ----------------------------------------------------------------- api
    def record(
        self,
        table: str,
        entity_id: str | int,
        since: str | None = None,
        until: str | None = None,
        error: BaseException | str = "",
    ) -> None:
        message = str(error)[:500]
        new = FailedFetch(table=table, entity_id=str(entity_id), since=since, until=until, error=message)
        with _LOCK:
            items = self._read()
            for existing in items:
                if existing.key == new.key:
                    existing.attempts += 1
                    existing.error = message
                    existing.last_attempt_at = _now()
                    break
            else:
                items.append(new)
            self._write(items)
        logger.warning("Queued for retry: %s entity=%s window=%s..%s", table, entity_id, since, until)

    def pending(self, table: str | None = None) -> list[FailedFetch]:
        with _LOCK:
            items = self._read()
        return [i for i in items if table is None or i.table == table]

    def resolve(self, table: str, entity_id: str | int, since: str | None = None, until: str | None = None) -> None:
        key = (table, str(entity_id), since, until)
        with _LOCK:
            items = [i for i in self._read() if i.key != key]
            self._write(items)

    def bury_exhausted(self) -> list[FailedFetch]:
        with _LOCK:
            items = self._read()
            live = [i for i in items if i.attempts < self.max_attempts]
            dead = [i for i in items if i.attempts >= self.max_attempts]
            if dead:
                self._write(self._read(self.dead_path) + dead, self.dead_path)
                self._write(live)
                logger.error(
                    "%d retry entr(y/ies) gave up after %d attempts; see %s",
                    len(dead), self.max_attempts, self.dead_path,
                )
        return dead

    def __len__(self) -> int:
        return len(self.pending())


_default_queue: RetryQueue | None = None


def get_retry_queue() -> RetryQueue:
    global _default_queue
    if _default_queue is None:
        from config import get_conf

        settings = get_conf()
        _default_queue = RetryQueue(settings.retry_queue_path, settings.retry_max_attempts)
    return _default_queue
