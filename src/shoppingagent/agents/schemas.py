from __future__ import annotations


from typing import Literal

from pydantic import BaseModel , ConfigDict , Field


class StrictModel(BaseModel):
   model_config = ConfigDict(
      extra="forbid",
      str_strip_whitespace=True,
      validate_assignment=True
   )

ImageItemStatus = Literal[
    "active",
    "crossed_out",
    "uncertain",
]



class ImageShoppingItem(StrictModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )
    raw_text: str | None = Field(
        default=None,
        max_length=300,
    )
    quantity: float | None = Field(
        default=None,
        gt=0,
        le=1000,
    )
    unit: str | None = Field(
        default=None,
        max_length=50,
    )
    status: ImageItemStatus = "active"
    confidence: float = Field(
        default=1.0,
        ge=0,
        le=1,
    )
    notes: str | None = Field(
        default=None,
        max_length=300,
    )


class ImageAnalysisResult(StrictModel):
    items: list[ImageShoppingItem] = Field(
        default_factory=list,
        max_length=50,
    )
    unreadable_fragments: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    warnings: list[str] = Field(
        default_factory=list,
        max_length=20,
    )



class ShoppingPreferences(StrictModel):
    vendor_key: str | None = Field(
        default=None,
        max_length=100,
    )
    category_slug: str | None = Field(
        default=None,
        max_length=100,
    )
    brand: str | None = Field(
        default=None,
        max_length=150,
    )
    country_of_origin: str | None = Field(
        default=None,
        max_length=100,
    )

    is_organic: bool | None = None
    is_vegan: bool | None = None
    is_vegetarian: bool | None = None
    is_gluten_free: bool | None = None
    is_halal: bool | None = None

    excluded_allergens: list[str] = Field(
        default_factory=list,
        max_length=30,
    )
    excluded_terms: list[str] = Field(
        default_factory=list,
        max_length=30,
    )


class ShoppingItem(StrictModel):
    item_id: str = Field(
        default="",
        max_length=50,
    )
    name: str = Field(
        min_length=1,
        max_length=200,
    )
    quantity: float = Field(
        default=1,
        gt=0,
        le=1000,
    )
    unit: str | None = Field(
        default=None,
        max_length=50,
    )
    preferred_brand: str | None = Field(
        default=None,
        max_length=150,
    )
    category_slug: str | None = Field(
        default=None,
        max_length=100,
    )
    notes: str | None = Field(
        default=None,
        max_length=300,
    )

    def build_search_query(self) -> str:
        parts = [self.name]

        if self.preferred_brand:
            parts.append(self.preferred_brand)

        if self.unit:
            parts.append(self.unit)

        return " ".join(parts)


class ShoppingRequest(StrictModel):
    original_text: str | None = Field(
        default=None,
        max_length=8000,
    )
    items: list[ShoppingItem] = Field(
        default_factory=list,
        max_length=30,
    )
    preferences: ShoppingPreferences = Field(
        default_factory=ShoppingPreferences,
    )
    clarification_questions: list[str] = Field(
        default_factory=list,
        max_length=10,
    )


class ProductCandidate(StrictModel):
    point_id: str
    record_id: str
    title: str

    score: float
    qdrant_score: float
    reranker_score: float | None = None

    vendor_key: str | None = None
    vendor_name: str | None = None
    vendor_product_id: str | None = None
    vendor_variant_id: str | None = None

    sku: str | None = None
    barcode: str | None = None
    brand: str | None = None
    category: str | None = None
    category_slug: str | None = None
    display_size: str | None = None
    country_of_origin: str | None = None

    is_organic: bool | None = None
    is_vegan: bool | None = None
    is_vegetarian: bool | None = None
    is_gluten_free: bool | None = None
    is_halal: bool | None = None

    match_reason: str | None = Field(
        default=None,
        max_length=500,
    )


class CatalogSearchResult(StrictModel):
    item_id: str
    query: str
    candidates: list[ProductCandidate] = Field(
        default_factory=list,
        max_length=10,
    )
    error: str | None = None


class MatchedShoppingItem(StrictModel):
    item_id: str
    requested_name: str
    requested_quantity: float
    requested_unit: str | None = None
    candidates: list[ProductCandidate] = Field(
        default_factory=list,
        max_length=10,
    )


class ShoppingResponse(StrictModel):
    summary: str = Field(
        min_length=1,
        max_length=2000,
    )
    matches: list[MatchedShoppingItem] = Field(
        default_factory=list,
        max_length=30,
    )
    unmatched_items: list[str] = Field(
        default_factory=list,
        max_length=30,
    )
    clarification_questions: list[str] = Field(
        default_factory=list,
        max_length=10,
    )
    warnings: list[str] = Field(
        default_factory=list,
        max_length=20,
    )


class ShoppingTurnResult(StrictModel):
    image_analysis: ImageAnalysisResult | None = None
    shopping_request: ShoppingRequest
    response: ShoppingResponse