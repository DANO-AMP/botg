import aiohttp
import logging

logger = logging.getLogger(__name__)

API_URL = "https://pay.crypt.bot/api"


class CryptoPayClient:
    def __init__(self, token: str) -> None:
        self._token = token
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Crypto-Pay-API-Token": self._token},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _api_call(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated API call. Returns the 'result' field."""
        session = await self._get_session()
        async with getattr(session, method)(f"{API_URL}{path}", **kwargs) as resp:
            resp.raise_for_status()
            data = await resp.json()
        if not data.get("ok"):
            error = data.get("error", {})
            raise ValueError(
                f"CryptoPay API error: {error.get('name', 'unknown')}: {error.get('message', '')}"
            )
        return data["result"]

    async def create_invoice(
        self, amount_usd: float, description: str = "",
        expires_in: int = 1800, payload: str = "",
    ) -> dict:
        """Create a payment invoice. Returns dict with invoice_id, pay_url, status."""
        body: dict = {
            "currency_type": "fiat",
            "fiat": "USD",
            "amount": f"{amount_usd:.2f}",
            "accepted_assets": "USDT,BTC,ETH,TON,LTC,BNB,TRX,USDC",
        }
        if description:
            body["description"] = description[:1024]
        if expires_in:
            body["expires_in"] = expires_in
        if payload:
            body["payload"] = payload[:4096]
        result = await self._api_call("post", "/createInvoice", json=body)
        return {
            "invoice_id": result["invoice_id"],
            "pay_url": result["bot_invoice_url"],
            "status": result["status"],
        }

    async def get_invoice_status(self, invoice_id: int) -> str:
        """Check invoice status. Returns 'active', 'paid', or 'expired'."""
        result = await self._api_call(
            "get", "/getInvoices", params={"invoice_ids": str(invoice_id)},
        )
        # API returns result as a direct array of Invoice objects
        items = result if isinstance(result, list) else result.get("items", [])
        if not items:
            return "expired"
        return items[0]["status"]

    async def delete_invoice(self, invoice_id: int) -> bool:
        """Delete an unpaid invoice. Returns True on success."""
        try:
            await self._api_call(
                "post", "/deleteInvoice", json={"invoice_id": invoice_id},
            )
            return True
        except Exception:
            return False
