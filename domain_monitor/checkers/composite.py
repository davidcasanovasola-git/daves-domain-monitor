"""
Composite Domain Checker.
Orchestrates multiple checking engines (Cloudflare DoH, RDAP, Cloudflare Registrar API)
to achieve maximum accuracy, speed, and metadata richness across all TLDs.
"""

import concurrent.futures
import logging
from typing import List, Optional

from .base import BaseChecker, DomainResult, DomainStatus
from .cloudflare_api import CloudflareAPIChecker
from .cloudflare_doh import CloudflareDoHChecker
from .rdap import RDAPChecker

logger = logging.getLogger(__name__)


class CompositeChecker(BaseChecker):
    """
    Intelligent multi-tier checker:
    1. Uses RDAP for detailed expiration / registrar dates (works on .com, .net, .org, .cat, .dev, etc.)
    2. Falls back to Cloudflare DNS-over-HTTPS (DoH) for ccTLDs (like .es) and zero-latency verification.
    3. Cross-verifies with Cloudflare API if token is provided.
    """

    def __init__(
        self,
        cloudflare_token: Optional[str] = None,
        cloudflare_account_id: Optional[str] = None,
        timeout: int = 6,
        expiring_threshold_days: int = 30,
    ):
        self.doh_checker = CloudflareDoHChecker(timeout=timeout)
        self.rdap_checker = RDAPChecker(
            timeout=timeout,
            expiring_threshold_days=expiring_threshold_days,
        )
        self.cf_api_checker = (
            CloudflareAPIChecker(cloudflare_token, cloudflare_account_id, timeout=timeout)
            if cloudflare_token
            else None
        )

    def check_domain(self, domain: str) -> DomainResult:
        clean_domain = domain.strip().lower()
        parts = clean_domain.split(".")
        tld = parts[-1] if len(parts) > 1 else ""

        # For .es and certain ccTLDs without standard RDAP, DoH is primary
        is_cctld_no_rdap = tld in ("es", "eu", "de", "fr", "it", "nl", "ru", "cn")

        if is_cctld_no_rdap:
            # Check via Cloudflare DoH first
            doh_res = self.doh_checker.check_domain(clean_domain)
            if doh_res.status in (DomainStatus.AVAILABLE, DomainStatus.REGISTERED):
                return doh_res

        # For gTLDs and RDAP-supported domains, try RDAP first for rich metadata
        rdap_res = self.rdap_checker.check_domain(clean_domain)
        res = None
        if rdap_res.status in (
            DomainStatus.AVAILABLE,
            DomainStatus.REGISTERED,
            DomainStatus.EXPIRING_SOON,
            DomainStatus.REDEMPTION,
        ):
            res = rdap_res
            # If RDAP marked available, double-check with Cloudflare DoH to confirm
            if rdap_res.status == DomainStatus.AVAILABLE:
                doh_res = self.doh_checker.check_domain(clean_domain)
                if doh_res.status == DomainStatus.REGISTERED:
                    res.status = DomainStatus.REGISTERED
                    res.is_available = False
                    res.nameservers = doh_res.nameservers
        else:
            # Fallback to Cloudflare DoH
            doh_res = self.doh_checker.check_domain(clean_domain)
            res = doh_res if doh_res.status != DomainStatus.ERROR else rdap_res

        # If marked available and Cloudflare API is configured, verify real-time registrability
        if res.is_available and self.cf_api_checker and self.cf_api_checker.is_configured():
            try:
                cf_check = self.cf_api_checker.check_pricing_and_availability(clean_domain)
                reason = cf_check.get("reason")
                if not cf_check.get("can_buy_on_cloudflare") and reason in ("domain_premium", "domain_reserved", "domain_unavailable"):
                    res.is_available = False
                    res.status = DomainStatus.REGISTERED
                    res.registrar = f"Registry ({reason})"
            except Exception:
                pass

        return res

    def check_batch(self, domains: List[str], max_workers: int = 10) -> List[DomainResult]:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_domain = {
                executor.submit(self.check_domain, domain): domain
                for domain in domains
            }
            for future in concurrent.futures.as_completed(future_to_domain):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    dom = future_to_domain[future]
                    results.append(
                        DomainResult(
                            domain=dom,
                            status=DomainStatus.ERROR,
                            error_message=str(e),
                            engine="composite",
                        )
                    )
        return results
