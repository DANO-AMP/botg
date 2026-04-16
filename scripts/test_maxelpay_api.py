"""Diagnostic script — calls MaxelPay API with real credentials and prints full response.

Usage:
    python scripts/test_maxelpay_api.py

Requires .env with MAXELPAY_API_KEY and WEBHOOK_BASE_URL set.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import aiohttp


API_KEY = os.environ.get("MAXELPAY_API_KEY", "")
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "http://185.209.229.208:8080").rstrip("/")
API_URL = "https://api.maxelpay.com/api/v1/payments/sessions"


async def main():
    if not API_KEY:
        print("ERROR: MAXELPAY_API_KEY not set in .env")
        return

    payload = {
        "orderId": "test_diagnostic_001",
        "amount": 1.00,
        "currency": "USD",
        "description": "Diagnostic test order",
        "successUrl": f"{WEBHOOK_BASE_URL}/payment/success",
        "cancelUrl": f"{WEBHOOK_BASE_URL}/payment/cancel",
        "callbackUrl": f"{WEBHOOK_BASE_URL}/webhook/maxelpay",
    }

    print(f"Calling MaxelPay API: {API_URL}")
    print(f"Payload: {json.dumps(payload, indent=2)}\n")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            API_URL,
            headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
            json=payload,
        ) as resp:
            status = resp.status
            body = await resp.text()

    print(f"HTTP Status: {status}")
    print(f"Raw response: {body}\n")

    try:
        data = json.loads(body)
        print(f"Parsed response: {json.dumps(data, indent=2)}")
        print("\n--- Field analysis ---")
        for key, value in data.items():
            print(f"  {key!r}: {value!r}")
    except json.JSONDecodeError:
        print("Response is not JSON")


if __name__ == "__main__":
    asyncio.run(main())
