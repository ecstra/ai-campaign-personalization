from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import JOB_INTERVAL_SECONDS, CAMPAIGN_CHECK_INTERVAL_SECONDS
from .processor import SchedulerProcessorUtility

_STARTUP_STAGGER_SECONDS = 5

class SchedulerUtility:
    _scheduler: AsyncIOScheduler | None = None

    @staticmethod
    def start_scheduler() -> None:
        if SchedulerUtility._scheduler is not None:
            return

        SchedulerUtility._scheduler = AsyncIOScheduler()
        now = datetime.now()

        SchedulerUtility._scheduler.add_job(
            SchedulerProcessorUtility.process_leads_job,
            trigger=IntervalTrigger(seconds=JOB_INTERVAL_SECONDS),
            id="email_processing_job",
            name="Process pending emails",
            replace_existing=True,
            next_run_time=now,
        )

        SchedulerUtility._scheduler.add_job(
            SchedulerProcessorUtility.check_scheduled_campaigns,
            trigger=IntervalTrigger(seconds=CAMPAIGN_CHECK_INTERVAL_SECONDS),
            id="scheduled_campaign_job",
            name="Auto-start scheduled campaigns",
            replace_existing=True,
            next_run_time=now + timedelta(seconds=_STARTUP_STAGGER_SECONDS),
        )

        SchedulerUtility._scheduler.start()

    @staticmethod
    def stop_scheduler() -> None:
        if SchedulerUtility._scheduler is None:
            return

        SchedulerUtility._scheduler.shutdown(wait=True)
        SchedulerUtility._scheduler = None
