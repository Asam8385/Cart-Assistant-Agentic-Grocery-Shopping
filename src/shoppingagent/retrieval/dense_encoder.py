from __future__ import annotations

from threading import Lock

from sentence_transformers import SentenceTransformer

from .query_normalizer import normalize_query

DEFAULT_DENSE_MODEL = "google/embeddinggemma-300m"
DEFAULT_VECTOR_SIZE = 768

class DenseQueryEncoder:
    """
    Reusable EmbeddingGemma query encoder.

    The model is loaded once by the application startup process and this
    object is shared by the HybridRetriever.
    """

    def __init__(
            self ,
            model: SentenceTransformer,
            * ,
            expected_dimension : int = DEFAULT_VECTOR_SIZE
    ) -> None:
        self._model = model
        self._lock = Lock()
        self.expected_dimension = expected_dimension

        dimension = model.get_sentence_embedding_dimension()

        if dimension != expected_dimension:
            raise RuntimeError(
                f"Dense model dimension is {dimension}; "
                f"expected {expected_dimension}."
            )  

           
    @classmethod
    def load(
        cls,
        model_name: str = DEFAULT_DENSE_MODEL,
        * , 
        expected_dimension: int = DEFAULT_VECTOR_SIZE,
        device: str | None = None,
    ) -> "DenseQueryEncoder":

        model = SentenceTransformer(
            model_name_or_path=model_name,
            device="cuda",
        )

        return cls(
            model,
            expected_dimension=expected_dimension,
        )

    def encode_query(self, query : str) -> list[float]:
        normalized_query = normalize_query(query)

        # This query prompt corresponds to the EmbeddingGemma document prompt
        # used by the Qdrant indexing script:
        #
        # Document: title: none | text: ...
        # Query:    task: search result | query: ...
        prompted_query = (
            f"task: search result | query: {normalized_query}"
        )

        # A lock prevents simultaneous calls from competing for the same
        # local Torch model during this simple test implementation. 
        # this is like a mutex and critical section
        with self._lock:
            embeddings = self._model.encode(
                [prompted_query],
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True

            )

        vector = embeddings[0].tolist()

        if len(vector) != self.expected_dimension:
            raise RuntimeError(
                f"Generated dense vector has {len(vector)} dimensions; "
                f"expected {self.expected_dimension}."
            )

        return [float(value) for value in vector]



