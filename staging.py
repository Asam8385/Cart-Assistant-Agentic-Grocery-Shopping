from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal

from agent_framework import (
    Agent,
    AgentSession,
    FunctionTool,
    ToolResultCompactionStrategy,
    tool,
)
from agent_framework.foundry import (
    FoundryChatClient,
)

from shoppingagent.retrieval import (
    HybridProductRetriever,
    ProductFilters,
)

from ._structured import (
    parse_structured_response,
)
from .prompts import (
    ROOT_AGENT_PROMPT,
)
from .schemas import (
    CatalogSearchResult,
    MatchedShoppingItem,
    ProductCandidate,
    ShoppingItem,
    ShoppingRequest,
    ShoppingResponse,
)


logger = logging.getLogger(__name__)

SearchMode = Literal[
    "hybrid",
    "dense",
    "sparse",
]


@dataclass(slots=True)
class _RetrievalRun:
    request: ShoppingRequest
    results: dict[
        str,
        CatalogSearchResult,
    ] = field(default_factory=dict)

    @property
    def items_by_id(
        self,
    ) -> dict[str, ShoppingItem]:
        return {
            item.item_id: item
            for item in self.request.items
        }


_ACTIVE_RETRIEVAL_RUN: ContextVar[
    _RetrievalRun | None
] = ContextVar(
    "shopping_agent_active_retrieval_run",
    default=None,
)


class RootShoppingAgent:
    def __init__(
        self,
        client: FoundryChatClient,
        retriever: HybridProductRetriever,
        *,
        search_mode: SearchMode = "hybrid",
        result_limit: int = 5,
        apply_reranker: bool = True,
    ) -> None:
        if search_mode not in {
            "hybrid",
            "dense",
            "sparse",
        }:
            raise ValueError(
                "search_mode must be hybrid, dense or sparse."
            )

        if not 1 <= result_limit <= 10:
            raise ValueError(
                "result_limit must be between 1 and 10."
            )

        self._retriever = retriever
        self._search_mode = search_mode
        self._result_limit = result_limit
        self._apply_reranker = apply_reranker

        self._search_tool = (
            self._create_search_tool()
        )

        self._agent = Agent(
            client=client,
            name="root-shopping-agent",
            description=(
                "Coordinates grounded catalogue retrieval "
                "for normalized shopping requests."
            ),
            instructions=ROOT_AGENT_PROMPT,
            tools=[self._search_tool],
            default_options={
                "max_tokens": 1800,
                "tool_choice": "auto",
            },
            compaction_strategy=(
                ToolResultCompactionStrategy(
                    keep_last_tool_call_groups=1,
                )
            ),
        )

    def create_session(
        self,
        *,
        session_id: str | None = None,
    ) -> AgentSession:
        return self._agent.create_session(
            session_id=session_id
        )

    def _create_search_tool(
        self,
    ) -> FunctionTool:
        @tool(
            name="search_catalog",
            description=(
                "Search the product catalogue for one exact "
                "ShoppingItem item_id from the current request."
            ),
        )
        async def search_catalog(
            item_id: str,
        ) -> str:
            run = _ACTIVE_RETRIEVAL_RUN.get()

            if run is None:
                return CatalogSearchResult(
                    item_id=item_id,
                    query="",
                    error=(
                        "No active shopping request exists."
                    ),
                ).model_dump_json()

            result = await self._search_item(
                run,
                item_id,
            )

            return result.model_dump_json(
                exclude_none=True
            )

        return search_catalog

    async def respond(
        self,
        request: ShoppingRequest,
        *,
        session: AgentSession | None = None,
    ) -> ShoppingResponse:
        if not request.items:
            return ShoppingResponse(
                summary=(
                    "I could not identify an active shopping "
                    "item to search for."
                ),
                clarification_questions=(
                    request.clarification_questions
                    or [
                        "What product would you like to find?"
                    ]
                ),
            )

        run = _RetrievalRun(
            request=request,
        )

        token = _ACTIVE_RETRIEVAL_RUN.set(run)

        try:
            generated_response: (
                ShoppingResponse | None
            ) = None

            try:
                raw_response = await self._agent.run(
                    (
                        "Fulfil this normalized shopping request:\n"
                        f"{request.model_dump_json(exclude_none=True)}"
                    ),
                    session=session,
                    options={
                        "response_format": ShoppingResponse,
                        "max_tokens": 1800,
                        "tool_choice": "auto",
                    },
                )

                generated_response = (
                    parse_structured_response(
                        raw_response,
                        ShoppingResponse,
                    )
                )
            except Exception:
                logger.exception(
                    "Root response generation failed. "
                    "Using grounded deterministic fallback."
                )

            missing_item_ids = [
                item.item_id
                for item in request.items
                if item.item_id not in run.results
            ]

            if missing_item_ids:
                await asyncio.gather(
                    *[
                        self._search_item(
                            run,
                            item_id,
                        )
                        for item_id in missing_item_ids
                    ]
                )

            return self._validate_and_ground(
                request=request,
                generated=generated_response,
                retrieval_results=run.results,
            )
        finally:
            _ACTIVE_RETRIEVAL_RUN.reset(token)

    async def _search_item(
        self,
        run: _RetrievalRun,
        item_id: str,
    ) -> CatalogSearchResult:
        existing = run.results.get(item_id)

        if existing is not None:
            return existing

        item = run.items_by_id.get(item_id)

        if item is None:
            return CatalogSearchResult(
                item_id=item_id,
                query="",
                error="Unknown shopping item identifier.",
            )

        preferences = run.request.preferences

        filters = ProductFilters(
            vendor_key=preferences.vendor_key,
            category_slug=(
                item.category_slug
                or preferences.category_slug
            ),
            brand=(
                item.preferred_brand
                or preferences.brand
            ),
            country_of_origin=(
                preferences.country_of_origin
            ),
            is_organic=preferences.is_organic,
            is_vegan=preferences.is_vegan,
            is_vegetarian=(
                preferences.is_vegetarian
            ),
            is_gluten_free=(
                preferences.is_gluten_free
            ),
            is_halal=preferences.is_halal,
        )

        query = item.build_search_query()

        try:
            hits = await asyncio.to_thread(
                self._retriever.search,
                query,
                mode=self._search_mode,
                limit=self._result_limit,
                filters=filters,
                apply_reranker=(
                    self._apply_reranker
                ),
            )

            result = CatalogSearchResult(
                item_id=item_id,
                query=query,
                candidates=[
                    self._candidate_from_hit(hit)
                    for hit in hits
                ],
            )
        except Exception:
            logger.exception(
                "Catalogue retrieval failed for item_id=%s",
                item_id,
            )

            result = CatalogSearchResult(
                item_id=item_id,
                query=query,
                error=(
                    "The catalogue search is temporarily "
                    "unavailable."
                ),
            )

        run.results[item_id] = result

        return result

    @staticmethod
    def _optional_string(
        value: object,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()

        return normalized or None

    def _candidate_from_hit(
        self,
        hit: object,
    ) -> ProductCandidate:
        payload = dict(
            getattr(
                hit,
                "payload",
                {},
            )
            or {}
        )

        return ProductCandidate(
            point_id=str(
                getattr(hit, "point_id")
            ),
            record_id=str(
                getattr(hit, "record_id")
            ),
            title=str(
                getattr(hit, "title")
            ),
            score=float(
                getattr(hit, "score")
            ),
            qdrant_score=float(
                getattr(hit, "qdrant_score")
            ),
            reranker_score=(
                float(
                    getattr(
                        hit,
                        "reranker_score",
                    )
                )
                if getattr(
                    hit,
                    "reranker_score",
                    None,
                )
                is not None
                else None
            ),
            vendor_key=self._optional_string(
                payload.get("vendor_key")
            ),
            vendor_name=self._optional_string(
                payload.get("vendor_name")
            ),
            vendor_product_id=(
                self._optional_string(
                    payload.get(
                        "vendor_product_id"
                    )
                )
            ),
            vendor_variant_id=(
                self._optional_string(
                    payload.get(
                        "vendor_variant_id"
                    )
                )
            ),
            sku=self._optional_string(
                payload.get("sku")
            ),
            barcode=self._optional_string(
                payload.get("barcode")
            ),
            brand=self._optional_string(
                payload.get("brand")
            ),
            category=self._optional_string(
                payload.get("category")
            ),
            category_slug=self._optional_string(
                payload.get("category_slug")
            ),
            display_size=self._optional_string(
                payload.get("display_size")
            ),
            country_of_origin=(
                self._optional_string(
                    payload.get(
                        "country_of_origin"
                    )
                )
            ),
            is_organic=payload.get("is_organic"),
            is_vegan=payload.get("is_vegan"),
            is_vegetarian=payload.get(
                "is_vegetarian"
            ),
            is_gluten_free=payload.get(
                "is_gluten_free"
            ),
            is_halal=payload.get("is_halal"),
        )

    def _validate_and_ground(
        self,
        *,
        request: ShoppingRequest,
        generated: ShoppingResponse | None,
        retrieval_results: dict[
            str,
            CatalogSearchResult,
        ],
    ) -> ShoppingResponse:
        generated_matches = {
            match.item_id: match
            for match in (
                generated.matches
                if generated
                else []
            )
        }

        validated_matches: list[
            MatchedShoppingItem
        ] = []
        unmatched_items: list[str] = []
        warnings = list(
            generated.warnings
            if generated
            else []
        )

        for item in request.items:
            result = retrieval_results.get(
                item.item_id
            )

            if result is None or result.error:
                unmatched_items.append(item.name)

                if result and result.error:
                    warnings.append(result.error)

                continue

            if not result.candidates:
                unmatched_items.append(item.name)
                continue

            trusted_by_id = {
                candidate.point_id: candidate
                for candidate in result.candidates
            }

            proposed_match = (
                generated_matches.get(
                    item.item_id
                )
            )

            selected: list[
                ProductCandidate
            ] = []

            if proposed_match:
                for proposed in (
                    proposed_match.candidates
                ):
                    trusted = trusted_by_id.get(
                        proposed.point_id
                    )

                    if trusted is None:
                        continue

                    selected.append(
                        trusted.model_copy(
                            update={
                                "match_reason": (
                                    proposed.match_reason
                                )
                            }
                        )
                    )

            if not selected:
                selected = result.candidates[:3]

            validated_matches.append(
                MatchedShoppingItem(
                    item_id=item.item_id,
                    requested_name=item.name,
                    requested_quantity=item.quantity,
                    requested_unit=item.unit,
                    candidates=selected[
                        :self._result_limit
                    ],
                )
            )

        clarification_questions = list(
            request.clarification_questions
        )

        if generated:
            clarification_questions.extend(
                generated.clarification_questions
            )

        clarification_questions = list(
            dict.fromkeys(
                question
                for question
                in clarification_questions
                if question.strip()
            )
        )

        warnings = list(
            dict.fromkeys(
                warning
                for warning in warnings
                if warning.strip()
            )
        )

        summary = (
            generated.summary
            if generated
            else (
                f"Found catalogue candidates for "
                f"{len(validated_matches)} requested "
                f"item(s)."
            )
        )

        return ShoppingResponse(
            summary=summary,
            matches=validated_matches,
            unmatched_items=list(
                dict.fromkeys(unmatched_items)
            ),
            clarification_questions=(
                clarification_questions
            ),
            warnings=warnings,
        )