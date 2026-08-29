"""
Tests for SQLite Database Manager.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from domain_monitor.database import Database
from domain_monitor.checkers.base import DomainResult, DomainStatus


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_domains.db"
        self.db = Database(str(self.db_path))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_add_and_get_domain(self):
        self.db.add_or_update_domain("carlos.es", priority="high", category="personal")
        domains = self.db.get_all_monitored_domains()
        self.assertEqual(len(domains), 1)
        self.assertEqual(domains[0]["domain"], "carlos.es")
        self.assertEqual(domains[0]["priority"], "high")

    def test_record_check_result_and_state_change(self):
        self.db.add_or_update_domain("carlos.es")

        # Initial check: Registered
        res1 = DomainResult(
            domain="carlos.es",
            status=DomainStatus.REGISTERED,
            is_available=False,
            engine="test",
        )
        changed, alert = self.db.record_check_result(res1)
        self.assertFalse(changed)

        # Transition: Becomes available!
        res2 = DomainResult(
            domain="carlos.es",
            status=DomainStatus.AVAILABLE,
            is_available=True,
            engine="test",
        )
        changed, alert = self.db.record_check_result(res2)
        self.assertTrue(changed)
        self.assertEqual(alert, "BECOME_AVAILABLE")

        # Stats
        stats = self.db.get_summary_stats()
        self.assertEqual(stats["available"], 1)

    def test_remove_domain(self):
        self.db.add_or_update_domain("test.es")
        self.assertTrue(self.db.remove_domain("test.es"))
        domains = self.db.get_all_monitored_domains()
        self.assertEqual(len(domains), 0)


if __name__ == "__main__":
    unittest.main()
