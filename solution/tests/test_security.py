
import pytest

from cryptography.fernet import Fernet
from solution.src.security import PIISecurity


@pytest.fixture
def security():
    # Generate temporary test keys.
    # Real application keys will come from environment variables.
    encryption_key = Fernet.generate_key().decode("utf-8")
    hmac_key = "a" * 64

    return PIISecurity(encryption_key, hmac_key)


def test_encrypt_and_decrypt(security):
    # Encrypting should not leave the original value visible.
    original = "9876543210"
    encrypted = security.encrypt(original)

    assert encrypted != original
    assert security.decrypt(encrypted) == original


def test_phone_fingerprint_is_consistent(security):
    # The same phone should always produce the same fingerprint.
    first = security.phone_fingerprint("+919876543210")
    second = security.phone_fingerprint("+919876543210")

    assert first == second


def test_different_phones_have_different_fingerprints(security):
    first = security.phone_fingerprint("+919876543210")
    second = security.phone_fingerprint("+919876543211")

    assert first != second


def test_mask_phone():
    assert PIISecurity.mask_phone("+919876543210") == "+91******3210"


def test_missing_environment_keys(monkeypatch):
    # Remove the keys from the environment.
    monkeypatch.delenv("PII_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("PII_HMAC_KEY", raising=False)

    # Prevent this test from loading keys from the real .env file.
    monkeypatch.setattr(
        "solution.src.security.load_dotenv",
        lambda: None,
    )

    # The method should fail when both keys are missing.
    with pytest.raises(RuntimeError):
        PIISecurity.from_environment()
