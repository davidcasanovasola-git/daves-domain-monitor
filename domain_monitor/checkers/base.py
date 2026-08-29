"""
Base domain data models and checker interfaces.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any


class DomainStatus(str, Enum):
    AVAILABLE = "AVAILABLE"              # Free to register
    REGISTERED = "REGISTERED"            # Registered & active
    EXPIRING_SOON = "EXPIRING_SOON"      # Registered but expires within alert threshold
    REDEMPTION = "REDEMPTION"            # In grace/redemption or pending deletion
    ERROR = "ERROR"                      # Failed to check (network, rate limit)
    UNKNOWN = "UNKNOWN"                  # Inconclusive status


@dataclass
class DomainResult:
    domain: str
    status: DomainStatus
    is_available: bool = False
    registrar: Optional[str] = None
    creation_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    days_until_expiration: Optional[int] = None
    raw_status: List[str] = field(default_factory=list)
    nameservers: List[str] = field(default_factory=list)
    engine: str = "unknown"
    error_message: Optional[str] = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def calculate_expiration_days(self) -> Optional[int]:
        if self.expiration_date:
            now = datetime.now(timezone.utc)
            # Ensure timezone awareness
            exp = self.expiration_date
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            delta = exp - now
            self.days_until_expiration = max(0, delta.days)
            return self.days_until_expiration
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "status": self.status.value,
            "is_available": self.is_available,
            "registrar": self.registrar,
            "creation_date": self.creation_date.isoformat() if self.creation_date else None,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "days_until_expiration": self.days_until_expiration,
            "raw_status": self.raw_status,
            "nameservers": self.nameservers,
            "engine": self.engine,
            "error_message": self.error_message,
            "checked_at": self.checked_at.isoformat(),
        }


class BaseChecker(ABC):
    """Abstract base class for domain availability checkers."""

    @abstractmethod
    def check_domain(self, domain: str) -> DomainResult:
        """Check availability and metadata for a single domain."""
        pass

    @abstractmethod
    def check_batch(self, domains: List[str], max_workers: int = 5) -> List[DomainResult]:
        """Check a batch of domains concurrently."""
        pass
