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
RETRY_SUFFIX = ":retry"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class WatermarkRun:
    table_name: str
    run_id: int
    started_at: datetime
    since: datetime | None  # incremental cut-off (already minus delta); None = full fetch


def get_last_success_start(session: Session, table_name: str) -> datetime | None:
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
    partial: bool = False,
) -> Iterator[WatermarkRun]:

    if partial:
        table_name = f"{table_name}{RETRY_SUFFIX}"
        full_refresh = True   # the caller supplies its own cut-off; do not consult the watermark
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


def raise_if_failed(
    name: str,
    failed_parents: list[str],
    since: datetime | None = None,
    error: str = "fetch failed",
) -> None:
    if not failed_parents:
        return
    from utils.retry_queue import get_retry_queue  # local import: avoids a cycle at module load

    queue = get_retry_queue()
    since_text = since.isoformat(timespec="seconds") if since else None
    for parent in failed_parents:
        queue.record(name, parent, since_text, None, error)
    raise RuntimeError(
        f"{name}: fetch failed for {len(failed_parents)} parent(s) ({', '.join(failed_parents)}); "
        "queued for retry; run marked Failed so the watermark does not advance"
    )
