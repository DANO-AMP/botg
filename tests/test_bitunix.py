import pytest
from bot.services.bitunix import BitunixClient


def test_params_to_url_query():
    client = BitunixClient("key", "secret")
    result = client._params_to_url_query({"coin": "BTC", "network": "TRC20", "limit": "10"})
    assert result == "coin=BTC&limit=10&network=TRC20"


def test_params_to_sign_str():
    client = BitunixClient("key", "secret")
    result = client._params_to_sign_str({"coin": "BTC", "network": "TRC20", "limit": "10"})
    assert result == "coinBTClimit10networkTRC20"


def test_auth_headers_fields():
    client = BitunixClient("mykey", "mysecret")
    headers = client._auth_headers()
    assert headers["api-key"] == "mykey"
    assert "nonce" in headers
    assert "timestamp" in headers
    assert "sign" in headers
    assert len(headers["nonce"]) == 32


def test_signing_determinism():
    client = BitunixClient("k", "s")
    sign1 = client._make_sign("testnonce", "1000", "", "")
    sign2 = client._make_sign("testnonce", "1000", "", "")
    assert sign1 == sign2


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
async def test_check_deposit_slightly_over(mocker):
    """Accept deposits slightly above expected (wallet rounding)."""
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": [{"status": "success", "amount": "5.033"}]}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is True


@pytest.mark.asyncio
async def test_check_deposit_way_over(mocker):
    """Reject deposits far above expected (different order)."""
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": [{"status": "success", "amount": "5.999"}]}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is False


@pytest.mark.asyncio
async def test_check_deposit_partial(mocker):
    """Reject partial payments (amount below expected)."""
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": [{"status": "success", "amount": "4.500"}]}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is False
