import pytest

from bot.utils.usernames import InvalidUsernameError, normalize_x_username


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("openai", "openai"),
        ("@OpenAI", "OpenAI"),
        ("  @x_dev  ", "x_dev"),
        ("A_15_char_name", "A_15_char_name"),
    ],
)
def test_normalize_x_username_accepts_valid_x_handles(raw: str, expected: str) -> None:
    assert normalize_x_username(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "@", "has-hyphen", "has space", "sixteen_characters", "../secret", "name!"],
)
def test_normalize_x_username_rejects_invalid_x_handles(raw: str) -> None:
    with pytest.raises(InvalidUsernameError):
        normalize_x_username(raw)

