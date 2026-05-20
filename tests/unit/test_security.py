from shared.ecowatch_common import decrypt_text, encrypt_text, sign_token, verify_token


def test_encrypt_roundtrip() -> None:
    value = "eco sensitive payload"
    encrypted = encrypt_text(value, "demo-key")
    assert encrypted != value
    assert decrypt_text(encrypted, "demo-key") == value


def test_token_roundtrip() -> None:
    token = sign_token({"sub": "USER-001", "role": "activist"}, "jwt-secret", exp_minutes=5)
    payload = verify_token(token, "jwt-secret")
    assert payload is not None
    assert payload["sub"] == "USER-001"
