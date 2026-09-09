from datetime import date, timedelta
from typing import Any

import pandas as pd

from config import get_conf
from utils.metaclient import MetaClient


def daily_window(since: str | None = None, until: str | None = None) -> tuple[str, str]:
    if since is None and until is None:
        target = date.today() - timedelta(days=1)
        return target.isoformat(), (target + timedelta(days=1)).isoformat()
    if since is None or until is None:
        raise ValueError("since and until must be provided together")
    start = date.fromisoformat(since)
    end = date.fromisoformat(until)
    if end <= start:
        raise ValueError("until must be later than since")
    return since, until


def as_date(value: Any) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.date()


def date_key(value: date | None) -> int | None:
    return int(value.strftime("%Y%m%d")) if value else None


def page_tokens(client: MetaClient, user_token: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for page in client.paginate("/me/accounts", user_token, {"fields": "id,access_token", "limit": 100}):
        for item in page:
            if item.get("id") and item.get("access_token"):
                tokens[str(item["id"])] = str(item["access_token"])
    configured = get_conf().page_access_token
    if configured:
        for page_id in tokens:
            tokens.setdefault(page_id, configured)
    return tokens


def log_fact_window(name: str, since: str, until: str, parent_count: int) -> None:
    from utils.logging import logger

    logger.info("Extracting %s for %d parent(s), window=%s to %s", name, parent_count, since, until)
