import pytest

from app.security import vault_crypto


def test_encrypt_roundtrip_and_ciphertext_hides_value():
    token = vault_crypto.encrypt("+919876543210")
    assert b"9876543210" not in token
    assert vault_crypto.decrypt(token) == "+919876543210"


def test_keyed_hash_is_stable_and_purpose_scoped():
    a = vault_crypto.keyed_hash("+919876543210", "phone")
    assert a == vault_crypto.keyed_hash("+919876543210", "phone")
    assert a != vault_crypto.keyed_hash("+919876543210", "aadhaar")
    assert "9876543210" not in a


@pytest.mark.parametrize(
    "raw", ["9876543210", "+91 98765 43210", "09876543210", "91-9876543210"]
)
def test_normalize_phone(raw):
    assert vault_crypto.normalize_phone(raw) == "+919876543210"


@pytest.mark.parametrize("raw", ["12345", "5876543210", "+1 415 555 0100"])
def test_normalize_phone_rejects_invalid(raw):
    with pytest.raises(ValueError):
        vault_crypto.normalize_phone(raw)


def test_reporter_ids_are_opaque_and_unique():
    ids = {vault_crypto.new_reporter_id() for _ in range(1000)}
    assert len(ids) == 1000
    assert all(i.startswith("R-") and len(i) == 34 for i in ids)
