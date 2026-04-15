import json
import pytest
from bot.services.maxelpay import MaxelPayClient


def test_encrypt_decrypt_roundtrip():
    client = MaxelPayClient("apikey", "mysecretkey12345678", "http://localhost:8080")
    payload = {"orderID": "order_1", "amount": "10.00", "currency": "USD"}
    encrypted = client._encrypt(payload)
    decrypted = client._decrypt(encrypted)
    assert decrypted == payload


def test_encrypt_produces_base64():
    client = MaxelPayClient("apikey", "mysecretkey12345678", "http://localhost:8080")
    encrypted = client._encrypt({"test": "value"})
    # Should be valid base64
    import base64
    decoded = base64.b64decode(encrypted)
    assert len(decoded) > 0


def test_encrypt_different_payloads_differ():
    client = MaxelPayClient("apikey", "mysecretkey12345678", "http://localhost:8080")
    enc1 = client._encrypt({"a": "1"})
    enc2 = client._encrypt({"b": "2"})
    assert enc1 != enc2


def test_decrypt_with_wrong_key_fails():
    client1 = MaxelPayClient("apikey", "mysecretkey12345678", "http://localhost:8080")
    client2 = MaxelPayClient("apikey", "othersecretkey123456", "http://localhost:8080")
    encrypted = client1._encrypt({"test": "value"})
    with pytest.raises(Exception):
        client2._decrypt(encrypted)


def test_short_key_padded():
    """Keys shorter than 32 bytes should be zero-padded."""
    client = MaxelPayClient("apikey", "shortkey1234567890", "http://localhost:8080")
    payload = {"key": "value"}
    encrypted = client._encrypt(payload)
    decrypted = client._decrypt(encrypted)
    assert decrypted == payload


def test_long_key_truncated():
    """Keys longer than 32 bytes should be truncated."""
    long_key = "a" * 64
    client = MaxelPayClient("apikey", long_key, "http://localhost:8080")
    payload = {"key": "value"}
    encrypted = client._encrypt(payload)
    decrypted = client._decrypt(encrypted)
    assert decrypted == payload


def test_api_url_staging():
    client = MaxelPayClient("key", "secret1234567890ab", "http://localhost", mode="stg")
    assert "stg" in client._api_url


def test_api_url_production():
    client = MaxelPayClient("key", "secret1234567890ab", "http://localhost", mode="prod")
    assert "prod" in client._api_url


def test_webhook_base_url_trailing_slash():
    client = MaxelPayClient("key", "secret1234567890ab", "http://localhost:8080/")
    assert client._webhook_base_url == "http://localhost:8080"


@pytest.mark.asyncio
async def test_create_checkout_success(mocker):
    client = MaxelPayClient("apikey", "mysecretkey12345678", "http://localhost:8080")

    mock_resp = mocker.MagicMock()
    mock_resp.status = 200
    mock_resp.json = mocker.AsyncMock(return_value={"result": "https://pay.maxelpay.com/checkout/abc123"})
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    session = mocker.MagicMock()
    session.post.return_value = mock_resp
    mocker.patch.object(client, "_get_session", return_value=session)

    result = await client.create_checkout(
        order_id="order_1",
        amount=10.0,
        user_name="testuser",
    )
    assert result["payment_url"] == "https://pay.maxelpay.com/checkout/abc123"
    assert result["order_id"] == "order_1"


@pytest.mark.asyncio
async def test_create_checkout_api_error(mocker):
    client = MaxelPayClient("apikey", "mysecretkey12345678", "http://localhost:8080")

    mock_resp = mocker.MagicMock()
    mock_resp.status = 422
    mock_resp.text = mocker.AsyncMock(return_value="Invalid API key")
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    session = mocker.MagicMock()
    session.post.return_value = mock_resp
    mocker.patch.object(client, "_get_session", return_value=session)

    with pytest.raises(ValueError, match="MaxelPay API error"):
        await client.create_checkout(order_id="order_1", amount=10.0)
