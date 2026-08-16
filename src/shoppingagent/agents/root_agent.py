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
                session_id: str | None =  None,
        ) -> AgentSession:
            return self._agent.create_session(
                session_id=session_id
            )


        