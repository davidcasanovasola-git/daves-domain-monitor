"""
Notification Manager.
Dispatches alerts and summaries across all enabled notification channels.
"""

import logging
from typing import Any, Dict, List, Optional

from ..checkers.base import DomainResult
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Coordinates and delivers messages across all active notifiers.
    """

    def __init__(self, notifiers: Optional[List[BaseNotifier]] = None):
        self.notifiers: List[BaseNotifier] = notifiers or []

    def add_notifier(self, notifier: BaseNotifier):
        self.notifiers.append(notifier)

    def dispatch_alert(self, result: DomainResult, alert_type: str, custom_message: Optional[str] = None):
        """Send alert to all enabled channels."""
        for n in self.notifiers:
            try:
                n.send_alert(result, alert_type, custom_message)
            except Exception as e:
                logger.error(f"Error dispatching alert to {n.__class__.__name__}: {e}")

    def dispatch_summary(self, stats: Dict[str, Any], available_domains: List[str]):
        """Send scan summary report to all channels."""
        for n in self.notifiers:
            try:
                n.send_summary(stats, available_domains)
            except Exception as e:
                logger.error(f"Error dispatching summary to {n.__class__.__name__}: {e}")
