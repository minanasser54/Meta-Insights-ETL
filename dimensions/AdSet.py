from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import AdAccount, AdSet, Campaign
from utils.dbloader import open_session, resolve_token, upsert
from utils.dimension_helpers import as_datetime, as_json, bare_account_id, with_updated_filter
from utils.logging import logger
from utils.metaclient import MetaClient, get_client
from utils.watermark import raise_if_failed, track_run


FIELDS = (
    "id,account_id,campaign_id,name,status,configured_status,effective_status,"
    "optimization_goal,daily_budget,lifetime_budget,budget_remaining,spend_cap,"
    "special_ad_category_country,is_budget_schedule_enabled,is_adset_budget_sharing_enabled,"
    "destination_type,is_dynamic_creative,pacing_type,attribution_spec,promoted_object,targeting,"
    "start_time,end_time,created_time,updated_time,source_adset_id"
)
PARAMS = {"fields": FIELDS, "limit": 100}
KEY_COLUMNS = ["AdSetID"]
OUTPUT_COLUMNS = [
    "AdSetID", "AdAccountID", "CampaignID", "AdSetName", "Status", "ConfiguredStatus",
    "EffectiveStatus", "OptimizationGoal", "DailyBudget", "LifetimeBudget", "BudgetRemaining",
    "SpendCap", "SpecialAdCategoryCountry", "IsBudgetScheduleEnabled", "IsAdSetBudgetSharingEnabled",
    "DestinationType", "IsDynamicCreative", "PacingType", "AttributionSpec", "PromotedObjectPageID",
    "PromotedObjectPixelID", "PromotedObjectAppID", "Targeting", "TargetingCountries", "TargetingAgeMin",
    "TargetingAgeMax", "TargetingGenders", "TargetingPublisherPlatforms", "TargetingFacebookPositions",
    "TargetingDevicePlatforms", "StartTime", "EndTime", "CreatedTime", "UpdatedTime", "SourceAdSetID",
]


# Incremental cut-off = last successful run's start (Watermark.metaadsetl) minus this delta,
# so clock skew or late-propagating updates can't drop rows. Safe because upsert is idempotent.
WATERMARK_DELTA = timedelta(hours=6)


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
            for page in client.paginate(f"/act_{bare_id}/adsets", token, params):
                for adset in page:
                    adset["_account_id"] = bare_id
                    rows.append(adset)
                    account_rows += 1
            logger.info("AdSet fetch done for AccountID=%s: %d row(s)", account_id, account_rows)
        except Exception:
            logger.exception("AdSet fetch failed for AccountID=%s", account_id)
            failed.append(bare_id)
            continue
        if index == len(account_ids) or index % 10 == 0:
            logger.info("Processed %d/%d ad accounts for AdSet", index, len(account_ids))
    logger.info(
        "AdSet extract summary: %s, %d row(s) fetched, %d account(s) failed",
        "full" if since is None else f"updated_time > {since.isoformat()}", len(rows), len(failed),
    )
    return rows, failed


def _transform(raw_rows: list[dict], campaign_ids: set[str]) -> pd.DataFrame:
    rows = []
    for adset in raw_rows:
        targeting = adset.get("targeting") or {}
        geo_locations = targeting.get("geo_locations") or {}
        promoted = adset.get("promoted_object") or {}
        campaign_id = str(adset.get("campaign_id")) if adset.get("campaign_id") else None
        if campaign_id not in campaign_ids:
            logger.warning("Skipping AdSetID=%s with campaign not present in Campaign staging: %s", adset.get("id"), campaign_id)
            continue
        rows.append({
            "AdSetID": adset.get("id"),
            "AdAccountID": bare_account_id(adset.get("_account_id") or adset.get("account_id")),
            "CampaignID": campaign_id,
            "AdSetName": adset.get("name"),
            "Status": adset.get("status"),
            "ConfiguredStatus": adset.get("configured_status"),
            "EffectiveStatus": adset.get("effective_status"),
            "OptimizationGoal": adset.get("optimization_goal"),
            "DailyBudget": adset.get("daily_budget"),
            "LifetimeBudget": adset.get("lifetime_budget"),
            "BudgetRemaining": adset.get("budget_remaining"),
            "SpendCap": adset.get("spend_cap"),
            "SpecialAdCategoryCountry": adset.get("special_ad_category_country"),
            "IsBudgetScheduleEnabled": adset.get("is_budget_schedule_enabled"),
            "IsAdSetBudgetSharingEnabled": adset.get("is_adset_budget_sharing_enabled"),
            "DestinationType": adset.get("destination_type"),
            "IsDynamicCreative": adset.get("is_dynamic_creative"),
            "PacingType": as_json(adset.get("pacing_type")),
            "AttributionSpec": as_json(adset.get("attribution_spec")),
            "PromotedObjectPageID": promoted.get("page_id"),
            "PromotedObjectPixelID": promoted.get("pixel_id"),
            "PromotedObjectAppID": promoted.get("application_id"),
            "Targeting": as_json(targeting),
            "TargetingCountries": as_json(geo_locations.get("countries")),
            "TargetingAgeMin": targeting.get("age_min"),
            "TargetingAgeMax": targeting.get("age_max"),
            "TargetingGenders": as_json(targeting.get("genders")),
            "TargetingPublisherPlatforms": as_json(targeting.get("publisher_platforms")),
            "TargetingFacebookPositions": as_json(targeting.get("facebook_positions")),
            "TargetingDevicePlatforms": as_json(targeting.get("device_platforms")),
            "StartTime": as_datetime(adset.get("start_time")),
            "EndTime": as_datetime(adset.get("end_time")),
            "CreatedTime": as_datetime(adset.get("created_time")),
            "UpdatedTime": as_datetime(adset.get("updated_time")),
            "SourceAdSetID": adset.get("source_adset_id"),
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def dimension_adset(
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
        with track_run(session, AdSet.__tablename__, delta=WATERMARK_DELTA, full_refresh=full_refresh, partial=parent_ids is not None) as run:
            account_ids = parent_ids if parent_ids is not None else [str(value) for value in session.execute(AdAccount.__table__.select().with_only_columns(AdAccount.AccountID)).scalars()]
            campaign_ids = {str(value) for value in session.execute(Campaign.__table__.select().with_only_columns(Campaign.CampaignID)).scalars()}
            access_token = token or resolve_token(session)
            logger.info(
                "Extracting AdSet for %d account(s) (%s); %d campaign IDs loaded from DB",
                len(account_ids), "FULL REFRESH" if run.since is None else f"incremental since {run.since}", len(campaign_ids),
            )

            fetch_since = since_override if parent_ids is not None else run.since
            raw, failed = _extract(client, access_token, account_ids, fetch_since)
            loaded = 0
            if raw:
                loaded = upsert(_transform(raw, campaign_ids), AdSet, KEY_COLUMNS, session=session)
            else:
                logger.info("No new or updated AdSet rows; nothing to upsert")
            raise_if_failed("AdSet", failed, since=run.since)
            return loaded
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    dimension_adset()
