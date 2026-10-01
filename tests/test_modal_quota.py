import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.session import (
    ModalMonthlyQuotaExceeded,
    ModalQuotaStoreUnavailable,
    reserve_modal_request,
)


class ModalQuotaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            valkey_url="redis://test",
            valkey_token="",
            modal_max_requests_per_month=400,
        )

    async def test_reservation_uses_atomic_monthly_counter(self):
        client = Mock()
        client.eval = AsyncMock(return_value=1)

        with patch("app.session._redis", return_value=client):
            await reserve_modal_request(self.settings)

        script, key_count, key, limit, ttl = client.eval.await_args.args
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        self.assertIn("INCR", script)
        self.assertEqual(key_count, 1)
        self.assertEqual(key, f"cloud-bot:modal-requests:{month}")
        self.assertEqual(limit, 400)
        self.assertEqual(ttl, 40 * 24 * 60 * 60)

    async def test_reservation_rejects_after_monthly_limit(self):
        client = Mock()
        client.eval = AsyncMock(return_value=0)

        with patch("app.session._redis", return_value=client):
            with self.assertRaises(ModalMonthlyQuotaExceeded):
                await reserve_modal_request(self.settings)

    async def test_reservation_fails_closed_when_valkey_is_unavailable(self):
        client = Mock()
        client.eval = AsyncMock(side_effect=ConnectionError("offline"))

        with patch("app.session._redis", return_value=client):
            with self.assertRaises(ModalQuotaStoreUnavailable):
                await reserve_modal_request(self.settings)


if __name__ == "__main__":
    unittest.main()