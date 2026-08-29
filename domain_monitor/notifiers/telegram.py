"""
Telegram Bot Notifier.
Sends formatted alerts and summary messages to a designated Telegram chat or group,
complete with inline interactive buttons for immediate purchasing via Cloudflare.
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ..checkers.base import DomainResult, DomainStatus
from .base import BaseNotifier

logger = logging.getLogger(__name__)


def format_spanish_datetime(dt) -> str:
    """Format a datetime object into a rich Spanish string."""
    if not dt:
        return "Fecha no especificada"
    days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    months = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]
    try:
        day_str = days[dt.weekday()]
        month_str = months[dt.month - 1]
        time_str = dt.strftime("%H:%M")
        return f"{day_str}, {dt.day} de {month_str} de {dt.year} a las {time_str} UTC"
    except Exception:
        return str(dt)


class TelegramNotifier(BaseNotifier):
    """
    Notifier for Telegram Bot API with inline button support.
    """

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 8):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.timeout = timeout
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_raw_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send message via Telegram API with optional inline keyboard buttons."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("ok", False)
        except Exception as e:
            logger.error(f"Telegram notification error: {e}")
            return False

    def send_alert(self, result: DomainResult, alert_type: str, custom_message: Optional[str] = None) -> bool:
        """Send urgent status alert for a domain with action buttons."""
        domain = result.domain
        status_val = result.status.value
        tld = domain.split(".")[-1].lower()

        inline_keyboard = []

        if alert_type in ("BECOME_AVAILABLE", "FOUND_AVAILABLE"):
            icon = "🎉 🚀"
            title = f"<b>¡DOMINIO DISPONIBLE!</b>\n<code>{domain}</code>"
            desc = "El dominio está <b>libre para registrar ahora mismo</b>."

            # Action buttons
            if tld == "es":
                # .es is registered via Red.es authorized registrars
                inline_keyboard = [
                    [
                        {"text": "🛒 Comprar en DonDominio", "url": f"https://www.dondominio.com/es/search/?domain={domain}"},
                        {"text": "🛒 Comprar en Porkbun", "url": f"https://porkbun.com/checkout/search?q={domain}"},
                    ]
                ]
            else:
                # Supported gTLD / Cloudflare Registrar domain
                inline_keyboard = [
                    [
                        {"text": "💳 Ver precio y Comprar con Cloudflare", "callback_data": f"buy_check:{domain}"},
                    ],
                    [
                        {"text": "🌐 Abrir Cloudflare Registrar", "url": "https://dash.cloudflare.com/?to=/:account/domains/register"},
                        {"text": "🔍 DonDominio", "url": f"https://www.dondominio.com/es/search/?domain={domain}"},
                    ]
                ]

        elif alert_type == "ENTERED_REDEMPTION":
            icon = "⏳ ⚠️"
            title = f"<b>¡DOMINIO EN REDENCIÓN / PENDING DELETE!</b>\n<code>{domain}</code>"
            desc = "El dominio ha caducado y está a punto de ser liberado al público."
            inline_keyboard = [
                [
                    {"text": "🔄 Monitorizar de cerca", "callback_data": f"recheck:{domain}"},
                ]
            ]
        elif alert_type.startswith("EXPIRING_") or alert_type == "EXPIRING_SOON":
            days = result.days_until_expiration or 0
            if alert_type == "EXPIRING_1D" or days <= 1:
                icon = "🚨 🔥"
                title = f"<b>¡ALERTA CRÍTICA: CADUCA MAÑANA!</b>\n<code>{domain}</code>"
                urgency = "⚠️ <b>¡El dominio vence en menos de 24 horas!</b>"
            elif alert_type == "EXPIRING_7D" or days <= 7:
                icon = "🔴 ⏰"
                title = f"<b>¡ALERTA ALTA: CADUCA EN {days} DÍAS!</b>\n<code>{domain}</code>"
                urgency = "⏳ <b>Última semana antes de expirar.</b>"
            elif alert_type == "EXPIRING_15D" or days <= 15:
                icon = "🟠 📅"
                title = f"<b>AVISO: CADUCA EN {days} DÍAS</b>\n<code>{domain}</code>"
                urgency = "📅 <b>Faltan 2 semanas para la fecha de expiración.</b>"
            else:
                icon = "🟡 🗓️"
                title = f"<b>AVISO: CADUCA EN {days} DÍAS</b>\n<code>{domain}</code>"
                urgency = "🗓️ <b>Entrando en el último mes (30 días restantes).</b>"

            dt_formatted = format_spanish_datetime(result.expiration_date)
            desc = (
                f"{urgency}\n\n"
                f"🗓️ <b>Fecha exacta estimada:</b>\n<code>{dt_formatted}</code>\n"
                f"🏢 <b>Registrador actual:</b> {result.registrar or 'Desconocido'}\n\n"
                f"💡 <i>Si el dueño no renueva en esta fecha, pasará a Redención y quedará libre.</i>"
            )
            inline_keyboard = [
                [
                    {"text": "🔄 Comprobar estado ahora", "callback_data": f"recheck:{domain}"},
                ]
            ]
        else:
            icon = "ℹ️"
            title = f"<b>Cambio de estado: {domain}</b>"
            desc = f"Nuevo estado: <b>{status_val}</b>"

        msg = (
            f"{icon} {title}\n\n"
            f"{desc}\n\n"
            f"<i>Verificado con: {result.engine}</i>"
        )

        if custom_message:
            msg += f"\n\n💬 <i>{custom_message}</i>"

        reply_markup = {"inline_keyboard": inline_keyboard} if inline_keyboard else None
        return self.send_raw_message(msg, reply_markup=reply_markup)

    def send_summary(self, stats: Dict[str, Any], available_domains: List[str]) -> bool:
        """Send periodic scan summary."""
        avail_count = stats.get("available", 0)
        total = stats.get("total", 0)
        expiring = stats.get("expiring", 0)

        lines = [
            "📊 <b>Resumen de Monitorización de Dominios</b>",
            f"Total monitorizados: <b>{total}</b>",
            f"🟢 Disponibles: <b>{avail_count}</b>",
            f"🟡 Caducan pronto: <b>{expiring}</b>",
            f"🔴 Registrados: <b>{stats.get('registered', 0)}</b>",
        ]

        inline_keyboard = []
        if available_domains:
            lines.append("\n🌟 <b>Dominios Disponibles Destacados:</b>")
            for dom in available_domains[:10]:
                lines.append(f" • <code>{dom}</code>")
            if len(available_domains) > 10:
                lines.append(f" <i>...y {len(available_domains) - 10} más.</i>")

            inline_keyboard.append([
                {"text": "🟢 Ver todos los disponibles", "callback_data": "view_available"}
            ])

        reply_markup = {"inline_keyboard": inline_keyboard} if inline_keyboard else None
        return self.send_raw_message("\n".join(lines), reply_markup=reply_markup)
