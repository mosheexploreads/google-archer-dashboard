"""
APScheduler setup — 4-hour recurring sync job + manual trigger support.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_JOB_ID = "full_sync"
_INTERVAL_HOURS = 4


def _sync_job():
    """Scheduled job: Archer only. Google Ads data arrives via CSV upload."""
    from .services.sync_service import run_full_sync
    run_full_sync()


def start_scheduler():
    global _scheduler
    executors = {"default": ThreadPoolExecutor(max_workers=1)}
    job_defaults = {"coalesce": True, "max_instances": 1}
    _scheduler = BackgroundScheduler(executors=executors, job_defaults=job_defaults)
    _scheduler.add_job(
        _sync_job,
        trigger="interval",
        hours=_INTERVAL_HOURS,
        id=_JOB_ID,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — sync every %d hours", _INTERVAL_HOURS)


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def trigger_sync_now():
    """Manually trigger the sync job immediately (non-blocking)."""
    import threading
    t = threading.Thread(target=_sync_job, daemon=True, name="manual-sync")
    t.start()
    logger.info("Manual sync triggered")


def get_next_run() -> Optional[datetime]:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(_JOB_ID)
    if job and job.next_run_time:
        return job.next_run_time
    return None
