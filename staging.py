from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import models


@dataclass(frozen=True, slots=True)
class ProductFilters:
    vendor_key: str | None = None
    category_slug: str | None = None
    brand: str | None = None
    product_type: str | None = None
    country_of_origin: str | None = None

    is_organic: bool | None = None
    is_vegan: bool | None = None
    is_vegetarian: bool | None = None
    is_gluten_free: bool | None = None
    is_halal: bool | None = None


def clean_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return value or None


def build_qdrant_filter(
    filters: ProductFilters | None,
) -> models.Filter | None:
    if filters is None:
        return None

    must: list[models.Condition] = []

    text_fields = {
        "vendor_key": filters.vendor_key,
        "category_slug": filters.category_slug,
        "brand": filters.brand,
        "product_type": filters.product_type,
        "country_of_origin": filters.country_of_origin,
    }

    for field_name, raw_value in text_fields.items():
        value = clean_optional_text(raw_value)

        if value is None:
            continue

        must.append(
            models.FieldCondition(
                key=field_name,
                match=models.MatchValue(value=value),
            )
        )

    boolean_fields = {
        "is_organic": filters.is_organic,
        "is_vegan": filters.is_vegan,
        "is_vegetarian": filters.is_vegetarian,
        "is_gluten_free": filters.is_gluten_free,
        "is_halal": filters.is_halal,
    }

    for field_name, value in boolean_fields.items():
        if value is None:
            continue

        must.append(
            models.FieldCondition(
                key=field_name,
                match=models.MatchValue(value=value),
            )
        )

    if not must:
        return None

    return models.Filter(must=must)