from __future__ import annotations

import json 
import os
import uuid
from collections.abc import Iterator , Sequence
from pathlib import Path
from typing import Any


from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# First/full database export:
INPUT_JSONL = DATA_DIR / "products.jsonl"

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv(
    "QDRANT_COLLECTION",
    "shopping-products-v1",
)

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


DENSE_MODEL_NAME = "google/embeddinggemma-300m"
DENSE_VECTOR_SIZE = 768

SPARSE_MODEL_NAME = "Qdrant/bm25"

BM25_LANGUAGE = "english"
BM25_AVG_DOCUMENT_LENGTH = 100.0

READ_BATCH_SIZE = 100
DENSE_ENCODING_BATCH_SIZE = 32


RECREATE_COLLECTION = False


def read_jsonl(path: Path) -> Iterator[dict[str , Any]]:
   if not path.exists():
        raise FileNotFoundError(f"JSONL input does not exist: {path}")

   with path.open("r" , encoding="utf-8") as file:
       for line_number , line in enumerate(file , start=1):

            if not line:
               continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at {path}:{line_number}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected a JSON object at {path}:{line_number}"
                )

            yield record
            

def batched(
    records: Iterator[dict[str, Any]],
    batch_size: int,
) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []

    for record in records:
        batch.append(record)

        if len(batch) >= batch_size:
            yield batch
            batch = []

    if batch:
        yield batch


# ---------------------------------------------------------------------------
# Stable point IDs
# ---------------------------------------------------------------------------

def get_record_id(record: dict[str, Any]) -> str:
    record_id = record.get("_id") or record.get("id")

    if not record_id:
        raise ValueError("A JSONL record does not contain '_id' or 'id'.")

    return str(record_id)
         
def qdrant_point_id(record_id: str) -> str:
    """
    Qdrant point IDs must be an integer or UUID.

    The product's stable string ID is converted into a deterministic UUID.
    The same source ID always produces the same Qdrant point ID.
    """
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"shoppingagent:product:{record_id}",
        )
    )


# ---------------------------------------------------------------------------
# Record handling
# ---------------------------------------------------------------------------

def get_operation(record: dict[str, Any]) -> str:
    operation = str(record.get("operation", "upsert")).lower().strip()

    if operation not in {"upsert", "delete"}:
        raise ValueError(f"Unsupported operation: {operation}")

    return operation


def get_document_text(record: dict[str, Any]) -> str:
    text = (
        record.get("chunk_text")
        or record.get("text")
        or record.get("document")
    )

    if not text or not str(text).strip():
        raise ValueError(
            f"Record {get_record_id(record)!r} does not contain document text."
        )

    return str(text).strip()

def build_payload(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata") or {}

    if not isinstance(metadata, dict):
        raise ValueError(
            f"Record {get_record_id(record)!r} has invalid metadata."
        )

    # Flatten metadata for simpler Qdrant filtering.
    payload: dict[str, Any] = dict(metadata)

    payload.update(
        {
            "_record_id": get_record_id(record),
            "operation": "upsert",
            "chunk_text": get_document_text(record),
            "content_hash": record.get("content_hash"),
            "metadata_hash": record.get("metadata_hash"),
            "source_version": record.get("source_version"),
            "dense_model": DENSE_MODEL_NAME,
            "sparse_model": SPARSE_MODEL_NAME,
        }
    )

    # Guarantees that every value is JSON serializable.
    return json.loads(json.dumps(payload, default=str))


def create_client() -> QdrantClient:
    return QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        timeout=120,
        cloud_inference=True
    )


def ensure_collection(client: QdrantClient) -> None:
    exists = client.collection_exists(QDRANT_COLLECTION)

    if exists and RECREATE_COLLECTION:
        client.delete_collection(QDRANT_COLLECTION)
        exists = False
        print(f"Deleted collection: {QDRANT_COLLECTION}")

    if exists:
        print(f"Using existing collection: {QDRANT_COLLECTION}")
        return

    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=DENSE_VECTOR_SIZE,
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            )
        },
    )

    create_payload_indexes(client)

    print(f"Created collection: {QDRANT_COLLECTION}")

def create_payload_indexes(client: QdrantClient) -> None:
    keyword_fields = [
        "vendor_id",
        "vendor_key",
        "category_slug",
        "product_type",
        "brand",
        "sku",
        "barcode",
        "currency",
    ]

    for field_name in keyword_fields:
        client.create_payload_index(
            collection_name=QDRANT_COLLECTION,
            field_name=field_name,
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )




# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

def load_dense_model() -> SentenceTransformer:
    model = SentenceTransformer(DENSE_MODEL_NAME)

    dimension = model.get_embedding_dimension()

    if dimension != DENSE_VECTOR_SIZE:
        raise RuntimeError(
            f"Expected dense dimension {DENSE_VECTOR_SIZE}, "
            f"but model returned {dimension}."
        )

    return model


def load_sparse_model() -> SparseTextEmbedding:
    return SparseTextEmbedding(
        model_name=SPARSE_MODEL_NAME,
        language=BM25_LANGUAGE,
        avg_len=BM25_AVG_DOCUMENT_LENGTH,
    )



# ---------------------------------------------------------------------------
# Upserts and deletions
# ---------------------------------------------------------------------------

def upsert_records(
    client: QdrantClient,
    dense_model: SentenceTransformer,
    sparse_model: SparseTextEmbedding,
    records: Sequence[dict[str, Any]],
) -> int:

    if not records:
        return 0

    texts = [get_document_text(record) for record in records]

    # EmbeddingGemma document prompt.
    document_texts = [
        f"title: none | text: {text}"
        for text in texts
    ]

    dense_vectors = dense_model.encode(
        document_texts,
        batch_size=DENSE_ENCODING_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    sparse_vectors = list(sparse_model.embed(texts))

    if len(dense_vectors) != len(records):
        raise RuntimeError("Dense embedding count does not match record count.")

    if len(sparse_vectors) != len(records):
        raise RuntimeError("Sparse embedding count does not match record count.")

    points: list[models.PointStruct] = []

    for record, dense_vector, sparse_vector in zip(
        records,
        dense_vectors,
        sparse_vectors,
        strict=True,
    ):
        record_id = get_record_id(record)

        point = models.PointStruct(
            id=qdrant_point_id(record_id),
            vector={
                DENSE_VECTOR_NAME: dense_vector.tolist(),
                SPARSE_VECTOR_NAME: models.SparseVector(
                    indices=[
                        int(index)
                        for index in sparse_vector.indices.tolist()
                    ],
                    values=[
                        float(value)
                        for value in sparse_vector.values.tolist()
                    ],
                ),
            },
            payload=build_payload(record),
        )

        points.append(point)

    client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=points,
        wait=True,
    )

    return len(points)

def delete_records(
    client: QdrantClient,
    records: Sequence[dict[str, Any]],
) -> int:
    if not records:
        return 0

    point_ids = [
        qdrant_point_id(get_record_id(record))
        for record in records
    ]

    client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=models.PointIdsList(
            points=point_ids,
        ),
        wait=True,
    )

    return len(point_ids)


def index_products() -> tuple[int , int , int]:
    client = create_client()
    ensure_collection(client)

    dense_model = load_dense_model()
    sparse_model = load_sparse_model()

    processed = 0
    upserted  = 0
    deleted = 0

    records = read_jsonl(INPUT_JSONL)

    for batch_number , batch in enumerate(
        batched(records, READ_BATCH_SIZE),
        start=1,
    ):
        upsert_batch = [
            record
            for record in batch
            if get_operation(record) == "upsert"
        ]

        delete_batch = [
            record
            for record in batch
            if get_operation(record) == "delete"
        ]

        upserted += upsert_records(
            client=client,
            dense_model=dense_model,
            sparse_model=sparse_model,
            records=upsert_batch,
        )

        deleted += delete_records(
            client=client,
            records=delete_batch,
        )

        processed += len(batch)

        print(
            f"Batch {batch_number}: "
            f"processed={processed:,}, "
            f"upserted={upserted:,}, "
            f"deleted={deleted:,}"
        )

    return processed, upserted, deleted


def main() -> None:
    load_dotenv()

    if READ_BATCH_SIZE < 1:
        raise ValueError("READ_BATCH_SIZE must be positive.")

    processed, upserted, deleted = index_products()

    print()
    print("Qdrant indexing completed.")
    print(f"Input file: {INPUT_JSONL.resolve()}")
    print(f"Collection: {QDRANT_COLLECTION}")
    print(f"Processed: {processed:,}")
    print(f"Upserted: {upserted:,}")
    print(f"Deleted: {deleted:,}")


if __name__ == "__main__":
    main()