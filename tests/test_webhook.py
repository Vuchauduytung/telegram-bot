import unittest

from fastapi.testclient import TestClient

from app.webhook import app, valid_webhook_secret


class WebhookSecretTests(unittest.TestCase):
    def test_health_endpoints(self):
        client = TestClient(app)
        for path in ("/health", "/healthz"):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})

    def test_accepts_matching_secret(self):
        self.assertTrue(valid_webhook_secret("expected-secret", "expected-secret"))

    def test_rejects_missing_or_incorrect_secret(self):
        self.assertFalse(valid_webhook_secret(None, "expected-secret"))
        self.assertFalse(valid_webhook_secret("wrong-secret", "expected-secret"))
        self.assertFalse(valid_webhook_secret("expected-secret", ""))


if __name__ == "__main__":
    unittest.main()