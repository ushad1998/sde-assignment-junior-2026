
import os
import hmac
import hashlib

from dotenv import load_dotenv
from cryptography.fernet import Fernet


class PIISecurity:
    """
    Handles encryption, decryption, phone matching, and masking.

    Encryption protects the original PII.
    HMAC creates a consistent fingerprint for matching.
    """

    def __init__(self, encryption_key: str, hmac_key: str):
        # Fernet requires its encryption key in bytes.
        self.cipher = Fernet(encryption_key.encode("utf-8"))

        # Convert the HMAC key from hexadecimal text into bytes.
        self.hmac_key = bytes.fromhex(hmac_key)

    @classmethod
    def from_environment(cls):
        """
        Load security keys from environment variables.

        Keys are not hardcoded in the source code.
        """
        # Load variables from the project's .env file.
        load_dotenv()

        encryption_key = os.environ.get("PII_ENCRYPTION_KEY")
        hmac_key = os.environ.get("PII_HMAC_KEY")

        # Stop immediately if either key is missing.
        if not encryption_key or not hmac_key:
            raise RuntimeError(
                "PII_ENCRYPTION_KEY and PII_HMAC_KEY must be configured"
            )

        return cls(encryption_key, hmac_key)

    def encrypt(self, value: str) -> str:
        """Encrypt a PII value and return its encrypted text."""
        encrypted = self.cipher.encrypt(value.encode("utf-8"))

        # Fernet returns bytes; SQLite can store the result as text.
        return encrypted.decode("utf-8")

    def decrypt(self, encrypted_value: str) -> str:
        """Decrypt an encrypted PII value."""
        decrypted = self.cipher.decrypt(
            encrypted_value.encode("utf-8")
        )

        return decrypted.decode("utf-8")

    def phone_fingerprint(self, canonical_phone: str) -> str:
        """
        Create a deterministic HMAC fingerprint for a phone number.

        The same phone number and HMAC key always produce
        the same fingerprint.
        """
        fingerprint = hmac.new(
            self.hmac_key,
            canonical_phone.encode("utf-8"),
            hashlib.sha256,
        )

        return fingerprint.hexdigest()

    @staticmethod
    def mask_phone(canonical_phone: str) -> str:
        """Show only the last four digits of an Indian phone number."""
        return "+91******" + canonical_phone[-4:]
