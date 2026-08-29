"""
Unit tests for DonDominio API integration.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from domain_monitor.checkers.base import DomainStatus
from domain_monitor.checkers.dondominio import DonDominioChecker


class TestDonDominioChecker(unittest.TestCase):

    def test_unconfigured(self):
        checker = DonDominioChecker()
        self.assertFalse(checker.is_configured())
        res = checker.check_domain("carlos.es")
        self.assertEqual(res.status, DomainStatus.UNKNOWN)

    def test_check_domain_available(self):
        checker = DonDominioChecker(api_user="test_user", api_key="test_key")
        self.assertTrue(checker.is_configured())

        mock_response = {
            "success": True,
            "response_data": {
                "available": True,
                "domain": "carlosdiaz.es",
            }
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            mock_urlopen.return_value = mock_cm

            res = checker.check_domain("carlosdiaz.es")
            self.assertTrue(res.is_available)
            self.assertEqual(res.status, DomainStatus.AVAILABLE)
            self.assertEqual(res.engine, "dondominio_api")


if __name__ == "__main__":
    unittest.main()
