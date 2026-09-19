import json
from datetime import datetime , timedelta, timezone
from typing import Any

import pandas as pd

from utils.logging import logger


from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Overlap before each watermark so clock skew / late-propagating updates can't drop rows.
# Safe because upsert is idempotent on the key column.
UPDATED_SINCE_BUFFER = timedelta(hours=6)


def get_watermarks(session: Session, model, group_column: str, time_column: str = "UpdatedTime") -> dict[str, datetime]:
    """Latest `time_column` already loaded, per `group_column`: {str(group_value): datetime}.

    Groups with no rows (or only NULL times) are absent, which makes callers do a full fetch
    for them. On any DB error returns {} so the run falls back to a full fetch.
    """
    try:
        result = session.execute(
            select(getattr(model, group_column), func.max(getattr(model, time_column)))
            .group_by(getattr(model, group_column))
        ).all()
    except Exception:
        logger.exception("Could not read %s watermarks; falling back to full fetch", model.__tablename__)
        session.rollback()
        return {}
    watermarks: dict[str, datetime] = {}
    for group_value, max_time in result:
        if group_value is None or max_time is None:
            continue
        watermarks[bare_account_id(group_value)] = max_time
    return watermarks


def with_updated_filter(params: dict, watermark: datetime | None) -> dict:
    """Copy of params with a Meta `filtering` clause on updated_time, or unchanged if no watermark."""
    params = dict(params)  # never mutate the module-level dict
    if watermark is not None:
        # Stored values are naive UTC (see as_datetime), so tag as UTC before converting.
        since_ts = int((watermark.replace(tzinfo=timezone.utc) - UPDATED_SINCE_BUFFER).timestamp())
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
    """Coerce a value to a plain int, e.g. for INTEGER/BIGINT columns fed by API fields
    that may arrive as numeric strings. Returns None on any non-numeric or missing input.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def bare_account_id(account_id: Any) -> str | None:
    """Meta ad account IDs are addressed with an 'act_' prefix (e.g. 'act_123456') but
    every AdAccountID foreign-key column in the warehouse (AdSet, Ad, AdInsightsDaily)
    stores the bare numeric ID as BIGINT. Always route account IDs through this helper
    before writing them to any AdAccountID column so the stored value is consistent and
    castable to BIGINT downstream, regardless of which form the caller happened to have.
    """
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
