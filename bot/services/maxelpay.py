import hashlib
import hmac
import logging

import aiohttp

logger = logging.getLogger(__name__)

API_BASE = "https://api.maxelpay.com/api/v1"


class MaxelPayClient:
    def __init__(self, api_key: str, secret_key: str, webhook_base_url: str) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._webhook_base_url = webhook_base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _headers(self) -> dict:
        return {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }

    async def create_checkout(
        self,
        order_id: str,
        amount: float,
        currency: str = "USD",
        description: str = "",
        user_email: str = "",
    ) -> dict:
        """Create a MaxelPay payment session and return the checkout URL.

        Returns dict with keys: payment_url, session_id, order_id
        """
        payload = {
            "orderId": order_id,
            "amount": amount,
            "currency": currency,
            "description": description or f"Order {order_id}",
            "successUrl": f"{self._webhook_base_url}/payment/success",
            "cancelUrl": f"{self._webhook_base_url}/payment/cancel",
            "callbackUrl": f"{self._webhook_base_url}/webhook/maxelpay",
        }
        if user_email:
            payload["customerEmail"] = user_email

        session = await self._get_session()
        async with session.post(
            f"{API_BASE}/payments/sessions",
            headers=self._headers(),
            json=payload,
        ) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise ValueError(f"MaxelPay API error ({resp.status}): {body}")
            response = await resp.json()

        # Response format: {"success": true, "data": {"paymentUrl": "...", "sessionId": "...", ...}}
        data = response.get("data", response)
        payment_url = data.get("paymentUrl") or data.get("checkoutUrl") or data.get("url")
        if not payment_url:
            raise ValueError(f"MaxelPay returned no payment URL: {response}")

        session_id = data.get("sessionId") or data.get("id") or ""

        return {
            "payment_url": payment_url,
            "session_id": session_id,
            "order_id": order_id,
        }

    async def get_session_status(self, session_id: str) -> dict:
        """Retrieve the current status of a payment session."""
        session = await self._get_session()
        async with session.get(
            f"{API_BASE}/payments/sessions/{session_id}/status",
            headers=self._headers(),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise ValueError(f"MaxelPay API error ({resp.status}): {body}")
            return await resp.json()

    def verify_webhook_signature(self, payload_bytes: bytes, signature: str) -> bool:
        """Verify the X-MaxelPay-Signature header using HMAC-SHA256."""
        expected = hmac.new(
            self._secret_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        try:
            return hmac.compare_digest(signature, expected)
        except Exception:
            return False
