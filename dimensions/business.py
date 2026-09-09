from datetime import datetime

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import Business
from utils.dbloader import open_session, resolve_token, upsert
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


ENDPOINT = "/me/adaccounts"
PARAMS = {"fields": "id,name,business{id,name}", "limit": 500}
KEY_COLUMNS = ["BusinessID"]
OUTPUT_COLUMNS = ["BusinessID", "BusinessName"]


def _extract(client: MetaClient, token: str) -> list[dict]:
    accounts_raw: list[dict] = []
    for page in client.paginate(ENDPOINT, token, PARAMS):
        accounts_raw.extend(page)
    return accounts_raw


def _transform(accounts_raw: list[dict]) -> pd.DataFrame:
    rows = []
    for account in accounts_raw:
        business = account.get("business") or {}
        if business.get("id"):
            rows.append({
                "BusinessID": business.get("id"),
                "BusinessName": business.get("name"),
            })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def dimension_business(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    last_run: datetime | None = None,
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        access_token = token or resolve_token(session)
        logger.info("Extracting Business; last_run=%s", last_run)
        rows = _transform(_extract(client, access_token))
        return upsert(rows, Business, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()
