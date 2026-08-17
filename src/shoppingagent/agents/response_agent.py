from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from agent_framework import Agent, BaseChatClient

from .events import EventFactory, StreamEvent
from .models import ExtractedRequest, SearchBatchResult
from .prompts import RESPONSE_AGENT_PROMPT


class ResponseAgent:
    """Receives grounded tool output and streams only the final wording."""

    def __init__(
        self,
        client: BaseChatClient[Any],
    ) -> None:
        self._agent = Agent(
            client=client,
            name="shopping-response-agent",
            description=(
                "Formats database-confirmed product results for the user."
            ),
            instructions=RESPONSE_AGENT_PROMPT,
            default_options={"max_tokens": 1000},
        )

    async def stream_response(
        self,
        extraction: ExtractedRequest,
        search: SearchBatchResult,
        events: EventFactory,
    ) -> AsyncIterator[StreamEvent]:
        yield events.create(
            "response.started",
            stage="response",
            message="Preparing the grounded response.",
        )

        context = self._build_context(extraction, search)
        prompt = (
            "Create the final response from this trusted pipeline result.\n"
            "<grounded_result>\n"
            f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}\n"
            "</grounded_result>"
        )

        response_stream = cast(
            Any,
            self._agent.run(
                prompt,
                stream=True,
                options={"max_tokens": 1000},
            ),
        )
        streamed_parts: list[str] = []

        async for update in response_stream:
            delta = update.text

            if not delta:
                continue

            streamed_parts.append(delta)
            yield events.create(
                "response.delta",
                stage="response",
                message="Streaming the final response.",
                data={"delta": delta},
            )

        final_response = await response_stream.get_final_response()
        message = final_response.text.strip() or "".join(streamed_parts).strip()

        if not message:
            message = self._fallback_message(search)

        yield events.create(
            "response.completed",
            stage="response",
            message="The final response is ready.",
            data={"message": message},
        )

    @staticmethod
    def _build_context(
        extraction: ExtractedRequest,
        search: SearchBatchResult,
    ) -> dict[str, Any]:
        item_contexts: list[dict[str, Any]] = []

        for result in search.items:
            available = []

            for candidate in result.available_candidates[:3]:
                availability = candidate.availability

                if availability is None:
                    continue

                offers = [
                    offer.model_dump(mode="json")
                    for offer in availability.offers
                    if offer.can_fulfill
                ][:2]

                available.append(
                    {
                        "point_id": candidate.point_id,
                        "record_id": candidate.record_id,
                        "title": candidate.title,
                        "vendor_name": candidate.vendor_name,
                        "brand": candidate.brand,
                        "display_size": candidate.display_size,
                        "sku": candidate.sku,
                        "offers": offers,
                    }
                )

            item_contexts.append(
                {
                    "item_id": result.item.item_id,
                    "requested_name": result.item.name,
                    "requested_quantity": result.item.quantity,
                    "requested_unit": result.item.unit,
                    "available_candidates": available,
                    "database_checked_candidate_count": len(
                        result.candidates
                    ),
                    "error": result.error,
                }
            )

        return {
            "items": item_contexts,
            "skipped_items": [
                item.model_dump(mode="json")
                for item in search.skipped_items
            ],
            "clarification_questions": extraction.clarification_questions,
            "preferences": extraction.preferences.model_dump(
                mode="json",
                exclude_none=True,
            ),
        }

    @staticmethod
    def _fallback_message(search: SearchBatchResult) -> str:
        available_count = sum(
            len(result.available_candidates)
            for result in search.items
        )

        if available_count:
            return (
                f"I found {available_count} available product option(s) "
                "for your shopping list."
            )

        return (
            "I could not confirm an available product for the requested "
            "items."
        )
