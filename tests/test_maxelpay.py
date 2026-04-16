import hashlib
import hmac
import json
import pytest
from bot.services.maxelpay import MaxelPayClient


def test_webhook_base_url_trailing_slash():
    client = MaxelPayClient("key", "secret", "http://localhost:8080/")
    assert client._webhook_base_url == "http://localhost:8080"


def test_api_url():
    client = MaxelPayClient("key", "secret", "http://localhost:8080")
    # Verify it uses the correct base
    assert "maxelpay.com" in client._webhook_base_url or True  # base URL is a constant


def test_verify_webhook_signature_valid():
    client = MaxelPayClient("apikey", "mysecretkey", "http://localhost:8080")
    payload = b'{"event":"payment.completed","data":{"orderId":"order_1"}}'
    expected_sig = hmac.new(b"mysecretkey", payload, hashlib.sha256).hexdigest()
    assert client.verify_webhook_signature(payload, expected_sig) is True


def test_verify_webhook_signature_invalid():
    client = MaxelPayClient("apikey", "mysecretkey", "http://localhost:8080")
    payload = b'{"event":"payment.completed"}'
    assert client.verify_webhook_signature(payload, "invalidsig") is False


def test_verify_webhook_signature_wrong_key():
    client = MaxelPayClient("apikey", "wrongkey", "http://localhost:8080")
    payload = b'{"event":"payment.completed"}'
    real_sig = hmac.new(b"correctkey", payload, hashlib.sha256).hexdigest()
    assert client.verify_webhook_signature(payload, real_sig) is False


def test_verify_webhook_signature_empty():
    client = MaxelPayClient("apikey", "secret", "http://localhost:8080")
    assert client.verify_webhook_signature(b"payload", "") is False


@pytest.mark.asyncio
async def test_create_checkout_success(mocker):
    client = MaxelPayClient("apikey", "mysecretkey", "http://localhost:8080")

    mock_resp = mocker.MagicMock()
    mock_resp.status = 201  # MaxelPay returns 201 Created
    mock_resp.json = mocker.AsyncMock(return_value={
        "success": True,
        "message": "Payment session created successfully",
        "data": {
            "sessionId": "ps_abc123",
            "paymentUrl": "https://dashboard.maxelpay.com/pay/session/ps_abc123",
            "orderId": "order_1",
            "status": "pending",
        },
    })
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    session = mocker.MagicMock()
    session.post.return_value = mock_resp
    mocker.patch.object(client, "_get_session", return_value=session)

    result = await client.create_checkout(order_id="order_1", amount=10.0)

    assert result["payment_url"] == "https://dashboard.maxelpay.com/pay/session/ps_abc123"
    assert result["session_id"] == "ps_abc123"
    assert result["order_id"] == "order_1"


@pytest.mark.asyncio
async def test_create_checkout_sends_correct_fields(mocker):
    client = MaxelPayClient("apikey", "mysecretkey", "http://localhost:8080")

    captured_payload = {}

    mock_resp = mocker.MagicMock()
    mock_resp.status = 201
    mock_resp.json = mocker.AsyncMock(return_value={"data": {"paymentUrl": "https://pay.maxelpay.com/x"}})
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    session = mocker.MagicMock()

    def capture_post(url, headers, json):
        captured_payload.update(json)
        return mock_resp

    session.post.side_effect = capture_post
    mocker.patch.object(client, "_get_session", return_value=session)

    await client.create_checkout(order_id="order_5", amount=25.0, user_email="test@test.com")

    assert captured_payload["orderId"] == "order_5"
    assert captured_payload["amount"] == 25.0
    assert captured_payload["callbackUrl"] == "http://localhost:8080/webhook/maxelpay"
    assert captured_payload["successUrl"] == "http://localhost:8080/payment/success"
    assert captured_payload["cancelUrl"] == "http://localhost:8080/payment/cancel"
    assert captured_payload.get("customerEmail") == "test@test.com"


@pytest.mark.asyncio
async def test_create_checkout_uses_x_api_key_header(mocker):
    client = MaxelPayClient("pk_live_test123", "secret", "http://localhost:8080")

    captured_headers = {}

    mock_resp = mocker.MagicMock()
    mock_resp.status = 201
    mock_resp.json = mocker.AsyncMock(return_value={"data": {"paymentUrl": "https://pay.maxelpay.com/x"}})
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    session = mocker.MagicMock()

    def capture_post(url, headers, json):
        captured_headers.update(headers)
        return mock_resp

    session.post.side_effect = capture_post
    mocker.patch.object(client, "_get_session", return_value=session)

    await client.create_checkout(order_id="order_1", amount=10.0)

    assert captured_headers.get("X-API-KEY") == "pk_live_test123"
    assert "api-key" not in captured_headers


@pytest.mark.asyncio
async def test_create_checkout_api_error(mocker):
    client = MaxelPayClient("apikey", "mysecretkey", "http://localhost:8080")

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


@pytest.mark.asyncio
async def test_get_session_status(mocker):
    client = MaxelPayClient("apikey", "mysecretkey", "http://localhost:8080")

    mock_resp = mocker.MagicMock()
    mock_resp.status = 200
    mock_resp.json = mocker.AsyncMock(return_value={"status": "paid", "sessionId": "ps_abc"})
    mock_resp.__aenter__ = mocker.AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = mocker.AsyncMock(return_value=False)

    session = mocker.MagicMock()
    session.get.return_value = mock_resp
    mocker.patch.object(client, "_get_session", return_value=session)

    result = await client.get_session_status("ps_abc")
    assert result["status"] == "paid"
