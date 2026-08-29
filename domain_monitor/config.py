"""
Configuration loader.
Parses config.yaml and environment variables (.env) with robust defaults.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


def load_env_file(filepath: str = ".env"):
    """Lightweight .env parser without external dependencies."""
    p = Path(filepath)
    if not p.exists():
        return
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k not in os.environ:
                os.environ[k] = v


def expand_env_vars(data: Any) -> Any:
    """Recursively expand ${VAR} or $VAR in config strings."""
    if isinstance(data, str):
        pattern = re.compile(r"\$\{?([A-Za-z0-9_]+)\}?")
        def repl(match):
            var = match.group(1)
            return os.getenv(var, "")
        return pattern.sub(repl, data)
    elif isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(item) for item in data]
    return data


@dataclass
class NameConfig:
    first_name: str = "carlos"
    last_name1: str = "diaz"
    last_name2: str = "garcia"
    keywords: List[str] = field(default_factory=lambda: ["dev", "tech", "ai", "code"])
    tlds: List[str] = field(default_factory=lambda: ["es", "com", "dev", "me", "io", "ai", "app", "net"])
    excluded_tlds: List[str] = field(default_factory=lambda: ["cat", "org"])
    excluded_slugs: List[str] = field(default_factory=lambda: ["carlosdiazgarcia", "diazgarcia"])
    excluded_domains: List[str] = field(default_factory=list)
    include_full_name: bool = False
    include_single_names: bool = True
    include_first_name_only: bool = True
    include_surname_only: bool = False
    include_first_and_last: bool = True
    include_second_surname: bool = False
    include_hyphenated: bool = True
    include_initials: bool = False


@dataclass
class CloudflareConfig:
    api_token: Optional[str] = None
    account_id: Optional[str] = None
    doh_url: str = "https://cloudflare-dns.com/dns-query"


@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    send_daily_summary: bool = True


@dataclass
class DonDominioConfig:
    api_user: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class DiscordConfig:
    enabled: bool = False
    webhook_url: Optional[str] = None


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_email: str = ""
    to_emails: List[str] = field(default_factory=list)
    use_tls: bool = True


@dataclass
class MonitorConfig:
    interval_hours: float = 0.5
    timeout_seconds: int = 8
    max_concurrency: int = 8
    expiring_threshold_days: int = 30
    database_path: str = "data/domains.db"


@dataclass
class AppConfig:
    name: NameConfig = field(default_factory=NameConfig)
    custom_domains: List[str] = field(default_factory=list)
    cloudflare: CloudflareConfig = field(default_factory=CloudflareConfig)
    dondominio: DonDominioConfig = field(default_factory=DonDominioConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)


def load_config(config_path: str = "config.yaml", env_path: str = ".env") -> AppConfig:
    """Load and parse YAML configuration combined with environment variables."""
    load_env_file(env_path)

    config_data: Dict[str, Any] = {}
    p = Path(config_path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            config_data = expand_env_vars(raw)

    # Name settings
    name_raw = config_data.get("name", {})
    name_cfg = NameConfig(
        first_name=name_raw.get("first_name", os.getenv("NAME_FIRST", "carlos")),
        last_name1=name_raw.get("last_name1", os.getenv("NAME_LAST1", "diaz")),
        last_name2=name_raw.get("last_name2", os.getenv("NAME_LAST2", "garcia")),
        keywords=name_raw.get("keywords", ["dev", "tech", "ai", "code"]),
        tlds=name_raw.get("tlds", ["es", "com", "dev", "me", "io", "ai", "app", "net"]),
        excluded_tlds=name_raw.get("excluded_tlds", ["cat", "org"]),
        excluded_slugs=name_raw.get("excluded_slugs", ["carlosdiazgarcia", "diazgarcia"]),
        excluded_domains=name_raw.get("excluded_domains", []),
        include_full_name=name_raw.get("include_full_name", False),
        include_single_names=name_raw.get("include_single_names", True),
        include_first_name_only=name_raw.get("include_first_name_only", True),
        include_surname_only=name_raw.get("include_surname_only", False),
        include_first_and_last=name_raw.get("include_first_and_last", True),
        include_second_surname=name_raw.get("include_second_surname", False),
        include_hyphenated=name_raw.get("include_hyphenated", True),
        include_initials=name_raw.get("include_initials", False),
    )

    # Cloudflare settings
    cf_raw = config_data.get("cloudflare", {})
    cf_token = cf_raw.get("api_token") or os.getenv("CLOUDFLARE_API_TOKEN") or None
    cf_account = cf_raw.get("account_id") or os.getenv("CLOUDFLARE_ACCOUNT_ID") or None
    cf_cfg = CloudflareConfig(
        api_token=cf_token,
        account_id=cf_account,
        doh_url=cf_raw.get("doh_url", "https://cloudflare-dns.com/dns-query"),
    )

    # DonDominio settings
    dd_raw = config_data.get("dondominio", {})
    dd_user = dd_raw.get("api_user") or os.getenv("DONDOMINIO_API_USER") or None
    dd_key = dd_raw.get("api_key") or os.getenv("DONDOMINIO_API_KEY") or None
    dd_cfg = DonDominioConfig(
        api_user=dd_user,
        api_key=dd_key,
    )

    # Telegram settings
    tg_raw = config_data.get("telegram", {})
    tg_token = tg_raw.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN") or None
    tg_chat = tg_raw.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID") or None
    tg_cfg = TelegramConfig(
        enabled=tg_raw.get("enabled", bool(tg_token and tg_chat)),
        bot_token=tg_token,
        chat_id=tg_chat,
        send_daily_summary=tg_raw.get("send_daily_summary", True),
    )

    # Discord settings
    disc_raw = config_data.get("discord", {})
    disc_url = disc_raw.get("webhook_url") or os.getenv("DISCORD_WEBHOOK_URL") or None
    disc_cfg = DiscordConfig(
        enabled=disc_raw.get("enabled", bool(disc_url)),
        webhook_url=disc_url,
    )

    # Email settings
    em_raw = config_data.get("email", {})
    em_cfg = EmailConfig(
        enabled=em_raw.get("enabled", False),
        smtp_host=em_raw.get("smtp_host", os.getenv("SMTP_HOST", "")),
        smtp_port=int(em_raw.get("smtp_port", os.getenv("SMTP_PORT", 587))),
        smtp_user=em_raw.get("smtp_user", os.getenv("SMTP_USER", "")),
        smtp_password=em_raw.get("smtp_password", os.getenv("SMTP_PASSWORD", "")),
        from_email=em_raw.get("from_email", os.getenv("FROM_EMAIL", "")),
        to_emails=em_raw.get("to_emails", [os.getenv("TO_EMAIL", "")]),
        use_tls=em_raw.get("use_tls", True),
    )

    # Monitor settings
    mon_raw = config_data.get("monitor", {})
    mon_cfg = MonitorConfig(
        interval_hours=float(mon_raw.get("interval_hours", os.getenv("MONITOR_INTERVAL_HOURS", 0.5))),
        timeout_seconds=int(mon_raw.get("timeout_seconds", 8)),
        max_concurrency=int(mon_raw.get("max_concurrency", 8)),
        expiring_threshold_days=int(mon_raw.get("expiring_threshold_days", 30)),
        database_path=mon_raw.get("database_path", "data/domains.db"),
    )

    # Custom domains list
    custom_domains = config_data.get("custom_domains", [])

    return AppConfig(
        name=name_cfg,
        custom_domains=custom_domains,
        cloudflare=cf_cfg,
        telegram=tg_cfg,
        discord=disc_cfg,
        email=em_cfg,
        monitor=mon_cfg,
    )
