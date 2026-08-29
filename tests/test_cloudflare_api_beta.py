"""
Unit tests for Cloudflare Registrar API Beta specifications.
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from domain_monitor.checkers.cloudflare_api import CloudflareAPIChecker, REASON_MESSAGES


class TestCloudflareAPIBeta(unittest.TestCase):

    def test_search_domains_mock(self):
        cf = CloudflareAPIChecker(api_token="dummy_token", account_id="dummy_acc")
        
        mock_response = {
            "success": True,
            "result": {
                "domains": [
                    {
                        "name": "acmecorp.com",
                        "registrable": True,
                        "tier": "standard",
                        "pricing": {
                            "currency": "USD",
                            "registration_cost": "8.57",
                            "renewal_cost": "8.57",
                        },
                    }
                ]
            },
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            mock_urlopen.return_value = mock_cm

            res = cf.search_domains("acme corp", limit=1)
            self.assertTrue(res["success"])
            self.assertEqual(len(res["domains"]), 1)
            self.assertEqual(res["domains"][0]["name"], "acmecorp.com")

    def test_domain_check_with_reason(self):
        cf = CloudflareAPIChecker(api_token="dummy_token", account_id="dummy_acc")

        mock_response = {
            "success": True,
            "result": {
                "domains": [
                    {
                        "name": "mybrand.uk",
                        "registrable": False,
                        "reason": "extension_not_supported_via_api",
                    }
                ]
            },
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            mock_urlopen.return_value = mock_cm

            res = cf.check_pricing_and_availability("mybrand.uk")
            self.assertTrue(res["supported"])
            self.assertFalse(res["can_buy_on_cloudflare"])
            self.assertIn("API beta", res["reason"])

    def test_purchase_domain_mock(self):
        cf = CloudflareAPIChecker(api_token="dummy_token", account_id="dummy_acc")

        mock_response = {
            "success": True,
            "result": {
                "state": "succeeded",
                "domain_name": "acmecorp.dev",
            },
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.status = 201
            mock_cm.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_cm.__enter__.return_value = mock_cm
            mock_urlopen.return_value = mock_cm

            res = cf.purchase_domain("acmecorp.dev")
            self.assertTrue(res["success"])
            self.assertEqual(res["state"], "succeeded")
            self.assertIn("éxito", res["message"])


if __name__ == "__main__":
    unittest.main()
