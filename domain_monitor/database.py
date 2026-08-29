"""
SQLite Database Manager.
Stores monitored domains, status transitions, scan histories, and sent alert logs.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .checkers.base import DomainResult, DomainStatus

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/domains.db"


class Database:
    """
    Manages SQLite storage for monitored domains, state tracking, and alert logs.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
            CREATE TABLE IF NOT EXISTS monitored_domains (
                domain TEXT PRIMARY KEY,
                priority TEXT DEFAULT 'medium',
                category TEXT DEFAULT 'general',
                current_status TEXT DEFAULT 'UNKNOWN',
                previous_status TEXT DEFAULT NULL,
                is_available INTEGER DEFAULT 0,
                registrar TEXT DEFAULT NULL,
                expiration_date TEXT DEFAULT NULL,
                days_until_expiration INTEGER DEFAULT NULL,
                last_alert_threshold INTEGER DEFAULT NULL,
                nameservers TEXT DEFAULT '[]',
                last_checked_at TEXT DEFAULT NULL,
                added_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                notes TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS check_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                status TEXT NOT NULL,
                is_available INTEGER NOT NULL,
                days_until_expiration INTEGER DEFAULT NULL,
                engine TEXT DEFAULT 'composite',
                error_message TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                channel TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                message TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_history_domain ON check_history(domain);
            CREATE INDEX IF NOT EXISTS idx_alert_domain ON alert_history(domain);
            """)
            # Ensure column migration for last_alert_threshold
            cursor.execute("PRAGMA table_info(monitored_domains)")
            cols = [r["name"] for r in cursor.fetchall()]
            if "last_alert_threshold" not in cols:
                cursor.execute("ALTER TABLE monitored_domains ADD COLUMN last_alert_threshold INTEGER DEFAULT NULL")
            conn.commit()

    def add_or_update_domain(
        self,
        domain: str,
        priority: str = "medium",
        category: str = "general",
        notes: str = "",
    ) -> bool:
        """Add a domain or update its priority/category if it exists."""
        clean = domain.strip().lower()
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO monitored_domains (domain, priority, category, added_at, is_active, notes)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    priority = excluded.priority,
                    category = excluded.category,
                    is_active = 1,
                    notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE monitored_domains.notes END
            """, (clean, priority, category, now, notes))
            conn.commit()
            return cursor.rowcount > 0

    def add_domains_batch(self, domain_tuples: List[Tuple[str, str]]) -> int:
        """Batch insert domains: list of (domain, priority)."""
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for domain, priority in domain_tuples:
                clean = domain.strip().lower()
                cursor.execute("""
                    INSERT INTO monitored_domains (domain, priority, category, added_at, is_active)
                    VALUES (?, ?, 'generated', ?, 1)
                    ON CONFLICT(domain) DO NOTHING
                """, (clean, priority, now))
                if cursor.rowcount > 0:
                    count += 1
            conn.commit()
        return count

    def clear_all_domains(self) -> int:
        """Clear all monitored domains (for clean reset / re-sync)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM monitored_domains")
            conn.commit()
            return cursor.rowcount

    def remove_domain(self, domain: str) -> bool:
        """Remove a domain from active monitoring."""
        clean = domain.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM monitored_domains WHERE domain = ?", (clean,))
            conn.commit()
            return cursor.rowcount > 0

    def get_all_monitored_domains(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Retrieve all monitored domains."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM monitored_domains"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, domain ASC"
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def record_check_result(self, result: DomainResult) -> Tuple[bool, Optional[str]]:
        """
        Record a check result.
        Returns (state_changed, alert_type) if a noteworthy status change occurred.
        """
        clean = result.domain.strip().lower()
        now = result.checked_at.isoformat()
        exp_iso = result.expiration_date.isoformat() if result.expiration_date else None
        ns_json = json.dumps(result.nameservers)

        state_changed = False
        alert_type = None

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Fetch previous state
            cursor.execute("SELECT current_status, is_available FROM monitored_domains WHERE domain = ?", (clean,))
            row = cursor.fetchone()

            prev_status = row["current_status"] if row else None
            prev_available = bool(row["is_available"]) if row else False

            # Check for noteworthy transition
            curr_status = result.status.value

            if prev_status and prev_status != "UNKNOWN":
                if not prev_available and result.is_available:
                    state_changed = True
                    alert_type = "BECOME_AVAILABLE"
                elif prev_status != curr_status:
                    state_changed = True
                    if result.status == DomainStatus.REDEMPTION:
                        alert_type = "ENTERED_REDEMPTION"
                    elif result.status == DomainStatus.EXPIRING_SOON:
                        alert_type = "EXPIRING_SOON"
                    else:
                        alert_type = "STATUS_CHANGED"
            elif result.is_available:
                # First check and it is available!
                state_changed = True
                alert_type = "FOUND_AVAILABLE"

            # Check expiration countdown milestones: 30, 15, 7, 1 days
            days_left = result.days_until_expiration
            if days_left is not None and not result.is_available:
                cursor.execute("SELECT last_alert_threshold FROM monitored_domains WHERE domain = ?", (clean,))
                t_row = cursor.fetchone()
                last_t = t_row["last_alert_threshold"] if t_row and t_row["last_alert_threshold"] is not None else 9999

                # Check smallest applicable threshold
                for threshold in (1, 7, 15, 30):
                    if days_left <= threshold and last_t > threshold:
                        state_changed = True
                        alert_type = f"EXPIRING_{threshold}D"
                        cursor.execute("UPDATE monitored_domains SET last_alert_threshold = ? WHERE domain = ?", (threshold, clean))
                        break

            # 2. Update monitored_domains table
            cursor.execute("""
                INSERT INTO monitored_domains (
                    domain, current_status, previous_status, is_available, registrar,
                    expiration_date, days_until_expiration, nameservers, last_checked_at, added_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    previous_status = monitored_domains.current_status,
                    current_status = excluded.current_status,
                    is_available = excluded.is_available,
                    registrar = excluded.registrar,
                    expiration_date = excluded.expiration_date,
                    days_until_expiration = excluded.days_until_expiration,
                    nameservers = excluded.nameservers,
                    last_checked_at = excluded.last_checked_at
            """, (
                clean,
                curr_status,
                prev_status,
                1 if result.is_available else 0,
                result.registrar,
                exp_iso,
                result.days_until_expiration,
                ns_json,
                now,
                now,
            ))

            # 3. Insert into check_history
            cursor.execute("""
                INSERT INTO check_history (
                    domain, checked_at, status, is_available, days_until_expiration, engine, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                clean,
                now,
                curr_status,
                1 if result.is_available else 0,
                result.days_until_expiration,
                result.engine,
                result.error_message,
            ))

            conn.commit()

        return state_changed, alert_type

    def record_alert(self, domain: str, alert_type: str, channel: str, message: str):
        """Log sent notification alert to avoid duplicates."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alert_history (domain, alert_type, channel, sent_at, message)
                VALUES (?, ?, ?, ?, ?)
            """, (domain.lower(), alert_type, channel, now, message))
            conn.commit()

    def get_summary_stats(self) -> Dict[str, int]:
        """Get summary statistics for dashboard / reports."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN current_status = 'AVAILABLE' THEN 1 ELSE 0 END) as available,
                    SUM(CASE WHEN current_status = 'REGISTERED' THEN 1 ELSE 0 END) as registered,
                    SUM(CASE WHEN current_status = 'EXPIRING_SOON' THEN 1 ELSE 0 END) as expiring,
                    SUM(CASE WHEN current_status = 'REDEMPTION' THEN 1 ELSE 0 END) as redemption,
                    SUM(CASE WHEN current_status = 'ERROR' THEN 1 ELSE 0 END) as errors
                FROM monitored_domains WHERE is_active = 1
            """)
            row = cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "available": row["available"] or 0,
                "registered": row["registered"] or 0,
                "expiring": row["expiring"] or 0,
                "redemption": row["redemption"] or 0,
                "errors": row["errors"] or 0,
            }
