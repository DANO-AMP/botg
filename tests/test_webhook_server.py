"""Integration tests for the MaxelPay webhook server.

These tests start a real aiohttp server and send HTTP requests to it,
verifying the full flow: signature check → DB update → bot notification.
"""

import hashlib
import hmac
import json
import pytest
from aiohttp.test_utils import TestServer, TestClient
from aiohttp import web
from unittest.mock import AsyncMock, MagicMock, patch

from bot.services import webhook_server
from bot.services.maxelpay import MaxelPayClient

SECRET = "testsecretkey12"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _payload(event: str, order_id: str, extra: dict | None = None) -> bytes:
    data = {"orderId": order_id}
    if extra:
        data.update(extra)
    return json.dumps({"event": event, "data": data}).encode()


def _make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/maxelpay", webhook_server._handle_maxelpay_webhook)
    return app


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture(autouse=True)
def setup_webhook_globals(mock_bot):
    """Wire up webhook server module globals before each test."""
    webhook_server._maxelpay_client = MaxelPayClient("api", SECRET, "http://localhost")
    webhook_server._bot = mock_bot
    webhook_server._admin_id = 999
    webhook_server._bonus_usd = 10.0
    yield
    webhook_server._maxelpay_client = None
    webhook_server._bot = None
    webhook_server._admin_id = 0


# ── helpers ──────────────────────────────────────────────────────────────────

async def _post(client, body: bytes, signature: str | None = None) -> int:
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-MaxelPay-Signature"] = signature
    resp = await client.post("/webhook/maxelpay", data=body, headers=headers)
    return resp.status


# ── signature verification ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_signature_returns_401():
    body = _payload("payment.completed", "order_1")
    async with TestClient(TestServer(_make_app())) as client:
        status = await _post(client, body, signature="badsig")
    assert status == 401


@pytest.mark.asyncio
async def test_valid_signature_accepted(mock_bot):
    body = _payload("payment.completed", "order_1")
    sig = _sign(body)
    order = {"id": 1, "user_id": 111, "status": "pending", "balance_used": 0.0}

    with patch("bot.services.webhook_server.db") as mock_db, \
         patch("bot.services.webhook_server.deliver_and_notify", new_callable=AsyncMock):
        mock_db.get_order = AsyncMock(return_value=order)
        async with TestClient(TestServer(_make_app())) as client:
            status = await _post(client, body, signature=sig)
    assert status == 200


@pytest.mark.asyncio
async def test_missing_signature_logs_warning_but_processes(mock_bot):
    """If no signature header is sent, we warn but don't reject (for easier testing)."""
    body = _payload("payment.expired", "order_99")

    with patch("bot.services.webhook_server.db") as mock_db:
        mock_db.get_order = AsyncMock(return_value=None)
        async with TestClient(TestServer(_make_app())) as client:
            status = await _post(client, body, signature=None)
    assert status == 200


# ── order payment.completed ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_order_payment_completed_triggers_delivery(mock_bot):
    order = {"id": 1, "user_id": 111, "status": "pending", "balance_used": 0.0}
    body = _payload("payment.completed", "order_1")
    sig = _sign(body)

    with patch("bot.services.webhook_server.db") as mock_db, \
         patch("bot.services.webhook_server.deliver_and_notify", new_callable=AsyncMock) as mock_deliver:
        mock_db.get_order = AsyncMock(return_value=order)
        async with TestClient(TestServer(_make_app())) as client:
            status = await _post(client, body, signature=sig)

    assert status == 200
    mock_deliver.assert_awaited_once()
    args = mock_deliver.call_args[0]
    assert args[0] == 1  # order_id


@pytest.mark.asyncio
async def test_order_payment_overpaid_also_delivers(mock_bot):
    order = {"id": 2, "user_id": 222, "status": "pending", "balance_used": 0.0}
    body = _payload("payment.overpaid", "order_2")
    sig = _sign(body)

    with patch("bot.services.webhook_server.db") as mock_db, \
         patch("bot.services.webhook_server.deliver_and_notify", new_callable=AsyncMock) as mock_deliver:
        mock_db.get_order = AsyncMock(return_value=order)
        async with TestClient(TestServer(_make_app())) as client:
            await _post(client, body, signature=sig)

    mock_deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_order_already_delivered_is_ignored(mock_bot):
    order = {"id": 1, "user_id": 111, "status": "delivered", "balance_used": 0.0}
    body = _payload("payment.completed", "order_1")
    sig = _sign(body)

    with patch("bot.services.webhook_server.db") as mock_db, \
         patch("bot.services.webhook_server.deliver_and_notify", new_callable=AsyncMock) as mock_deliver:
        mock_db.get_order = AsyncMock(return_value=order)
        async with TestClient(TestServer(_make_app())) as client:
            status = await _post(client, body, signature=sig)

    assert status == 200
    mock_deliver.assert_not_awaited()


# ── order payment.expired ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_order_expired_updates_status_and_notifies_user(mock_bot):
    order = {"id": 3, "user_id": 333, "status": "pending", "balance_used": 0.0}
    body = _payload("payment.expired", "order_3")
    sig = _sign(body)

    with patch("bot.services.webhook_server.db") as mock_db:
        mock_db.get_order = AsyncMock(return_value=order)
        mock_db.update_order_status = AsyncMock()
        mock_db.update_user_balance = AsyncMock()
        async with TestClient(TestServer(_make_app())) as client:
            status = await _post(client, body, signature=sig)

    assert status == 200
    mock_db.update_order_status.assert_awaited_once_with(3, "expired")
    mock_bot.send_message.assert_awaited_once()
    assert mock_bot.send_message.call_args[0][0] == 333


@pytest.mark.asyncio
async def test_order_expired_refunds_balance_used(mock_bot):
    order = {"id": 4, "user_id": 444, "status": "pending", "balance_used": 15.0}
    body = _payload("payment.expired", "order_4")
    sig = _sign(body)

    with patch("bot.services.webhook_server.db") as mock_db:
        mock_db.get_order = AsyncMock(return_value=order)
        mock_db.update_order_status = AsyncMock()
        mock_db.update_user_balance = AsyncMock()
        async with TestClient(TestServer(_make_app())) as client:
            await _post(client, body, signature=sig)

    mock_db.update_user_balance.assert_awaited_once_with(444, 15.0)


# ── deposit webhooks ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deposit_completed_credits_balance(mock_bot):
    deposit = {"id": 10, "user_id": 555, "status": "pending", "amount_usd": 25.0}
    body = _payload("payment.completed", "deposit_10")
    sig = _sign(body)

    with patch("bot.services.webhook_server.db") as mock_db:
        mock_db.get_deposit = AsyncMock(return_value=deposit)
        mock_db.update_deposit_status = AsyncMock()
        mock_db.update_user_balance = AsyncMock()
        async with TestClient(TestServer(_make_app())) as client:
            status = await _post(client, body, signature=sig)

    assert status == 200
    mock_db.update_deposit_status.assert_awaited_once_with(10, "completed")
    mock_db.update_user_balance.assert_awaited_once_with(555, 25.0)


@pytest.mark.asyncio
async def test_deposit_expired_updates_status(mock_bot):
    deposit = {"id": 11, "user_id": 666, "status": "pending", "amount_usd": 10.0}
    body = _payload("payment.expired", "deposit_11")
    sig = _sign(body)

    with patch("bot.services.webhook_server.db") as mock_db:
        mock_db.get_deposit = AsyncMock(return_value=deposit)
        mock_db.update_deposit_status = AsyncMock()
        async with TestClient(TestServer(_make_app())) as client:
            status = await _post(client, body, signature=sig)

    assert status == 200
    mock_db.update_deposit_status.assert_awaited_once_with(11, "expired")


# ── edge cases ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_order_id_returns_200_no_crash():
    body = json.dumps({"event": "payment.completed", "data": {}}).encode()
    sig = _sign(body)

    async with TestClient(TestServer(_make_app())) as client:
        status = await _post(client, body, signature=sig)
    assert status == 200


@pytest.mark.asyncio
async def test_invalid_json_returns_400():
    body = b"not json at all"
    sig = _sign(body)

    async with TestClient(TestServer(_make_app())) as client:
        status = await _post(client, body, signature=sig)
    assert status == 400


@pytest.mark.asyncio
async def test_unknown_order_id_prefix_returns_200():
    body = _payload("payment.completed", "unknown_99")
    sig = _sign(body)

    async with TestClient(TestServer(_make_app())) as client:
        status = await _post(client, body, signature=sig)
    assert status == 200
