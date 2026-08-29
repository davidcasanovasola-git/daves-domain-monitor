"""
RDAP (Registration Data Access Protocol) Domain Checker.
Queries RFC 7482/9082 compliant RDAP services to extract authoritative registration,
expiration, and redemption status for gTLDs and supported ccTLDs.
"""

import concurrent.futures
import datetime
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .base import BaseChecker, DomainResult, DomainStatus

logger = logging.getLogger(__name__)

RDAP_BASE_URL = "https://rdap.org/domain"

# Registry-specific fallback endpoints for faster direct lookup
REGISTRY_RDAP = {
    "com": "https://rdap.verisign.com/com/v1/domain",
    "net": "https://rdap.verisign.com/net/v1/domain",
    "org": "https://rdap.publicinterestregistry.org/rdap/domain",
    "dev": "https://rdap.nic.google/domain",
    "app": "https://rdap.nic.google/domain",
    "page": "https://rdap.nic.google/domain",
    "cat": "https://rdap.fundacio.cat/rdap/domain",
    "io": "https://rdap.identitydigital.services/rdap/domain",
    "me": "https://rdap.identitydigital.services/rdap/domain",
    "info": "https://rdap.identitydigital.services/rdap/domain",
    "tech": "https://rdap.centralnic.com/tech/domain",
    "online": "https://rdap.centralnic.com/online/domain",
    "site": "https://rdap.centralnic.com/site/domain",
}


def _parse_iso_date(date_str: Optional[str]) -> Optional[datetime.datetime]:
    if not date_str:
        return None
    try:
        # Standard ISO 8601: e.g. 2026-11-08T06:12:51Z
        clean = date_str.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(clean)
    except Exception:
        # Try strptime fallbacks
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.datetime.strptime(date_str, fmt)
                return dt.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                continue
    return None


class RDAPChecker(BaseChecker):
    """
    Checker that uses the standard RDAP protocol.
    Extracts rich metadata: expiration date, registrar, redemption states.
    """

    def __init__(self, timeout: int = 8, expiring_threshold_days: int = 30):
        self.timeout = timeout
        self.expiring_threshold_days = expiring_threshold_days
        self.headers = {
            "Accept": "application/rdap+json, application/json",
            "User-Agent": "Mozilla/5.0 (compatible; DomainMonitor/1.0; +https://github.com/davidcasanovasola-git/daves-domain-monitor)",
        }

    def _get_rdap_url(self, domain: str) -> str:
        parts = domain.lower().split(".")
        if len(parts) >= 2:
            tld = parts[-1]
            if tld in REGISTRY_RDAP:
                return f"{REGISTRY_RDAP[tld]}/{domain}"
        return f"{RDAP_BASE_URL}/{domain}"

    def check_domain(self, domain: str) -> DomainResult:
        clean_domain = domain.strip().lower()
        url = self._get_rdap_url(clean_domain)

        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return self._parse_rdap_response(clean_domain, data)

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return DomainResult(
                    domain=clean_domain,
                    status=DomainStatus.AVAILABLE,
                    is_available=True,
                    engine="rdap",
                    raw_status=["NOT_FOUND_404"],
                )
            elif e.code == 429:
                return DomainResult(
                    domain=clean_domain,
                    status=DomainStatus.ERROR,
                    error_message="RDAP Rate Limit (HTTP 429)",
                    engine="rdap",
                )
            else:
                return DomainResult(
                    domain=clean_domain,
                    status=DomainStatus.ERROR,
                    error_message=f"RDAP HTTP {e.code}: {e.reason}",
                    engine="rdap",
                )
        except Exception as e:
            logger.debug(f"RDAP error for {clean_domain}: {e}")
            return DomainResult(
                domain=clean_domain,
                status=DomainStatus.ERROR,
                error_message=str(e),
                engine="rdap",
            )

    def _parse_rdap_response(self, domain: str, data: Dict[str, Any]) -> DomainResult:
        events = data.get("events", [])
        expiration_str = None
        creation_str = None

        for event in events:
            action = event.get("eventAction", "").lower()
            if action in ("expiration", "registration expiration"):
                expiration_str = event.get("eventDate")
            elif action in ("registration", "registration date"):
                creation_str = event.get("eventDate")

        exp_dt = _parse_iso_date(expiration_str)
        reg_dt = _parse_iso_date(creation_str)

        # Extract statuses
        raw_statuses = [str(s).lower() for s in data.get("status", [])]

        # Extract registrar
        registrar = None
        for entity in data.get("entities", []):
            roles = entity.get("roles", [])
            if "registrar" in roles:
                vcard = entity.get("vcardArray", [])
                if len(vcard) > 1 and isinstance(vcard[1], list):
                    for prop in vcard[1]:
                        if prop and prop[0] == "fn" and len(prop) > 3:
                            registrar = prop[3]
                            break
                if not registrar and "handle" in entity:
                    registrar = entity.get("handle")

        # Extract nameservers
        nameservers = []
        for ns in data.get("nameservers", []):
            ns_name = ns.get("ldhName") or ns.get("handle")
            if ns_name:
                nameservers.append(ns_name.lower())

        # Determine domain status
        is_redemption = any(
            term in " ".join(raw_statuses)
            for term in ("redemption", "redemptionperiod", "pendingdelete", "pending delete", "quarantine")
        )

        status = DomainStatus.REGISTERED
        if is_redemption:
            status = DomainStatus.REDEMPTION

        result = DomainResult(
            domain=domain,
            status=status,
            is_available=False,
            registrar=registrar,
            creation_date=reg_dt,
            expiration_date=exp_dt,
            raw_status=raw_statuses,
            nameservers=nameservers,
            engine="rdap",
            raw_data=data,
        )

        days_left = result.calculate_expiration_days()
        if days_left is not None and not is_redemption:
            if days_left <= self.expiring_threshold_days:
                result.status = DomainStatus.EXPIRING_SOON

        return result

    def check_batch(self, domains: List[str], max_workers: int = 5) -> List[DomainResult]:
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
                            engine="rdap",
                        )
                    )
        return results
