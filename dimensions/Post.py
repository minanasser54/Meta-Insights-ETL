from datetime import date, datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from models import Page, Post
from config import get_conf
from utils.dbloader import open_session, read_ids, resolve_token, upsert
from utils.dimension_helpers import as_datetime
from utils.logging import logger
from utils.metaclient import MetaClient, get_client
from utils.watermark import raise_if_failed, track_run


FIELDS = "id,created_time,updated_time,permalink_url,status_type,is_published,is_expired,is_hidden"
PARAMS = {"fields": FIELDS, "limit": 100}
KEY_COLUMNS = ["PostID"]
OUTPUT_COLUMNS = ["PostID", "PageID", "CreatedTime", "UpdatedTime", "PermalinkURL", "StatusType", "IsPublished", "IsExpired", "IsHidden"]

# Incremental cut-off = last successful run's start (Watermark.metaadsetl) minus this delta.
# /posts `since` filters on created_time, NOT updated_time, so edits to old posts
# (IsHidden/IsPublished/IsExpired/...) are invisible to it. The delta therefore doubles as a
# lookback: everything created within this window before the last run is re-fetched every run
# so recent posts keep their flags in sync. Older posts are only refreshed by full_refresh=True.
WATERMARK_DELTA = timedelta(days=30)
FULL_REFRESH_WEEKDAY = 3

def _page_tokens(client: MetaClient, user_token: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for page in client.paginate("/me/accounts", user_token, {"fields": "id,access_token", "limit": 500}):
        for item in page:
            if item.get("id") and item.get("access_token"):
                tokens[str(item["id"])] = str(item["access_token"])
    return tokens


def _since_params(since: datetime | None) -> dict:
    params = dict(PARAMS)  # never mutate the module-level dict
    if since is not None:
        # `since` is naive UTC (see as_datetime), so tag as UTC before converting.
        params["since"] = int(since.replace(tzinfo=timezone.utc).timestamp())
    return params


def _extract(
    client: MetaClient,
    user_token: str,
    page_ids: list[str],
    since: datetime | None,
) -> tuple[list[dict], list[str]]:
    """Returns (rows, failed_page_ids). A Page with no access token is skipped with a warning, not failed."""
    if not page_ids:
        return [], []
    tokens = _page_tokens(client, user_token)
    rows: list[dict] = []
    failed: list[str] = []
    params = _since_params(since)
    for index, page_id in enumerate(page_ids, start=1):
        page_token = tokens.get(page_id) or get_conf().page_access_token
        if not page_token:
            logger.warning("Skipping Post fetch because no Page access token was returned for PageID=%s", page_id)
            continue
        page_rows = 0
        try:
            for page in client.paginate(f"/{page_id}/posts", page_token, params):
                for post in page:
                    post["_page_id"] = page_id
                    rows.append(post)
                    page_rows += 1
            logger.info("Post fetch done for PageID=%s: %d row(s)", page_id, page_rows)
        except Exception:
            logger.exception("Post fetch failed for PageID=%s", page_id)
            failed.append(str(page_id))
            continue
        if index == len(page_ids) or index % 100 == 0:
            logger.info("Processed %d/%d pages for Post", index, len(page_ids))
    logger.info(
        "Post extract summary: %s, %d row(s) fetched, %d page(s) failed",
        "full" if since is None else f"created_time >= {since.isoformat()}", len(rows), len(failed),
    )
    return rows, failed


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
                logger.info("Today is the weekly Post full-refresh day; ignoring the watermark")

        with track_run(session, Post.__tablename__, delta=WATERMARK_DELTA, full_refresh=full_refresh) as run:
            page_ids = read_ids(session, Page, "PageID")
            access_token = token or resolve_token(session)
            logger.info(
                "Extracting Post for %d page(s) (%s)",
                len(page_ids), "FULL REFRESH" if run.since is None else f"incremental since {run.since}",
            )

            raw, failed = _extract(client, access_token, page_ids, run.since)
            loaded = 0
            if raw:
                loaded = upsert(_transform(raw), Post, KEY_COLUMNS, session=session)
            else:
                logger.info("No new or updated Post rows; nothing to upsert")
            raise_if_failed("Post", failed)
            return loaded
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    dimension_post()
