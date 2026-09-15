from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import Connection, Engine, delete, desc
from sqlalchemy.orm import Session

from config import get_conf
from facts.fact_helpers import daily_window, date_key, log_fact_window, page_tokens
from models import Post, PostInsightsDaily
from utils.dbloader import open_session, resolve_token, upsert
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


METRICS = "post_activity_by_action_type,post_reactions_by_type_total"
PARAMS = {"metric": METRICS, "period": "lifetime", "limit": 100}
KEY_COLUMNS = ["PostID", "DateKey"]
OUTPUT_COLUMNS = ["PostID", "Date", "DateKey", "Shares", "Reactions", "Comments"]


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _find_metric_value(value: Any, names: set[str]) -> float | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in names:
                number = _number(child)
                if number is not None:
                    return number
            found = _find_metric_value(child, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_metric_value(child, names)
            if found is not None:
                return found
    return None


def _sum_numeric_leaves(value: Any) -> float | None:
    if isinstance(value, dict):
        numbers = [_sum_numeric_leaves(child) for child in value.values()]
        numbers = [number for number in numbers if number is not None]
        return sum(numbers) if numbers else None
    if isinstance(value, list):
        numbers = [_sum_numeric_leaves(child) for child in value]
        numbers = [number for number in numbers if number is not None]
        return sum(numbers) if numbers else None
    return _number(value)


def _extract(client: MetaClient, user_token: str, posts: list[dict], snapshot_date: str) -> list[dict]:
    tokens = page_tokens(client, user_token)
    rows: list[dict] = []
    params = dict(PARAMS)
    for index, post in enumerate(posts, start=1):
        post_id = str(post["PostID"])
        page_id = str(post["PageID"])
        page_token = tokens.get(page_id) or get_conf().page_access_token
        if not page_token:
            logger.warning("Skipping PostInsightsDaily because no Page access token exists for PageID=%s", page_id)
            continue
        try:
            for page in client.paginate(f"/{post_id}/insights", page_token, params):
                for metric in page:
                    values = metric.get("values") or []
                    if values:
                        value = values[-1].get("value")
                    else:
                        value = metric.get("value")
                    if values or value is not None:
                        rows.append({
                            "PostID": post_id,
                            "Date": date.fromisoformat(snapshot_date),
                            "MetricName": metric.get("name"),
                            "Value": value,
                        })
        except Exception:
            logger.exception("PostInsightsDaily fetch failed for PostID=%s", post_id)
            continue
        if index == len(posts) or index % 100 == 0:
            logger.info("Processed %d/%d posts for PostInsightsDaily", index, len(posts))
    return rows


def _transform(raw_rows: list[dict]) -> pd.DataFrame:
    totals: dict[tuple[str, date], dict[str, float | None]] = {}
    for row in raw_rows:
        post_id = row.get("PostID")
        day = row.get("Date")
        if not post_id or not day:
            continue
        key = (str(post_id), day)
        totals.setdefault(key, {"Shares": None, "Reactions": None, "Comments": None})
        metric_name = row.get("MetricName") or ""
        value = row.get("Value")
        if metric_name == "post_reactions_by_type_total":
            explicit_total = _find_metric_value(value, {"total", "total_count"})
            totals[key]["Reactions"] = explicit_total if explicit_total is not None else _sum_numeric_leaves(value)
        elif metric_name == "post_activity_by_action_type":
            totals[key]["Shares"] = _find_metric_value(value, {"share", "shares"})
            totals[key]["Comments"] = _find_metric_value(value, {"comment", "comments"})

    rows = []
    for (post_id, day), values in totals.items():
        rows.append({"PostID": post_id, "Date": day, "DateKey": date_key(day), **values})
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def fact_post_insights_daily(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    since: str | None = None,
    until: str | None = None,
    post_mode: str | None = None,
    post_limit: int | None = None,
) -> int:
    since, until = daily_window(since, until)
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        settings = get_conf()
        mode = (post_mode or settings.post_insights_mode).lower()
        limit = post_limit if post_limit is not None else settings.post_insights_limit
        post_query = Post.__table__.select().with_only_columns(Post.PostID, Post.PageID, Post.CreatedTime).order_by(desc(Post.CreatedTime))
        if mode == "recent":
            post_query = post_query.limit(limit)
        post_query = post_query.where(Post.PostID.is_not(None), Post.PageID.is_not(None))
        posts = session.execute(post_query).mappings().all()
        posts = [dict(row) for row in posts]
        access_token = token or resolve_token(session)
        logger.info("PostInsightsDaily mode=%s limit=%s", mode, limit)
        log_fact_window("PostInsightsDaily", since, until, len(posts))
        snapshot_date = until
        raw_rows = _extract(client, access_token, posts, snapshot_date)
        if not raw_rows:
            logger.warning(
                "PostInsightsDaily returned no lifetime values for the selected posts."
            )
        rows = _transform(raw_rows)
        session.execute(delete(PostInsightsDaily).where(PostInsightsDaily.Date >= date.fromisoformat(snapshot_date)))
        session.commit()
        return upsert(rows, PostInsightsDaily, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    fact_post_insights_daily()
