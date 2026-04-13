from bot.services.password import generate_password


def test_length():
    assert len(generate_password(12)) == 12
    assert len(generate_password(16)) == 16


def test_complexity():
    pwd = generate_password(12)
    assert any(c.isupper() for c in pwd)
    assert any(c.islower() for c in pwd)
    assert any(c.isdigit() for c in pwd)
    assert any(c in "!@#$%^&*" for c in pwd)


def test_unique():
    passwords = {generate_password() for _ in range(100)}
    assert len(passwords) == 100
