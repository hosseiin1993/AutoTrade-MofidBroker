"""Small coercions for broker payloads."""

from __future__ import annotations


def as_int(value: object) -> int | None:
    """Whole number from the broker, or None when the field is missing or not numeric."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
    return None
