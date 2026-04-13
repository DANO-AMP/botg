import pytest
from bot.services.bitunix import BitunixClient


def test_sort_params():
    client = BitunixClient("key", "secret")
    result = client._sort_params({"coin": "BTC", "network": "TRC20", "limit": "10"})
    assert result == "coin=BTC&limit=10&network=TRC20"


def test_make_headers_fields():
    client = BitunixClient("mykey", "mysecret")
    headers = client._make_headers()
    assert headers["api-key"] == "mykey"
    assert "nonce" in headers
    assert "timestamp" in headers
    assert "sign" in headers
    assert len(headers["nonce"]) == 32


def test_signing_determinism():
    client = BitunixClient("k", "s")
    h1 = client._make_headers_with_values("testnonce", "1000", "", "")
    h2 = client._make_headers_with_values("testnonce", "1000", "", "")
    assert h1["sign"] == h2["sign"]


@pytest.mark.asyncio
async def test_check_deposit_found(mocker):
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": [{"status": "success", "amount": "5.003"}]}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is True


@pytest.mark.asyncio
async def test_check_deposit_not_found(mocker):
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": []}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is False


@pytest.mark.asyncio
async def test_check_deposit_wrong_amount(mocker):
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": [{"status": "success", "amount": "5.999"}]}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is False
