"""
Discord Webhook Notifier.
Sends rich embed cards to a Discord channel.
"""

import json
import logging
import urllib.request
from typing import Any, Dict, List, Optional

from ..checkers.base import DomainResult, DomainStatus
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class DiscordNotifier(BaseNotifier):
    """
    Notifier for Discord Webhooks.
    """

    def __init__(self, webhook_url: str, timeout: int = 8):
        self.webhook_url = webhook_url.strip()
        self.timeout = timeout

    def _post(self, payload: Dict[str, Any]) -> bool:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "DomainMonitor/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            logger.error(f"Discord webhook error: {e}")
            return False

    def send_alert(self, result: DomainResult, alert_type: str, custom_message: Optional[str] = None) -> bool:
        domain = result.domain

        if alert_type in ("BECOME_AVAILABLE", "FOUND_AVAILABLE"):
            color = 0x2ECC71  # Green
            title = f"🎉 Domain Available: {domain}"
            desc = f"The domain **`{domain}`** is free to register!"
        elif alert_type == "ENTERED_REDEMPTION":
            color = 0xE67E22  # Orange
            title = f"⏳ In Redemption / Pending Delete: {domain}"
            desc = f"The domain **`{domain}`** is entering expiration/redemption phase!"
        elif alert_type == "EXPIRING_SOON":
            color = 0xF1C40F  # Yellow
            days = result.days_until_expiration or "?"
            title = f"⏰ Expiring Soon ({days} days): {domain}"
            desc = f"Expiration date: {result.expiration_date}"
        else:
            color = 0x3498DB  # Blue
            title = f"ℹ️ Status Changed: {domain}"
            desc = f"New status: {result.status.value}"

        fields = [
            {"name": "Domain", "value": f"`{domain}`", "inline": True},
            {"name": "Status", "value": f"`{result.status.value}`", "inline": True},
            {"name": "Engine", "value": result.engine, "inline": True},
            {
                "name": "Register Now",
                "value": f"[Cloudflare](https://dash.cloudflare.com/) | [DonDominio](https://www.dondominio.com/es/search/?domain={domain}) | [Porkbun](https://porkbun.com/checkout/search?q={domain})",
                "inline": False,
            },
        ]

        if custom_message:
            fields.append({"name": "Note", "value": custom_message, "inline": False})

        embed = {
            "title": title,
            "description": desc,
            "color": color,
            "fields": fields,
            "footer": {"text": "Dave's Domain Monitor"},
            "timestamp": result.checked_at.isoformat(),
        }

        return self._post({"embeds": [embed]})

    def send_summary(self, stats: Dict[str, Any], available_domains: List[str]) -> bool:
        avail_count = stats.get("available", 0)
        total = stats.get("total", 0)

        embed = {
            "title": "📊 Domain Monitor Summary Report",
            "color": 0x3498DB,
            "fields": [
                {"name": "Total Monitored", "value": str(total), "inline": True},
                {"name": "Available", "value": f"🟢 {avail_count}", "inline": True},
                {"name": "Expiring Soon", "value": f"🟡 {stats.get('expiring', 0)}", "inline": True},
            ],
            "footer": {"text": "Dave's Domain Monitor"},
        }

        if available_domains:
            domain_list_str = "\n".join([f"• `{d}`" for d in available_domains[:10]])
            embed["fields"].append({
                "name": "🌟 Available Domains",
                "value": domain_list_str,
                "inline": False,
            })

        return self._post({"embeds": [embed]})
