import pytest
import pytest_asyncio
from bot import db


@pytest_asyncio.fixture
async def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    await db.connect(db_path)
    yield
    await db.close()


@pytest.mark.asyncio
async def test_get_or_create_user_new(test_db):
    user = await db.get_or_create_user(123, "alice", None)
    assert user["id"] == 123
    assert user["username"] == "alice"
    assert user["balance"] == 0.0


@pytest.mark.asyncio
async def test_get_or_create_user_idempotent(test_db):
    await db.get_or_create_user(123, "alice", None)
    user = await db.get_or_create_user(123, "alice_updated", None)
    assert user["id"] == 123


@pytest.mark.asyncio
async def test_update_user_balance(test_db):
    await db.get_or_create_user(123, "alice", None)
    await db.update_user_balance(123, 10.0)
    user = await db.get_user(123)
    assert user["balance"] == 10.0


@pytest.mark.asyncio
async def test_referral_bonus_only_once(test_db):
    await db.get_or_create_user(100, "referrer", None)
    await db.get_or_create_user(200, "referred", 100)
    await db.add_referral(100, 200)
    applied = await db.apply_referral_bonus_if_first_purchase(200, 10.0)
    assert applied is True
    applied_again = await db.apply_referral_bonus_if_first_purchase(200, 10.0)
    assert applied_again is False


@pytest.mark.asyncio
async def test_referral_bonus_credits_both(test_db):
    await db.get_or_create_user(100, "referrer", None)
    await db.get_or_create_user(200, "referred", 100)
    await db.add_referral(100, 200)
    await db.apply_referral_bonus_if_first_purchase(200, 10.0)
    referrer = await db.get_user(100)
    referred = await db.get_user(200)
    assert referrer["balance"] == 10.0
    assert referred["balance"] == 10.0


@pytest.mark.asyncio
async def test_get_referral_stats(test_db):
    await db.get_or_create_user(100, "referrer", None)
    await db.get_or_create_user(200, "ref1", 100)
    await db.get_or_create_user(300, "ref2", 100)
    await db.add_referral(100, 200)
    await db.add_referral(100, 300)
    await db.apply_referral_bonus_if_first_purchase(200, 10.0)
    stats = await db.get_referral_stats(100)
    assert stats["count"] == 2
    assert stats["total_earned"] == 10.0
