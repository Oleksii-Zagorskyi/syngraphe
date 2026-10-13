"""The sending password's key (DL-0372, DL-0384): read from the environment where a password is
encrypted or decrypted, never by the configuration every process loads at start; rotated by
keeping the previous key beside the current one.

Keys are generated for each test; the passwords are synthetic examples.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet, InvalidToken

pytestmark = [pytest.mark.fast]

PASSWORD = "synthetic-sending-password"


def test_rotation_reads_the_previous_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from mail import secrets

    key_a = Fernet.generate_key().decode()
    key_b = Fernet.generate_key().decode()
    monkeypatch.setenv("MAIL_PASSWORD_KEY", key_a)
    monkeypatch.delenv("MAIL_PASSWORD_KEY_PREVIOUS", raising=False)
    blob = secrets.encrypt(PASSWORD)
    assert isinstance(blob, bytes)
    assert PASSWORD.encode() not in blob

    monkeypatch.setenv("MAIL_PASSWORD_KEY", key_b)
    monkeypatch.setenv("MAIL_PASSWORD_KEY_PREVIOUS", key_a)
    assert secrets.keys() == (key_b, key_a)
    assert secrets.decrypt(blob) == PASSWORD
    # What is encrypted now is under the current key.
    assert Fernet(key_b.encode()).decrypt(secrets.encrypt(PASSWORD)).decode() == PASSWORD

    monkeypatch.delenv("MAIL_PASSWORD_KEY_PREVIOUS")
    assert secrets.keys() == (key_b,)
    with pytest.raises(InvalidToken):
        secrets.decrypt(blob)

    # An unfilled placeholder is no key.
    monkeypatch.setenv("MAIL_PASSWORD_KEY_PREVIOUS", "???")
    assert secrets.keys() == (key_b,)
    with pytest.raises(InvalidToken):
        secrets.decrypt(blob)


@pytest.mark.parametrize("absent", [None, "", "???"])
def test_the_key_is_read_where_it_is_used(
    monkeypatch: pytest.MonkeyPatch, absent: str | None
) -> None:
    from mail import secrets
    from syngraphe import config
    from syngraphe.config import ConfigurationError

    for name in ("MAIL_PASSWORD_KEY", "MAIL_PASSWORD_KEY_PREVIOUS"):
        monkeypatch.delenv(name, raising=False)
    if absent is not None:
        monkeypatch.setenv("MAIL_PASSWORD_KEY", absent)

    # The configuration every process loads at start neither reads nor needs it. The environment
    # is passed as it stands, so `.env` cannot put the key back.
    config.load(dict(os.environ))

    with pytest.raises(ConfigurationError) as refused:
        secrets.encrypt(PASSWORD)
    assert "MAIL_PASSWORD_KEY" in refused.value.missing
    assert "MAIL_PASSWORD_KEY" in str(refused.value)
    with pytest.raises(ConfigurationError):
        secrets.keys()


@pytest.mark.parametrize("name", ["MAIL_PASSWORD_KEY", "MAIL_PASSWORD_KEY_PREVIOUS"])
def test_a_malformed_key_is_named_and_never_quoted(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    from mail import secrets
    from syngraphe.config import ConfigurationError

    monkeypatch.setenv("MAIL_PASSWORD_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv(name, "not-a-key-ключ")
    with pytest.raises(ConfigurationError) as refused:
        secrets.keys()
    assert name in refused.value.malformed
    assert "ключ" not in str(refused.value)
