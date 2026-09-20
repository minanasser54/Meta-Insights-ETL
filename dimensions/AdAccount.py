from datetime import datetime

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import AdAccount
from utils.dbloader import open_session, resolve_token, upsert
from utils.dimension_helpers import as_int, bare_account_id
from utils.logging import logger
from utils.metaclient import MetaClient, get_client
from utils.watermark import track_run


ENDPOINT = "/me/adaccounts"
PARAMS = {
    "fields": (
        "id,name,account_status,currency,timezone_name,"
        "timezone_offset_hours_utc,disable_reason,amount_spent,balance,"
        "spend_cap,min_campaign_group_spend_cap,min_daily_budget,"
        "funding_source_details,is_personal,business{id,name}"
    ),
    "limit": 100,
}
KEY_COLUMNS = ["AccountID"]
OUTPUT_COLUMNS = [
    "AccountID", "AccountName", "AccountStatus", "DisableReason", "Currency",
    "TimezoneName", "TimezoneOffsetHrsUtc", "AmountSpent", "Balance", "SpendCap",
    "MinCampaignGroupSpendCap", "MinDailyBudget", "IsPersonal", "BusinessID",
    "FundingSourceID", "FundingSourceDisplayString", "FundingSourceType",
]


def _extract(client: MetaClient, token: str) -> list[dict]:
    accounts_raw: list[dict] = []
    for page in client.paginate(ENDPOINT, token, PARAMS):
        accounts_raw.extend(page)
    return accounts_raw


def _transform(accounts_raw: list[dict]) -> pd.DataFrame:
    rows = []
    for account in accounts_raw:
        # Meta returns "act_123"; store the bare numeric ID as BIGINT like every other AdAccountID column.
        account_id = as_int(bare_account_id(account.get("id")))
        if account_id is None:
            logger.warning("Skipping ad account with missing/non-numeric id: %r", account.get("id"))
            continue
        business = account.get("business") or {}
        funding = account.get("funding_source_details") or {}
        rows.append({
            "AccountID": account_id,
            "AccountName": account.get("name"),
            "AccountStatus": account.get("account_status"),
            "DisableReason": account.get("disable_reason"),
            "Currency": account.get("currency"),
            "TimezoneName": account.get("timezone_name"),
            "TimezoneOffsetHrsUtc": account.get("timezone_offset_hours_utc"),
            "AmountSpent": account.get("amount_spent"),
            "Balance": account.get("balance"),
            "SpendCap": account.get("spend_cap"),
            "MinCampaignGroupSpendCap": account.get("min_campaign_group_spend_cap"),
            "MinDailyBudget": account.get("min_daily_budget"),
            "IsPersonal": account.get("is_personal"),
            "BusinessID": business.get("id"),
            "FundingSourceID": funding.get("id"),
            "FundingSourceDisplayString": funding.get("display_string"),
            "FundingSourceType": funding.get("type"),
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def dimension_adaccount(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    last_run: datetime | None = None,
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        with track_run(session, AdAccount.__tablename__):
            access_token = token or resolve_token(session)
            logger.info("Extracting AdAccount; last_run=%s", last_run)
            rows = _transform(_extract(client, access_token))
            return upsert(rows, AdAccount, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    dimension_adaccount()
