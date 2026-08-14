from __future__ import annotations

import re
import unicodedata

WHITESPACE_PATTERN = re.compile(r"\s+")
CONTROL_CHARACTER_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)


def normalize_query(
      query: str,
      *,
      maximum_length: int = 500
):
    """
    Perform conservative query normalization.

    Important:
    - Preserves product identifiers, barcodes and hyphens.
    - Converts OCR line breaks into spaces.
    - Does not remove multilingual characters.
    """

    if not isinstance(query , str):
        raise TypeError("Search query must be a string.")

    query = unicodedata.normalize("NFKC", query)
    query = CONTROL_CHARACTER_PATTERN.sub(" ", query)
    query = WHITESPACE_PATTERN.sub(" ", query).strip()

    if len(query) > maximum_length:
        raise ValueError(
            f"Search query cannot exceed {maximum_length} characters."
        )

    if not any(character.isalnum() for character in query):
        raise ValueError(
            "Search query must contain at least one letter or number."
        )

    return query