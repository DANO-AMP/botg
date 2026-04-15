import base64
import json
import logging
import time

import aiohttp
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

logger = logging.getLogger(__name__)

STAGING_URL = "https://api.maxelpay.com/v1/stg/merchant/order/checkout"
PRODUCTION_URL = "https://api.maxelpay.com/v1/prod/merchant/order/checkout"


class MaxelPayClient:
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        webhook_base_url: str,
        site_name: str = "TelegramShop",
        mode: str = "prod",
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._webhook_base_url = webhook_base_url.rstrip("/")
        self._site_name = site_name
        self._api_url = PRODUCTION_URL if mode == "prod" else STAGING_URL
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _encrypt(self, payload: dict) -> str:
        """Encrypt payload with AES-256-CBC, matching MaxelPay's PHP implementation."""
        key_bytes = self._secret_key.encode("utf-8")
        # PHP openssl_encrypt zero-pads key to 32 bytes if shorter, truncates if longer
        key = key_bytes.ljust(32, b"\0")[:32]
        iv = self._secret_key[:16].encode("utf-8")

        data = json.dumps(payload).encode("utf-8")
        padder = PKCS7(128).padder()
        padded = padder.update(data) + padder.finalize()

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()

        return base64.b64encode(encrypted).decode("utf-8")

    def _decrypt(self, encrypted_b64: str) -> dict:
        """Decrypt an AES-256-CBC encrypted payload from MaxelPay."""
        key_bytes = self._secret_key.encode("utf-8")
        key = key_bytes.ljust(32, b"\0")[:32]
        iv = self._secret_key[:16].encode("utf-8")

        encrypted = base64.b64decode(encrypted_b64)

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(encrypted) + decryptor.finalize()

        unpadder = PKCS7(128).unpadder()
        data = unpadder.update(padded) + unpadder.finalize()

        return json.loads(data.decode("utf-8"))

    async def create_checkout(
        self,
        order_id: str,
        amount: float,
        currency: str = "USD",
        user_name: str = "Customer",
        user_email: str = "",
    ) -> dict:
        """Create a MaxelPay checkout and return the payment URL.

        Returns dict with keys: payment_url, order_id
        """
        payload = {
            "orderID": order_id,
            "amount": f"{amount:.2f}",
            "currency": currency,
            "timestamp": int(time.time()),
            "userName": user_name,
            "siteName": self._site_name,
            "userEmail": user_email or "customer@shop.bot",
            "redirectUrl": f"{self._webhook_base_url}/payment/success",
            "websiteUrl": self._webhook_base_url,
            "cancelUrl": f"{self._webhook_base_url}/payment/cancel",
            "webhookUrl": f"{self._webhook_base_url}/webhook/maxelpay",
        }

        encrypted = self._encrypt(payload)
        session = await self._get_session()

        async with session.post(
            self._api_url,
            headers={
                "api-key": self._api_key,
                "Content-Type": "application/json",
            },
            json={"data": encrypted},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise ValueError(f"MaxelPay API error ({resp.status}): {body}")
            data = await resp.json()

        payment_url = data.get("result")
        if not payment_url:
            raise ValueError(f"MaxelPay returned no payment URL: {data}")

        return {
            "payment_url": payment_url,
            "order_id": order_id,
        }
