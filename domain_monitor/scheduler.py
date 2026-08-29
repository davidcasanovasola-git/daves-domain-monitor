"""
Scheduler and Background Monitor Loop.
Handles recurring scans, status difference detection, and automatic notification dispatching.
"""

import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

from .checkers.base import DomainResult, DomainStatus
from .checkers.composite import CompositeChecker
from .config import AppConfig
from .database import Database
from .notifiers.manager import NotificationManager

logger = logging.getLogger(__name__)


class DomainMonitorDaemon:
    """
    Background daemon running periodic domain health and availability checks.
    """

    def __init__(
        self,
        config: AppConfig,
        db: Database,
        checker: CompositeChecker,
        notifier_mgr: NotificationManager,
    ):
        self.config = config
        self.db = db
        self.checker = checker
        self.notifier_mgr = notifier_mgr
        self.running = True
        self.last_daily_summary = 0.0

        # Setup graceful termination signals
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame):
        logger.info(f"Received signal {signum}, stopping daemon...")
        self.running = False

    def run_once(self) -> List[DomainResult]:
        """Execute a single complete monitoring pass."""
        monitored = self.db.get_all_monitored_domains(active_only=True)
        if not monitored:
            logger.warning("No active domains to monitor in database.")
            return []

        domain_names = [d["domain"] for d in monitored]
        logger.info(f"Starting check for {len(domain_names)} domains...")

        results = self.checker.check_batch(
            domain_names,
            max_workers=self.config.monitor.max_concurrency,
        )

        available_list = []
        for res in results:
            state_changed, alert_type = self.db.record_check_result(res)
            if res.is_available:
                available_list.append(res.domain)

            # If a critical transition happened (e.g. domain freed up or expiring), alert immediately!
            if state_changed and (
                alert_type in ("BECOME_AVAILABLE", "FOUND_AVAILABLE", "ENTERED_REDEMPTION", "EXPIRING_SOON")
                or (alert_type and alert_type.startswith("EXPIRING_"))
            ):
                logger.info(f"Triggering alert for {res.domain} (type={alert_type})")
                self.notifier_mgr.dispatch_alert(res, alert_type)
                self.db.record_alert(
                    res.domain,
                    alert_type,
                    "all",
                    f"Status changed to {res.status.value}",
                )

        logger.info(f"Completed check. {len(available_list)} available domains found.")
        return results

    def run_loop(self):
        """Continuous monitoring loop."""
        interval_seconds = max(60, self.config.monitor.interval_hours * 3600)
        logger.info(f"Starting Dave's Domain Monitor daemon (Interval: {self.config.monitor.interval_hours}h)...")
        print(f"🚀 Dave's Domain Monitor started. Checking every {self.config.monitor.interval_hours} hours. Press Ctrl+C to exit.")

        while self.running:
            try:
                self.run_once()

                # Send daily summary if 24 hours elapsed
                now = time.time()
                if (now - self.last_daily_summary) >= 86400:
                    stats = self.db.get_summary_stats()
                    all_domains = self.db.get_all_monitored_domains()
                    avail = [d["domain"] for d in all_domains if d["current_status"] == "AVAILABLE"]
                    self.notifier_mgr.dispatch_summary(stats, avail)
                    self.last_daily_summary = now

            except Exception as e:
                logger.error(f"Error during scan iteration: {e}", exc_info=True)

            # Sleep in short increments to respond swiftly to shutdown signals
            sleep_step = 2
            slept = 0
            while self.running and slept < interval_seconds:
                time.sleep(sleep_step)
                slept += sleep_step

        logger.info("Daemon stopped gracefully.")
        print("\n👋 Dave's Domain Monitor stopped.")
