import unittest
from unittest.mock import patch

from api.client_factory import create_clients


class ClientFactoryTest(unittest.TestCase):
    def test_create_clients_uses_single_generic_model_config(self):
        with (
            patch("api.client_factory.Config.MODEL_API_KEY", "test-key"),
            patch("api.client_factory.Config.MODEL_BASE_URL", "https://api.example.com/v1"),
            patch("api.client_factory.Config.MODEL_NAME", "test-model"),
            patch("api.client_factory.Config.MAX_RETRY", 5),
            patch("api.client_factory.Config.REQUEST_TIMEOUT", 120),
        ):
            bundle = create_clients()

        self.assertEqual("test-model", bundle.model)
        self.assertEqual("https://api.example.com/v1", bundle.client.base_url)
        self.assertEqual("test-key", bundle.client.api_key)
        self.assertEqual(5, bundle.client.max_retry)
        self.assertEqual(120, bundle.client.timeout)

    def test_create_clients_requires_model_api_key(self):
        with (
            patch("api.client_factory.Config.MODEL_API_KEY", ""),
            patch("api.client_factory.Config.MODEL_BASE_URL", "https://api.example.com/v1"),
            patch("api.client_factory.Config.MODEL_NAME", "test-model"),
        ):
            with self.assertRaisesRegex(ValueError, "MODEL_API_KEY"):
                create_clients()

    def test_create_clients_requires_model_name(self):
        with (
            patch("api.client_factory.Config.MODEL_API_KEY", "test-key"),
            patch("api.client_factory.Config.MODEL_BASE_URL", "https://api.example.com/v1"),
            patch("api.client_factory.Config.MODEL_NAME", ""),
        ):
            with self.assertRaisesRegex(ValueError, "MODEL_NAME"):
                create_clients()


if __name__ == "__main__":
    unittest.main()
