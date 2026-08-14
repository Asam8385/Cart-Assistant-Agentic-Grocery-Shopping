from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

import numpy as np
from sentence_transformers import CrossEncoder
from torch import nn

from .models import SearchHit
from .query_normalizer import normalize_query


DEFAULT_RERANKER_MODEL = (
    "cross-encoder/ms-marco-MiniLM-L2-v2"
)


@dataclass(frozen=True, slots=True)
class RerankerSettings:
    batch_size: int = 16
    maximum_candidates: int = 40

    identifier_boost: float = 0.25
    alias_boost: float = 0.10
    title_boost: float = 0.08


class HuggingFaceReranker:
    """
    Small Hugging Face cross-encoder reranker.

    Qdrant retrieves the first candidate set. This model then scores each
    (query, product-text) pair and reorders those candidates.
    """

    def __init__(
        self,
        model: CrossEncoder,
        *,
        settings: RerankerSettings | None = None,
    ) -> None:
        self._model = model
        self._lock = Lock()
        self.settings = (
            settings or RerankerSettings()
        )

        if self.settings.batch_size < 1:
            raise ValueError(
                "Reranker batch size must be positive."
            )

        if self.settings.maximum_candidates < 1:
            raise ValueError(
                "Reranker maximum candidates "
                "must be positive."
            )

    @classmethod
    def load(
        cls,
        model_name: str = DEFAULT_RERANKER_MODEL,
        *,
        device: str | None = "cpu",
        maximum_length: int = 256,
        settings: RerankerSettings | None = None,
    ) -> "HuggingFaceReranker":
        if maximum_length < 16:
            raise ValueError(
                "Reranker maximum length must "
                "be at least 16."
            )

        model = CrossEncoder(
            model_name_or_path=model_name,
            device=device,
            max_length=maximum_length,

            # Produce a zero-to-one relevance value.
            # The sigmoid does not change the result ordering.
            activation_fn=nn.Sigmoid(),
        )

        return cls(
            model,
            settings=settings,
        )

    def rerank(
        self,
        query: str,
        hits: list[SearchHit],
    ) -> list[SearchHit]:
        if not hits:
            return []

        normalized_query = normalize_query(query)

        candidates = hits[
            : self.settings.maximum_candidates
        ]

        passages = [
            self._build_passage(hit)
            for hit in candidates
        ]

        pairs = [
            (normalized_query, passage)
            for passage in passages
        ]

        with self._lock:
            predicted_scores = self._model.predict(
                pairs,
                batch_size=self.settings.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

        scores = np.asarray(
            predicted_scores,
            dtype=float,
        ).reshape(-1)

        if len(scores) != len(candidates):
            raise RuntimeError(
                "Reranker score count does not "
                "match candidate count."
            )

        for hit, predicted_score in zip(
            candidates,
            scores,
            strict=True,
        ):
            relevance_score = float(
                predicted_score
            )

            exact_boost, reasons = (
                self._calculate_exact_match_boost(
                    normalized_query,
                    hit,
                )
            )

            hit.reranker_score = relevance_score

            # This final value is a ranking score. It may exceed 1.0
            # when a verified identifier or alias boost is applied.
            hit.score = (
                relevance_score + exact_boost
            )

            hit.boost_reasons = reasons

        candidates.sort(
            key=lambda hit: (
                hit.score,
                hit.qdrant_score,
            ),
            reverse=True,
        )

        return candidates

    @staticmethod
    def _build_passage(
        hit: SearchHit,
    ) -> str:
        payload = hit.payload

        # The indexed chunk already contains product name, vendor,
        # category, size, identifiers, aliases and dietary information.
        chunk_text = str(
            payload.get("chunk_text") or ""
        ).strip()

        if chunk_text:
            return chunk_text

        # Fallback for points that do not have chunk_text.
        values = [
            hit.title,
            str(payload.get("brand") or ""),
            str(payload.get("category_path") or ""),
            str(payload.get("display_size") or ""),
            str(payload.get("sku") or ""),
            str(payload.get("barcode") or ""),
        ]

        aliases_value = payload.get("aliases") or []

        if isinstance(aliases_value, list):
            values.extend(
                str(alias)
                for alias in aliases_value
            )
        elif isinstance(aliases_value, str):
            values.append(aliases_value)

        return ". ".join(
            value.strip()
            for value in values
            if value.strip()
        )

    def _calculate_exact_match_boost(
        self,
        query: str,
        hit: SearchHit,
    ) -> tuple[float, list[str]]:
        normalized_query = query.casefold().strip()
        payload = hit.payload

        boost = 0.0
        reasons: list[str] = []

        identifiers = {
            str(
                payload.get("sku") or ""
            ).casefold().strip(),
            str(
                payload.get("barcode") or ""
            ).casefold().strip(),
            str(
                payload.get(
                    "vendor_product_id"
                ) or ""
            ).casefold().strip(),
            str(
                payload.get(
                    "vendor_variant_id"
                ) or ""
            ).casefold().strip(),
            str(
                payload.get("_record_id") or ""
            ).casefold().strip(),
        }

        identifiers.discard("")

        if normalized_query in identifiers:
            boost += (
                self.settings.identifier_boost
            )
            reasons.append("exact identifier")

        aliases_value = payload.get("aliases") or []

        if isinstance(aliases_value, str):
            aliases = [aliases_value]
        else:
            aliases = [
                str(alias)
                for alias in aliases_value
            ]

        normalized_aliases = {
            alias.casefold().strip()
            for alias in aliases
            if alias.strip()
        }

        if normalized_query in normalized_aliases:
            boost += self.settings.alias_boost
            reasons.append("exact alias")

        normalized_title = (
            hit.title.casefold().strip()
        )

        if normalized_query == normalized_title:
            boost += self.settings.title_boost
            reasons.append("exact title")

        return boost, reasons