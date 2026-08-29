"""
Tests for Checkers and Parsers.
"""

import unittest
from datetime import datetime, timezone
from domain_monitor.checkers.base import DomainResult, DomainStatus
from domain_monitor.checkers.cloudflare_doh import CloudflareDoHChecker
from domain_monitor.checkers.rdap import RDAPChecker, _parse_iso_date


class TestCheckers(unittest.TestCase):

    def test_parse_iso_date(self):
        dt = _parse_iso_date("2026-11-08T06:12:51Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 11)

    def test_domain_result_expiration_calc(self):
        exp = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1)
        res = DomainResult(
            domain="example.com",
            status=DomainStatus.REGISTERED,
            expiration_date=exp,
        )
        days = res.calculate_expiration_days()
        self.assertIsNotNone(days)
        self.assertGreater(days, 300)

    def test_cloudflare_doh_live(self):
        checker = CloudflareDoHChecker(timeout=5)
        # Check a known registered domain
        res_reg = checker.check_domain("google.com")
        self.assertEqual(res_reg.status, DomainStatus.REGISTERED)

        # Check an extremely unlikely random domain
        res_avail = checker.check_domain("thisdomaindoesnotexist-carlosdiaz-987654321.com")
        self.assertEqual(res_avail.status, DomainStatus.AVAILABLE)
        self.assertTrue(res_avail.is_available)


if __name__ == "__main__":
    unittest.main()
