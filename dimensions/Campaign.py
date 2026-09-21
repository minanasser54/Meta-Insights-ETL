from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import AdAccount, Campaign
from utils.dbloader import open_session, read_ids, resolve_token, upsert
from utils.dimension_helpers import as_datetime, as_json, bare_account_id, with_updated_filter
from utils.logging import logger
from utils.metaclient import MetaClient, get_client
from utils.watermark import raise_if_failed, track_run


FIELDS = (
    "id,account_id,name,objective,buying_type,status,configured_status,"
    "effective_status,daily_budget,lifetime_budget,budget_remaining,spend_cap,"
    "special_ad_categories,special_ad_category_country,is_budget_schedule_enabled,"
    "is_adset_budget_sharing_enabled,destination_type,is_dynamic_creative,"
    "pacing_type,attribution_spec,promoted_object,start_time,stop_time,"
    "created_time,updated_time"
)
PARAMS = {"fields": FIELDS, "limit": 500}
KEY_COLUMNS = ["CampaignID"]
OUTPUT_COLUMNS = [
    "CampaignID", "AdAccountID", "CampaignName", "Objective", "BuyingType", "Status",
    "ConfiguredStatus", "EffectiveStatus", "DailyBudget", "LifetimeBudget", "BudgetRemaining",
    "SpendCap", "SpecialAdCategories", "SpecialAdCategoryCountry", "IsBudgetScheduleEnabled",
    "IsAdSetBudgetSharingEnabled", "DestinationType", "IsDynamicCreative", "PacingType",
    "AttributionSpec", "PromotedObjectPageID", "PromotedObjectPixelID", "PromotedObjectAppID",
    "StartTime", "StopTime", "CreatedTime", "UpdatedTime",
]

# Incremental cut-off = last successful run's start (Watermark.metaadsetl) minus this delta,
# so clock skew or late-propagating updates can't drop rows. Safe because upsert is idempotent.
WATERMARK_DELTA = timedelta(days=1)


def _extract(
    client: MetaClient,
    token: str,
    account_ids: list[str],
    since: datetime | None,
) -> tuple[list[dict], list[str]]:
    """Returns (rows, failed_account_ids)."""
    rows: list[dict] = []
    failed: list[str] = []
    params = with_updated_filter(PARAMS, since)  # updated_time > since; unfiltered if since is None
    for index, account_id in enumerate(account_ids, start=1):
        bare_id = bare_account_id(account_id)
        account_rows = 0
        try:
            for page in client.paginate(f"/act_{bare_id}/campaigns", token, params):
                for campaign in page:
                    campaign["_account_id"] = bare_id
                    rows.append(campaign)
                    account_rows += 1
            logger.info("Campaign fetch done for AccountID=%s: %d row(s)", account_id, account_rows)
        except Exception:
            logger.exception("Campaign fetch failed for AccountID=%s", account_id)
            failed.append(bare_id)
            continue
        if index == len(account_ids) or index % 100 == 0:
            logger.info("Processed %d/%d ad accounts for Campaign", index, len(account_ids))
    logger.info(
        "Campaign extract summary: %s, %d row(s) fetched, %d account(s) failed",
        "full" if since is None else f"updated_time > {since.isoformat()}", len(rows), len(failed),
    )
    return rows, failed


def _transform(raw_rows: list[dict]) -> pd.DataFrame:
    rows = []
    for campaign in raw_rows:
        promoted = campaign.get("promoted_object") or {}
        rows.append({
            "CampaignID": campaign.get("id"),
            "AdAccountID": bare_account_id(campaign.get("_account_id") or campaign.get("account_id")),
            "CampaignName": campaign.get("name"),
            "Objective": campaign.get("objective"),
            "BuyingType": campaign.get("buying_type"),
            "Status": campaign.get("status"),
            "ConfiguredStatus": campaign.get("configured_status"),
            "EffectiveStatus": campaign.get("effective_status"),
            "DailyBudget": campaign.get("daily_budget"),
            "LifetimeBudget": campaign.get("lifetime_budget"),
            "BudgetRemaining": campaign.get("budget_remaining"),
            "SpendCap": campaign.get("spend_cap"),
            "SpecialAdCategories": as_json(campaign.get("special_ad_categories")),
            "SpecialAdCategoryCountry": campaign.get("special_ad_category_country"),
            "IsBudgetScheduleEnabled": campaign.get("is_budget_schedule_enabled"),
            "IsAdSetBudgetSharingEnabled": campaign.get("is_adset_budget_sharing_enabled"),
            "DestinationType": campaign.get("destination_type"),
            "IsDynamicCreative": campaign.get("is_dynamic_creative"),
            "PacingType": as_json(campaign.get("pacing_type")),
            "AttributionSpec": as_json(campaign.get("attribution_spec")),
            "PromotedObjectPageID": promoted.get("page_id"),
            "PromotedObjectPixelID": promoted.get("pixel_id"),
            "PromotedObjectAppID": promoted.get("application_id"),
            "StartTime": as_datetime(campaign.get("start_time")),
            "StopTime": as_datetime(campaign.get("stop_time")),
            "CreatedTime": as_datetime(campaign.get("created_time")),
            "UpdatedTime": as_datetime(campaign.get("updated_time")),
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def dimension_campaign(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    last_run: datetime | None = None,  # unused: kept so run_staging's call signature stays compatible
    full_refresh: bool = False,        # True ignores the watermark (e.g. periodic job to catch hard deletes/missed rows)
    parent_ids: list[str] | None = None,  # retry: only these parents
    since_override: datetime | None = None,  # retry: original cut-off (None + parent_ids = full fetch)
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        with track_run(session, Campaign.__tablename__, delta=WATERMARK_DELTA, full_refresh=full_refresh, partial=parent_ids is not None) as run:
            account_ids = parent_ids if parent_ids is not None else read_ids(session, AdAccount, "AccountID")
            access_token = token or resolve_token(session)
            logger.info(
                "Extracting Campaign for %d account(s) (%s)",
                len(account_ids), "FULL REFRESH" if run.since is None else f"incremental since {run.since}",
            )

            fetch_since = since_override if parent_ids is not None else run.since
            raw, failed = _extract(client, access_token, account_ids, fetch_since)
            loaded = 0
            if raw:
                loaded = upsert(_transform(raw), Campaign, KEY_COLUMNS, session=session)
            else:
                logger.info("No new or updated Campaign rows; nothing to upsert")
            raise_if_failed("Campaign", failed, since=run.since)
            return loaded
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    dimension_campaign()
