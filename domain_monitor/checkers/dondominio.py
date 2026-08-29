"""
DonDominio API Checker & Whois Integrator.
Allows checking domain availability and whois status through DonDominio (MrDomain) API,
specialized for .es domains and other ccTLDs.
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from .base import BaseChecker, DomainResult, DomainStatus

logger = logging.getLogger(__name__)

DONDOMINIO_API_BASE = "https://dondominio.com/api"


class DonDominioChecker(BaseChecker):
    """
    Checker leveraging DonDominio API for Spanish .es domains and WHOIS queries.
    """

    def __init__(
        self,
        api_user: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 8,
    ):
        self.api_user = (api_user or "").strip()
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    def is_configured(self) -> bool:
        """Check if API credentials are provided."""
        return bool(self.api_user and self.api_key)

    def check_domain(self, domain: str) -> DomainResult:
        """Check availability of a domain via DonDominio API."""
        clean = domain.strip().lower()

        if not self.is_configured():
            return DomainResult(
                domain=clean,
                status=DomainStatus.UNKNOWN,
                is_available=False,
                engine="dondominio",
                error_message="DonDominio API credentials not configured",
            )

        payload_dict = {
            "apiuser": self.api_user,
            "apikey": self.api_key,
            "action": "domain/check",
            "domain": clean,
            "response_type": "json",
        }
        data_encoded = urllib.parse.urlencode(payload_dict).encode("utf-8")

        try:
            req = urllib.request.Request(
                DONDOMINIO_API_BASE,
                data=data_encoded,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

                # DonDominio response format: {"success": true, "response_data": {"available": true/false, "price": ...}}
                resp_data = data.get("response_data", {})
                is_avail = bool(resp_data.get("available", False))
                status = DomainStatus.AVAILABLE if is_avail else DomainStatus.REGISTERED

                return DomainResult(
                    domain=clean,
                    status=status,
                    is_available=is_avail,
                    registrar="DonDominio",
                    engine="dondominio_api",
                    raw_data=data,
                )

        except Exception as e:
            logger.debug(f"DonDominio check failed for {clean}: {e}")
            return DomainResult(
                domain=clean,
                status=DomainStatus.ERROR,
                is_available=False,
                engine="dondominio_api",
                error_message=str(e),
            )

    def check_batch(self, domains: list, max_workers: int = 10) -> list:
        """Check multiple domains."""
        return [self.check_domain(d) for d in domains]
