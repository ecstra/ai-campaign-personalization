from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import JOB_INTERVAL_SECONDS, REPLY_CHECK_INTERVAL_SECONDS
from .processor import SchedulerProcessorUtility

class SchedulerUtility:
    _scheduler: AsyncIOScheduler | None = None

    @staticmethod
    def start_scheduler() -> None:
        if SchedulerUtility._scheduler is not None:
            return

        SchedulerUtility._scheduler = AsyncIOScheduler()

        SchedulerUtility._scheduler.add_job(
            SchedulerProcessorUtility.process_leads_job,
            trigger=IntervalTrigger(seconds=JOB_INTERVAL_SECONDS),
            id="email_processing_job",
            name="Process pending emails",
            replace_existing=True,
            next_run_time=datetime.now(),
        )

        SchedulerUtility._scheduler.add_job(
            SchedulerProcessorUtility.check_replies_job,
            trigger=IntervalTrigger(seconds=REPLY_CHECK_INTERVAL_SECONDS),
            id="reply_checking_job",
            name="Check for email replies via IMAP",
            replace_existing=True,
            next_run_time=datetime.now(),
        )

        SchedulerUtility._scheduler.add_job(
            SchedulerProcessorUtility.check_scheduled_campaigns,
            trigger=IntervalTrigger(seconds=60),
            id="scheduled_campaign_job",
            name="Auto-start scheduled campaigns",
            replace_existing=True,
            next_run_time=datetime.now(),
        )

        SchedulerUtility._scheduler.start()

    @staticmethod
    def stop_scheduler() -> None:
        if SchedulerUtility._scheduler is None:
            return

        SchedulerUtility._scheduler.shutdown(wait=False)
        SchedulerUtility._scheduler = None
