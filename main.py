from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any

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
from facts.PostInsightsDaily import fact_post_insights_daily
from utils.dbloader import create_schema, get_engine
from utils.logging import logger
from utils.metaclient import MetaClient


def run_staging(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    last_run: datetime | None = None,
) -> None:
    engine = db_connection or get_engine()
    create_schema(engine)
    logger.info("Starting staging ETL")
    dimensions = (
        ("Business", dimension_business),
        ("AdAccount", dimension_adaccount),
        ("Campaign", dimension_campaign),
        ("AdSet", dimension_adset),
        ("Ad and Creative", dimension_ad_and_creative),
        ("Page", dimension_page),
        ("Post", dimension_post),
    )
    for name, dimension in dimensions:
        try:
            loaded = dimension(db_connection=engine, metaclient=metaclient, token=token, last_run=last_run)
            logger.info("Dimension %s completed: %d rows", name, loaded)
        except Exception:
            logger.exception("Dimension %s failed; continuing with the next dimension", name)
    facts = (
        ("AdInsightsDaily", fact_ad_insights_daily),
        ("PageInsightsDaily", fact_page_insights_daily),

        # PostInsightsDaily runs daily only (no since/until): its metrics are
        # lifetime-only, so each run captures today's current totals as a
        # dated snapshot. It intentionally has no place in historical backfill
        # — see run_month_backfill below.
        
        ("PostInsightsDaily", fact_post_insights_daily),
    )
    for name, fact in facts:
        try:
            loaded = fact(db_connection=engine, metaclient=metaclient, token=token)
            logger.info("Fact %s completed: %d rows", name, loaded)
        except Exception:
            logger.exception("Fact %s failed; continuing with the next fact", name)
    logger.info("Staging ETL completed")


def _chunk_date_range(since: str, until: str, chunk_days: int = 10) -> list[tuple[str, str]]:
    """Split [since, until] into consecutive chunks of at most `chunk_days` days each."""
    start = date.fromisoformat(since)
    end = date.fromisoformat(until)
    chunks: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = chunk_end + timedelta(days=1)
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

    # Engine is thread-safe and hands each thread its own pooled connection,
    # so running many chunk-scoped fact calls concurrently against the same
    # engine is safe. Cap worker count so we don't fire an unbounded number of
    # simultaneous API calls for very long backfill ranges.
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
    """
    One-time backfill for PostInsightsDaily: a single run over ALL posts
    (post_mode="all", no limit), threaded for speed.

    This is NOT a historical date-range backfill. post_activity_by_action_type
    and post_reactions_by_type_total only support period=lifetime, and Meta
    ignores since/until for lifetime-period metrics (confirmed empirically) —
    there is no way to retrieve a past value for these metrics. This call
    captures today's current totals for every post as a single dated snapshot
    (the starting point in the table), stamped with today's date. From here,
    each daily run (via run_staging) adds one more day's snapshot, so the
    history in PostInsightsDaily grows by one row per post per day going
    forward.
    """
    engine = get_engine()
    create_schema(engine)
    loaded = fact_post_insights_daily(db_connection=engine, post_mode="all", max_workers=max_workers)
    logger.info("PostInsightsDaily backfill completed: %d rows", loaded)





if __name__ == "__main__":
    run_staging()

    # Historical backfill example. Run manually

    # run_month_backfill(since="2026-01-01", until="2026-09-14", chunk_days=10)
    # run_post_insights_backfill(50)
























# from datetime import datetime

# from sqlalchemy import Connection, Engine
# from sqlalchemy.orm import Session

# from dimensions.AdAccount import dimension_adaccount
# from dimensions.AdSet import dimension_adset
# from dimensions.AdandCreative import dimension_ad_and_creative
# from dimensions.Campaign import dimension_campaign
# from dimensions.business import dimension_business
# from dimensions.Page import dimension_page
# from dimensions.Post import dimension_post
# from facts.AdInsightsDaily import fact_ad_insights_daily
# from facts.PageInsightsDaily import fact_page_insights_daily
# from facts.PostInsightsDaily import fact_post_insights_daily
# from utils.dbloader import create_schema, get_engine
# from utils.logging import logger
# from utils.metaclient import MetaClient


# def run_staging(
#     db_connection: Engine | Connection | Session | None = None,
#     metaclient: MetaClient | None = None,
#     token: str | None = None,
#     last_run: datetime | None = None,
# ) -> None:
#     engine = db_connection or get_engine()
#     create_schema(engine)
#     logger.info("Starting staging ETL")
#     dimensions = (
#         # ("Business", dimension_business),
#         # ("AdAccount", dimension_adaccount),
#         # ("Campaign", dimension_campaign),
#         # ("AdSet", dimension_adset),
#         # ("Ad and Creative", dimension_ad_and_creative),
#         # ("Page", dimension_page),
#         # ("Post", dimension_post),
#     )
#     for name, dimension in dimensions:
#         try:
#             loaded = dimension(db_connection=engine, metaclient=metaclient, token=token, last_run=last_run)
#             logger.info("Dimension %s completed: %d rows", name, loaded)
#         except Exception:
#             logger.exception("Dimension %s failed; continuing with the next dimension", name)
#     facts = (
#         #("AdInsightsDaily", fact_ad_insights_daily),
#         #("PageInsightsDaily", fact_page_insights_daily),
#         ("PostInsightsDaily", fact_post_insights_daily),
#     )
#     for name, fact in facts:
#         try:
#             loaded = fact(db_connection=engine, metaclient=metaclient, token=token)
#             logger.info("Fact %s completed: %d rows", name, loaded)
#         except Exception:
#             logger.exception("Fact %s failed; continuing with the next fact", name)
#     logger.info("Staging ETL completed")


# def run_month_backfill(since: str = "2026-08-01", until: str = "2026-09-01") -> None:
#     engine = get_engine()
#     create_schema(engine)
#     #fact_ad_insights_daily(db_connection=engine, since=since, until=until)
#     #fact_page_insights_daily(db_connection=engine, since=since, until=until)
#     #fact_post_insights_daily(db_connection=engine, since=since, until=until, post_mode="recent")


# # Historical backfill example. Run manually, never from the daily task:
# # from main import run_month_backfill
# # run_month_backfill("2026-08-01", "2026-09-01")


# if __name__ == "__main__":
#     run_staging()
#     #run_month_backfill("2026-01-01", "2026-01-05")