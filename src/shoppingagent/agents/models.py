from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


ItemStatus = Literal[
    "active",
    "crossed_out",
    "uncertain",
]


class ExtractedItem(StrictModel):
    item_id: str = ""
    name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0, le=1000)
    unit: str | None = Field(default=None, max_length=40)
    preferred_brand: str | None = Field(default=None, max_length=120)
    category_slug: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=300)
    status: ItemStatus = "active"
    confidence: float = Field(default=1, ge=0, le=1)

    def search_query(self) -> str:
        parts = [self.name]

        if self.preferred_brand:
            parts.append(self.preferred_brand)

        if self.unit:
            parts.append(self.unit)

        return " ".join(parts)


class ExtractionPreferences(StrictModel):
    vendor_key: str | None = Field(default=None, max_length=120)
    brand: str | None = Field(default=None, max_length=120)
    category_slug: str | None = Field(default=None, max_length=120)
    country_of_origin: str | None = Field(default=None, max_length=80)
    is_organic: bool | None = None
    is_vegan: bool | None = None
    is_vegetarian: bool | None = None
    is_gluten_free: bool | None = None
    is_halal: bool | None = None
    excluded_allergens: list[str] = Field(
        default_factory=list,
        max_length=30,
    )


class ExtractedRequest(StrictModel):
    items: list[ExtractedItem] = Field(
        default_factory=list,
        max_length=50,
    )
    preferences: ExtractionPreferences = Field(
        default_factory=ExtractionPreferences,
    )
    clarification_questions: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    unreadable_fragments: list[str] = Field(
        default_factory=list,
        max_length=20,
    )


class StoreOffer(StrictModel):
    store_id: int
    store_key: str
    store_name: str
    price: str
    compare_at_price: str | None = None
    currency: str
    stock_quantity: int
    min_order_quantity: int
    max_order_quantity: int
    aisle_location: str | None = None
    last_checked_at: str | None = None
    can_fulfill: bool


class AvailabilityResult(StrictModel):
    record_id: str
    exists_in_database: bool
    product_active: bool
    requested_quantity: float
    is_available: bool
    total_stock: int = 0
    offers: list[StoreOffer] = Field(default_factory=list)


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
    is_organic: bool | None = None
    is_vegan: bool | None = None
    is_vegetarian: bool | None = None
    is_gluten_free: bool | None = None
    is_halal: bool | None = None
    availability: AvailabilityResult | None = None


class ItemSearchResult(StrictModel):
    item: ExtractedItem
    query: str
    candidates: list[ProductCandidate] = Field(default_factory=list)
    error: str | None = None

    @property
    def available_candidates(self) -> list[ProductCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.availability is not None
            and candidate.availability.is_available
        ]


class SearchBatchResult(StrictModel):
    items: list[ItemSearchResult] = Field(default_factory=list)
    skipped_items: list[ExtractedItem] = Field(default_factory=list)


class PipelineResult(StrictModel):
    extraction: ExtractedRequest
    search: SearchBatchResult
    message: str


@dataclass(frozen=True, slots=True)
class PipelineInput:
    user_text: str | None = None
    image_bytes: bytes | None = None
    image_media_type: str | None = None
    request_id: str | None = None

    def validate(self) -> None:
        if not (self.user_text or "").strip() and not self.image_bytes:
            raise ValueError("Text or an image is required.")

        if self.image_bytes and not self.image_media_type:
            raise ValueError(
                "image_media_type is required when image_bytes is provided."
            )
