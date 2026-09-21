from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any
import time
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from dimensions.AdAccount import dimension_adaccount
from dimensions.AdSet import dimension_adset
from dimensions.AdandCreative import dimension_ad_and_creative
from dimensions.Campaign import dimension_campaign
from dimensions.business import dimension_business
from dimensions.Page import dimension_page
from dimensions.Post import dimension_post
from facts.AdInsightsDaily import fact_ad_insights_daily
from facts.PageInsightsDaily import fact_page_insights_daily
from facts.PostInsightsSnapshot import fact_post_insights_snapshot
from utils.dbloader import create_schema, get_engine
from utils.logging import logger
from utils.metaclient import MetaClient

from config import get_conf
from retry_failed import run_retries

configs=get_conf()

def _chunk_date_range(since: str, until: str, chunk_days: int = 10) -> list[tuple[str, str]]:
    start = date.fromisoformat(since)
    end = date.fromisoformat(until)
    chunks: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        chunk_last = min(cursor + timedelta(days=chunk_days - 1), end)   # inclusive last day
        chunks.append((cursor.isoformat(), (chunk_last + timedelta(days=1)).isoformat()))
        cursor = chunk_last + timedelta(days=1)
    return chunks


def run_month_backfill(since: str = "2026-08-01", until: str = "2026-09-01", chunk_days: int = 10) -> None:
    engine = get_engine()
    create_schema(engine)

    chunks = _chunk_date_range(since, until, chunk_days=chunk_days)
    logger.info("Backfill split into %d chunk(s) of up to %d day(s): %s", len(chunks), chunk_days, chunks)

    tasks: dict[str, Any] = {}
    for chunk_since, chunk_until in chunks:
        tasks[f"AdInsightsDaily[{chunk_since}:{chunk_until}]"] = lambda s=chunk_since, u=chunk_until: fact_ad_insights_daily(
            db_connection=engine, since=s, until=u
        )
        tasks[f"PageInsightsDaily[{chunk_since}:{chunk_until}]"] = lambda s=chunk_since, u=chunk_until: fact_page_insights_daily(
            db_connection=engine, since=s, until=u
        )

    max_workers = min(len(tasks), 10)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                loaded = future.result()
                logger.info("%s backfill completed: %d rows", name, loaded)
            except Exception:
                logger.exception("%s backfill failed", name)


def run_post_insights_backfill(max_workers: int = 10) -> None:
    engine = get_engine()
    create_schema(engine)
    loaded = fact_post_insights_snapshot(db_connection=engine, post_mode="all", max_workers=max_workers)
    logger.info("PostInsightsSnapshot backfill completed: %d rows", loaded)
