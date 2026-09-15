from datetime import datetime

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import AdAccount, AdSet, Campaign
from utils.dbloader import open_session, resolve_token, upsert
from utils.dimension_helpers import as_datetime, as_json, bare_account_id
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


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


def _extract(client: MetaClient, token: str, account_ids: list[str]) -> list[dict]:
    rows: list[dict] = []
    for index, account_id in enumerate(account_ids, start=1):
        try:
            for page in client.paginate(f"/act_{bare_account_id(account_id)}/adsets", token, PARAMS):
                for adset in page:
                    adset["_account_id"] = bare_account_id(account_id)
                    rows.append(adset)
            logger.info("AdSet fetch done for AccountID=%s", account_id)
        except Exception:
            logger.exception("AdSet fetch failed for AccountID=%s", account_id)
            continue
        if index == len(account_ids) or index % 10 == 0:
            logger.info("Processed %d/%d ad accounts for AdSet", index, len(account_ids))
    return rows


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
    last_run: datetime | None = None,
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        account_ids = [str(value) for value in session.execute(AdAccount.__table__.select().with_only_columns(AdAccount.AccountID)).scalars()]
        campaign_ids = {str(value) for value in session.execute(Campaign.__table__.select().with_only_columns(Campaign.CampaignID)).scalars()}
        access_token = token or resolve_token(session)
        logger.info("Extracting AdSet for %d account(s); %d campaign IDs loaded from DB; last_run=%s", len(account_ids), len(campaign_ids), last_run)
        rows = _transform(_extract(client, access_token, account_ids), campaign_ids)
        return upsert(rows, AdSet, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    dimension_adset()
