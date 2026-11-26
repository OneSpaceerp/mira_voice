"""Encryption of secrets Mira must be able to read back (carrier passwords): Fernet
(AES-128-CBC + HMAC-SHA256) with MIRA_DATA_KEY from /opt/mira/.env. Passwords Mira only has
to check (staff logins, SIP extensions) are hashed instead, never encrypted.

MultiFernet: MIRA_DATA_KEY may hold several comma-separated keys, newest first, so keys can be
rotated without losing old data (re-encrypt with `rotate`)."""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from mira_core.config import get_settings

__all__ = ["InvalidToken", "decrypt", "encrypt", "rotate"]


@lru_cache
def _fernet() -> MultiFernet:
    raw = get_settings().data_key.get_secret_value()
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("MIRA_DATA_KEY is not set (install.sh generates it)")
    return MultiFernet([Fernet(k) for k in keys])


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Raises InvalidToken if the data was altered or the key is wrong."""
    return _fernet().decrypt(token).decode()


def rotate(token: str) -> str:
    """Re-encrypt with the newest key."""
    return _fernet().rotate(token).decode()
