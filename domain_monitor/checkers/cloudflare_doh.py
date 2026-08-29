"""
Cloudflare DNS-over-HTTPS (DoH) Domain Checker.
Queries Cloudflare's 1.1.1.1 DNS over HTTPS API for high-speed, zero-auth domain availability checking.
"""

import concurrent.futures
import json
import logging
import urllib.parse
import urllib.request
from typing import List, Optional

from .base import BaseChecker, DomainResult, DomainStatus

logger = logging.getLogger(__name__)

CLOUDFLARE_DOH_URL = "https://cloudflare-dns.com/dns-query"


class CloudflareDoHChecker(BaseChecker):
    """
    Checker that uses Cloudflare's 1.1.1.1 DNS-over-HTTPS endpoint.
    Fast, reliable, and requires no API key.
    """

    def __init__(self, timeout: int = 5, doh_url: str = CLOUDFLARE_DOH_URL):
        self.timeout = timeout
        self.doh_url = doh_url
        self.headers = {
            "Accept": "application/dns-json",
            "User-Agent": "DomainMonitor/1.0",
        }

    def _query_dns(self, name: str, qtype: str = "NS") -> dict:
        """Query Cloudflare DoH API for a specific record type."""
        params = urllib.parse.urlencode({"name": name, "type": qtype})
        url = f"{self.doh_url}?{params}"
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def check_domain(self, domain: str) -> DomainResult:
        """
        Check domain status via Cloudflare DoH.
        - Status 3 (NXDOMAIN) -> AVAILABLE
        - Status 0 (NOERROR with answers/records) -> REGISTERED
        """
        clean_domain = domain.strip().lower()
        try:
            # Query NS records
            data_ns = self._query_dns(clean_domain, "NS")
            status_code = data_ns.get("Status")

            # Status 3 is NXDOMAIN (Domain does not exist -> Available)
            if status_code == 3:
                # Double check with SOA record
                data_soa = self._query_dns(clean_domain, "SOA")
                if data_soa.get("Status") == 3:
                    return DomainResult(
                        domain=clean_domain,
                        status=DomainStatus.AVAILABLE,
                        is_available=True,
                        engine="cloudflare_doh",
                        raw_status=["NXDOMAIN"],
                        raw_data={"ns": data_ns, "soa": data_soa},
                    )

            # Status 0 is NOERROR (Domain exists)
            if status_code == 0:
                answers = data_ns.get("Answer", [])
                nameservers = [
                    a.get("data", "").rstrip(".")
                    for a in answers
                    if a.get("type") == 2
                ]
                return DomainResult(
                    domain=clean_domain,
                    status=DomainStatus.REGISTERED,
                    is_available=False,
                    nameservers=nameservers,
                    engine="cloudflare_doh",
                    raw_status=["NOERROR"],
                    raw_data={"ns": data_ns},
                )

            # Check A / SOA record if NS returned no answers or status 2/4/5
            data_a = self._query_dns(clean_domain, "A")
            if data_a.get("Status") == 3:
                return DomainResult(
                    domain=clean_domain,
                    status=DomainStatus.AVAILABLE,
                    is_available=True,
                    engine="cloudflare_doh",
                    raw_status=["NXDOMAIN_A"],
                    raw_data={"a": data_a},
                )
            elif data_a.get("Status") == 0 and data_a.get("Answer"):
                return DomainResult(
                    domain=clean_domain,
                    status=DomainStatus.REGISTERED,
                    is_available=False,
                    engine="cloudflare_doh",
                    raw_status=["NOERROR_A"],
                    raw_data={"a": data_a},
                )

            # Inconclusive
            return DomainResult(
                domain=clean_domain,
                status=DomainStatus.UNKNOWN,
                is_available=False,
                engine="cloudflare_doh",
                raw_status=[f"DNS_STATUS_{status_code}"],
                raw_data={"ns": data_ns, "a": data_a},
            )

        except Exception as e:
            logger.debug(f"Cloudflare DoH error for {clean_domain}: {e}")
            return DomainResult(
                domain=clean_domain,
                status=DomainStatus.ERROR,
                is_available=False,
                engine="cloudflare_doh",
                error_message=str(e),
            )

    def check_batch(self, domains: List[str], max_workers: int = 8) -> List[DomainResult]:
        """Check multiple domains concurrently with thread pool."""
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
                            engine="cloudflare_doh",
                        )
                    )
        return results
