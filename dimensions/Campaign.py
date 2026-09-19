import json
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import Connection, Engine, func, select
from sqlalchemy.orm import Session

from models import AdAccount, Campaign
from utils.dbloader import open_session, read_ids, resolve_token, upsert
from utils.dimension_helpers import as_datetime, as_json, bare_account_id
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


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

# Re-fetch window before each account's watermark so clock skew or late-propagating
# updates can't drop rows. Safe because upsert is idempotent on CampaignID.
UPDATED_SINCE_BUFFER = timedelta(days=1)


def _get_account_watermarks(session: Session) -> dict[str, datetime]:
    """Latest UpdatedTime already loaded, per ad account: {bare_account_id: datetime}.

    Accounts with no campaigns (or only NULL UpdatedTime) are absent from the result,
    which makes them get a full fetch. On any DB error returns {} so the whole run
    safely falls back to a full fetch instead of failing.
    """
    try:
        result = session.execute(
            select(Campaign.AdAccountID, func.max(Campaign.UpdatedTime))
            .group_by(Campaign.AdAccountID)
        ).all()
    except Exception:
        logger.exception("Could not read Campaign watermarks; falling back to full fetch")
        session.rollback()
        return {}

    watermarks: dict[str, datetime] = {}
    for account_id, max_updated in result:
        key = bare_account_id(account_id)
        if key is None or max_updated is None:
            continue
        watermarks[key] = max_updated
    #logger.info(watermarks)
    return watermarks


def _build_params(watermark: datetime | None) -> dict:
    params = dict(PARAMS)  # copy: never mutate the module-level dict
    if watermark is not None:
        # Stored values are naive UTC (see as_datetime), so tag as UTC before converting.
        since_ts = int((watermark.replace(tzinfo=timezone.utc) - UPDATED_SINCE_BUFFER).timestamp())
        params["filtering"] = json.dumps([
            {"field": "updated_time", "operator": "GREATER_THAN", "value": since_ts}
        ])
    return params


def _extract(
    client: MetaClient,
    token: str,
    account_ids: list[str],
    watermarks: dict[str, datetime],
) -> list[dict]:
    rows: list[dict] = []
    full_count = 0
    incremental_count = 0
    for index, account_id in enumerate(account_ids, start=1):
        bare_id = bare_account_id(account_id)
        watermark = watermarks.get(bare_id)
        params = _build_params(watermark)
        if watermark is None:
            full_count += 1
        else:
            incremental_count += 1
        account_rows = 0
        try:
            for page in client.paginate(f"/act_{bare_id}/campaigns", token, params):
                for campaign in page:
                    campaign["_account_id"] = bare_id
                    rows.append(campaign)
                    account_rows += 1
            logger.info(
                "Campaign fetch done for AccountID=%s (%s): %d row(s)",
                account_id,
                "full" if watermark is None else f"since {watermark.isoformat()}",
                account_rows,
            )
        except Exception:
            # Nothing is stored for this account, so its watermark doesn't advance
            # and the next run retries the same window.
            logger.exception("Campaign fetch failed for AccountID=%s", account_id)
            continue
        if index == len(account_ids) or index % 100 == 0:
            logger.info("Processed %d/%d ad accounts for Campaign", index, len(account_ids))
    logger.info(
        "Campaign extract summary: %d account(s) full, %d incremental, %d row(s) fetched",
        full_count, incremental_count, len(rows),
    )
    return rows


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
    full_refresh: bool = False,        # True bypasses watermarks (e.g. weekly job to catch hard deletes/missed rows)
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        account_ids = read_ids(session, AdAccount, "AccountID")
        access_token = token or resolve_token(session)

        watermarks = {} if full_refresh else _get_account_watermarks(session)
        logger.info(
            "Extracting Campaign for %d account(s) (%s); %d with watermark",
            len(account_ids), "FULL REFRESH" if full_refresh else "incremental", len(watermarks),
        )

        raw = _extract(client, access_token, account_ids, watermarks)
        if not raw:
            logger.info("No new or updated Campaign rows; nothing to upsert")
            return 0
        return upsert(_transform(raw), Campaign, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    dimension_campaign()


