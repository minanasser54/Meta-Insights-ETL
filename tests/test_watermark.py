import json, os, sys, tempfile
from datetime import date, datetime, timedelta

tmp = tempfile.mkdtemp()
os.environ.update(
    METAETL_SQLITE_PATH=f"{tmp}/t.sqlite3", METAETL_USER_TOKEN="tok",
    METAETL_LOG_DIRECTORY=f"{tmp}/logs", METAETL_PAGE_ACCESS_TOKEN="ptok",
)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, select

import models
from models import Ad, AdAccount, AdSet, Campaign, EtlWatermark, Post, Business, Page
from utils.dbloader import create_schema, get_engine, open_session
from utils.watermark import track_run, get_last_success_start
import dimensions.Campaign as dCampaign
import dimensions.AdSet as dAdSet
import dimensions.AdandCreative as dAd
import dimensions.Post as dPost
from dimensions.AdAccount import dimension_adaccount
from dimensions.business import dimension_business
from dimensions.Page import dimension_page
from dimensions.Campaign import dimension_campaign
from dimensions.AdSet import dimension_adset
from dimensions.AdandCreative import dimension_ad_and_creative
from dimensions.Post import dimension_post
from facts.AdInsightsDaily import fact_ad_insights_daily
from facts.PageInsightsDaily import fact_page_insights_daily
from facts.PostInsightsDaily import fact_post_insights_daily
import main  # all imports in main.py still resolve

eng = get_engine()
create_schema(eng)


class Fake:
    def __init__(self):
        self.calls = []
        self.fail = set()  # endpoints (suffix match) that raise

    def close(self): pass

    def paginate(self, endpoint, token, params=None):
        self.calls.append((endpoint, dict(params or {})))
        for f in self.fail:
            if endpoint.endswith(f):
                raise RuntimeError("boom")
        if endpoint == "/me/adaccounts":
            yield [{"id": "act_111", "name": "A", "business": {"id": "9", "name": "B"}},
                   {"id": "act_222", "name": "B", "business": {"id": "9", "name": "B"}}]
        elif endpoint == "/me/accounts":
            yield [{"id": "5", "access_token": "pt"}]
        elif endpoint == "/9/owned_pages":
            yield [{"id": "5", "name": "P"}]
        elif endpoint.endswith("/campaigns"):
            a = endpoint.split("_")[1].split("/")[0]
            yield [{"id": f"{a}01", "name": "c", "updated_time": "2026-09-01T00:00:00+0000"}]
        elif endpoint.endswith("/adsets"):
            a = endpoint.split("_")[1].split("/")[0]
            yield [{"id": f"{a}11", "campaign_id": f"{a}01", "name": "s", "updated_time": "2026-09-01T00:00:00+0000"}]
        elif endpoint.endswith("/ads"):
            a = endpoint.split("_")[1].split("/")[0]
            yield [{"id": f"{a}21", "adset_id": f"{a}11", "campaign_id": f"{a}01", "account_id": a,
                    "creative": {"id": "777"}, "name": "a", "updated_time": "2026-09-01T00:00:00+0000"}]
        elif endpoint == "/5/posts":
            yield [{"id": "5_1", "created_time": "2026-09-01T00:00:00+0000"}]
        elif endpoint.endswith("/insights") and endpoint.startswith("/act_"):
            y = (date.today() - timedelta(days=1)).isoformat()
            yield [{"date_start": y, "ad_id": "9", "account_id": "act_111", "impressions": "10"}]
        elif endpoint == "/5/insights":
            yield [{"name": "page_views_total", "values": [{"end_time": f"{date.today().isoformat()}T07:00:00+0000", "value": 3}]}]
        elif endpoint == "/5_1/insights":
            yield [{"name": "post_reactions_by_type_total", "values": [{"value": {"like": 2}}]}]
        else:
            yield []


def runs(name=None):
    with open_session(eng)[0] as s:
        q = select(EtlWatermark).order_by(EtlWatermark.RunID)
        if name:
            q = q.where(EtlWatermark.TableName == name)
        return [(r.TableName, r.StartTime, r.EndTime, r.Status) for r in s.execute(q).scalars()]


def filt(c, suffix):
    """Meta `filtering` clause of the last call to an endpoint, as a dict (or None)."""
    call = [p for e, p in c.calls if e.endswith(suffix)][-1]
    return json.loads(call["filtering"])[0] if "filtering" in call else None


# ---------- schema ----------
insp = inspect(eng)
tables = insp.get_table_names()
assert "Creative" not in tables, tables
assert "metaadsetl" in tables, tables
assert [c["name"] for c in insp.get_columns("metaadsetl")] == ["RunID", "TableName", "StartTime", "EndTime", "Status"]
assert "Creative" not in [c.name for c in Ad.__table__.columns] and "CreativeID" in Ad.__table__.columns
print("schema ok: Creative gone, metaadsetl present")

# ---------- run 1: dims, no prior success => full fetch ----------
c = Fake()
assert dimension_business(eng, c, "tok") == 1
assert dimension_adaccount(eng, c, "tok") == 2
assert dimension_campaign(eng, c, "tok") == 2
assert dimension_adset(eng, c, "tok") == 2
assert dimension_ad_and_creative(eng, c, "tok") == 2
assert dimension_page(eng, c, "tok") == 1
assert dimension_post(eng, c, "tok", full_refresh=False) == 1

with open_session(eng)[0] as s:
    ids = sorted(s.execute(select(AdAccount.AccountID)).scalars())
    assert ids == [111, 222] and all(isinstance(i, int) for i in ids), ids
    assert s.execute(select(Ad.CreativeID)).scalars().first() == 777
print("AdAccount ids are bare ints:", ids)

assert filt(c, "/campaigns") is None and filt(c, "/adsets") is None and filt(c, "/ads") is None
assert "since" not in [p for e, p in c.calls if e == "/5/posts"][-1]
assert "creative{id}" in [p for e, p in c.calls if e.endswith("/ads")][-1]["fields"]
for name in ("Business", "AdAccount", "Campaign", "AdSet", "Ad", "Page", "Post"):
    r = runs(name)
    assert len(r) == 1 and r[0][3] == "Success" and r[0][2] is not None and r[0][2] >= r[0][1], (name, r)
print("run 1: every dim logged Running->Success, first fetch was full")

# ---------- run 2: incremental = last success START - per-file delta ----------
starts = {n: runs(n)[-1][1] for n in ("Campaign", "AdSet", "Ad", "Post")}
c = Fake()
dimension_campaign(eng, c, "tok"); dimension_adset(eng, c, "tok"); dimension_ad_and_creative(eng, c, "tok")
dimension_post(eng, c, "tok", full_refresh=False)


def ts(dt):  # naive UTC datetime -> epoch seconds
    return int((dt - datetime(1970, 1, 1)).total_seconds())


for suffix, name, delta in (("/campaigns", "Campaign", dCampaign.WATERMARK_DELTA),
                            ("/adsets", "AdSet", dAdSet.WATERMARK_DELTA),
                            ("/ads", "Ad", dAd.WATERMARK_DELTA)):
    f = filt(c, suffix)
    assert f == {"field": "updated_time", "operator": "GREATER_THAN", "value": ts(starts[name] - delta)}, (name, f)
post_params = [p for e, p in c.calls if e == "/5/posts"][-1]
assert post_params["since"] == ts(starts["Post"] - dPost.WATERMARK_DELTA), post_params
print("run 2: filters use last start - delta:",
      {k: v for k, v in (("Campaign", dCampaign.WATERMARK_DELTA), ("AdSet", dAdSet.WATERMARK_DELTA),
                         ("Ad", dAd.WATERMARK_DELTA), ("Post", dPost.WATERMARK_DELTA))})

# ---------- failure: one account errors => Failed, watermark must NOT advance ----------
good_start = runs("Campaign")[-1][1]
c = Fake(); c.fail = {"act_222/campaigns"}
try:
    dimension_campaign(eng, c, "tok")
    raise SystemExit("expected failure")
except RuntimeError as e:
    assert "222" in str(e)
last = runs("Campaign")[-1]
assert last[3] == "Failed" and last[2] is not None
with open_session(eng)[0] as s:
    assert get_last_success_start(s, "Campaign") == good_start          # unchanged
    assert s.execute(select(Campaign.CampaignID).where(Campaign.CampaignID == 11101)).first()  # good account still loaded
c = Fake()
dimension_campaign(eng, c, "tok")
f = filt(c, "/campaigns")
assert f["value"] == ts(good_start - dCampaign.WATERMARK_DELTA), "retry must reuse the last SUCCESS start"
assert runs("Campaign")[-1][3] == "Success"
print("failure: run marked Failed, watermark not advanced, retry re-fetches the same window")

# ---------- exception before any fetch (bad token) is also logged as Failed ----------
try:
    dimension_adset(eng, Fake(), token=None)   # resolve_token uses env token -> succeeds; force error differently
except Exception:
    pass
n_before = len(runs("AdSet"))
class Boom(Fake):
    def paginate(self, *a, **k): raise RuntimeError("api down")
try:
    dimension_adset(eng, Boom(), "tok")
    raise SystemExit("expected failure")
except RuntimeError:
    pass
assert len(runs("AdSet")) == n_before + 1 and runs("AdSet")[-1][3] == "Failed"

# ---------- full_refresh bypasses the watermark but is still logged ----------
c = Fake()
dimension_campaign(eng, c, "tok", full_refresh=True)
assert filt(c, "/campaigns") is None and runs("Campaign")[-1][3] == "Success"
print("full_refresh: no filter, still logged")

# ---------- stale 'Running' row (crashed process) is ignored ----------
with open_session(eng)[0] as s:
    s.add(EtlWatermark(TableName="Campaign", StartTime=datetime.utcnow() + timedelta(hours=1), Status="Running"))
    s.commit()
    latest_success = s.execute(select(EtlWatermark.StartTime).where(
        EtlWatermark.TableName == "Campaign", EtlWatermark.Status == "Success").order_by(EtlWatermark.StartTime.desc())).scalars().first()
    assert get_last_success_start(s, "Campaign") == latest_success
print("crashed 'Running' rows do not move the watermark")

# ---------- facts log too ----------
c = Fake()
assert fact_ad_insights_daily(eng, c, "tok") == 1
assert fact_page_insights_daily(eng, c, "tok") == 1
assert fact_post_insights_daily(eng, c, "tok", post_mode="all") == 1
for name in ("AdInsightsDaily", "PageInsightsDaily", "PostInsightsDaily"):
    assert runs(name)[-1][3] == "Success", name
print("facts logged Success")

# ---------- full run_staging path ----------
# PostInsightsDaily is a plain INSERT keyed (PostID, DateKey): a 2nd run on the same day violates the PK
# (pre-existing behaviour, unrelated to the watermark). Clear today's snapshot so this step is independent.
from sqlalchemy import delete
from models import PostInsightsDaily
with open_session(eng)[0] as s:
    s.execute(delete(PostInsightsDaily)); s.commit()
main.run_staging(db_connection=eng, metaclient=Fake(), token="tok")
for name in ("Business", "AdAccount", "Campaign", "AdSet", "Ad", "Page", "Post",
             "AdInsightsDaily", "PageInsightsDaily", "PostInsightsDaily"):
    assert runs(name)[-1][3] in ("Success",), (name, runs(name)[-1])
print("run_staging: all 10 tables have a Success row")
print("\nALL TESTS PASSED")
