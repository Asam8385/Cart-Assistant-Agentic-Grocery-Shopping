from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from .events import EventFactory, StreamEvent
from .models import (
    ExtractedRequest,
    ItemSearchResult,
    SearchBatchResult,
)
from .tools import AvailabilityTool, CatalogSearchTool


logger = logging.getLogger(__name__)


class ProductSearchAgent:
    """Deterministic tool loop; no LLM decides or hides tool calls."""

    def __init__(
        self,
        catalog_search: CatalogSearchTool,
        availability: AvailabilityTool,
    ) -> None:
        self._catalog_search = catalog_search
        self._availability = availability

    async def stream_search(
        self,
        extraction: ExtractedRequest,
        events: EventFactory,
    ) -> AsyncIterator[StreamEvent]:
        yield events.create(
            "product_search.started",
            stage="product_search",
            message="Searching extracted items one by one.",
            data={"item_count": len(extraction.items)},
        )

        results: list[ItemSearchResult] = []
        skipped_items = []

        for item in extraction.items:
            if item.status != "active":
                skipped_items.append(item)
                yield events.create(
                    "product_search.item_skipped",
                    stage="product_search",
                    item_id=item.item_id,
                    message=(
                        "Skipped crossed-out item."
                        if item.status == "crossed_out"
                        else "Skipped uncertain item pending clarification."
                    ),
                    data={"item": item.model_dump(mode="json")},
                )
                continue

            yield events.create(
                "product_search.item_started",
                stage="product_search",
                item_id=item.item_id,
                message=f"Searching for {item.name}.",
                data={"item": item.model_dump(mode="json")},
            )

            yield events.create(
                "tool.call.started",
                stage="product_search",
                item_id=item.item_id,
                tool_name="hybrid_catalog_search",
                message=f"Calling hybrid retrieval for {item.name}.",
                data={
                    "arguments": {
                        "query": item.search_query(),
                        "preferences": extraction.preferences.model_dump(
                            mode="json",
                            exclude_none=True,
                        ),
                    }
                },
            )

            try:
                candidates = await self._catalog_search.search(
                    item,
                    extraction.preferences,
                )
            except Exception:
                logger.exception(
                    "Hybrid retrieval failed for item_id=%s",
                    item.item_id,
                )
                error = "Hybrid catalogue retrieval failed."
                result = ItemSearchResult(
                    item=item,
                    query=item.search_query(),
                    error=error,
                )
                results.append(result)

                yield events.create(
                    "tool.call.failed",
                    stage="product_search",
                    item_id=item.item_id,
                    tool_name="hybrid_catalog_search",
                    message=error,
                )
                yield events.create(
                    "product_search.item_completed",
                    stage="product_search",
                    item_id=item.item_id,
                    message=f"Search failed for {item.name}.",
                    data={"result": result.model_dump(mode="json")},
                )
                continue

            yield events.create(
                "tool.call.completed",
                stage="product_search",
                item_id=item.item_id,
                tool_name="hybrid_catalog_search",
                message=(
                    f"Hybrid retrieval returned {len(candidates)} "
                    "candidate(s)."
                ),
                data={
                    "candidate_count": len(candidates),
                    "candidates": [
                        candidate.model_dump(mode="json", exclude_none=True)
                        for candidate in candidates
                    ],
                },
            )

            checked_candidates = []

            for candidate in candidates:
                yield events.create(
                    "tool.call.started",
                    stage="availability",
                    item_id=item.item_id,
                    tool_name="check_product_availability",
                    message=f"Checking live availability for {candidate.title}.",
                    data={
                        "arguments": {
                            "record_id": candidate.record_id,
                            "requested_quantity": item.quantity,
                        }
                    },
                )

                try:
                    availability = await self._availability.check(
                        candidate.record_id,
                        item.quantity,
                    )
                except Exception:
                    logger.exception(
                        "Availability check failed for record_id=%s",
                        candidate.record_id,
                    )
                    yield events.create(
                        "tool.call.failed",
                        stage="availability",
                        item_id=item.item_id,
                        tool_name="check_product_availability",
                        message=(
                            "The database availability check failed for "
                            f"{candidate.title}."
                        ),
                        data={"record_id": candidate.record_id},
                    )
                    continue

                checked_candidate = candidate.model_copy(
                    update={"availability": availability}
                )
                checked_candidates.append(checked_candidate)

                yield events.create(
                    "tool.call.completed",
                    stage="availability",
                    item_id=item.item_id,
                    tool_name="check_product_availability",
                    message=(
                        f"{candidate.title} is available."
                        if availability.is_available
                        else f"{candidate.title} is not currently available."
                    ),
                    data={
                        "candidate": checked_candidate.model_dump(
                            mode="json",
                            exclude_none=True,
                        )
                    },
                )

            result = ItemSearchResult(
                item=item,
                query=item.search_query(),
                candidates=checked_candidates,
            )
            results.append(result)

            yield events.create(
                "product_search.item_completed",
                stage="product_search",
                item_id=item.item_id,
                message=(
                    f"Finished searching and checking {item.name}."
                ),
                data={"result": result.model_dump(mode="json")},
            )

        batch = SearchBatchResult(
            items=results,
            skipped_items=skipped_items,
        )

        yield events.create(
            "product_search.completed",
            stage="product_search",
            message="All searchable items have been processed.",
            data={"search": batch.model_dump(mode="json")},
        )
