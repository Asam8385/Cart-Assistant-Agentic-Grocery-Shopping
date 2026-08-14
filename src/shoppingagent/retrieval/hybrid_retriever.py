from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

from qdrant_client import QdrantClient, models

from dotenv import load_dotenv

load_dotenv(
    
)


from .dense_encoder import (
    DEFAULT_DENSE_MODEL,
    DEFAULT_VECTOR_SIZE,
    DenseQueryEncoder,
)
from .filters import (
    ProductFilters,
    build_qdrant_filter,
)
from .models import SearchHit
from .query_normalizer import normalize_query
from .reranker import HuggingFaceReranker
from .sparse_encoder import (
    DEFAULT_BM25_AVERAGE_DOCUMENT_LENGTH,
    DEFAULT_BM25_LANGUAGE,
    DEFAULT_SPARSE_MODEL,
    SparseQueryEncoder,
)


SearchMode = Literal[
    "hybrid",
    "dense",
    "sparse",
]

VALID_SEARCH_MODES = {
    "hybrid",
    "dense",
    "sparse",
}


@dataclass(frozen=True, slots=True)
class RetrievalSettings:
    qdrant_url: str
    qdrant_api_key: str | None
    collection_name: str

    dense_vector_name: str
    sparse_vector_name: str

    dense_model_name: str
    dense_vector_size: int
    dense_device: str | None

    sparse_model_name: str
    bm25_language: str
    bm25_average_document_length: float

    reranker_model_name: str
    reranker_device: str | None
    reranker_maximum_length: int
    reranker_batch_size: int
    reranker_candidate_limit: int

    qdrant_timeout: int

    @classmethod
    def from_environment(
        cls,
    ) -> "RetrievalSettings":
        qdrant_url = os.getenv(
            "QDRANT_URL",
            "http://localhost:6333",
        ).strip()

        if not qdrant_url:
            raise RuntimeError(
                "QDRANT_URL cannot be empty."
            )

        api_key = os.getenv("QDRANT_API_KEY")

        if api_key is not None:
            api_key = api_key.strip() or None

        dense_device = (
            os.getenv("DENSE_DEVICE") or ""
        ).strip() or None

        reranker_device = (
            os.getenv(
                "RERANKER_DEVICE",
                "Cuda",
            )
        ).strip() or None

        settings = cls(
            qdrant_url=qdrant_url,
            qdrant_api_key=api_key,
            collection_name=os.getenv(
                "QDRANT_COLLECTION",
                "shopping-products-v1",
            ).strip(),
            dense_vector_name=os.getenv(
                "DENSE_VECTOR_NAME",
                "dense",
            ).strip(),
            sparse_vector_name=os.getenv(
                "SPARSE_VECTOR_NAME",
                "sparse",
            ).strip(),
            dense_model_name=os.getenv(
                "DENSE_MODEL_NAME",
                DEFAULT_DENSE_MODEL,
            ).strip(),
            dense_vector_size=int(
                os.getenv(
                    "DENSE_VECTOR_SIZE",
                    str(DEFAULT_VECTOR_SIZE),
                )
            ),
            dense_device=dense_device,
            sparse_model_name=os.getenv(
                "SPARSE_MODEL_NAME",
                DEFAULT_SPARSE_MODEL,
            ).strip(),
            bm25_language=os.getenv(
                "BM25_LANGUAGE",
                DEFAULT_BM25_LANGUAGE,
            ).strip(),
            bm25_average_document_length=float(
                os.getenv(
                    "BM25_AVG_DOCUMENT_LENGTH",
                    str(
                        DEFAULT_BM25_AVERAGE_DOCUMENT_LENGTH
                    ),
                )
            ),
            reranker_model_name=os.getenv(
                "RERANKER_MODEL",
                (
                    "cross-encoder/"
                    "ms-marco-MiniLM-L2-v2"
                ),
            ).strip(),
            reranker_device=reranker_device,
            reranker_maximum_length=int(
                os.getenv(
                    "RERANKER_MAX_LENGTH",
                    "256",
                )
            ),
            reranker_batch_size=int(
                os.getenv(
                    "RERANKER_BATCH_SIZE",
                    "16",
                )
            ),
            reranker_candidate_limit=int(
                os.getenv(
                    "RERANKER_CANDIDATE_LIMIT",
                    "40",
                )
            ),
            qdrant_timeout=int(
                os.getenv(
                    "QDRANT_SEARCH_TIMEOUT",
                    "30",
                )
            ),
        )

        settings.validate()

        return settings

    def validate(self) -> None:
        required_strings = {
            "collection_name": self.collection_name,
            "dense_vector_name": (
                self.dense_vector_name
            ),
            "sparse_vector_name": (
                self.sparse_vector_name
            ),
            "dense_model_name": (
                self.dense_model_name
            ),
            "sparse_model_name": (
                self.sparse_model_name
            ),
            "reranker_model_name": (
                self.reranker_model_name
            ),
        }

        for field_name, value in (
            required_strings.items()
        ):
            if not value:
                raise ValueError(
                    f"{field_name} cannot be empty."
                )

        if self.dense_vector_size < 1:
            raise ValueError(
                "Dense vector size must be positive."
            )

        if (
            self.bm25_average_document_length
            <= 0
        ):
            raise ValueError(
                "BM25 average document length "
                "must be positive."
            )

        if self.reranker_maximum_length < 16:
            raise ValueError(
                "Reranker maximum length must "
                "be at least 16."
            )

        if self.reranker_batch_size < 1:
            raise ValueError(
                "Reranker batch size must "
                "be positive."
            )

        if self.reranker_candidate_limit < 1:
            raise ValueError(
                "Reranker candidate limit must "
                "be positive."
            )

        if self.qdrant_timeout < 1:
            raise ValueError(
                "Qdrant timeout must be positive."
            )


class HybridProductRetriever:
    def __init__(
        self,
        *,
        client: QdrantClient,
        dense_encoder: DenseQueryEncoder,
        sparse_encoder: SparseQueryEncoder,
        reranker: HuggingFaceReranker,
        collection_name: str,
        dense_vector_name: str = "dense",
        sparse_vector_name: str = "sparse",
        timeout: int = 80,
        default_candidate_limit: int = 40,
    ) -> None:
        self.client = client
        self.dense_encoder = dense_encoder
        self.sparse_encoder = sparse_encoder
        self.reranker = reranker

        self.collection_name = collection_name
        self.dense_vector_name = dense_vector_name
        self.sparse_vector_name = (
            sparse_vector_name
        )

        self.timeout = timeout
        self.default_candidate_limit = (
            default_candidate_limit
        )

    def health_check(
        self,
    ) -> dict[str, object]:
        if not self.client.collection_exists(
            self.collection_name
        ):
            raise RuntimeError(
                f"Qdrant collection does not exist: "
                f"{self.collection_name}"
            )

        collection = self.client.get_collection(
            self.collection_name
        )

        return {
            "status": "ready",
            "collection": self.collection_name,
            "points_count": (
                collection.points_count
            ),
            "indexed_vectors_count": (
                collection.indexed_vectors_count
            ),
        }

    def search(
        self,
        query: str,
        *,
        mode: SearchMode = "hybrid",
        limit: int = 10,
        candidate_limit: int | None = None,
        filters: ProductFilters | None = None,
        apply_reranker: bool = True,
    ) -> list[SearchHit]:
        normalized_query = normalize_query(query)

        normalized_mode = mode.strip().lower()

        if normalized_mode not in (
            VALID_SEARCH_MODES
        ):
            raise ValueError(
                "Search mode must be hybrid, "
                "dense or sparse."
            )

        search_mode = cast(
            SearchMode,
            normalized_mode,
        )

        if not 1 <= limit <= 50:
            raise ValueError(
                "Result limit must be between "
                "1 and 50."
            )

        if candidate_limit is None:
            candidate_limit = max(
                self.default_candidate_limit,
                limit * 4,
            )

        candidate_limit = min(
            max(candidate_limit, limit),
            100,
        )

        # When reranking is disabled, there is no reason to retrieve
        # extra candidates.
        retrieval_limit = (
            candidate_limit
            if apply_reranker
            else limit
        )

        query_filter = build_qdrant_filter(
            filters
        )

        if search_mode == "hybrid":
            points = self._hybrid_search(
                normalized_query,
                limit=retrieval_limit,
                candidate_limit=candidate_limit,
                query_filter=query_filter,
            )
        elif search_mode == "dense":
            points = self._dense_search(
                normalized_query,
                limit=retrieval_limit,
                query_filter=query_filter,
            )
        else:
            points = self._sparse_search(
                normalized_query,
                limit=retrieval_limit,
                query_filter=query_filter,
            )

        hits = [
            self._point_to_hit(point)
            for point in points
        ]

        if apply_reranker:
            hits = self.reranker.rerank(
                normalized_query,
                hits,
            )

        return hits[:limit]

    def _hybrid_search(
        self,
        query: str,
        *,
        limit: int,
        candidate_limit: int,
        query_filter: models.Filter | None,
    ) -> list[models.ScoredPoint]:
        dense_vector = (
            self.dense_encoder.encode_query(query)
        )

        sparse_vector = (
            self.sparse_encoder.encode_query(query)
        )

        dense_prefetch = models.Prefetch(
            query=dense_vector,
            using=self.dense_vector_name,
            filter=query_filter,
            limit=candidate_limit,
        )

        # BM25 can return an empty sparse query for text containing
        # only ignored tokens. In that situation, continue with dense
        # search instead of sending an empty sparse vector.
        if not sparse_vector.indices:
            return self._dense_search(
                query,
                limit=limit,
                query_filter=query_filter,
            )

        sparse_prefetch = models.Prefetch(
            query=sparse_vector,
            using=self.sparse_vector_name,
            filter=query_filter,
            limit=candidate_limit,
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                dense_prefetch,
                sparse_prefetch,
            ],
            query=models.FusionQuery(
                fusion=models.Fusion.RRF,
            ),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            timeout=self.timeout,
        )

        return list(response.points)

    def _dense_search(
        self,
        query: str,
        *,
        limit: int,
        query_filter: models.Filter | None,
    ) -> list[models.ScoredPoint]:
        dense_vector = (
            self.dense_encoder.encode_query(query)
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=dense_vector,
            using=self.dense_vector_name,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            timeout=self.timeout,
        )

        return list(response.points)

    def _sparse_search(
        self,
        query: str,
        *,
        limit: int,
        query_filter: models.Filter | None,
    ) -> list[models.ScoredPoint]:
        sparse_vector = (
            self.sparse_encoder.encode_query(query)
        )

        if not sparse_vector.indices:
            return []

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=sparse_vector,
            using=self.sparse_vector_name,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            timeout=self.timeout,
        )

        return list(response.points)

    @staticmethod
    def _point_to_hit(
        point: models.ScoredPoint,
    ) -> SearchHit:
        payload = dict(point.payload or {})
        qdrant_score = float(
            point.score or 0.0
        )

        return SearchHit(
            point_id=str(point.id),
            record_id=str(
                payload.get("_record_id")
                or point.id
            ),
            title=derive_product_title(
                payload
            ),
            score=qdrant_score,
            qdrant_score=qdrant_score,
            reranker_score=None,
            payload=payload,
        )


def derive_product_title(
    payload: dict[str, object],
) -> str:
    explicit_title = payload.get(
        "product_name"
    )

    if explicit_title:
        return str(explicit_title)

    chunk_text = str(
        payload.get("chunk_text") or ""
    )

    first_sentence = chunk_text.split(
        ".",
        maxsplit=1,
    )[0].strip()

    if first_sentence.casefold().startswith(
        "product:"
    ):
        title = first_sentence.split(
            ":",
            maxsplit=1,
        )[1].strip()

        if title:
            return title

    aliases = payload.get("aliases")

    if isinstance(aliases, list) and aliases:
        return str(aliases[0]).title()

    sku = payload.get("sku")

    if sku:
        return str(sku)

    return "Unnamed product"