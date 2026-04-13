import secrets
import string

_UPPER = string.ascii_uppercase
_LOWER = string.ascii_lowercase
_DIGITS = string.digits
_SPECIAL = "!@#$%^&*"
_ALPHABET = _UPPER + _LOWER + _DIGITS + _SPECIAL


def generate_password(length: int = 12) -> str:
    while True:
        pwd = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (
            any(c in _UPPER for c in pwd)
            and any(c in _LOWER for c in pwd)
            and any(c in _DIGITS for c in pwd)
            and any(c in _SPECIAL for c in pwd)
        ):
            return pwd
