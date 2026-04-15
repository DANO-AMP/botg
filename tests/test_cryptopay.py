import pytest
from bot.services.cryptopay import CryptoPayClient


@pytest.mark.asyncio
async def test_create_invoice(mocker):
    client = CryptoPayClient("test-token")
    mocker.patch.object(client, "_api_call", return_value={
        "invoice_id": 12345,
        "bot_invoice_url": "https://t.me/CryptoBot?start=abc",
        "status": "active",
    })
    result = await client.create_invoice(10.0, description="Test purchase")
    assert result["invoice_id"] == 12345
    assert result["pay_url"] == "https://t.me/CryptoBot?start=abc"
    assert result["status"] == "active"


@pytest.mark.asyncio
async def test_create_invoice_passes_correct_body(mocker):
    client = CryptoPayClient("test-token")
    mock_call = mocker.patch.object(client, "_api_call", return_value={
        "invoice_id": 1,
        "bot_invoice_url": "https://t.me/CryptoBot?start=x",
        "status": "active",
    })
    await client.create_invoice(25.50, description="My item", expires_in=600)
    mock_call.assert_called_once_with("post", "/createInvoice", json={
        "currency_type": "fiat",
        "fiat": "USD",
        "amount": "25.50",
        "accepted_assets": "USDT,BTC,ETH,TON,LTC,BNB,TRX,USDC",
        "description": "My item",
        "expires_in": 600,
    })


@pytest.mark.asyncio
async def test_get_invoice_status_paid(mocker):
    client = CryptoPayClient("test-token")
    mocker.patch.object(client, "_api_call", return_value={
        "items": [{"invoice_id": 123, "status": "paid"}],
    })
    status = await client.get_invoice_status(123)
    assert status == "paid"


@pytest.mark.asyncio
async def test_get_invoice_status_active(mocker):
    client = CryptoPayClient("test-token")
    mocker.patch.object(client, "_api_call", return_value={
        "items": [{"invoice_id": 456, "status": "active"}],
    })
    status = await client.get_invoice_status(456)
    assert status == "active"


@pytest.mark.asyncio
async def test_get_invoice_status_not_found(mocker):
    client = CryptoPayClient("test-token")
    mocker.patch.object(client, "_api_call", return_value={"items": []})
    status = await client.get_invoice_status(999)
    assert status == "expired"


@pytest.mark.asyncio
async def test_get_invoice_status_list_format(mocker):
    """Handle API returning a list directly instead of {items: [...]}."""
    client = CryptoPayClient("test-token")
    mocker.patch.object(client, "_api_call", return_value=[
        {"invoice_id": 789, "status": "paid"},
    ])
    status = await client.get_invoice_status(789)
    assert status == "paid"


@pytest.mark.asyncio
async def test_create_invoice_api_error(mocker):
    client = CryptoPayClient("test-token")
    mocker.patch.object(
        client, "_api_call",
        side_effect=ValueError("CryptoPay API error: INVALID_AMOUNT: Amount is too small"),
    )
    with pytest.raises(ValueError, match="INVALID_AMOUNT"):
        await client.create_invoice(0.001)
