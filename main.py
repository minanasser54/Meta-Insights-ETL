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
from utils.backfill import *

from config import get_conf
from retry_failed import run_retries

configs=get_conf()

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
            if name=="Campaign"  or name=="Ad and Creative" or name=="Post":
                loaded = dimension(db_connection=engine, metaclient=metaclient, token=token, last_run=last_run,full_refresh=configs.full_refresh)
                logger.info("Dimension %s completed: %d rows", name, loaded)
            elif name=="AdSet":
                loaded = dimension(db_connection=engine, metaclient=metaclient, token=token, last_run=last_run,full_refresh=True)
                logger.info("Dimension %s completed: %d rows", name, loaded)
            else :
                loaded = dimension(db_connection=engine, metaclient=metaclient, token=token, last_run=last_run)
                logger.info("Dimension %s completed: %d rows", name, loaded)
            #time.sleep(3)
        except Exception:
            #time.sleep(1)
            logger.exception("Dimension %s failed; continuing with the next dimension", name)
    facts = (
        ("AdInsightsDaily", fact_ad_insights_daily),
        ("PageInsightsDaily", fact_page_insights_daily),

        # PostInsightsSnapshot runs daily only (no since/until): its metrics are lifetime-only, so each run captures today's current totals as a
        ("PostInsightsSnapshot", fact_post_insights_snapshot),
    )
    for name, fact in facts:
        try:
            loaded = fact(db_connection=engine, metaclient=metaclient, token=token)
            logger.info("Fact %s completed: %d rows", name, loaded)
            #time.sleep(3)
        except Exception:
            #time.sleep(1)
            logger.exception("Fact %s failed; continuing with the next fact", name)
    logger.info("Staging ETL completed")






if __name__ == "__main__":

    # Historical backfill example. Run manually
    #run_staging()

    #run_month_backfill(since="2026-09-18", until="2026-09-20", chunk_days=10)
    #run_post_insights_backfill(50)

    #run_staging()

    run_retries()

