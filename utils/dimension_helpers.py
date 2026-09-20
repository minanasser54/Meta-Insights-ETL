import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from utils.logging import logger


def with_updated_filter(params: dict, since: datetime | None) -> dict:
    params = dict(params)
    if since is not None:
        # Stored/computed values are naive UTC, so tag as UTC before converting.
        since_ts = int(since.replace(tzinfo=timezone.utc).timestamp())
        params["filtering"] = json.dumps([
            {"field": "updated_time", "operator": "GREATER_THAN", "value": since_ts}
        ])
    return params


def as_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        parsed = pd.to_datetime(value, unit="s", utc=True, errors="coerce")
    else:
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().replace(tzinfo=None)


def as_json(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def bare_account_id(account_id: Any) -> str | None:
    if account_id is None:
        return None
    return str(account_id).removeprefix("act_")


def fetch_for_parents(client, parent_ids: list[str], endpoint_template: str, token: str, params: dict) -> list[dict]:
    rows: list[dict] = []
    total = len(parent_ids)
    for index, parent_id in enumerate(parent_ids, start=1):
        try:
            for page in client.paginate(endpoint_template.format(parent_id=parent_id), token, params):
                rows.extend(page)
        except Exception:
            logger.exception("API fetch failed for parent_id=%s", parent_id)
            continue
        if index == total or index % 100 == 0:
            logger.info("Processed %d/%d parent IDs", index, total)
    return rows
