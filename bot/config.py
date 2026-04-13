import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    telegram_token: str
    bitunix_api_key: str
    bitunix_secret_key: str
    admin_telegram_id: int
    referral_bonus_usd: float
    order_timeout_minutes: int
    payment_check_interval: int
    db_path: str


def load_config() -> Config:
    return Config(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        bitunix_api_key=os.environ["BITUNIX_API_KEY"],
        bitunix_secret_key=os.environ["BITUNIX_SECRET_KEY"],
        admin_telegram_id=int(os.environ["ADMIN_TELEGRAM_ID"]),
        referral_bonus_usd=float(os.getenv("REFERRAL_BONUS_USD", "10.0")),
        order_timeout_minutes=int(os.getenv("ORDER_TIMEOUT_MINUTES", "30")),
        payment_check_interval=int(os.getenv("PAYMENT_CHECK_INTERVAL_SECONDS", "30")),
        db_path=os.getenv("DB_PATH", "data/shop.db"),
    )
