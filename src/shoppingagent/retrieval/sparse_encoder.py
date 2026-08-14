from __future__ import annotations

from threading import Lock

from fastembed import SparseTextEmbedding
from qdrant_client import models

from .query_normalizer import normalize_query


DEFAULT_SPARSE_MODEL = "Qdrant/bm25"
DEFAULT_BM25_LANGUAGE = "english"
DEFAULT_BM25_AVERAGE_DOCUMENT_LENGTH = 100.0


class SparseQueryEncoder:
    """
    Reusable FastEmbed BM25 query encoder.

    The model, language and average document length must match the
    configuration used by index_products_qdrant.py.
    """

    def __init__(
        self,
        model: SparseTextEmbedding,
    ) -> None:
        self._model = model
        self._lock = Lock()

    @classmethod
    def load(
        cls,
        model_name: str = DEFAULT_SPARSE_MODEL,
        *,
        language: str = DEFAULT_BM25_LANGUAGE,
        average_document_length: float = (
            DEFAULT_BM25_AVERAGE_DOCUMENT_LENGTH
        ),
    ) -> "SparseQueryEncoder":
        if average_document_length <= 0:
            raise ValueError(
                "BM25 average document length "
                "must be positive."
            )

        model = SparseTextEmbedding(
            model_name=model_name,
            language=language,
            avg_len=average_document_length,
        )

        return cls(model)

    def encode_query(
        self,
        query: str,
    ) -> models.SparseVector:
        normalized_query = normalize_query(query)

        with self._lock:
            embeddings = list(
                self._model.query_embed(
                    normalized_query
                )
            )

        if len(embeddings) != 1:
            raise RuntimeError(
                "BM25 query encoder did not return "
                "exactly one embedding."
            )

        embedding = embeddings[0]

        indices = [
            int(index)
            for index in embedding.indices
        ]

        values = [
            float(value)
            for value in embedding.values
        ]

        if len(indices) != len(values):
            raise RuntimeError(
                "Sparse-vector indices and values "
                "have different lengths."
            )

        return models.SparseVector(
            indices=indices,
            values=values,
        )