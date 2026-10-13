"""The sending passwords at rest (DL-0202, DL-0372, DL-0384): authenticated encryption under a key
the environment supplies, with the previous key beside it while one is rotated. The keys are read
where a password is encrypted or decrypted, so a process that does neither needs none."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, MultiFernet

from syngraphe.config import ConfigurationError, _Reader


def keys() -> tuple[str, ...]:
    """The current key and, when set, the previous one; `ConfigurationError` naming the current
    key when it is absent."""
    reader = _Reader(dict(os.environ))
    current = reader.string("MAIL_PASSWORD_KEY")
    previous = reader.string("MAIL_PASSWORD_KEY_PREVIOUS", "")
    for name, value in (("MAIL_PASSWORD_KEY", current), ("MAIL_PASSWORD_KEY_PREVIOUS", previous)):
        if value and not _is_key(value):
            # Named, never quoted: the message carries no part of the value.
            reader.malformed.append(name)
    if reader.missing or reader.malformed:
        raise ConfigurationError(reader.missing, reader.malformed)
    return (current, previous) if previous else (current,)


def _is_key(value: str) -> bool:
    try:
        Fernet(value.encode("ascii"))
    except (ValueError, UnicodeError):
        return False
    return True


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(key.encode("ascii")) for key in keys()])


def encrypt(password: str) -> bytes:
    """`password` as a token under the current key."""
    return _fernet().encrypt(password.encode("utf-8"))


def decrypt(blob: bytes) -> str:
    """The password a token holds, under the current key or the previous one;
    `cryptography.fernet.InvalidToken` when neither opens it."""
    return _fernet().decrypt(blob).decode("utf-8")


def rotated(blob: bytes) -> bytes:
    """`blob` re-encrypted under the current key, whichever key opens it now."""
    return _fernet().rotate(blob)
