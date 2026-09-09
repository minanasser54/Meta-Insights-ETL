from datetime import datetime

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import Business, Page
from utils.dbloader import open_session, read_ids, resolve_token, upsert
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


FIELDS = "id,name,verification_status,is_verified,is_published,business{id}"
PARAMS = {"fields": FIELDS, "limit": 100}
KEY_COLUMNS = ["PageID"]
OUTPUT_COLUMNS = ["PageID", "PageName", "BusinessID", "VerificationStatus", "IsVerified", "IsPublished"]


def _extract(client: MetaClient, token: str, business_ids: list[str]) -> list[dict]:
    rows: list[dict] = []
    for index, business_id in enumerate(business_ids, start=1):
        try:
            for page in client.paginate(f"/{business_id}/owned_pages", token, PARAMS):
                for item in page:
                    item["_business_id"] = business_id
                    rows.append(item)
        except Exception:
            logger.exception("Page fetch failed for BusinessID=%s", business_id)
            continue
        if index == len(business_ids) or index % 100 == 0:
            logger.info("Processed %d/%d businesses for Page", index, len(business_ids))
    return rows


def _transform(raw_rows: list[dict]) -> pd.DataFrame:
    rows = []
    for page in raw_rows:
        business = page.get("business") or {}
        rows.append({
            "PageID": page.get("id"),
            "PageName": page.get("name"),
            "BusinessID": business.get("id") or page.get("_business_id"),
            "VerificationStatus": page.get("verification_status"),
            "IsVerified": page.get("is_verified"),
            "IsPublished": page.get("is_published"),
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def dimension_page(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    last_run: datetime | None = None,
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        business_ids = read_ids(session, Business, "BusinessID")
        access_token = token or resolve_token(session)
        logger.info("Extracting Page for %d business(es); last_run=%s", len(business_ids), last_run)
        return upsert(_transform(_extract(client, access_token, business_ids)), Page, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    dimension_page()
