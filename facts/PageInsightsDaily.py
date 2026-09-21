from datetime import date, timedelta

import pandas as pd
from sqlalchemy import Connection, Engine, delete
from sqlalchemy.orm import Session

from config import get_conf
from facts.fact_helpers import as_date, date_key, daily_window, log_fact_window, page_tokens
from models import Page, PageInsightsDaily
from utils.dbloader import open_session, resolve_token, upsert
from utils.logging import logger
from utils.metaclient import MetaClient, get_client
from utils.retry_queue import get_retry_queue
from utils.watermark import track_run


TABLE = PageInsightsDaily.__tablename__
PAGE_INSIGHT_METRICS = ["page_views_total", "page_post_engagements", "page_video_views"]
PARAMS = {"period": "day", "metric": ",".join(PAGE_INSIGHT_METRICS), "limit": 100}
KEY_COLUMNS = ["PageID", "DateKey", "MetricName"]
OUTPUT_COLUMNS = ["PageID", "Date", "DateKey", "MetricName", "Value"]


def _extract(
    client: MetaClient, user_token: str, page_ids: list[str], since: str, until: str,
    record_failures: bool = True,
) -> tuple[list[dict], list[str]]:
    """Returns (rows, failed_page_ids). A page with no token is treated as failed so it gets retried."""
    tokens = page_tokens(client, user_token)
    rows: list[dict] = []
    failed: list[str] = []
    queue = get_retry_queue()
    params = {**PARAMS, "since": since, "until": until}
    for index, page_id in enumerate(page_ids, start=1):
        page_token = tokens.get(page_id) or get_conf().page_access_token
        if not page_token:
            logger.warning("Skipping PageInsightsDaily because no Page access token exists for PageID=%s", page_id)
            failed.append(str(page_id))
            if record_failures:
                queue.record(TABLE, page_id, since, until, "no page access token")
            continue
        try:
            for page in client.paginate(f"/{page_id}/insights", page_token, params):
                for metric in page:
                    for value in metric.get("values", []):
                        period_end = as_date(value.get("end_time"))
                        day = period_end - timedelta(days=1) if period_end else None
                        if day and since <= day.isoformat() < until:
                            rows.append({"PageID": page_id, "Date": day, "MetricName": metric.get("name"), "Value": value.get("value")})
            logger.info("PageInsightsDaily fetch done for PageID=%s", page_id)
        except Exception as exc:
            logger.exception("PageInsightsDaily fetch failed for PageID=%s", page_id)
            failed.append(str(page_id))
            if record_failures:
                queue.record(TABLE, page_id, since, until, exc)
            continue
        if index == len(page_ids) or index % 25 == 0:
            logger.info("Processed %d/%d pages for PageInsightsDaily", index, len(page_ids))
    return rows, failed


def _transform(raw_rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(raw_rows, columns=["PageID", "Date", "MetricName", "Value"])
    if frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    frame["DateKey"] = frame["Date"].map(date_key)
    frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce")
    return frame[OUTPUT_COLUMNS].dropna(subset=["PageID", "Date", "MetricName"]).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def fact_page_insights_daily(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    since: str | None = None,
    until: str | None = None,
    page_ids: list[str] | None = None,         # retry: restrict to these pages
    record_failures: bool = True,
    failed_out: list[str] | None = None,
) -> int:
    since, until = daily_window(since, until)
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        with track_run(session, TABLE, partial=page_ids is not None):
            if page_ids is None:
                page_ids = [str(value) for value in session.execute(Page.__table__.select().with_only_columns(Page.PageID)).scalars()]
            access_token = token or resolve_token(session)
            log_fact_window("PageInsightsDaily", since, until, len(page_ids))
            raw, failed = _extract(client, access_token, page_ids, since, until, record_failures)
            if failed_out is not None:
                failed_out.extend(failed)
            if failed:
                logger.warning("PageInsightsDaily: %d page(s) failed and are queued for retry: %s", len(failed), ", ".join(failed))
            rows = _transform(raw)
            # Only clear the window for pages that fetched OK, and do it in the same transaction as the
            # insert. The original deleted (and committed) the window for ALL pages before fetching, so a
            # failed page lost the rows it already had.
            ok_ids = [int(p) for p in page_ids if str(p) not in set(failed)]
            if ok_ids:
                session.execute(
                    delete(PageInsightsDaily).where(
                        PageInsightsDaily.PageID.in_(ok_ids),
                        PageInsightsDaily.Date >= date.fromisoformat(since),
                        PageInsightsDaily.Date < date.fromisoformat(until),
                    )
                )
            loaded = upsert(rows, PageInsightsDaily, KEY_COLUMNS, session=session, commit=False)
            session.commit()
            return loaded
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    fact_page_insights_daily()

