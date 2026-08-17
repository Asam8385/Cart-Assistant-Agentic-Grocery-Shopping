from __future__ import annotations

import inspect
import logging
import os
from dataclasses import dataclass
from typing import Any

from agent_framework import BaseChatClient
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from shoppingagent.retrieval import HybridProductRetriever

from .image_analyzer_agent import ImageAnalyzerAgent
from .pipeline import ShoppingAgentPipeline
from .product_search_agent import ProductSearchAgent
from .response_agent import ResponseAgent
from .tools import (
    AvailabilityTool,
    HybridCatalogSearchTool,
    MySQLAvailabilityTool,
)


logger = logging.getLogger(__name__)


def _first_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)

        if value and value.strip():
            return value.strip()

    return None


def _bool_value(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    normalized = value.strip().casefold()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    raise RuntimeError(f"{name} must be true or false.")


@dataclass(frozen=True, slots=True)
class AgentSettings:
    project_endpoint: str
    vision_model: str
    response_model: str
    retrieval_mode: str = "hybrid"
    retrieval_limit: int = 5
    apply_reranker: bool = True
    maximum_image_bytes: int = 10 * 1024 * 1024
    maximum_text_chars: int = 8000
    enable_instrumentation: bool = True
    enable_sensitive_data: bool = False

    @classmethod
    def from_environment(cls) -> "AgentSettings":
        endpoint = _first_value(
            "FOUNDRY_PROJECT_ENDPOINT",
            "AZURE_AI_PROJECT_ENDPOINT",
        )

        if endpoint is None:
            raise RuntimeError(
                "FOUNDRY_PROJECT_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT "
                "is required."
            )

        default_model = _first_value(
            "FOUNDRY_MODEL",
            "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        )
        vision_model = _first_value(
            "AZURE_AI_VISION_MODEL_DEPLOYMENT_NAME",
            "FOUNDRY_VISION_MODEL",
        ) or default_model
        response_model = _first_value(
            "AZURE_AI_RESPONSE_MODEL_DEPLOYMENT_NAME",
            "FOUNDRY_RESPONSE_MODEL",
        ) or default_model

        if vision_model is None or response_model is None:
            raise RuntimeError(
                "AZURE_AI_MODEL_DEPLOYMENT_NAME or the stage-specific "
                "model deployment variables are required."
            )

        retrieval_mode = os.getenv(
            "AGENT_RETRIEVAL_MODE",
            "hybrid",
        ).strip().lower()

        if retrieval_mode not in {"hybrid", "dense", "sparse"}:
            raise RuntimeError(
                "AGENT_RETRIEVAL_MODE must be hybrid, dense or sparse."
            )

        retrieval_limit = int(
            os.getenv("AGENT_RETRIEVAL_LIMIT", "5")
        )

        if not 1 <= retrieval_limit <= 10:
            raise RuntimeError(
                "AGENT_RETRIEVAL_LIMIT must be between 1 and 10."
            )

        return cls(
            project_endpoint=endpoint,
            vision_model=vision_model,
            response_model=response_model,
            retrieval_mode=retrieval_mode,
            retrieval_limit=retrieval_limit,
            apply_reranker=_bool_value(
                "AGENT_APPLY_RERANKER",
                True,
            ),
            maximum_image_bytes=int(
                os.getenv(
                    "AGENT_MAX_IMAGE_BYTES",
                    str(10 * 1024 * 1024),
                )
            ),
            maximum_text_chars=int(
                os.getenv("AGENT_MAX_TEXT_CHARS", "8000")
            ),
            enable_instrumentation=_bool_value(
                "ENABLE_INSTRUMENTATION",
                True,
            ),
            enable_sensitive_data=_bool_value(
                "ENABLE_SENSITIVE_DATA",
                False,
            ),
        )


@dataclass(slots=True)
class AgentRuntime:
    pipeline: ShoppingAgentPipeline
    credential: TokenCredential

    async def close(self) -> None:
        close = getattr(self.credential, "close", None)

        if close is None:
            return

        result = close()

        if inspect.isawaitable(result):
            await result


def _create_client(
    settings: AgentSettings,
    model: str,
    credential: TokenCredential,
) -> FoundryChatClient:
    client = FoundryChatClient(
        project_endpoint=settings.project_endpoint,
        model=model,
        credential=credential,
    )

    if settings.enable_instrumentation:
        try:
            client.configure_azure_monitor(
                enable_sensitive_data=settings.enable_sensitive_data
            )
        except ImportError:
            logger.warning(
                "Azure Monitor exporter is not installed; local Agent "
                "Framework telemetry will continue without that exporter."
            )
        except Exception:
            logger.exception(
                "Azure Monitor setup failed; pipeline startup will continue."
            )

    return client


def create_agent_runtime(
    retriever: HybridProductRetriever,
    *,
    settings: AgentSettings | None = None,
    credential: TokenCredential | None = None,
    availability_tool: AvailabilityTool | None = None,
    vision_client: BaseChatClient[Any] | None = None,
    response_client: BaseChatClient[Any] | None = None,
) -> AgentRuntime:
    resolved_settings = settings or AgentSettings.from_environment()
    resolved_credential = credential or DefaultAzureCredential(
        exclude_interactive_browser_credential=True,
    )

    resolved_vision_client = vision_client or _create_client(
        resolved_settings,
        resolved_settings.vision_model,
        resolved_credential,
    )

    if response_client is not None:
        resolved_response_client = response_client
    elif resolved_settings.response_model == resolved_settings.vision_model:
        resolved_response_client = resolved_vision_client
    else:
        resolved_response_client = _create_client(
            resolved_settings,
            resolved_settings.response_model,
            resolved_credential,
        )

    catalog_tool = HybridCatalogSearchTool(
        retriever,
        mode=resolved_settings.retrieval_mode,
        limit=resolved_settings.retrieval_limit,
        apply_reranker=resolved_settings.apply_reranker,
    )
    resolved_availability = (
        availability_tool or MySQLAvailabilityTool.from_environment()
    )

    pipeline = ShoppingAgentPipeline(
        image_analyzer=ImageAnalyzerAgent(
            resolved_vision_client,
            maximum_image_bytes=resolved_settings.maximum_image_bytes,
            maximum_text_chars=resolved_settings.maximum_text_chars,
        ),
        product_search=ProductSearchAgent(
            catalog_tool,
            resolved_availability,
        ),
        response_agent=ResponseAgent(resolved_response_client),
    )

    return AgentRuntime(
        pipeline=pipeline,
        credential=resolved_credential,
    )
