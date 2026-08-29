"""
Unit tests for Cloudflare pricing, buy flow, and Telegram interactive buttons.
"""

import unittest
from unittest.mock import MagicMock, patch
from domain_monitor.checkers.cloudflare_api import CloudflareAPIChecker
from domain_monitor.notifiers.telegram import TelegramNotifier
from domain_monitor.checkers.base import DomainResult, DomainStatus


class TestBuyFlow(unittest.TestCase):

    def test_unsupported_cctld_es(self):
        cf = CloudflareAPIChecker()
        res = cf.check_pricing_and_availability("carlos.es")
        self.assertFalse(res["supported"])
        self.assertIn("DonDominio", res["reason"])
        self.assertIn("dondominio.com", res["alternative_url"])

    def test_missing_credentials_message(self):
        cf = CloudflareAPIChecker(api_token=None, account_id=None)
        res = cf.check_pricing_and_availability("carlosdiaz.com")
        self.assertTrue(res["supported"])
        self.assertFalse(res["can_buy_on_cloudflare"])
        self.assertIn("Faltan credenciales", res["error"])

    def test_telegram_alert_inline_keyboard(self):
        notifier = TelegramNotifier(bot_token="12345:dummy", chat_id="12345")
        
        # Test .com domain alert has buy button
        res_com = DomainResult(
            domain="carlosdiaz.com",
            status=DomainStatus.AVAILABLE,
            is_available=True,
            engine="rdap",
        )
        
        with patch.object(notifier, "send_raw_message") as mock_send:
            notifier.send_alert(res_com, "BECOME_AVAILABLE")
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            reply_markup = kwargs.get("reply_markup")
            self.assertIsNotNone(reply_markup)
            buttons = reply_markup.get("inline_keyboard", [])
            # Check callback data contains buy_check:carlosdiaz.com
            self.assertEqual(buttons[0][0]["callback_data"], "buy_check:carlosdiaz.com")

        # Test .es domain alert has DonDominio button
        res_es = DomainResult(
            domain="carlos.es",
            status=DomainStatus.AVAILABLE,
            is_available=True,
            engine="cloudflare_doh",
        )
        with patch.object(notifier, "send_raw_message") as mock_send:
            notifier.send_alert(res_es, "BECOME_AVAILABLE")
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            reply_markup = kwargs.get("reply_markup")
            buttons = reply_markup.get("inline_keyboard", [])
            self.assertIn("dondominio.com", buttons[0][0]["url"])


if __name__ == "__main__":
    unittest.main()
