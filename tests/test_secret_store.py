from __future__ import annotations

import os
import unittest

from cryptography.fernet import Fernet

from backend.config import get_settings
from backend.secret_store import decrypt_secret, encrypt_secret


class SecretStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env = {
            "APP_ENV": os.environ.get("APP_ENV"),
            "CREDENTIAL_ENCRYPTION_KEY": os.environ.get("CREDENTIAL_ENCRYPTION_KEY"),
        }
        os.environ["APP_ENV"] = "production"
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        get_settings.cache_clear()

    def tearDown(self) -> None:
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_round_trip_does_not_store_plaintext(self) -> None:
        encrypted = encrypt_secret("local-secret")
        self.assertTrue(encrypted.startswith("enc:v1:"))
        self.assertNotIn("local-secret", encrypted)
        self.assertEqual(decrypt_secret(encrypted), "local-secret")

    def test_plaintext_rows_remain_readable_for_migration(self) -> None:
        self.assertEqual(decrypt_secret("legacy-secret"), "legacy-secret")
