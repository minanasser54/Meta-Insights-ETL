"""ETL run log / incremental watermark, stored in Watermark.metaadsetl.

Every dimension/fact run is wrapped in `track_run`:

    with track_run(session, "Campaign", delta=WATERMARK_DELTA) as run:
        ... fetch rows with `run.since` ...

* On entry a row (TableName, StartTime=now, EndTime=NULL, Status='Running') is
  inserted and committed immediately, so it is visible even if the run dies.
* On normal exit the row is updated to Status='Success' with EndTime.
* On any exception the row is updated to Status='Failed' with EndTime and the
  exception is re-raised.

`run.since` is the incremental cut-off for that table:

    MAX(StartTime) over that table's 'Success' rows  -  delta

Only 'Success' rows count, so a failed (or crashed, still 'Running') run never
advances the watermark. StartTime rather than EndTime is used so rows changed
while a run was in flight are picked up by the next one; `delta` widens the
overlap further (safe because every load is an idempotent upsert).
`run.since` is None on the very first run, or when full_refresh=True, meaning
"fetch everything".

All timestamps are naive UTC, matching how Meta timestamps are stored elsewhere
in the warehouse (see dimension_helpers.as_datetime).
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from models import EtlWatermark
from utils.logging import logger

STATUS_RUNNING = "Running"
STATUS_SUCCESS = "Success"
STATUS_FAILED = "Failed"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class WatermarkRun:
    table_name: str
    run_id: int
    started_at: datetime
    since: datetime | None  # incremental cut-off (already minus delta); None = full fetch


def get_last_success_start(session: Session, table_name: str) -> datetime | None:
    """Latest StartTime of a successful run of `table_name`, or None.

    On any DB error returns None so the run falls back to a full fetch rather than failing.
    """
    try:
        return session.execute(
            select(func.max(EtlWatermark.StartTime)).where(
                EtlWatermark.TableName == table_name,
                EtlWatermark.Status == STATUS_SUCCESS,
            )
        ).scalar()
    except Exception:
        logger.exception("Could not read watermark for %s; falling back to full fetch", table_name)
        session.rollback()
        return None


def _finish(session: Session, run_id: int, status: str) -> None:
    """Close the run row. Never raises: a logging problem must not mask the ETL result.

    If this update itself fails the row stays 'Running', which the watermark ignores,
    so the next run simply re-fetches from the previous successful start.
    """
    try:
        if status == STATUS_FAILED:
            session.rollback()  # the session may be mid-failure; make it usable again
        session.execute(
            update(EtlWatermark)
            .where(EtlWatermark.RunID == run_id)
            .values(EndTime=utc_now(), Status=status)
        )
        session.commit()
    except Exception:
        logger.exception("Could not mark watermark run_id=%s as %s", run_id, status)
        session.rollback()


@contextmanager
def track_run(
    session: Session,
    table_name: str,
    delta: timedelta | None = None,
    full_refresh: bool = False,
) -> Iterator[WatermarkRun]:
    last_start = None if full_refresh else get_last_success_start(session, table_name)
    since = None
    if last_start is not None:
        since = last_start - delta if delta else last_start

    started_at = utc_now()
    row = EtlWatermark(TableName=table_name, StartTime=started_at, EndTime=None, Status=STATUS_RUNNING)
    try:
        session.add(row)
        session.flush()
        run_id = row.RunID
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Could not create watermark row for %s", table_name)
        raise

    logger.info(
        "Watermark run started: table=%s run_id=%s since=%s (%s)",
        table_name, run_id, since,
        "full refresh requested" if full_refresh else ("no prior success; full fetch" if since is None else f"last success start {last_start} - {delta}"),
    )
    try:
        yield WatermarkRun(table_name, run_id, started_at, since)
    except BaseException:
        _finish(session, run_id, STATUS_FAILED)
        raise
    else:
        _finish(session, run_id, STATUS_SUCCESS)


def raise_if_failed(name: str, failed_parents: list[str]) -> None:
    """Fail the run if any parent (account/page) could not be fetched.

    The rows that *were* fetched are upserted first; raising afterwards marks the run
    'Failed' so the watermark does not advance past data we never received. The next
    run re-fetches from the previous successful start.
    """
    if failed_parents:
        raise RuntimeError(
            f"{name}: fetch failed for {len(failed_parents)} parent(s) ({', '.join(failed_parents)}); "
            "run marked Failed so the watermark does not advance"
        )
