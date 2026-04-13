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


@pytest.mark.asyncio
async def test_category_crud(test_db):
    cat_id = await db.add_category("AI Services", "AI tools")
    cats = await db.get_active_categories()
    assert len(cats) == 1
    assert cats[0]["name"] == "AI Services"
    await db.toggle_category(cat_id)
    cats = await db.get_active_categories()
    assert len(cats) == 0
    await db.toggle_category(cat_id)
    cats = await db.get_active_categories()
    assert len(cats) == 1


@pytest.mark.asyncio
async def test_category_get(test_db):
    cat_id = await db.add_category("Cloud", "")
    cat = await db.get_category(cat_id)
    assert cat["id"] == cat_id
    assert cat["name"] == "Cloud"


@pytest.mark.asyncio
async def test_product_crud(test_db):
    cat_id = await db.add_category("AI", "")
    prod_id = await db.add_product(cat_id, "Gemini Pro", "desc", 5.0, "account")
    prod = await db.get_product(prod_id)
    assert prod["name"] == "Gemini Pro"
    assert prod["price_usd"] == 5.0
    assert prod["type"] == "account"
    await db.update_product_field(prod_id, "price_usd", 7.0)
    prod = await db.get_product(prod_id)
    assert prod["price_usd"] == 7.0


@pytest.mark.asyncio
async def test_product_toggle_and_filter(test_db):
    cat_id = await db.add_category("Cat", "")
    prod_id = await db.add_product(cat_id, "Prod", "", 3.0, "string")
    prods = await db.get_products_by_category(cat_id, active_only=True)
    assert len(prods) == 1
    await db.toggle_product(prod_id)
    prods = await db.get_products_by_category(cat_id, active_only=True)
    assert len(prods) == 0
    prods = await db.get_products_by_category(cat_id, active_only=False)
    assert len(prods) == 1


@pytest.mark.asyncio
async def test_stock_items(test_db):
    cat_id = await db.add_category("Keys", "")
    prod_id = await db.add_product(cat_id, "API Key", "", 3.0, "string")
    added = await db.add_stock_items(prod_id, ["key1", "key2", "key3"])
    assert added == 3
    counts = await db.get_stock_count(prod_id)
    assert counts["total"] == 3
    assert counts["available"] == 3
    await db.get_or_create_user(1, "u", None)
    item = await db.get_available_stock_item(prod_id)
    assert item is not None
    await db.mark_stock_sold(item["id"], 1)
    counts = await db.get_stock_count(prod_id)
    assert counts["available"] == 2
