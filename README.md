# Meta Marketing ETL

A staging-layer ETL pipeline that pulls Facebook/Meta Marketing API data (Business, Ad Account, Campaign, AdSet, Ad, Creative, Page, Post) and their daily insight metrics into a SQL Server staging schema (`STG.Marketing`), using SQLAlchemy for the DB layer and pandas for transformation.

## What It Does

Each run has two phases:

1. **Dimensions** — slow-changing entity data (Business → AdAccount → Campaign → AdSet → Ad/Creative → Page → Post). Loaded in that order because each step reads IDs written by the previous one.
2. **Facts** — daily metrics tied to a date (AdInsightsDaily, PageInsightsDaily, PostInsightsSnapshot).

All loads are **upserts** (insert new rows, update existing ones) keyed by natural IDs, except `PostInsightsSnapshot`, which is **insert-only** by design (see below).

## Project Structure

```
main.py                  # Entry points: run_staging(), run_month_backfill(), run_post_insights_backfill()
models.py                # SQLAlchemy ORM models (one class per staging table)
STG_DimTables.sql        # DDL reference for dimension tables
Stg_FactTables.sql       # DDL reference for fact tables

dimensions/
  business.py            # Business
  AdAccount.py           # AdAccount
  Campaign.py             # Campaign
  AdSet.py                # AdSet
  AdandCreative.py        # Ad + Creative (loaded together)
  Page.py                 # Page
  Post.py                 # Post

facts/
  AdInsightsDaily.py      # Ad-level daily performance metrics
  PageInsightsDaily.py    # Page-level daily metrics
  PostInsightsSnapshot.py    # Post-level lifetime metrics, snapshotted daily
  fact_helpers.py         # Shared date/window/token helpers for fact modules

utils/
  dbloader.py             # Engine creation, session handling, generic upsert()
  dimension_helpers.py    # Type coercion (datetime/json/int) + Meta ID helpers
  metaclient.py           # Meta Graph API client: auth, retry, pagination
```

## How a Dimension Module Works (pattern used by all of them)

Every file in `dimensions/` follows the same shape:

1. `_extract(client, token, parent_ids)` — calls the Meta Graph API, paginating over one or more parent IDs (e.g. one call per ad account).
2. `_transform(raw_rows)` — flattens the JSON into a flat `pandas.DataFrame` matching the target table's columns.
3. `dimension_x(db_connection, metaclient, token, last_run)` — opens a DB session, resolves an access token, runs extract → transform → `upsert()`, and closes cleanly.

Fact modules (`facts/`) follow the same extract → transform → load shape, but scope the API pull to a `since`/`until` date window instead of a parent-ID list.

## Setup

Requires (not included in this file set, expected in a `config.py`):

```python
class Settings:
    database_backend: str        # "sqlserver" or "sqlite"
    sql_schema: str              # "STG.Marketing"
    sqlalchemy_url() -> str
    api_version: str             # e.g. "v21.0"
    token_source: str            # "env" | "db" | "auto"
    user_token: str | None
    token_query: str | None
    page_access_token: str | None
    post_insights_mode: str      # "recent" | "all"
    post_insights_limit: int
```

Environment variable expected: `METAETL_USER_TOKEN` (per `resolve_token()` error message), or a DB-stored token reachable via `token_query`.

## Running It

```python
from main import run_staging

# Daily run — dimensions, then facts for "yesterday"
run_staging()
```