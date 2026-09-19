import json
from datetime import date

import pandas as pd
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from facts.fact_helpers import as_date, date_key, daily_window, log_fact_window
from models import AdAccount, AdInsightsDaily
from utils.dbloader import open_session, resolve_token, upsert
from utils.dimension_helpers import bare_account_id
from utils.logging import logger
from utils.metaclient import MetaClient, get_client


FIELDS = (
    "date_start,date_stop,account_id,campaign_id,adset_id,ad_id,"
    "impressions,reach,frequency,spend,social_spend,clicks,unique_clicks,"
    "cpc,cpp,inline_link_clicks,inline_link_click_ctr,cost_per_inline_link_click,"
    "inline_post_engagement,cost_per_inline_post_engagement,actions,cost_per_action_type"
)
PARAMS = {"level": "ad", "time_increment": 1, "fields": FIELDS, "limit": 100}
KEY_COLUMNS = ["AdID", "DateKey"]

# LEAD_ACTION_TYPES = {"lead", "onsite_conversion.lead", "leadgen_grouped"}
LEAD_ACTION_TYPES = {"lead"}

OUTPUT_COLUMNS = [
    "AdID", "AdSetID", "CampaignID", "AdAccountID", "Date", "DateKey", "Impressions", "Reach",
    "Frequency", "Spend", "SocialSpend", "Clicks", "UniqueClicks", "CPC", "CPP", "InlineLinkClicks",
    "InlineLinkClickCTR", "CostPerInlineLinkClick", "InlinePostEngagement", "CostPerInlinePostEngagement",
    "Leads", "CostPerLead",
]


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _action_value(actions, action_types: set[str]):
    total = 0.0
    found = False
    for action in actions or []:
        if action.get("action_type") in action_types:
            value = _number(action.get("value"))
            if value is not None:
                total += value
                found = True
    return total if found else None


def _extract(client: MetaClient, token: str, account_ids: list[str], since: str, until: str) -> list[dict]:
    rows: list[dict] = []
    params = {**PARAMS, "time_range": json.dumps({"since": since, "until": until})}
    for index, account_id in enumerate(account_ids, start=1):
        try:
            for page in client.paginate(f"/act_{bare_account_id(account_id)}/insights", token, params):
                rows.extend(page)
            logger.info("AdInsightsDaily fetch done for AccountID=%s", account_id)
        except Exception:
            logger.exception("AdInsightsDaily fetch failed for AccountID=%s", account_id)
            continue
        if index == len(account_ids) or index % 10 == 0:
            logger.info("Processed %d/%d ad accounts for AdInsightsDaily", index, len(account_ids))
    return rows


def _transform(raw_rows: list[dict]) -> pd.DataFrame:
    rows = []
    for item in raw_rows:
        day = as_date(item.get("date_start"))
        rows.append({
            "AdID": item.get("ad_id"), "AdSetID": item.get("adset_id"), "CampaignID": item.get("campaign_id"),
            "AdAccountID": bare_account_id(item.get("account_id")), "Date": day, "DateKey": date_key(day),
            "Impressions": _number(item.get("impressions")), "Reach": _number(item.get("reach")),
            "Frequency": _number(item.get("frequency")), "Spend": _number(item.get("spend")),
            "SocialSpend": _number(item.get("social_spend")), "Clicks": _number(item.get("clicks")),
            "UniqueClicks": _number(item.get("unique_clicks")), "CPC": _number(item.get("cpc")),
            "CPP": _number(item.get("cpp")), "InlineLinkClicks": _number(item.get("inline_link_clicks")),
            "InlineLinkClickCTR": _number(item.get("inline_link_click_ctr")),
            "CostPerInlineLinkClick": _number(item.get("cost_per_inline_link_click")),
            "InlinePostEngagement": _number(item.get("inline_post_engagement")),
            "CostPerInlinePostEngagement": _number(item.get("cost_per_inline_post_engagement")),
            "Leads": _action_value(item.get("actions"), LEAD_ACTION_TYPES),
            "CostPerLead": _action_value(item.get("cost_per_action_type"), LEAD_ACTION_TYPES),
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).dropna(subset=["AdID", "Date"]).drop_duplicates(subset=KEY_COLUMNS).reset_index(drop=True)


def fact_ad_insights_daily(
    db_connection: Engine | Connection | Session | None = None,
    metaclient: MetaClient | None = None,
    token: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> int:
    since, until = daily_window(since, until)
    session, owns_session = open_session(db_connection)
    client = metaclient or get_client()
    try:
        account_ids = [str(value) for value in session.execute(AdAccount.__table__.select().with_only_columns(AdAccount.AccountID)).scalars()]
        access_token = token or resolve_token(session)
        log_fact_window("AdInsightsDaily", since, until, len(account_ids))
        rows = _transform(_extract(client, access_token, account_ids, since, until))
        return upsert(rows, AdInsightsDaily, KEY_COLUMNS, session=session)
    finally:
        if owns_session:
            session.close()
        if metaclient is None:
            client.close()


if __name__ == "__main__":
    fact_ad_insights_daily()
