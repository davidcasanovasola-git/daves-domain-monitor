"""
Interactive Telegram Bot Daemon.
Allows controlling the domain monitor, checking availability, and executing
domain purchases directly through Cloudflare with price confirmations, official menu commands,
and persistent mobile buttons.
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .checkers.base import DomainResult, DomainStatus
from .checkers.cloudflare_api import CloudflareAPIChecker
from .checkers.composite import CompositeChecker
from .database import Database

logger = logging.getLogger(__name__)


def get_main_reply_keyboard() -> Dict[str, Any]:
    """Returns persistent tactile keypad buttons for mobile/desktop."""
    return {
        "keyboard": [
            [{"text": "📊 Estado"}, {"text": "🟢 Disponibles"}],
            [{"text": "🔍 Escanear Ahora"}, {"text": "⏰ Por Caducar"}],
            [{"text": "ℹ️ Ayuda"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


class InteractiveTelegramBot:
    """
    Interactive Telegram Bot using long-polling with Cloudflare purchase support,
    official menu commands, and quick-action keyboards.
    """

    def __init__(
        self,
        bot_token: str,
        allowed_chat_id: Optional[str],
        db: Database,
        checker: CompositeChecker,
        cf_api: Optional[CloudflareAPIChecker] = None,
        interval_hours: float = 6.0,
    ):
        self.bot_token = bot_token.strip()
        self.allowed_chat_id = str(allowed_chat_id).strip() if allowed_chat_id else None
        self.db = db
        self.checker = checker
        self.cf_api = cf_api or CloudflareAPIChecker()
        self.interval_hours = float(interval_hours)
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.last_update_id = 0
        self._setup_bot_commands()

    def _save_chat_id_to_env(self, chat_id: str, env_path: str = ".env"):
        """Persist auto-discovered Chat ID to .env file."""
        try:
            lines = []
            found = False
            p = Path(env_path)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("TELEGRAM_CHAT_ID="):
                            lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
                            found = True
                        else:
                            lines.append(line)
            if not found:
                lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
            with open(p, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            logger.error(f"Failed to persist chat_id to .env: {e}")

    def _setup_bot_commands(self):
        """Register official Telegram Bot Menu commands (/setMyCommands)."""
        commands = [
            {"command": "status", "description": "📊 Ver estado y resumen de dominios"},
            {"command": "available", "description": "🟢 Listar dominios libres y precios"},
            {"command": "check", "description": "🔍 Escanear todos los dominios ahora"},
            {"command": "expiring", "description": "⏰ Ver dominios que caducan pronto"},
            {"command": "menu", "description": "📱 Mostrar botones interactivos"},
            {"command": "help", "description": "ℹ️ Ayuda e instrucciones"},
        ]
        try:
            res = self._api_call("setMyCommands", {"commands": commands}, timeout=10)
            if res.get("ok"):
                logger.info("Registered official Telegram Bot Menu Commands.")
        except Exception as e:
            logger.debug(f"Could not register setMyCommands: {e}")

    def _api_call(self, method: str, data: Optional[dict] = None, timeout: int = 30) -> dict:
        url = f"{self.base_url}/{method}"
        req_data = None
        headers = {}
        if data is not None:
            req_data = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=req_data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> bool:
        """Acknowledge a callback query to stop the loading icon on Telegram."""
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            res = self._api_call("answerCallbackQuery", payload, timeout=10)
            return res.get("ok", False)
        except Exception as e:
            logger.debug(f"Error answering callback query: {e}")
            return False

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        # Default to main reply keyboard if no reply_markup provided
        actual_markup = reply_markup if reply_markup is not None else get_main_reply_keyboard()

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
            "reply_markup": actual_markup,
        }

        try:
            res = self._api_call("sendMessage", payload, timeout=10)
            return res.get("ok", False)
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    def handle_command(self, chat_id: str, text: str):
        clean_text = text.strip()
        parts = clean_text.split()
        if not parts:
            return
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        # Match either slash commands or button text
        lower = clean_text.lower()

        if cmd in ("/start", "/help", "/menu") or "ayuda" in lower:
            msg = (
                "🤖 <b>Dave's Domain Monitor — Sniper & Compras Cloudflare</b>\n\n"
                "<b>Comandos y Botones:</b>\n"
                "• 📊 <b>Estado (/status)</b> — Resumen de dominios vigilados\n"
                "• 🟢 <b>Disponibles (/available)</b> — Dominios libres para comprar\n"
                "• 🔍 <b>Escanear Ahora (/check)</b> — Escaneo completo inmediato\n"
                "• ⏰ <b>Por Caducar (/expiring)</b> — Dominios que caducan pronto\n"
                "• 💳 <code>/buy &lt;dominio&gt;</code> — Consultar precio y comprar dominio\n"
                "• 🔍 <code>/checkdomain &lt;dominio&gt;</code> — Comprobar un dominio en tiempo real\n"
                "• ➕ <code>/add &lt;dominio&gt;</code> — Añadir dominio a la lista\n"
                "• 🗑️ <code>/remove &lt;dominio&gt;</code> — Eliminar un dominio\n"
            )
            self.send_message(chat_id, msg, reply_markup=get_main_reply_keyboard())

        elif cmd == "/status" or "estado" in lower:
            stats = self.db.get_summary_stats()
            msg = (
                "📊 <b>Estado de Monitorización:</b>\n\n"
                f"• Total en seguimiento: <b>{stats['total']}</b>\n"
                f"• 🟢 Disponibles: <b>{stats['available']}</b>\n"
                f"• 🟡 Caducan pronto: <b>{stats['expiring']}</b>\n"
                f"• 🔴 En redención: <b>{stats['redemption']}</b>\n"
                f"• 🔒 Registrados: <b>{stats['registered']}</b>\n"
                f"• ⚠️ Errores: <b>{stats['errors']}</b>"
            )
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🟢 Ver Disponibles", "callback_data": "view_available"}],
                    [{"text": "🔄 Escanear Ahora", "callback_data": "scan_all"}],
                ]
            }
            self.send_message(chat_id, msg, reply_markup=reply_markup)

        elif cmd == "/available" or "disponible" in lower:
            self._show_available_domains(chat_id)

        elif cmd == "/buy":
            if not args:
                self.send_message(chat_id, "⚠️ Uso: <code>/buy micartera.dev</code>")
                return
            target = args[0].strip().lower()
            self._prompt_buy_domain(chat_id, target)

        elif cmd == "/expiring" or "caduc" in lower:
            domains = self.db.get_all_monitored_domains()
            exp = [d for d in domains if d["current_status"] in ("EXPIRING_SOON", "REDEMPTION")]
            if not exp:
                self.send_message(chat_id, "ℹ️ No hay dominios a punto de caducar en los próximos 30 días.")
            else:
                lines = [f"🟡 <b>Dominios por caducar / Redención ({len(exp)}):</b>\n"]
                for d in exp:
                    days = d.get("days_until_expiration")
                    days_str = f"({days} días)" if days is not None else ""
                    lines.append(f"• <code>{d['domain']}</code> {days_str}")
                self.send_message(chat_id, "\n".join(lines))

        elif cmd == "/check" or "escanear" in lower:
            self.send_message(chat_id, "⏳ Iniciando escaneo completo de dominios...")
            all_domains = self.db.get_all_monitored_domains()
            domain_names = [d["domain"] for d in all_domains]
            results = self.checker.check_batch(domain_names)

            avail_found = []
            for r in results:
                self.db.record_check_result(r)
                if r.is_available:
                    avail_found.append(r.domain)

            stats = self.db.get_summary_stats()
            msg = (
                f"✅ <b>Escaneo completado.</b>\n"
                f"Total escaneados: {len(results)}\n"
                f"🟢 Disponibles: {len(avail_found)}\n"
                f"🟡 Caducan pronto: {stats['expiring']}"
            )
            reply_markup = None
            if avail_found:
                msg += "\n\n<b>Disponibles destacados:</b>\n" + "\n".join([f"• <code>{d}</code>" for d in avail_found[:10]])
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "🟢 Ver todos y Comprar", "callback_data": "view_available"}]
                    ]
                }
            self.send_message(chat_id, msg, reply_markup=reply_markup)

        elif cmd == "/checkdomain":
            if not args:
                self.send_message(chat_id, "⚠️ Uso: <code>/checkdomain micartera.dev</code>")
                return
            target = args[0].strip().lower()
            self.send_message(chat_id, f"🔍 Comprobando <code>{target}</code>...")
            res = self.checker.check_domain(target)
            if res.is_available:
                tld = target.split(".")[-1].lower()
                buttons = []
                if tld != "es":
                    buttons.append([{"text": "💳 Consultar precio y comprar", "callback_data": f"buy_check:{target}"}])
                    buttons.append([{"text": "🌐 Abrir Cloudflare", "url": "https://dash.cloudflare.com/?to=/:account/domains/register"}])
                else:
                    buttons.append([{"text": "🛒 Comprar en DonDominio", "url": f"https://www.dondominio.com/es/search/?domain={target}"}])

                self.send_message(
                    chat_id,
                    f"🎉 <b>¡{target} ESTÁ DISPONIBLE!</b>\n\nMotor: {res.engine}",
                    reply_markup={"inline_keyboard": buttons},
                )
            else:
                exp = f"\nCaduca: <code>{res.expiration_date}</code>" if res.expiration_date else ""
                reg = f"\nRegistrador: <code>{res.registrar}</code>" if res.registrar else ""
                self.send_message(
                    chat_id,
                    f"🔒 <b>{target}</b> está <b>{res.status.value}</b>.{exp}{reg}\nMotor: {res.engine}",
                )

        elif cmd == "/check" or clean_text == "🔍 Escanear Ahora":
            self.send_message(chat_id, "⏳ Iniciando escaneo completo de dominios...")
            all_domains = self.db.get_all_monitored_domains()
            domain_names = [d["domain"] for d in all_domains]
            results = self.checker.check_batch(domain_names)

            avail_found = []
            for r in results:
                self.db.record_check_result(r)
                if r.is_available:
                    avail_found.append(r.domain)

            stats = self.db.get_summary_stats()
            msg = (
                f"✅ <b>Escaneo completado.</b>\n"
                f"Total escaneados: {len(results)}\n"
                f"🟢 Disponibles: {len(avail_found)}\n"
                f"🟡 Caducan pronto: {stats['expiring']}"
            )
            reply_markup = None
            if avail_found:
                msg += "\n\n<b>Disponibles destacados:</b>\n" + "\n".join([f"• <code>{d}</code>" for d in avail_found[:10]])
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "🟢 Ver todos y Comprar", "callback_data": "view_available"}]
                    ]
                }
            self.send_message(chat_id, msg, reply_markup=reply_markup)

        elif cmd == "/add":
            if not args:
                self.send_message(chat_id, "⚠️ Uso: <code>/add midominio.com</code>")
                return
            new_dom = args[0].strip().lower()
            self.db.add_or_update_domain(new_dom, priority="high")
            self.send_message(chat_id, f"✅ Dominio <code>{new_dom}</code> añadido a la monitorización con prioridad alta.")

        elif cmd == "/remove":
            if not args:
                self.send_message(chat_id, "⚠️ Uso: <code>/remove midominio.com</code>")
                return
            rem_dom = args[0].strip().lower()
            self.db.remove_domain(rem_dom)
            self.send_message(chat_id, f"🗑️ Dominio <code>{rem_dom}</code> eliminado del seguimiento.")

    def _show_available_domains(self, chat_id: str):
        """Display available domains with quick purchase action buttons."""
        domains = self.db.get_all_monitored_domains()
        avail = [d for d in domains if d["current_status"] == "AVAILABLE"]
        if not avail:
            self.send_message(chat_id, "ℹ️ No hay ningún dominio libre en este momento.")
            return

        lines = [f"🟢 <b>Dominios Disponibles ({len(avail)}):</b>\n"]
        buttons = []

        for d in avail[:10]:
            dom_name = d["domain"]
            tld = dom_name.split(".")[-1].lower()
            lines.append(f"• <code>{dom_name}</code>")

            if tld == "es":
                buttons.append([
                    {"text": f"🛒 {dom_name} (DonDominio)", "url": f"https://www.dondominio.com/es/search/?domain={dom_name}"}
                ])
            else:
                buttons.append([
                    {"text": f"💳 Comprar {dom_name} (Cloudflare)", "callback_data": f"buy_check:{dom_name}"}
                ])

        if len(avail) > 10:
            lines.append(f"\n<i>...y {len(avail) - 10} más.</i>")

        reply_markup = {"inline_keyboard": buttons}
        self.send_message(chat_id, "\n".join(lines), reply_markup=reply_markup)

    def _prompt_buy_domain(self, chat_id: str, domain: str):
        """Fetch pricing and show confirmation dialog for Cloudflare registration."""
        clean = domain.strip().lower()
        tld = clean.split(".")[-1]

        if tld == "es":
            msg = (
                f"ℹ️ <b>El dominio <code>{clean}</code> tiene extensión .es</b>\n\n"
                "Cloudflare Registrar no registra dominios <code>.es</code> directamente "
                "(solo gestiona su DNS).\n\n"
                "👉 Puedes registrarlo en <b>DonDominio</b> o <b>Porkbun</b> al mejor precio:"
            )
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🛒 Comprar en DonDominio", "url": f"https://www.dondominio.com/es/search/?domain={clean}"}],
                    [{"text": "🛒 Comprar en Porkbun", "url": f"https://porkbun.com/checkout/search?q={clean}"}],
                ]
            }
            self.send_message(chat_id, msg, reply_markup=reply_markup)
            return

        self.send_message(chat_id, f"⏳ Consultando disponibilidad y precio para <code>{clean}</code> en Cloudflare Registrar...")

        pricing_info = self.cf_api.check_pricing_and_availability(clean)

        if not pricing_info.get("supported"):
            msg = f"⚠️ <b>Dominio no soportado:</b>\n{pricing_info.get('reason')}"
            reply_markup = None
            if pricing_info.get("alternative_url"):
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "🛒 Comprar en Registrador Alternativo", "url": pricing_info["alternative_url"]}]
                    ]
                }
            self.send_message(chat_id, msg, reply_markup=reply_markup)
            return

        if pricing_info.get("error"):
            msg = (
                f"⚠️ <b>No se pudo consultar el precio automático:</b>\n{pricing_info.get('error')}\n\n"
                "Puedes registrarlo directamente desde el panel de Cloudflare:"
            )
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🌐 Abrir Cloudflare Registrar", "url": pricing_info.get("direct_url", "https://dash.cloudflare.com/")}]
                ]
            }
            self.send_message(chat_id, msg, reply_markup=reply_markup)
            return

        price_val = pricing_info.get("price", "9.77")
        currency = pricing_info.get("currency", "USD")
        renewal_val = pricing_info.get("renewal_price", price_val)
        tier = pricing_info.get("tier", "standard")

        msg = (
            f"🛒 <b>Detalles de Compra en Cloudflare:</b>\n\n"
            f"• <b>Dominio:</b> <code>{clean}</code>\n"
            f"• <b>Precio Registro (1 año):</b> <code>{price_val} {currency}</code>\n"
            f"• <b>Precio Renovación:</b> <code>{renewal_val} {currency}/año</code>\n"
            f"• <b>Tipo / Tier:</b> <code>{tier}</code>\n"
            f"• <b>Protección Whois:</b> ✅ Gratis incluida\n"
            f"• <b>Método de Pago:</b> Tarjeta / Saldo configurado en Cloudflare\n\n"
            f"⚡ <i>Al pulsar confirmar, el dominio se registrará y activará en tu cuenta de Cloudflare.</i>\n\n"
            f"¿Deseas registrar <code>{clean}</code> ahora?"
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": f"💳 Confirmar Registro (${price_val} USD)", "callback_data": f"buy_confirm:{clean}"},
                ],
                [
                    {"text": "❌ Cancelar", "callback_data": f"buy_cancel:{clean}"},
                ],
            ]
        }

        self.send_message(chat_id, msg, reply_markup=reply_markup)

    def _execute_purchase(self, chat_id: str, domain: str):
        """Execute domain registration via Cloudflare API."""
        clean = domain.strip().lower()
        self.send_message(chat_id, f"🚀 Procesando <code>{clean}</code> en Cloudflare...")

        res = self.cf_api.purchase_domain(clean)

        if res.get("simulated"):
            self.send_message(chat_id, res.get("message", "🛡️ Modo seguro: Compra simulada."))
            return

        if res.get("success"):
            self.db.add_or_update_domain(clean, priority="high")
            check_res = DomainResult(
                domain=clean,
                status=DomainStatus.REGISTERED,
                is_available=False,
                registrar="Cloudflare Registrar",
                engine="cloudflare_api",
            )
            self.db.record_check_result(check_res)

            msg = (
                f"🎉 <b>¡DOMINIO COMPRADO CON ÉXITO!</b>\n\n"
                f"El dominio <code>{clean}</code> ha sido registrado y activado en tu cuenta de Cloudflare.\n\n"
                f"• Puedes gestionar sus DNS desde <a href='https://dash.cloudflare.com/'>Cloudflare Dashboard</a>."
            )
            self.send_message(chat_id, msg)
        else:
            err = res.get("error", "Error desconocido")
            msg = (
                f"❌ <b>Error al comprar el dominio {clean}:</b>\n\n"
                f"<code>{err}</code>\n\n"
                "Verifica que tienes un método de pago activo y el acuerdo de registrador aceptado en Cloudflare."
            )
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🌐 Abrir Cloudflare Billing", "url": "https://dash.cloudflare.com/?to=/:account/billing"}]
                ]
            }
            self.send_message(chat_id, msg, reply_markup=reply_markup)

    def handle_callback_query(self, query_id: str, chat_id: str, data: str):
        """Process inline button clicks."""
        self.answer_callback_query(query_id)

        if data.startswith("buy_check:"):
            domain = data.split(":", 1)[1]
            self._prompt_buy_domain(chat_id, domain)

        elif data.startswith("buy_confirm:"):
            domain = data.split(":", 1)[1]
            self._execute_purchase(chat_id, domain)

        elif data.startswith("buy_cancel:"):
            domain = data.split(":", 1)[1]
            self.send_message(chat_id, f"❌ Compra cancelada para <code>{domain}</code>.")

        elif data.startswith("recheck:"):
            domain = data.split(":", 1)[1]
            res = self.checker.check_domain(domain)
            self.db.record_check_result(res)
            msg = f"🔍 <b>{domain}</b> está actualmente: <b>{res.status.value}</b> (Motor: {res.engine})"
            self.send_message(chat_id, msg)

        elif data == "view_available":
            self._show_available_domains(chat_id)

        elif data == "scan_all":
            self.handle_command(chat_id, "/check")

    def _start_background_scanner(self):
        """Start periodic background domain scanner thread."""
        import threading
        t = threading.Thread(target=self._background_scanner_loop, daemon=True)
        t.start()
        logger.info(f"Started background domain scanner thread (interval: {self.interval_hours}h)")

    def _background_scanner_loop(self):
        """Periodically scan monitored domains and notify user if status changes."""
        interval_seconds = max(60, int(self.interval_hours * 3600))
        while True:
            try:
                time.sleep(interval_seconds)
                logger.info("Executing scheduled periodic domain scan in background thread...")
                monitored = self.db.get_all_monitored_domains(active_only=True)
                if not monitored:
                    continue
                domain_names = [d["domain"] for d in monitored]
                results = self.checker.check_batch(domain_names, max_workers=8)
                for res in results:
                    state_changed, alert_type = self.db.record_check_result(res)
                    if state_changed and (
                        alert_type in ("BECOME_AVAILABLE", "FOUND_AVAILABLE", "ENTERED_REDEMPTION", "EXPIRING_SOON")
                        or (alert_type and alert_type.startswith("EXPIRING_"))
                    ):
                        if self.allowed_chat_id:
                            notifier = TelegramNotifier(self.bot_token, self.allowed_chat_id)
                            notifier.send_alert(res, alert_type)
            except Exception as e:
                logger.error(f"Error in periodic background domain scan: {e}")

    def run_polling(self):
        """Start long-polling loop handling both messages and callback queries."""
        logger.info("Starting Telegram Bot interactive polling loop...")
        self._start_background_scanner()
        print(f"🤖 Telegram Bot polling started (Automatic scan every {self.interval_hours}h). Press Ctrl+C to stop.")

        while True:
            try:
                data = self._api_call(
                    "getUpdates",
                    {"offset": self.last_update_id + 1, "timeout": 20},
                    timeout=30,
                )
                if data.get("ok"):
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]

                        # 1. Handle Inline Button Clicks (Callback Queries)
                        if "callback_query" in update:
                            cb = update["callback_query"]
                            cb_id = cb["id"]
                            chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                            cb_data = cb.get("data", "")

                            if self.allowed_chat_id and chat_id != self.allowed_chat_id:
                                self.answer_callback_query(cb_id, "Acceso no autorizado.")
                                continue

                            self.handle_callback_query(cb_id, chat_id, cb_data)
                            continue

                        # 2. Handle Regular Messages & Tactile Keyboard Clicks
                        msg = update.get("message", {})
                        text = msg.get("text", "")
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        user_info = msg.get("from", {})
                        user_name = user_info.get("first_name", "Usuario")

                        # Auto-link first user if no chat_id is configured
                        if not self.allowed_chat_id and chat_id:
                            self.allowed_chat_id = chat_id
                            self._save_chat_id_to_env(chat_id)
                            logger.info(f"Auto-linked Chat ID {chat_id} for user {user_name}")
                            print(f"✅ ¡Vinculado automáticamente con Telegram Chat ID: {chat_id} ({user_name})!")
                            self.send_message(
                                chat_id,
                                f"🎉 <b>¡Hola {user_name}! Conexión establecida con éxito.</b>\n"
                                f"Tu Telegram (Chat ID: <code>{chat_id}</code>) ha sido vinculado a Dave's Domain Monitor.",
                            )

                        if self.allowed_chat_id and chat_id != self.allowed_chat_id:
                            logger.warning(f"Unauthorized access attempt from chat_id={chat_id}")
                            continue

                        if text:
                            self.handle_command(chat_id, text)

            except Exception as e:
                logger.error(f"Polling loop error: {e}")
                time.sleep(3)
