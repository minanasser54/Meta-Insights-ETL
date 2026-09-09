import json
from datetime import datetime
from typing import Any

import pandas as pd

from utils.logging import logger


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