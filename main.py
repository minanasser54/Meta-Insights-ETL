from datetime import datetime

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
        # ("AdAccount", dimension_adaccount),
        # ("Campaign", dimension_campaign),
        # ("AdSet", dimension_adset),
        # ("Ad and Creative", dimension_ad_and_creative),
        # ("Page", dimension_page),
        # ("Post", dimension_post),
    )
    for name, dimension in dimensions:
        try:
            loaded = dimension(db_connection=engine, metaclient=metaclient, token=token, last_run=last_run)
            logger.info("Dimension %s completed: %d rows", name, loaded)
        except Exception:
            logger.exception("Dimension %s failed; continuing with the next dimension", name)
    facts = (
        # ("AdInsightsDaily", fact_ad_insights_daily),
        # ("PageInsightsDaily", fact_page_insights_daily),
        ("PostInsightsDaily", fact_post_insights_daily),
    )
    for name, fact in facts:
        try:
            loaded = fact(db_connection=engine, metaclient=metaclient, token=token)
            logger.info("Fact %s completed: %d rows", name, loaded)
        except Exception:
            logger.exception("Fact %s failed; continuing with the next fact", name)
    logger.info("Staging ETL completed")


def run_month_backfill(since: str = "2026-08-01", until: str = "2026-09-01") -> None:
    engine = get_engine()
    create_schema(engine)
    fact_ad_insights_daily(db_connection=engine, since=since, until=until)
    fact_page_insights_daily(db_connection=engine, since=since, until=until)
    fact_post_insights_daily(db_connection=engine, since=since, until=until, post_mode="all")


# Historical backfill example. Run manually, never from the daily task:
# from main import run_month_backfill
# run_month_backfill("2026-08-01", "2026-09-01")


if __name__ == "__main__":
    run_staging()
    #run_month_backfill("2026-09-07", "2026-09-09")
