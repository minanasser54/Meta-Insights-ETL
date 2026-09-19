from datetime import datetime, timedelta, timezone ,date  

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import Page, Post
from config import get_conf
from utils.dbloader import open_session, read_ids, resolve_token, upsert
from utils.dimension_helpers import as_datetime, get_watermarks
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


FIELDS = "id,created_time,updated_time,permalink_url,status_type,is_published,is_expired,is_hidden"
PARAMS = {"fields": FIELDS, "limit": 100}
KEY_COLUMNS = ["PostID"]
OUTPUT_COLUMNS = ["PostID", "PageID", "CreatedTime", "UpdatedTime", "PermalinkURL", "StatusType", "IsPublished", "IsExpired", "IsHidden"]

# /posts `since` filters on created_time, NOT updated_time, so edits to old posts
# (IsHidden/IsPublished/IsExpired/...) are invisible to it. Re-fetch everything created
# within this window on every run so recent posts keep their flags in sync. Older posts
# are only refreshed by full_refresh=True.
POST_LOOKBACK = timedelta(days=30)
FULL_REFRESH_WEEKDAY = 3

def _page_tokens(client: MetaClient, user_token: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for page in client.paginate("/me/accounts", user_token, {"fields": "id,access_token", "limit": 500}):
        for item in page:
            if item.get("id") and item.get("access_token"):
                tokens[str(item["id"])] = str(item["access_token"])
    return tokens


def _since_params(watermark: datetime | None) -> dict:
    params = dict(PARAMS)  # never mutate the module-level dict
    if watermark is not None:
        # Stored values are naive UTC (see as_datetime), so tag as UTC before converting.
        since_dt = watermark.replace(tzinfo=timezone.utc) - POST_LOOKBACK
        params["since"] = int(since_dt.timestamp())
    return params


def _extract(
    client: MetaClient,
    user_token: str,
    page_ids: list[str],
    watermarks: dict[str, datetime],
) -> list[dict]:
    if not page_ids:
        return []
    tokens = _page_tokens(client, user_token)
    rows: list[dict] = []
    for index, page_id in enumerate(page_ids, start=1):
        page_token = tokens.get(page_id) or get_conf().page_access_token
        if not page_token:
            logger.warning("Skipping Post fetch because no Page access token was returned for PageID=%s", page_id)
            continue
        watermark = watermarks.get(str(page_id))
        params = _since_params(watermark)
        page_rows = 0
        try:
            for page in client.paginate(f"/{page_id}/posts", page_token, params):
                for post in page:
                    post["_page_id"] = page_id
                    rows.append(post)
                    page_rows += 1
            logger.info(
                "Post fetch done for PageID=%s (%s): %d row(s)",
                page_id, "full" if watermark is None else f"since {watermark.isoformat()} minus {POST_LOOKBACK}", page_rows,
            )
        except Exception:
            logger.exception("Post fetch failed for PageID=%s", page_id)
            continue
        if index == len(page_ids) or index % 100 == 0:
            logger.info("Processed %d/%d pages for Post", index, len(page_ids))
    return rows


def _transform(raw_rows: list[dict]) -> pd.DataFrame:
    rows = []
    for post in raw_rows:
        rows.append({
            "PostID": post.get("id"),
            "PageID": post.get("_page_id"),
            "CreatedTime": as_datetime(post.get("created_time")),
            "UpdatedTime": as_datetime(post.get("updated_time")),
            "PermalinkURL": post.get("permalink_url"),
            "StatusType": post.get("status_type"),
            "IsPublished": post.get("is_published"),
            "IsExpired": post.get("is_expired"),
            "IsHidden": post.get("is_hidden"),
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def dimension_post(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    last_run: datetime | None = None,  # unused: kept so run_staging's call signature stays compatible
    full_refresh: bool | None = None,  # None = auto (full on FULL_REFRESH_WEEKDAY); True/False forces the mode
) -> int:
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        if full_refresh is None:
            full_refresh = date.today().weekday() == FULL_REFRESH_WEEKDAY
            if full_refresh:
                logger.info("Today is the weekly Post full-refresh day; ignoring watermarks")

        page_ids = read_ids(session, Page, "PageID")
        access_token = token or resolve_token(session)

        # Watermark = newest CreatedTime already stored per page (since filters on created_time).
        watermarks = {} if full_refresh else get_watermarks(session, Post, "PageID", time_column="CreatedTime")
        logger.info(
            "Extracting Post for %d page(s) (%s, lookback=%s); %d with watermark",
            len(page_ids), "FULL REFRESH" if full_refresh else "incremental", POST_LOOKBACK, len(watermarks),
        )

        raw = _extract(client, access_token, page_ids, watermarks)
        if not raw:
            logger.info("No new or updated Post rows; nothing to upsert")
            return 0
        return upsert(_transform(raw), Post, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()

if __name__ == "__main__":
    dimension_post()

