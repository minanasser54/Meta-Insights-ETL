from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import Connection, Engine, desc, insert
from sqlalchemy.orm import Session

from config import get_conf
from facts.fact_helpers import daily_window, date_key, log_fact_window, page_tokens
from models import Post, PostInsightsDaily
from utils.dbloader import open_session, resolve_token
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


METRICS = "post_activity_by_action_type,post_reactions_by_type_total"
OUTPUT_COLUMNS = ["PostID", "Date", "DateKey", "Shares", "Reactions", "Comments", "LoadDate"]


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


def _fetch_post(client: MetaClient, page_token: str, post_id: str, snapshot_date: date) -> list[dict]:
    rows: list[dict] = []
    params = {"metric": METRICS, "period": "lifetime", "limit": 100}
    for page in client.paginate(f"/{post_id}/insights", page_token, params):
        for metric in page:
            metric_name = metric.get("name")
            values = metric.get("values") or []
            value = values[-1].get("value") if values else metric.get("value")
            if value is None:
                continue
            rows.append({
                "PostID": post_id,
                "Date": snapshot_date,
                "MetricName": metric_name,
                "Value": value,
            })
    return rows


def _extract(
    client: MetaClient,
    user_token: str,
    posts: list[dict],
    snapshot_date: date,
    max_workers: int = 10,
) -> list[dict]:
    # post_activity_by_action_type and post_reactions_by_type_total only support
    # period=lifetime, and Meta ignores `since`/`until` for lifetime-period metrics
    # (confirmed empirically: identical values regardless of `until`). There is no
    # way to retrieve a historical value for a past date — lifetime always means
    # "the cumulative total right now". So we fetch each post's current lifetime
    # totals once per run and label the row with today's snapshot date. Running
    # this job daily and inserting (never overwriting) builds a true day-by-day
    # history of cumulative totals going forward.
    #
    # Fetching is I/O-bound (waiting on HTTP), so posts are fetched concurrently
    # via a thread pool. MetaClient shares one requests.Session, which is safe
    # for concurrent use.
    tokens = page_tokens(client, user_token)
    rows: list[dict] = []
    total = len(posts)
    completed = 0

    def task(post: dict) -> list[dict]:
        post_id = str(post["PostID"])
        page_id = str(post["PageID"])
        page_token = tokens.get(page_id) or get_conf().page_access_token
        if not page_token:
            logger.warning("Skipping PostInsightsDaily because no Page access token exists for PageID=%s", page_id)
            return []
        try:
            return _fetch_post(client, page_token, post_id, snapshot_date)
        except Exception:
            logger.exception("PostInsightsDaily fetch failed for PostID=%s", post_id)
            return []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(task, post): post for post in posts}
        for future in as_completed(futures):
            rows.extend(future.result())
            completed += 1
            if completed == total or completed % 100 == 0:
                logger.info("Processed %d/%d posts for PostInsightsDaily", completed, total)
    return rows


def _transform(raw_rows: list[dict], load_date: datetime) -> pd.DataFrame:
    totals: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        post_id = row.get("PostID")
        day = row.get("Date")
        if not post_id or not day:
            continue
        totals.setdefault(post_id, {"Date": day, "Shares": None, "Reactions": None, "Comments": None})
        metric_name = row.get("MetricName") or ""
        value = row.get("Value")
        if metric_name == "post_reactions_by_type_total":
            explicit_total = _find_metric_value(value, {"total", "total_count"})
            totals[post_id]["Reactions"] = explicit_total if explicit_total is not None else _sum_numeric_leaves(value)
        elif metric_name == "post_activity_by_action_type":
            totals[post_id]["Shares"] = _find_metric_value(value, {"share", "shares"})
            totals[post_id]["Comments"] = _find_metric_value(value, {"comment", "comments"})

    rows = []
    for post_id, values in totals.items():
        day = values["Date"]
        rows.append({
            "PostID": post_id,
            "Date": day,
            "DateKey": date_key(day),
            "Shares": values["Shares"],
            "Reactions": values["Reactions"],
            "Comments": values["Comments"],
            "LoadDate": load_date,
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).reset_index(drop=True)


def _to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to insert-ready records, replacing pandas NaN with
    real None so SQL Server receives NULL instead of silently coercing NaN
    into a sentinel int (e.g. -9223372036854775808 for BIGINT columns)."""
    return [
        {key: (None if pd.isna(value) else value) for key, value in record.items()}
        for record in df.to_dict(orient="records")
    ]


def fact_post_insights_daily(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    since: str | None = None,
    until: str | None = None,
    post_mode: str | None = None,
    post_limit: int | None = None,
    max_workers: int = 10,
) -> int:
    since, until = daily_window(since, until)
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        settings = get_conf()
        mode = (post_mode or settings.post_insights_mode).lower()
        limit = post_limit if post_limit is not None else settings.post_insights_limit
        until_date = date.fromisoformat(until)

        base_columns = (Post.PostID, Post.PageID, Post.CreatedTime)
        base_filters = (Post.PostID.is_not(None), Post.PageID.is_not(None))

        if mode == "recent":
            # The latest `limit` posts that existed as of the snapshot day (until).
            post_query = (
                Post.__table__.select()
                .with_only_columns(*base_columns)
                .where(*base_filters, Post.CreatedTime <= until_date)
                .order_by(desc(Post.CreatedTime))
                .limit(limit)
            )
        else:
            post_query = (
                Post.__table__.select()
                .with_only_columns(*base_columns)
                .where(*base_filters)
                .order_by(desc(Post.CreatedTime))
            )
        posts = [dict(row) for row in session.execute(post_query).mappings().all()]

        access_token = token or resolve_token(session)
        logger.info("PostInsightsDaily mode=%s limit=%s snapshot_date=%s", mode, limit, until)
        log_fact_window("PostInsightsDaily", since, until, len(posts))

        raw_rows = _extract(client, access_token, posts, until_date, max_workers=max_workers)
        if not raw_rows:
            logger.warning("PostInsightsDaily returned no values for the selected posts on %s.", until)
        load_date = datetime.now()
        rows = _transform(raw_rows, load_date)

        if rows.empty:
            logger.info("No rows to insert into PostInsightsDaily")
            return 0

        session.execute(insert(PostInsightsDaily), _to_records(rows))
        session.commit()
        return len(rows)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    fact_post_insights_daily()
