"""
Console Notifier & Terminal Styler.
Formats domain results into beautiful ANSI colored tables and terminal outputs.
"""

from typing import Any, Dict, List, Optional
from ..checkers.base import DomainResult, DomainStatus
from .base import BaseNotifier


# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
GRAY = "\033[90m"
WHITE = "\033[97m"


def status_badge(status: DomainStatus) -> str:
    if status == DomainStatus.AVAILABLE:
        return f"{GREEN}{BOLD}🟢 AVAILABLE{RESET}"
    elif status == DomainStatus.EXPIRING_SOON:
        return f"{YELLOW}{BOLD}🟡 EXPIRING{RESET}"
    elif status == DomainStatus.REDEMPTION:
        return f"{RED}{BOLD}🔴 REDEMPTION{RESET}"
    elif status == DomainStatus.REGISTERED:
        return f"{GRAY}🔒 REGISTERED{RESET}"
    elif status == DomainStatus.ERROR:
        return f"{RED}⚠️ ERROR{RESET}"
    return f"{GRAY}❓ UNKNOWN{RESET}"


class ConsoleNotifier(BaseNotifier):
    """
    Prints styled tables and alerts directly to stdout.
    """

    def send_alert(self, result: DomainResult, alert_type: str, custom_message: Optional[str] = None) -> bool:
        badge = status_badge(result.status)
        print(f"\n{BOLD}🔔 [DOMAIN ALERT]{RESET} {badge} {WHITE}{BOLD}{result.domain}{RESET}")
        if result.expiration_date:
            print(f"   📅 Expiration: {result.expiration_date} ({result.days_until_expiration} days left)")
        if result.registrar:
            print(f"   🏢 Registrar: {result.registrar}")
        if custom_message:
            print(f"   💬 Note: {custom_message}")
        print()
        return True

    def send_summary(self, stats: Dict[str, Any], available_domains: List[str]) -> bool:
        print(f"\n{BOLD}{CYAN}=== MONITOR SUMMARY ==={RESET}")
        print(f"Total: {stats.get('total', 0)} | "
              f"{GREEN}Available: {stats.get('available', 0)}{RESET} | "
              f"{YELLOW}Expiring: {stats.get('expiring', 0)}{RESET} | "
              f"Registered: {stats.get('registered', 0)}")
        if available_domains:
            print(f"{BOLD}{GREEN}Available domains:{RESET} {', '.join(available_domains[:10])}")
        print()
        return True

    @staticmethod
    def print_results_table(results: List[DomainResult]):
        """Print a nicely aligned ASCII table of domain results."""
        if not results:
            print(f"{GRAY}No domains to display.{RESET}")
            return

        # Sort: Available first, then Expiring, then Redemption, then Registered
        priority_order = {
            DomainStatus.AVAILABLE: 0,
            DomainStatus.EXPIRING_SOON: 1,
            DomainStatus.REDEMPTION: 2,
            DomainStatus.REGISTERED: 3,
            DomainStatus.ERROR: 4,
            DomainStatus.UNKNOWN: 5,
        }
        sorted_results = sorted(results, key=lambda r: (priority_order.get(r.status, 9), r.domain))

        header = f"{'Domain':<30} {'Status':<16} {'Expires In':<14} {'Registrar':<22} {'Engine':<12}"
        separator = "-" * len(header)

        print(f"\n{BOLD}{header}{RESET}")
        print(separator)

        for res in sorted_results:
            badge = status_badge(res.status)
            exp_str = f"{res.days_until_expiration} days" if res.days_until_expiration is not None else "-"
            reg_str = (res.registrar[:20] + "..") if res.registrar and len(res.registrar) > 20 else (res.registrar or "-")
            domain_styled = f"{BOLD}{res.domain}{RESET}" if res.is_available else res.domain
            print(f"{domain_styled:<30} {badge:<25} {exp_str:<14} {reg_str:<22} {res.engine:<12}")

        print(separator)
