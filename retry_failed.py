"""
Drain the failed-fetch queue.

    python retry_failed.py            # retry everything pending
    python retry_failed.py --list     # just show what is queued

Every entry is re-fetched for exactly the entity and time range that originally failed:
  * facts       -> since/until stored on the entry (until is exclusive)
  * dimensions  -> the incremental cut-off stored in `since` (null = it was a full fetch)

Outcomes per entry
  success -> removed from the queue
  failure -> stays queued, attempts += 1
  attempts >= retry_max_attempts -> moved to <queue>.dead.txt for manual review (nothing is
                                    written to the fact table: a gap stays a gap, never a fake 0)
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime

from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from config import get_conf
from dimensions.AdSet import dimension_adset
from dimensions.AdandCreative import dimension_ad_and_creative
from dimensions.Campaign import dimension_campaign
from dimensions.Page import dimension_page
from dimensions.Post import dimension_post
from facts.AdInsightsDaily import fact_ad_insights_daily
from facts.PageInsightsDaily import fact_page_insights_daily
from utils.dbloader import create_schema, get_engine
from utils.logging import logger
from utils.metaclient import MetaClient, get_client
from utils.retry_queue import FailedFetch, get_retry_queue

# table name (as stored in the queue) -> (callable, kind, id-keyword)
FACT_HANDLERS = {
    "AdInsightsDaily": (fact_ad_insights_daily, "account_ids"),
    "PageInsightsDaily": (fact_page_insights_daily, "page_ids"),
}
DIM_HANDLERS = {
    "Campaign": dimension_campaign,
    "AdSet": dimension_adset,
    "Ad": dimension_ad_and_creative,
    "Post": dimension_post,
}
# Dimensions whose parents are Businesses rather than accounts/pages are re-run in full: they are
# tiny, and their upsert is idempotent.
FULL_RERUN_DIMS = {"Page": dimension_page}


def _still_queued(queue, entry: FailedFetch) -> bool:
    return any(p.key == entry.key for p in queue.pending(entry.table))


def _retry_fact(engine, client: MetaClient, entry: FailedFetch) -> None:
    fn, id_kw = FACT_HANDLERS[entry.table]
    failed: list[str] = []
    # record_failures=False: the runner owns queue bookkeeping so attempts are not double counted.
    fn(db_connection=engine, metaclient=client, since=entry.since, until=entry.until,
       record_failures=False, failed_out=failed, **{id_kw: [entry.entity_id]})
    if failed:
        # Facts swallow per-entity errors, so surface it as an exception for the runner.
        raise RuntimeError(f"{entry.table} still failing for {entry.entity_id}")


def _retry_dimension(engine, client: MetaClient, entry: FailedFetch) -> None:
    since = datetime.fromisoformat(entry.since) if entry.since else None
    if entry.table in FULL_RERUN_DIMS:
        FULL_RERUN_DIMS[entry.table](db_connection=engine, metaclient=client)
        return
    DIM_HANDLERS[entry.table](
        db_connection=engine, metaclient=client, parent_ids=[entry.entity_id], since_override=since,
    )


def run_retries(db_connection: Engine | Connection | Session | None = None, metaclient: MetaClient | None = None) -> dict:
    queue = get_retry_queue()
    entries = queue.pending()
    summary = {"attempted": 0, "succeeded": 0, "failed": 0, "abandoned": 0}
    if not entries:
        logger.info("Retry queue is empty")
        return summary

    engine = db_connection or get_engine()
    create_schema(engine)
    client = metaclient or get_client()
    logger.info("Retrying %d failed fetch(es)", len(entries))

    # Dimensions first (parents), then facts (which need up-to-date parents for zero-fill).
    order = {**{t: 0 for t in list(FULL_RERUN_DIMS) + list(DIM_HANDLERS)}, **{t: 1 for t in FACT_HANDLERS}}
    entries.sort(key=lambda e: order.get(e.table, 2))
    try:
        for entry in entries:
            summary["attempted"] += 1
            # Remove first, then re-record on failure: this gives correct `attempts` accounting and
            # lets the inner run re-queue itself for dimensions (via raise_if_failed).
            queue.resolve(entry.table, entry.entity_id, entry.since, entry.until)
            try:
                if entry.table in FACT_HANDLERS:
                    _retry_fact(engine, client, entry)
                elif entry.table in DIM_HANDLERS or entry.table in FULL_RERUN_DIMS:
                    _retry_dimension(engine, client, entry)
                else:
                    logger.warning("No retry handler for table=%s; leaving it queued", entry.table)
                    queue.record(entry.table, entry.entity_id, entry.since, entry.until, "no handler")
                    continue
                summary["succeeded"] += 1
            except Exception as exc:
                summary["failed"] += 1
                _requeue_preserving_attempts(queue, entry, exc)
    finally:
        if metaclient is None:
            client.close()

    dead = queue.bury_exhausted()
    summary["abandoned"] = len(dead)
    logger.info("Retry summary: %s; %d still queued", summary, len(queue))
    return summary


def _requeue_preserving_attempts(queue, entry: FailedFetch, exc: BaseException) -> None:
    """Put a still-failing entry back with its attempt counter carried forward."""
    # The inner run may already have re-queued it (dimensions do, via raise_if_failed).
    existing = [p for p in queue.pending(entry.table) if p.key == entry.key]
    if existing:
        # that fresh record has attempts=1; overwrite with the carried-forward count.
        queue.resolve(entry.table, entry.entity_id, entry.since, entry.until)
    carried = FailedFetch(
        table=entry.table, entity_id=entry.entity_id, since=entry.since, until=entry.until,
        error=str(exc)[:500], attempts=entry.attempts + 1,
        first_failed_at=entry.first_failed_at,
    )
    with_items = queue.pending()
    with_items.append(carried)
    queue._write(with_items)  # noqa: SLF001 - same-package helper; keeps first_failed_at


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="show queued entries and exit")
    args = parser.parse_args()
    if args.list:
        for e in get_retry_queue().pending():
            print(f"{e.table:20} entity={e.entity_id:>18} window={e.since}..{e.until} attempts={e.attempts} err={e.error[:60]}")
        return
    print(run_retries())


if __name__ == "__main__":
    main()
