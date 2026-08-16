from __future__ import annotations

import json

from agent_framework import Agent
from agent_framework.foundry import (
    FoundryChatClient,
)

from ._structured import (
    parse_structured_response,
)
from .prompts import (
    DATA_COLLECTOR_PROMPT,
)
from .schemas import (
    ImageAnalysisResult,
    ShoppingItem,
    ShoppingRequest,
)


class DataCollectorAgent:
    def __init__(
        self,
        client: FoundryChatClient,
        *,
        maximum_text_length: int = 8000,
    ) -> None:
        if maximum_text_length < 1:
            raise ValueError(
                "maximum_text_length must be positive."
            )

        self._maximum_text_length = (
            maximum_text_length
        )

        self._agent = Agent(
            client=client,
            name="data-collector-agent",
            description=(
                "Normalizes text and image extraction into "
                "a structured shopping request."
            ),
            instructions=DATA_COLLECTOR_PROMPT,
            default_options={
                "max_tokens": 1400,
            },
        )

    async def collect(
        self,
        *,
        user_text: str | None = None,
        image_analysis: (
            ImageAnalysisResult | None
        ) = None,
    ) -> ShoppingRequest:
        normalized_text = (
            user_text.strip()
            if user_text
            else ""
        )

        if (
            len(normalized_text)
            > self._maximum_text_length
        ):
            raise ValueError(
                "The user text exceeds the configured limit."
            )

        if not normalized_text and image_analysis is None:
            raise ValueError(
                "Text or image analysis must be provided."
            )

        payload = {
            "user_text": normalized_text or None,
            "image_analysis": (
                image_analysis.model_dump(
                    mode="json"
                )
                if image_analysis
                else None
            ),
        }

        response = await self._agent.run(
            (
                "Normalize the following request data.\n"
                "<request_data>\n"
                f"{json.dumps(payload, ensure_ascii=False)}\n"
                "</request_data>"
            ),
            options={
                "response_format": ShoppingRequest,
                "max_tokens": 1400,
            },
        )

        request = parse_structured_response(
            response,
            ShoppingRequest,
        )

        return self._normalize_result(
            request,
            original_text=normalized_text,
            image_analysis=image_analysis,
        )

    @staticmethod
    def _normalize_key(value: str) -> str:
        return " ".join(
            value.casefold().split()
        )

    def _normalize_result(
        self,
        request: ShoppingRequest,
        *,
        original_text: str,
        image_analysis: (
            ImageAnalysisResult | None
        ),
    ) -> ShoppingRequest:
        crossed_out_names: set[str] = set()

        if image_analysis is not None:
            crossed_out_names = {
                self._normalize_key(item.name)
                for item in image_analysis.items
                if item.status == "crossed_out"
            }

        normalized_items: list[ShoppingItem] = []
        seen: set[
            tuple[
                str,
                str | None,
                str | None,
            ]
        ] = set()

        for item in request.items:
            name_key = self._normalize_key(
                item.name
            )

            if name_key in crossed_out_names:
                continue

            deduplication_key = (
                name_key,
                (
                    self._normalize_key(
                        item.preferred_brand
                    )
                    if item.preferred_brand
                    else None
                ),
                (
                    self._normalize_key(item.unit)
                    if item.unit
                    else None
                ),
            )

            if deduplication_key in seen:
                continue

            seen.add(deduplication_key)

            normalized_items.append(
                item.model_copy(
                    update={
                        "item_id": (
                            f"item-"
                            f"{len(normalized_items) + 1}"
                        )
                    }
                )
            )

            if len(normalized_items) >= 30:
                break

        return request.model_copy(
            update={
                "original_text": (
                    original_text or None
                ),
                "items": normalized_items,
            }
        )