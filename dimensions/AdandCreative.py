from datetime import datetime

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import Ad, AdAccount, AdSet, Creative
from utils.dbloader import open_session, resolve_token, upsert
from utils.dimension_helpers import (
    UPDATED_SINCE_BUFFER,
    as_datetime,
    as_int,
    as_json,
    bare_account_id,
    get_watermarks,
    with_updated_filter,
)
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


FIELDS = (
    "id,account_id,campaign_id,adset_id,creative{id,name},name,status,configured_status,"
    "effective_status,ad_active_time,source_ad_id,effective_object_story_id,object_story_id,"
    "scheduled_start_time,scheduled_end_time,created_time,updated_time"
)
PARAMS = {"fields": FIELDS, "limit": 100}
AD_KEYS = ["AdID"]
CREATIVE_KEYS = ["CreativeId"]
AD_COLUMNS = [
    "AdID", "AdAccountID", "CampaignID", "AdSetID", "CreativeID", "AdName", "Status",
    "ConfiguredStatus", "EffectiveStatus", "AdActiveTime", "SourceAdID", "EffectiveObjectStoryID",
    "ObjectStoryID", "ScheduledStartTime", "ScheduledEndTime", "CreatedTime", "UpdatedTime",
]
CREATIVE_COLUMNS = ["CreativeId", "CreativeName"]


def _extract(
    client: MetaClient,
    token: str,
    account_ids: list[str],
    parent_by_adset: dict[str, dict],
    watermarks: dict[str, datetime],
) -> list[dict]:
    rows: list[dict] = []
    full_count = 0
    incremental_count = 0
    for index, account_id in enumerate(account_ids, start=1):
        bare_id = bare_account_id(account_id)
        watermark = watermarks.get(bare_id)
        params = with_updated_filter(PARAMS, watermark)
        if watermark is None:
            full_count += 1
        else:
            incremental_count += 1
        account_rows = 0
        try:
            for page in client.paginate(f"/act_{bare_id}/ads", token, params):
                for ad in page:
                    adset_id = str(ad.get("adset_id")) if ad.get("adset_id") else None
                    parent = parent_by_adset.get(adset_id)
                    if not parent:
                        parent = {
                            "CampaignID": ad.get("campaign_id"),
                            "AdAccountID": bare_account_id(ad.get("account_id") or account_id),
                        }
                    ad["_adset_id"] = adset_id
                    ad["_campaign_id"] = parent["CampaignID"]
                    ad["_account_id"] = bare_account_id(parent["AdAccountID"] or account_id)
                    rows.append(ad)
                    account_rows += 1
            logger.info(
                "Ad fetch done for AccountID=%s (%s): %d row(s)",
                account_id, "full" if watermark is None else f"since {watermark.isoformat()}", account_rows,
            )
        except Exception:
            # Nothing is stored for this account, so its watermark doesn't advance
            # and the next run retries the same window.
            logger.exception("Ad fetch failed for AccountID=%s", account_id)
            continue
        if index == len(account_ids) or index % 10 == 0:
            logger.info("Processed %d/%d ad accounts for Ad and Creative", index, len(account_ids))
    logger.info(
        "Ad extract summary: %d account(s) full, %d incremental, %d row(s) fetched",
        full_count, incremental_count, len(rows),
    )
    return rows


def _transform(raw_rows: list[dict], parent_by_adset: dict[str, dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    ad_rows = []
    creative_rows = []
    for ad in raw_rows:
        creative = ad.get("creative") or {}
        creative_id = creative.get("id")
        if creative_id:
            creative_rows.append({"CreativeId": creative_id, "CreativeName": creative.get("name")})
        ad_rows.append({
            "AdID": ad.get("id"),
            "AdAccountID": bare_account_id(ad.get("_account_id")),
            "CampaignID": ad.get("_campaign_id"),
            "AdSetID": ad.get("_adset_id"),
            "CreativeID": creative_id,
            "AdName": ad.get("name"),
            "Status": ad.get("status"),
            "ConfiguredStatus": ad.get("configured_status"),
            "EffectiveStatus": ad.get("effective_status"),
            "AdActiveTime": as_int(ad.get("ad_active_time")),
            "SourceAdID": ad.get("source_ad_id"),
            "EffectiveObjectStoryID": ad.get("effective_object_story_id"),
            "ObjectStoryID": ad.get("object_story_id"),
            "ScheduledStartTime": as_datetime(ad.get("scheduled_start_time")),
            "ScheduledEndTime": as_datetime(ad.get("scheduled_end_time")),
            "CreatedTime": as_datetime(ad.get("created_time")),
            "UpdatedTime": as_datetime(ad.get("updated_time")),
        })
    ads = pd.DataFrame(ad_rows, columns=AD_COLUMNS).drop_duplicates(subset=AD_KEYS).reset_index(drop=True)
    creatives = pd.DataFrame(creative_rows, columns=CREATIVE_COLUMNS).drop_duplicates(subset=CREATIVE_KEYS).reset_index(drop=True)
    return ads, creatives


def dimension_ad_and_creative(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    last_run: datetime | None = None,  # unused: kept so run_staging's call signature stays compatible
    full_refresh: bool = False,        # True bypasses watermarks (e.g. weekly job to catch hard deletes/missed rows)
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        account_ids = [str(value) for value in session.execute(AdAccount.__table__.select().with_only_columns(AdAccount.AccountID)).scalars()]
        adset_rows = session.execute(AdSet.__table__.select()).mappings().all()
        parent_by_adset = {
            str(row["AdSetID"]): {
                "CampaignID": str(row["CampaignID"]) if row["CampaignID"] else None,
                "AdAccountID": bare_account_id(row["AdAccountID"]) if row["AdAccountID"] else None,
            }
            for row in adset_rows
        }
        access_token = token or resolve_token(session)

        watermarks = {} if full_refresh else get_watermarks(session, Ad, "AdAccountID")
        logger.info(
            "Extracting Ad and Creative for %d account(s) (%s, buffer=%s); %d with watermark",
            len(account_ids), "FULL REFRESH" if full_refresh else "incremental",
            UPDATED_SINCE_BUFFER, len(watermarks),
        )

        raw = _extract(client, access_token, account_ids, parent_by_adset, watermarks)
        if not raw:
            logger.info("No new or updated Ad rows; nothing to upsert")
            return 0
        ads, creatives = _transform(raw, parent_by_adset)
        creative_count = upsert(creatives, Creative, CREATIVE_KEYS, session=session, commit=False)
        ad_count = upsert(ads, Ad, AD_KEYS, session=session)
        return creative_count + ad_count
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


dimension_adandcreative = dimension_ad_and_creative


if __name__ == "__main__":
    dimension_ad_and_creative()

