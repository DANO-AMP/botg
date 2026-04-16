import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    telegram_token: str
    admin_telegram_ids: list[int]
    log_chat_id: int | None
    maxelpay_api_key: str
    maxelpay_secret_key: str
    webhook_base_url: str
    webhook_port: int
    referral_bonus_usd: float
    order_timeout_minutes: int
    db_path: str

    @property
    def notification_targets(self) -> list[int]:
        """Admin IDs + log group (if configured)."""
        targets = list(self.admin_telegram_ids)
        if self.log_chat_id and self.log_chat_id not in targets:
            targets.append(self.log_chat_id)
        return targets


def load_config() -> Config:
    raw_log = os.getenv("LOG_CHAT_ID", "")
    return Config(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        admin_telegram_ids=[int(x.strip()) for x in os.environ["ADMIN_TELEGRAM_ID"].split(",")],
        log_chat_id=int(raw_log) if raw_log.strip() else None,
        maxelpay_api_key=os.environ["MAXELPAY_API_KEY"],
        maxelpay_secret_key=os.environ["MAXELPAY_SECRET_KEY"],
        webhook_base_url=os.environ["WEBHOOK_BASE_URL"],
        webhook_port=int(os.getenv("WEBHOOK_PORT", "8080")),
        referral_bonus_usd=float(os.getenv("REFERRAL_BONUS_USD", "10.0")),
        order_timeout_minutes=int(os.getenv("ORDER_TIMEOUT_MINUTES", "30")),
        db_path=os.getenv("DB_PATH", "data/shop.db"),
    )
