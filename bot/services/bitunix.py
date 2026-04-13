import hashlib
import json
import random
import time
import uuid
import aiohttp

BASE_URL = "https://api.bitunix.com"

CRYPTO_NETWORKS: dict[str, str] = {
    "USDT": "TRC20",
    "BTC": "BTC",
    "ETH": "ERC20",
}

TICKER_SYMBOLS: dict[str, str | None] = {
    "USDT": None,   # stablecoin, 1:1 with USD
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}


class BitunixClient:
    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(base_url=BASE_URL)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _sort_params(self, params: dict) -> str:
        return "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    def _make_headers_with_values(
        self, nonce: str, timestamp: str, query_str: str, body_str: str
    ) -> dict:
        message = nonce + timestamp + self._api_key + query_str + body_str
        digest = hashlib.sha256(message.encode()).hexdigest()
        sign = hashlib.sha256((digest + self._secret_key).encode()).hexdigest()
        return {
            "api-key": self._api_key,
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": sign,
            "Content-Type": "application/json",
        }

    def _make_headers(self, query_str: str = "", body_str: str = "") -> dict:
        nonce = uuid.uuid4().hex[:32]
        timestamp = str(int(time.time() * 1000))
        return self._make_headers_with_values(nonce, timestamp, query_str, body_str)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        session = await self._get_session()
        query_str = self._sort_params(params) if params else ""
        headers = self._make_headers(query_str=query_str)
        url = f"{path}?{query_str}" if query_str else path
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

    async def _post(self, path: str, body: dict | None = None) -> dict:
        session = await self._get_session()
        body = body or {}
        body_str = json.dumps(body, separators=(",", ":"))
        headers = self._make_headers(body_str=body_str)
        async with session.post(path, headers=headers, data=body_str) as resp:
            return await resp.json()

    async def get_ticker_price(self, symbol: str) -> float:
        """Get current price for symbol (e.g. 'BTCUSDT')."""
        data = await self._get("/api/spot/v1/market/ticker", {"symbol": symbol})
        return float(data["data"]["close"])

    async def get_deposit_address(self, crypto: str) -> str:
        """Get deposit address for given crypto."""
        network = CRYPTO_NETWORKS.get(crypto, crypto)
        data = await self._get(
            "/api/spot/v1/deposit/address", {"coin": crypto, "network": network}
        )
        return data["data"]["address"]

    async def get_crypto_amount(self, usd_amount: float, crypto: str) -> float:
        """Convert USD to crypto amount with small unique increment for order identification."""
        symbol = TICKER_SYMBOLS.get(crypto)
        if symbol is None:
            base = usd_amount
        else:
            price = await self.get_ticker_price(symbol)
            base = usd_amount / price
        increment = random.uniform(0.001, 0.009)
        return round(base + increment, 8)

    async def check_deposit(self, coin: str, expected_amount: float, since_ms: int) -> bool:
        """Returns True if a successful deposit of expected_amount arrived since since_ms."""
        data = await self._post("/api/spot/v1/deposit/page", {
            "coin": coin,
            "type": "deposit",
            "startTime": since_ms,
            "limit": 100,
        })
        for item in (data.get("data") or {}).get("resultList", []):
            if item.get("status") == "success":
                if abs(float(item["amount"]) - expected_amount) < 0.0001:
                    return True
        return False
