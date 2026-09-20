from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import Ad, AdAccount, AdSet
from utils.dbloader import open_session, resolve_token, upsert
from utils.dimension_helpers import as_datetime, as_int, bare_account_id, with_updated_filter
from utils.logging import logger
from utils.metaclient import MetaClient, get_client
from utils.watermark import raise_if_failed, track_run


FIELDS = (
    "id,account_id,campaign_id,adset_id,creative{id},name,status,configured_status,"
    "effective_status,ad_active_time,source_ad_id,effective_object_story_id,object_story_id,"
    "scheduled_start_time,scheduled_end_time,created_time,updated_time"
)
PARAMS = {"fields": FIELDS, "limit": 100}
AD_KEYS = ["AdID"]
AD_COLUMNS = [
    "AdID", "AdAccountID", "CampaignID", "AdSetID", "CreativeID", "AdName", "Status",
    "ConfiguredStatus", "EffectiveStatus", "AdActiveTime", "SourceAdID", "EffectiveObjectStoryID",
    "ObjectStoryID", "ScheduledStartTime", "ScheduledEndTime", "CreatedTime", "UpdatedTime",
]

# Incremental cut-off = last successful run's start (Watermark.metaadsetl) minus this delta,
# so clock skew or late-propagating updates can't drop rows. Safe because upsert is idempotent.
WATERMARK_DELTA = timedelta(hours=6)


def _extract(
    client: MetaClient,
    token: str,
    account_ids: list[str],
    parent_by_adset: dict[str, dict],
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
            logger.info("Ad fetch done for AccountID=%s: %d row(s)", account_id, account_rows)
        except Exception:
            logger.exception("Ad fetch failed for AccountID=%s", account_id)
            failed.append(bare_id)
            continue
        if index == len(account_ids) or index % 10 == 0:
            logger.info("Processed %d/%d ad accounts for Ad", index, len(account_ids))
    logger.info(
        "Ad extract summary: %s, %d row(s) fetched, %d account(s) failed",
        "full" if since is None else f"updated_time > {since.isoformat()}", len(rows), len(failed),
    )
    return rows, failed


def _transform(raw_rows: list[dict], parent_by_adset: dict[str, dict]) -> pd.DataFrame:
    ad_rows = []
    for ad in raw_rows:
        creative = ad.get("creative") or {}
        ad_rows.append({
            "AdID": ad.get("id"),
            "AdAccountID": bare_account_id(ad.get("_account_id")),
            "CampaignID": ad.get("_campaign_id"),
            "AdSetID": ad.get("_adset_id"),
            "CreativeID": creative.get("id"),
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
    return pd.DataFrame(ad_rows, columns=AD_COLUMNS).drop_duplicates(subset=AD_KEYS).reset_index(drop=True)


def dimension_ad_and_creative(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    last_run: datetime | None = None,  # unused: kept so run_staging's call signature stays compatible
    full_refresh: bool = False,        # True ignores the watermark (e.g. periodic job to catch hard deletes/missed rows)
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        with track_run(session, Ad.__tablename__, delta=WATERMARK_DELTA, full_refresh=full_refresh) as run:
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
            logger.info(
                "Extracting Ad for %d account(s) (%s)",
                len(account_ids), "FULL REFRESH" if run.since is None else f"incremental since {run.since}",
            )

            raw, failed = _extract(client, access_token, account_ids, parent_by_adset, run.since)
            loaded = 0
            if raw:
                loaded = upsert(_transform(raw, parent_by_adset), Ad, AD_KEYS, session=session)
            else:
                logger.info("No new or updated Ad rows; nothing to upsert")
            raise_if_failed("Ad", failed)
            return loaded
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


dimension_adandcreative = dimension_ad_and_creative


if __name__ == "__main__":
    dimension_ad_and_creative()
