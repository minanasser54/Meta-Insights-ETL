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


PAGE_INSIGHT_METRICS = ["page_views_total", "page_post_engagements", "page_video_views"]
PARAMS = {"period": "day", "metric": ",".join(PAGE_INSIGHT_METRICS), "limit": 100}
KEY_COLUMNS = ["PageID", "Date", "MetricName"]
OUTPUT_COLUMNS = ["PageID", "Date", "DateKey", "MetricName", "Value"]


def _extract(client: MetaClient, user_token: str, page_ids: list[str], since: str, until: str) -> list[dict]:
    tokens = page_tokens(client, user_token)
    rows: list[dict] = []
    params = {**PARAMS, "since": since, "until": until}
    for index, page_id in enumerate(page_ids, start=1):
        page_token = tokens.get(page_id) or get_conf().page_access_token
        if not page_token:
            logger.warning("Skipping PageInsightsDaily because no Page access token exists for PageID=%s", page_id)
            continue
        try:
            for page in client.paginate(f"/{page_id}/insights", page_token, params):
                for metric in page:
                    for value in metric.get("values", []):
                        period_end = as_date(value.get("end_time"))
                        day = period_end - timedelta(days=1) if period_end else None
                        if day and since <= day.isoformat() < until:
                            rows.append({"PageID": page_id, "Date": day, "MetricName": metric.get("name"), "Value": value.get("value")})
        except Exception:
            logger.exception("PageInsightsDaily fetch failed for PageID=%s", page_id)
            continue
        if index == len(page_ids) or index % 25 == 0:
            logger.info("Processed %d/%d pages for PageInsightsDaily", index, len(page_ids))
    return rows


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
) -> int:
    since, until = daily_window(since, until)
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        page_ids = [str(value) for value in session.execute(Page.__table__.select().with_only_columns(Page.PageID)).scalars()]
        access_token = token or resolve_token(session)
        log_fact_window("PageInsightsDaily", since, until, len(page_ids))
        rows = _transform(_extract(client, access_token, page_ids, since, until))
        session.execute(delete(PageInsightsDaily).where(PageInsightsDaily.Date >= date.fromisoformat(until)))
        session.commit()
        return upsert(rows, PageInsightsDaily, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    fact_page_insights_daily()
