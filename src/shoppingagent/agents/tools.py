from __future__ import annotations

import asyncio
import math
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

from mysql.connector.pooling import MySQLConnectionPool

from shoppingagent.retrieval import (
    HybridProductRetriever,
    ProductFilters,
)

from .models import (
    AvailabilityResult,
    ExtractedItem,
    ExtractionPreferences,
    ProductCandidate,
    StoreOffer,
)


class CatalogSearchTool(Protocol):
    async def search(
        self,
        item: ExtractedItem,
        preferences: ExtractionPreferences,
    ) -> list[ProductCandidate]: ...


class AvailabilityTool(Protocol):
    async def check(
        self,
        record_id: str,
        requested_quantity: float,
    ) -> AvailabilityResult: ...


def _optional_string(value: object) -> str | None:
    if value is None:
        return None

    result = str(value).strip()
    return result or None


class HybridCatalogSearchTool:
    """Adapter over the already-loaded Qdrant hybrid retriever."""

    def __init__(
        self,
        retriever: HybridProductRetriever,
        *,
        mode: str = "hybrid",
        limit: int = 5,
        apply_reranker: bool = True,
    ) -> None:
        if mode not in {"hybrid", "dense", "sparse"}:
            raise ValueError("mode must be hybrid, dense or sparse.")

        if not 1 <= limit <= 10:
            raise ValueError("limit must be between 1 and 10.")

        self._retriever = retriever
        self._mode = mode
        self._limit = limit
        self._apply_reranker = apply_reranker

    async def search(
        self,
        item: ExtractedItem,
        preferences: ExtractionPreferences,
    ) -> list[ProductCandidate]:
        filters = ProductFilters(
            vendor_key=preferences.vendor_key,
            category_slug=(
                item.category_slug or preferences.category_slug
            ),
            brand=item.preferred_brand or preferences.brand,
            country_of_origin=preferences.country_of_origin,
            is_organic=preferences.is_organic,
            is_vegan=preferences.is_vegan,
            is_vegetarian=preferences.is_vegetarian,
            is_gluten_free=preferences.is_gluten_free,
            is_halal=preferences.is_halal,
        )

        hits = await asyncio.to_thread(
            self._retriever.search,
            item.search_query(),
            mode=self._mode,
            limit=self._limit,
            filters=filters,
            apply_reranker=self._apply_reranker,
        )

        candidates: list[ProductCandidate] = []

        for hit in hits:
            payload = dict(hit.payload or {})

            candidates.append(
                ProductCandidate(
                    point_id=str(hit.point_id),
                    record_id=str(hit.record_id),
                    title=str(hit.title),
                    score=float(hit.score),
                    qdrant_score=float(hit.qdrant_score),
                    reranker_score=(
                        float(hit.reranker_score)
                        if hit.reranker_score is not None
                        else None
                    ),
                    vendor_key=_optional_string(
                        payload.get("vendor_key")
                    ),
                    vendor_name=_optional_string(
                        payload.get("vendor_name")
                    ),
                    vendor_product_id=_optional_string(
                        payload.get("vendor_product_id")
                    ),
                    vendor_variant_id=_optional_string(
                        payload.get("vendor_variant_id")
                    ),
                    sku=_optional_string(payload.get("sku")),
                    barcode=_optional_string(payload.get("barcode")),
                    brand=_optional_string(payload.get("brand")),
                    category=_optional_string(payload.get("category")),
                    category_slug=_optional_string(
                        payload.get("category_slug")
                    ),
                    display_size=_optional_string(
                        payload.get("display_size")
                    ),
                    is_organic=payload.get("is_organic"),
                    is_vegan=payload.get("is_vegan"),
                    is_vegetarian=payload.get("is_vegetarian"),
                    is_gluten_free=payload.get("is_gluten_free"),
                    is_halal=payload.get("is_halal"),
                )
            )

        return candidates


class MySQLAvailabilityTool:
    """Checks live product/store availability using vector_record_id."""

    _QUERY = """
        SELECT
            pv.vector_record_id,
            pv.active AS variant_active,
            pv.deleted_at AS variant_deleted_at,
            p.active AS product_active,
            p.deleted_at AS product_deleted_at,
            v.active AS vendor_active,
            so.store_id,
            s.store_key,
            s.name AS store_name,
            s.active AS store_active,
            so.price,
            so.compare_at_price,
            so.currency,
            so.stock_quantity,
            so.is_available AS offer_available,
            so.min_order_quantity,
            so.max_order_quantity,
            so.aisle_location,
            so.last_checked_at
        FROM product_variants AS pv
        INNER JOIN products AS p
            ON p.id = pv.product_id
        INNER JOIN vendors AS v
            ON v.id = p.vendor_id
        LEFT JOIN store_offers AS so
            ON so.variant_id = pv.id
        LEFT JOIN stores AS s
            ON s.id = so.store_id
        WHERE pv.vector_record_id = %s
        ORDER BY
            so.is_available DESC,
            so.price ASC,
            so.store_id ASC
    """

    def __init__(self, pool: MySQLConnectionPool) -> None:
        self._pool = pool

    @classmethod
    def from_environment(cls) -> "MySQLAvailabilityTool":
        password = os.getenv("MYSQL_PASSWORD")

        if password is None:
            raise RuntimeError("MYSQL_PASSWORD is required.")

        pool = MySQLConnectionPool(
            pool_name=f"shopping_agent_{uuid4().hex[:10]}",
            pool_size=int(os.getenv("MYSQL_POOL_SIZE", "5")),
            pool_reset_session=True,
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "root"),
            password=password,
            database=os.getenv("MYSQL_DATABASE", "shopping_agent"),
            charset="utf8mb4",
            autocommit=True,
        )

        return cls(pool)

    async def check(
        self,
        record_id: str,
        requested_quantity: float,
    ) -> AvailabilityResult:
        return await asyncio.to_thread(
            self._check_sync,
            record_id,
            requested_quantity,
        )

    def _check_sync(
        self,
        record_id: str,
        requested_quantity: float,
    ) -> AvailabilityResult:
        connection = self._pool.get_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(self._QUERY, (record_id,))
            rows: list[dict[str, Any]] = cursor.fetchall()
        finally:
            cursor.close()
            connection.close()

        if not rows:
            return AvailabilityResult(
                record_id=record_id,
                exists_in_database=False,
                product_active=False,
                requested_quantity=requested_quantity,
                is_available=False,
            )

        first = rows[0]
        product_active = bool(
            first["variant_active"]
            and first["variant_deleted_at"] is None
            and first["product_active"]
            and first["product_deleted_at"] is None
            and first["vendor_active"]
        )

        required_units = max(1, math.ceil(requested_quantity))
        offers: list[StoreOffer] = []
        total_stock = 0

        for row in rows:
            if row.get("store_id") is None:
                continue

            stock_quantity = int(row["stock_quantity"] or 0)
            total_stock += stock_quantity

            can_fulfill = bool(
                product_active
                and row.get("store_active")
                and row.get("offer_available")
                and stock_quantity >= required_units
                and int(row["min_order_quantity"]) <= required_units
                and int(row["max_order_quantity"]) >= required_units
            )

            offers.append(
                StoreOffer(
                    store_id=int(row["store_id"]),
                    store_key=str(row["store_key"]),
                    store_name=str(row["store_name"]),
                    price=_decimal_string(row["price"]),
                    compare_at_price=(
                        _decimal_string(row["compare_at_price"])
                        if row.get("compare_at_price") is not None
                        else None
                    ),
                    currency=str(row["currency"]),
                    stock_quantity=stock_quantity,
                    min_order_quantity=int(row["min_order_quantity"]),
                    max_order_quantity=int(row["max_order_quantity"]),
                    aisle_location=_optional_string(
                        row.get("aisle_location")
                    ),
                    last_checked_at=_datetime_string(
                        row.get("last_checked_at")
                    ),
                    can_fulfill=can_fulfill,
                )
            )

        offers.sort(
            key=lambda offer: (
                not offer.can_fulfill,
                Decimal(offer.price),
            )
        )

        return AvailabilityResult(
            record_id=record_id,
            exists_in_database=True,
            product_active=product_active,
            requested_quantity=requested_quantity,
            is_available=any(offer.can_fulfill for offer in offers),
            total_stock=total_stock,
            offers=offers,
        )


def _decimal_string(value: object) -> str:
    return format(Decimal(str(value)), "f")


def _datetime_string(value: object) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)
