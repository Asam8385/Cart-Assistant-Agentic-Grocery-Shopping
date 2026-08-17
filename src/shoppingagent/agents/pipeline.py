from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from .events import EventFactory, StreamEvent
from .image_analyzer_agent import ImageAnalyzerAgent
from .models import (
    ExtractedRequest,
    PipelineInput,
    PipelineResult,
    SearchBatchResult,
)
from .product_search_agent import ProductSearchAgent
from .response_agent import ResponseAgent


logger = logging.getLogger(__name__)


class ShoppingAgentPipeline:
    """Explicit streaming orchestration; this class is not an LLM agent."""

    def __init__(
        self,
        image_analyzer: ImageAnalyzerAgent,
        product_search: ProductSearchAgent,
        response_agent: ResponseAgent,
    ) -> None:
        self._image_analyzer = image_analyzer
        self._product_search = product_search
        self._response_agent = response_agent

    async def stream(
        self,
        request: PipelineInput,
    ) -> AsyncIterator[StreamEvent]:
        request.validate()
        events = EventFactory(request.request_id)

        yield events.create(
            "pipeline.started",
            stage="pipeline",
            message="Shopping pipeline started.",
        )

        try:
            extraction: ExtractedRequest | None = None

            async for event in self._image_analyzer.stream_extract(
                request,
                events,
            ):
                if event.event == "image_analysis.completed":
                    extraction = ExtractedRequest.model_validate(
                        event.data["extraction"]
                    )

                yield event

            if extraction is None:
                raise RuntimeError(
                    "The extraction stage did not produce JSON."
                )

            search: SearchBatchResult | None = None

            async for event in self._product_search.stream_search(
                extraction,
                events,
            ):
                if event.event == "product_search.completed":
                    search = SearchBatchResult.model_validate(
                        event.data["search"]
                    )

                yield event

            if search is None:
                raise RuntimeError(
                    "The product search stage did not produce a result."
                )

            message = ""

            async for event in self._response_agent.stream_response(
                extraction,
                search,
                events,
            ):
                if event.event == "response.completed":
                    message = str(event.data["message"])

                yield event

            result = PipelineResult(
                extraction=extraction,
                search=search,
                message=message,
            )

            yield events.create(
                "pipeline.completed",
                stage="pipeline",
                message="Shopping pipeline completed.",
                data={"result": result.model_dump(mode="json")},
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "Shopping pipeline failed trace_id=%s",
                events.trace_id,
            )
            yield events.create(
                "pipeline.failed",
                stage="pipeline",
                message="The shopping request could not be completed.",
                data={"error_type": type(exc).__name__},
            )

    async def stream_sse(
        self,
        request: PipelineInput,
    ) -> AsyncIterator[str]:
        async for event in self.stream(request):
            yield event.to_sse()
