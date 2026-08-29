"""
Command Line Interface (CLI) for Dave's Domain Monitor.
"""

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import List
import yaml

from .checkers.base import DomainResult, DomainStatus
from .checkers.cloudflare_api import CloudflareAPIChecker
from .checkers.composite import CompositeChecker
from .config import AppConfig, load_config
from .database import Database
from .generator import DomainGenerator
from .notifiers.console import ConsoleNotifier
from .notifiers.discord import DiscordNotifier
from .notifiers.email import EmailNotifier
from .notifiers.manager import NotificationManager
from .notifiers.telegram import TelegramNotifier
from .scheduler import DomainMonitorDaemon
from .telegram_bot import InteractiveTelegramBot


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
    )


def build_notification_manager(config: AppConfig) -> NotificationManager:
    mgr = NotificationManager()
    mgr.add_notifier(ConsoleNotifier())

    if config.telegram.enabled and config.telegram.bot_token and config.telegram.chat_id:
        mgr.add_notifier(TelegramNotifier(config.telegram.bot_token, config.telegram.chat_id))

    if config.discord.enabled and config.discord.webhook_url:
        mgr.add_notifier(DiscordNotifier(config.discord.webhook_url))

    if config.email.enabled and config.email.smtp_host:
        mgr.add_notifier(
            EmailNotifier(
                smtp_host=config.email.smtp_host,
                smtp_port=config.email.smtp_port,
                smtp_user=config.email.smtp_user,
                smtp_password=config.email.smtp_password,
                from_email=config.email.from_email,
                to_emails=config.email.to_emails,
                use_tls=config.email.use_tls,
            )
        )

    return mgr


def cmd_setup(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Interactive setup wizard for new users / Open Source onboarding."""
    print("\n" + "=" * 60)
    print("🚀 DAVE'S DOMAIN MONITOR - ASISTENTE DE CONFIGURACIÓN")
    print("=" * 60)
    print("Vamos a configurar tu monitor de dominios personalizado.\n")

    fn = input(f"• Nombre (ej. carlos) [{config.name.first_name}]: ").strip() or config.name.first_name
    ln1 = input(f"• Primer apellido (ej. diaz) [{config.name.last_name1}]: ").strip() or config.name.last_name1
    ln2 = input(f"• Segundo apellido (ej. garcia) [{config.name.last_name2}]: ").strip() or config.name.last_name2
    
    tlds_default = ",".join(config.name.tlds)
    tlds_input = input(f"• TLDs a monitorizar separados por comas [{tlds_default}]: ").strip()
    tlds_list = [t.strip().lstrip(".") for t in tlds_input.split(",") if t.strip()] if tlds_input else config.name.tlds

    print("\n--- Integración con Telegram (Opcional para alertas y compras) ---")
    tg_token = input("• Telegram Bot Token (@BotFather) [Dejar vacío para omitir]: ").strip()
    tg_chat = input("• Telegram Chat ID (@userinfobot) [Dejar vacío para omitir]: ").strip()

    print("\n--- Integración con Cloudflare Registrar API (Opcional para compras 1-click) ---")
    cf_account = input("• Cloudflare Account ID [Dejar vacío para omitir]: ").strip()
    cf_token = input("• Cloudflare API Token (permiso Registrar Write) [Dejar vacío para omitir]: ").strip()

    # Create / update .env
    env_lines = [
        "# Dave's Domain Monitor - Configuration",
        f"NAME_FIRST={fn}",
        f"NAME_LAST1={ln1}",
        f"NAME_LAST2={ln2}",
        f"TELEGRAM_BOT_TOKEN={tg_token}",
        f"TELEGRAM_CHAT_ID={tg_chat}",
        f"CLOUDFLARE_ACCOUNT_ID={cf_account}",
        f"CLOUDFLARE_API_TOKEN={cf_token}",
    ]
    with open(".env", "w", encoding="utf-8") as f:
        f.write("\n".join(env_lines) + "\n")

    # Create config.yaml
    cfg_dict = {
        "name": {
            "first_name": fn,
            "last_name1": ln1,
            "last_name2": ln2,
            "keywords": ["dev", "tech", "ai", "code", "bio"],
            "tlds": tlds_list,
        },
        "custom_domains": [
            f"{fn}.es",
            f"{fn}.com",
            f"{fn}.dev",
            f"{fn}{ln1}.com",
            f"{fn}{ln1}.es",
        ],
        "cloudflare": {
            "api_token": "${CLOUDFLARE_API_TOKEN}",
            "account_id": "${CLOUDFLARE_ACCOUNT_ID}",
            "doh_url": "https://cloudflare-dns.com/dns-query",
        },
        "telegram": {
            "enabled": bool(tg_token and tg_chat),
            "bot_token": "${TELEGRAM_BOT_TOKEN}",
            "chat_id": "${TELEGRAM_CHAT_ID}",
            "send_daily_summary": True,
        },
        "monitor": {
            "interval_hours": 6,
            "timeout_seconds": 8,
            "max_concurrency": 8,
            "expiring_threshold_days": 30,
            "database_path": "data/domains.db",
        },
    }

    with open("config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(cfg_dict, f, default_flow_style=False, allow_unicode=True)

    print("\n✅ ¡Configuración guardada con éxito en .env y config.yaml!")
    print("🌱 Inicializando base de datos con tus combinaciones...")
    
    # Reload and init
    new_cfg = load_config("config.yaml", ".env")
    gen = DomainGenerator(fn, ln1, ln2, custom_tlds=tlds_list)
    generated = gen.generate_domains(tlds=tlds_list)
    for c in new_cfg.custom_domains:
        generated.append((c.lower(), "high"))
    added = db.add_domains_batch(generated)
    print(f"✨ Se han añadido {added} dominios a tu lista de monitorización.")
    print("\n💡 Puedes ejecutar 'domain-monitor check' para comprobarlos todos ahora mismo.")


def cmd_init(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Seed the database with personalized domain combinations according to config rules."""
    if getattr(args, "clean", False):
        cleared = db.clear_all_domains()
        print(f"🧹 Base de datos limpiada ({cleared} dominios antiguos eliminados).")

    print("🌱 Initializing domain monitor database...")

    gen = DomainGenerator(
        first_name=config.name.first_name,
        last_name1=config.name.last_name1,
        last_name2=config.name.last_name2,
        additional_keywords=config.name.keywords,
        custom_tlds=config.name.tlds,
        excluded_tlds=config.name.excluded_tlds,
        excluded_slugs=config.name.excluded_slugs,
        excluded_domains=config.name.excluded_domains,
        include_full_name=config.name.include_full_name,
        include_single_names=config.name.include_single_names,
        include_first_name_only=config.name.include_first_name_only,
        include_surname_only=config.name.include_surname_only,
        include_first_and_last=config.name.include_first_and_last,
        include_second_surname=config.name.include_second_surname,
        include_hyphenated=config.name.include_hyphenated,
        include_initials=config.name.include_initials,
    )
    generated = gen.generate_domains(tlds=config.name.tlds)

    for custom in config.custom_domains:
        c_clean = custom.strip().lower()
        tld = c_clean.split(".")[-1].lower()
        if tld not in config.name.excluded_tlds and c_clean not in config.name.excluded_domains:
            generated.append((c_clean, "high"))

    added = db.add_domains_batch(generated)
    print(f"✅ Database initialized at: {config.monitor.database_path}")
    print(f"✨ Added {added} candidate domains to monitoring list.")
    print("💡 Run 'domain-monitor check' to perform your first domain availability scan.")


def cmd_check(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Check availability for domains."""
    if args.domains:
        target_domains = [d.strip().lower() for d in args.domains]
        print(f"🔍 Checking {len(target_domains)} domain(s)...")
        results = checker.check_batch(target_domains, max_workers=config.monitor.max_concurrency)
        for r in results:
            db.record_check_result(r)
    else:
        monitored = db.get_all_monitored_domains(active_only=True)
        if not monitored:
            print("⚠️ No domains found in database. Run 'domain-monitor setup' first.")
            return
        target_domains = [d["domain"] for d in monitored]
        print(f"🔍 Checking {len(target_domains)} monitored domains with Cloudflare & RDAP...")
        results = checker.check_batch(target_domains, max_workers=config.monitor.max_concurrency)

        notifier_mgr = build_notification_manager(config)
        for r in results:
            changed, alert_type = db.record_check_result(r)
            if changed and alert_type in ("BECOME_AVAILABLE", "FOUND_AVAILABLE", "ENTERED_REDEMPTION", "EXPIRING_SOON"):
                if not isinstance(notifier_mgr.notifiers[0], ConsoleNotifier) or len(notifier_mgr.notifiers) > 1:
                    notifier_mgr.dispatch_alert(r, alert_type)

    ConsoleNotifier.print_results_table(results)

    stats = db.get_summary_stats()
    ConsoleNotifier().send_summary(stats, [r.domain for r in results if r.is_available])


def cmd_status(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Show current cached status of all monitored domains."""
    domains = db.get_all_monitored_domains()
    if not domains:
        print("⚠️ No domains in database. Run 'domain-monitor setup' first.")
        return

    from datetime import datetime
    results = []
    for d in domains:
        exp_dt = None
        if d.get("expiration_date"):
            try:
                exp_dt = datetime.fromisoformat(d["expiration_date"])
            except Exception:
                pass

        results.append(
            DomainResult(
                domain=d["domain"],
                status=DomainStatus(d.get("current_status", "UNKNOWN")),
                is_available=bool(d.get("is_available")),
                registrar=d.get("registrar"),
                expiration_date=exp_dt,
                days_until_expiration=d.get("days_until_expiration"),
                engine="db_cache",
            )
        )

    ConsoleNotifier.print_results_table(results)
    stats = db.get_summary_stats()
    ConsoleNotifier().send_summary(stats, [d["domain"] for d in domains if d.get("is_available")])


def cmd_search(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Search for candidate domains via Cloudflare Registrar discovery endpoint."""
    query = args.query.strip()
    print(f"🔎 Buscando sugerencias de dominios para '{query}' en Cloudflare Registrar API...")
    res = cf_api.search_domains(query, limit=args.limit)

    if not res.get("success"):
        print(f"⚠️ {res.get('error')}")
        return

    domains = res.get("domains", [])
    if not domains:
        print("ℹ️ No se encontraron sugerencias.")
        return

    print(f"\n{'Dominio':<28} {'Disponible':<12} {'Precio Reg.':<16} {'Renovación':<16}")
    print("-" * 72)
    for d in domains:
        name = d.get("name", "")
        registrable = "🟢 Sí" if d.get("registrable") else "🔴 No"
        pricing = d.get("pricing", {})
        curr = pricing.get("currency", "USD")
        reg_cost = f"{pricing.get('registration_cost', '-')} {curr}"
        ren_cost = f"{pricing.get('renewal_cost', '-')} {curr}"
        print(f"{name:<28} {registrable:<12} {reg_cost:<16} {ren_cost:<16}")
    print("-" * 72)


def cmd_monitor(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Start continuous daemon monitoring."""
    notifier_mgr = build_notification_manager(config)
    daemon = DomainMonitorDaemon(config, db, checker, notifier_mgr)
    daemon.run_loop()


def cmd_generate(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Generate combinations and display or add them."""
    fn = args.name or config.name.first_name
    ln1 = args.last1 or config.name.last_name1
    ln2 = args.last2 or config.name.last_name2
    tlds = args.tlds.split(",") if args.tlds else config.name.tlds

    gen = DomainGenerator(first_name=fn, last_name1=ln1, last_name2=ln2)
    domains_with_priority = gen.generate_domains(tlds=tlds)

    print(f"✨ Generated {len(domains_with_priority)} domains for '{fn} {ln1} {ln2}':\n")
    for dom, priority in domains_with_priority:
        print(f" • [{priority.upper():<6}] {dom}")

    if args.add:
        added = db.add_domains_batch(domains_with_priority)
        print(f"\n✅ Added {added} new domains to the database!")


def cmd_add(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Add one or more domains."""
    for dom in args.domains:
        clean = dom.strip().lower()
        db.add_or_update_domain(clean, priority=args.priority, category=args.category)
        print(f"✅ Added '{clean}' (Priority: {args.priority})")


def cmd_remove(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Remove one or more domains."""
    for dom in args.domains:
        clean = dom.strip().lower()
        if db.remove_domain(clean):
            print(f"🗑️ Removed '{clean}'")
        else:
            print(f"⚠️ '{clean}' was not found.")


def cmd_buy(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Check price and purchase domain via Cloudflare Registrar."""
    target = args.domain.strip().lower()
    tld = target.split(".")[-1]

    if tld == "es":
        print(f"ℹ️ El dominio '{target}' es .es (ccTLD de España).")
        print("   Cloudflare Registrar no registra dominios .es directamente.")
        print(f"   👉 Puedes comprarlo en DonDominio: https://www.dondominio.com/es/search/?domain={target}")
        print(f"   👉 O en Porkbun: https://porkbun.com/checkout/search?q={target}")
        return

    print(f"⏳ Consultando disponibilidad y precio de '{target}' en Cloudflare...")
    pricing = cf_api.check_pricing_and_availability(target)

    if not pricing.get("supported"):
        print(f"⚠️ {pricing.get('reason')}")
        return

    if pricing.get("error"):
        print(f"⚠️ {pricing.get('error')}")
        return

    price = pricing.get("price", "9.77")
    renewal = pricing.get("renewal_price", price)
    currency = pricing.get("currency", "USD")
    tier = pricing.get("tier", "standard")

    print("\n" + "=" * 50)
    print(f"🛒 DETALLES DE COMPRA CLOUDFLARE:")
    print(f" • Dominio:            {target}")
    print(f" • Precio Registro:    {price} {currency} (1 año)")
    print(f" • Renovación Anual:   {renewal} {currency}/año")
    print(f" • Tipo / Tier:        {tier}")
    print(f" • Cuenta Cloudflare:  {config.cloudflare.account_id or 'No configurada'}")
    print("=" * 50)
    print("⚠️  Esta acción registrará el dominio y cargará el importe en tu cuenta de Cloudflare.")

    if not args.yes:
        confirm = input("\n¿Confirmas la compra inmediata de este dominio? [s/N]: ").strip().lower()
        if confirm not in ("s", "si", "y", "yes"):
            print("❌ Operación cancelada.")
            return

    print(f"\n🚀 Procesando registro de '{target}' en Cloudflare Registrar...")
    res = cf_api.purchase_domain(target)

    if res.get("simulated"):
        print(f"\n{res.get('message')}")
        return

    if res.get("success"):
        print(f"🎉 ¡ÉXITO! {res.get('message', 'El dominio ha sido registrado.')}")
        db.add_or_update_domain(target, priority="high")
        db.record_check_result(
            DomainResult(
                domain=target,
                status=DomainStatus.REGISTERED,
                is_available=False,
                registrar="Cloudflare Registrar",
                engine="cloudflare_api",
            )
        )
    else:
        print(f"❌ Error al registrar el dominio: {res.get('error')}")


def cmd_telegram_bot(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Run interactive Telegram Bot with Cloudflare purchase button support."""
    if not config.telegram.bot_token:
        print("❌ Error: TELEGRAM_BOT_TOKEN is not configured in config.yaml o .env")
        print("💡 Ejecuta 'domain-monitor setup' para configurar tus claves fácilmente.")
        sys.exit(1)
    bot = InteractiveTelegramBot(
        bot_token=config.telegram.bot_token,
        allowed_chat_id=config.telegram.chat_id,
        db=db,
        checker=checker,
        cf_api=cf_api,
        interval_hours=config.monitor.interval_hours,
    )
    bot.run_polling()


def cmd_test_notify(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Send test alert across all configured channels."""
    print("📤 Sending test alert...")
    notifier_mgr = build_notification_manager(config)

    test_res = DomainResult(
        domain="example.com",
        status=DomainStatus.AVAILABLE,
        is_available=True,
        engine="test_engine",
    )
    notifier_mgr.dispatch_alert(test_res, "FOUND_AVAILABLE", "This is a test notification from Dave's Domain Monitor.")
    print("✅ Test notifications dispatched to all enabled channels.")


def cmd_export(args, config: AppConfig, db: Database, checker: CompositeChecker, cf_api: CloudflareAPIChecker):
    """Export monitored domains to JSON or CSV."""
    domains = db.get_all_monitored_domains()
    output_path = args.output

    if args.format == "csv":
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if domains:
                writer = csv.DictWriter(f, fieldnames=list(domains[0].keys()))
                writer.writeheader()
                writer.writerows(domains)
        print(f"✅ Exported {len(domains)} domains to CSV: {output_path}")
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(domains, f, indent=2, ensure_ascii=False)
        print(f"✅ Exported {len(domains)} domains to JSON: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        prog="domain-monitor",
        description="Dave's Domain Monitor - Open-Source Domain Availability, Price & Purchase Monitor",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("-e", "--env", default=".env", help="Path to .env file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup
    p_setup = subparsers.add_parser("setup", help="Interactive onboarding & configuration wizard")
    p_setup.set_defaults(func=cmd_setup)

    # init
    p_init = subparsers.add_parser("init", help="Initialize database with candidate name combinations")
    p_init.add_argument("-c", "--clean", action="store_true", help="Clear all previous domains before initializing")
    p_init.set_defaults(func=cmd_init)

    # check
    p_check = subparsers.add_parser("check", help="Scan domains availability now")
    p_check.add_argument("domains", nargs="*", help="Optional specific domain(s) to check")
    p_check.set_defaults(func=cmd_check)

    # search
    p_search = subparsers.add_parser("search", help="Search candidate domains via Cloudflare Registrar discovery API")
    p_search.add_argument("query", help="Keyword or phrase to search (e.g. acme corp)")
    p_search.add_argument("-l", "--limit", type=int, default=5, help="Number of results (default: 5)")
    p_search.set_defaults(func=cmd_search)

    # status
    p_status = subparsers.add_parser("status", help="Display last known status from database")
    p_status.set_defaults(func=cmd_status)

    # buy
    p_buy = subparsers.add_parser("buy", help="Check price and purchase domain via Cloudflare Registrar")
    p_buy.add_argument("domain", help="Domain to purchase (e.g. mybrand.com)")
    p_buy.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    p_buy.set_defaults(func=cmd_buy)

    # monitor
    p_monitor = subparsers.add_parser("monitor", help="Run continuous background monitor daemon")
    p_monitor.set_defaults(func=cmd_monitor)

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate domain combinations from name")
    p_gen.add_argument("--name", help="First name")
    p_gen.add_argument("--last1", help="First surname")
    p_gen.add_argument("--last2", help="Second surname")
    p_gen.add_argument("--tlds", help="Comma-separated TLDs (e.g. es,com,dev,cat)")
    p_gen.add_argument("--add", action="store_true", help="Automatically add generated domains to database")
    p_gen.set_defaults(func=cmd_generate)

    # add
    p_add = subparsers.add_parser("add", help="Add domain(s) to monitoring list")
    p_add.add_argument("domains", nargs="+", help="Domain names to add (e.g. example.com)")
    p_add.add_argument("-p", "--priority", choices=["high", "medium", "low"], default="high", help="Domain priority")
    p_add.add_argument("--category", default="personal", help="Category tag")
    p_add.set_defaults(func=cmd_add)

    # remove
    p_rem = subparsers.add_parser("remove", help="Remove domain(s) from monitoring list")
    p_rem.add_argument("domains", nargs="+", help="Domain names to remove")
    p_rem.set_defaults(func=cmd_remove)

    # telegram-bot
    p_tg = subparsers.add_parser("telegram-bot", help="Run interactive Telegram Bot with Cloudflare buy buttons")
    p_tg.set_defaults(func=cmd_telegram_bot)

    # test-notify
    p_tn = subparsers.add_parser("test-notify", help="Send a test notification to verify Telegram/Discord alerts")
    p_tn.set_defaults(func=cmd_test_notify)

    # export
    p_exp = subparsers.add_parser("export", help="Export domains and statuses to JSON/CSV")
    p_exp.add_argument("-o", "--output", default="domains_export.json", help="Output file path")
    p_exp.add_argument("-f", "--format", choices=["json", "csv"], default="json", help="Export format")
    p_exp.set_defaults(func=cmd_export)

    args = parser.parse_args()

    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    config = load_config(args.config, args.env)
    db = Database(config.monitor.database_path)
    cf_api = CloudflareAPIChecker(
        api_token=config.cloudflare.api_token,
        account_id=config.cloudflare.account_id,
        timeout=config.monitor.timeout_seconds,
    )
    checker = CompositeChecker(
        cloudflare_token=config.cloudflare.api_token,
        cloudflare_account_id=config.cloudflare.account_id,
        timeout=config.monitor.timeout_seconds,
        expiring_threshold_days=config.monitor.expiring_threshold_days,
    )

    args.func(args, config, db, checker, cf_api)


if __name__ == "__main__":
    main()
