"""
Base Notifier Interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..checkers.base import DomainResult


class BaseNotifier(ABC):
    """Abstract base for all alert notification channels."""

    @abstractmethod
    def send_alert(self, result: DomainResult, alert_type: str, custom_message: Optional[str] = None) -> bool:
        """Send an urgent domain status alert (e.g. Domain is now Available)."""
        pass

    @abstractmethod
    def send_summary(self, stats: Dict[str, Any], available_domains: list) -> bool:
        """Send a periodic scan summary report."""
        pass
