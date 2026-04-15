import hashlib
import json
import random
import time
import uuid
import aiohttp

BASE_URL = "https://fapi.bitunix.com"

TICKER_SYMBOLS: dict[str, str | None] = {
    "USDT": None,   # stablecoin, 1:1 with USD
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}


class BitunixClient:
    def __init__(self, api_key: str, secret_key: str, deposit_addresses: dict[str, str] | None = None) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._deposit_addresses = deposit_addresses or {}
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(base_url=BASE_URL)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _params_to_url_query(self, params: dict) -> str:
        """Standard URL query string: key=value&key=value (sorted)."""
        return "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    def _params_to_sign_str(self, params: dict) -> str:
        """Bitunix signing format: keyvaluekey2value2 (sorted, no separators)."""
        return "".join(f"{k}{v}" for k, v in sorted(params.items()))

    def _make_sign(self, nonce: str, timestamp: str, query_sign: str, body_str: str) -> str:
        message = nonce + timestamp + self._api_key + query_sign + body_str
        digest = hashlib.sha256(message.encode()).hexdigest()
        return hashlib.sha256((digest + self._secret_key).encode()).hexdigest()

    def _auth_headers(self, query_sign: str = "", body_str: str = "") -> dict:
        nonce = uuid.uuid4().hex[:32]
        timestamp = str(int(time.time() * 1000))
        sign = self._make_sign(nonce, timestamp, query_sign, body_str)
        return {
            "api-key": self._api_key,
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": sign,
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        session = await self._get_session()
        url_query = self._params_to_url_query(params) if params else ""
        sign_query = self._params_to_sign_str(params) if params else ""
        headers = self._auth_headers(query_sign=sign_query)
        url = f"{path}?{url_query}" if url_query else path
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _post(self, path: str, body: dict | None = None) -> dict:
        session = await self._get_session()
        body_str = json.dumps(body, separators=(",", ":")) if body else ""
        headers = self._auth_headers(body_str=body_str)
        async with session.post(path, headers=headers, data=body_str) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_ticker_price(self, symbol: str) -> float:
        """Get current futures price for symbol (e.g. 'BTCUSDT')."""
        data = await self._get("/api/v1/futures/market/tickers", {"symbol": symbol})
        items = data.get("data") or []
        item = next((x for x in items if x["symbol"] == symbol), None)
        if not item:
            raise ValueError(f"Symbol {symbol} not found in tickers")
        return float(item["lastPrice"])

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

    def get_deposit_address(self, crypto: str) -> str:
        """Get pre-configured deposit address for given crypto."""
        addr = self._deposit_addresses.get(crypto)
        if not addr:
            raise ValueError(f"No deposit address configured for {crypto}")
        return addr

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
                amount_str = item.get("amount")
                if amount_str:
                    amount = float(amount_str)
                    if amount >= expected_amount - 1e-6 and amount < expected_amount + 0.05:
                        return True
        return False
