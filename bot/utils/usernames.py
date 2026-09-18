from __future__ import annotations

import re


class InvalidUsernameError(ValueError):
    """Raised when an X username does not match the official handle shape."""


_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def normalize_x_username(value: str) -> str:
    username = value.strip()
    if username.startswith("@"):
        username = username[1:]
    if not _USERNAME_RE.fullmatch(username):
        raise InvalidUsernameError(
            "X usernames must be 1-15 characters and contain only letters, numbers, or underscores."
        )
    return username

