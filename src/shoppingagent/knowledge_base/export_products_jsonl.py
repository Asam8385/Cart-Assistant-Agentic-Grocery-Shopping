from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Iterator

import mysql.connector

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "CHANGE_ME")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "shopping_agent")

DATA_DIRECTORY = Path(__file__).resolve().parent / "data"

# Complete active-catalog snapshot.
SNAPSHOT_OUTPUT = DATA_DIRECTORY / "products.jsonl"

# Latest pending UPSERT and DELETE events.
PENDING_CHANGES_OUTPUT = (
    DATA_DIRECTORY / "products_pending_changes.jsonl"
)

EXPORT_FULL_SNAPSHOT = True
EXPORT_PENDING_CHANGES = True

FETCH_BATCH_SIZE = 1000


# ---------------------------------------------------------------------------
# Configuration and database helpers
# ---------------------------------------------------------------------------

def validate_configuration() -> None:
    if MYSQL_PASSWORD == "CHANGE_ME" or not MYSQL_PASSWORD:
        raise SystemExit(
            "Set MYSQL_PASSWORD in the script or as an environment variable."
        )

    if not re.fullmatch(r"[A-Za-z0-9_]+", MYSQL_DATABASE):
        raise SystemExit(
            "MYSQL_DATABASE may contain only letters, digits, and underscores."
        )

    if FETCH_BATCH_SIZE < 1:
        raise SystemExit("FETCH_BATCH_SIZE must be positive.")


def connection_config() -> dict[str, Any]:
    config: dict[str, Any] = {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
        "database": MYSQL_DATABASE,
        "charset": "utf8mb4",
        "connection_timeout": 15,
        "autocommit": True,
    }

    ssl_ca = os.getenv("MYSQL_SSL_CA")

    if ssl_ca:
        config.update(
            ssl_ca=ssl_ca,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )

    return config


def decode_json(
    value: Any,
    default: Any,
) -> Any:
    if value is None:
        return default

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")

    if isinstance(value, str):
        return json.loads(value)

    return value


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def canonical_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def load_aliases(
    connection: Any,
) -> dict[int, list[str]]:
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                product_id,
                alias
            FROM product_aliases
            ORDER BY
                product_id,
                alias
            """
        )

        aliases: dict[int, list[str]] = defaultdict(list)

        for product_id, alias in cursor:
            aliases[int(product_id)].append(str(alias))

        return dict(aliases)

    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Retrieval-document creation
# ---------------------------------------------------------------------------

def build_chunk_text(
    row: dict[str, Any],
    aliases: list[str],
    dietary_tags: list[str],
    allergens: list[str],
) -> str:
    category_path = " > ".join(
        value
        for value in (
            row.get("parent_category_name"),
            row.get("category_name"),
        )
        if value
    )

    parts = [
        (
            f"Product: {row['brand_name']} "
            f"{row['product_name']}."
        ),
        f"Vendor: {row['vendor_name']}.",
        f"Category: {category_path}.",
        f"Variant size: {row['display_size']}.",
        (
            f"Identifiers: SKU {row['sku']}; "
            f"barcode {row['barcode']}."
        ),
    ]

    if aliases:
        parts.append(
            f"Also known as: {', '.join(aliases)}."
        )

    if row.get("description"):
        parts.append(
            f"Description: {row['description']}"
        )

    if row.get("ingredients"):
        parts.append(
            f"Ingredients: {row['ingredients']}."
        )

    if dietary_tags:
        parts.append(
            "Dietary and product tags: "
            f"{', '.join(dietary_tags)}."
        )

    if allergens:
        parts.append(
            "Contains or may contain: "
            f"{', '.join(allergens)}."
        )
    elif row.get("product_type") == "grocery":
        parts.append("Declared allergens: none.")

    return " ".join(parts)


def build_upsert_record(
    row: dict[str, Any],
    aliases: list[str],
    *,
    source_version: str,
    event_id: int | None = None,
) -> dict[str, Any]:
    dietary_tags = [
        str(value)
        for value in decode_json(
            row.get("dietary_tags"),
            [],
        )
    ]

    allergens = [
        str(value)
        for value in decode_json(
            row.get("allergens"),
            [],
        )
    ]

    size_value = row["size_value"]

    if isinstance(size_value, Decimal):
        size_value = float(size_value)

    category_path = " > ".join(
        value
        for value in (
            row.get("parent_category_name"),
            row.get("category_name"),
        )
        if value
    )

    chunk_text = build_chunk_text(
        row,
        aliases,
        dietary_tags,
        allergens,
    )

    metadata: dict[str, Any] = {
        "schema_version": "2.0",
        "source": "mysql",
        "document_type": "vendor_product_variant",

        "vendor_id": str(row["vendor_id"]),
        "vendor_key": row["vendor_key"],
        "vendor_name": row["vendor_name"],

        "product_id": str(row["product_id"]),
        "vendor_product_id": row["vendor_product_id"],

        "variant_id": str(row["variant_id"]),
        "vendor_variant_id": row["vendor_variant_id"],

        "sku": row["sku"],
        "barcode": row.get("barcode") or "",

        "brand": row["brand_name"],

        "category": row["category_name"],
        "category_slug": row["category_slug"],
        "parent_category": (
            row.get("parent_category_name")
            or ""
        ),
        "category_path": category_path,

        "product_type": row["product_type"],

        "size_value": size_value,
        "size_unit": row["size_unit"],
        "pack_count": int(row["pack_count"]),
        "display_size": row["display_size"],

        "country_of_origin": (
            row.get("country_of_origin")
            or ""
        ),

        "is_organic": bool(row["is_organic"]),
        "is_vegan": bool(row["is_vegan"]),
        "is_vegetarian": bool(row["is_vegetarian"]),
        "is_gluten_free": bool(row["is_gluten_free"]),
        "is_halal": bool(row["is_halal"]),

        "dietary_tags": dietary_tags,
        "allergens": allergens,
        "aliases": aliases,

        "source_version": source_version,
        "source_updated_at": utc_iso(
            row.get("source_updated_at")
        ),
    }

    content_hash = hashlib.sha256(
        chunk_text.encode("utf-8")
    ).hexdigest()

    metadata_hash = canonical_hash(metadata)

    record: dict[str, Any] = {
        "operation": "upsert",
        "_id": row["vector_record_id"],
        "source_version": source_version,
        "chunk_text": chunk_text,
        "content_hash": content_hash,
        "metadata_hash": metadata_hash,
        "metadata": metadata,
    }

    if event_id is not None:
        record["event_id"] = event_id

    return record


def build_delete_record(
    row: dict[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "vendor_id": str(row["outbox_vendor_id"]),
        "entity_type": row["entity_type"],
        "entity_id": str(row["entity_id"]),
    }

    if row.get("vendor_key"):
        metadata["vendor_key"] = row["vendor_key"]

    if row.get("vendor_product_id"):
        metadata["vendor_product_id"] = (
            row["vendor_product_id"]
        )

    if row.get("vendor_variant_id"):
        metadata["vendor_variant_id"] = (
            row["vendor_variant_id"]
        )

    return {
        "event_id": int(row["event_id"]),
        "operation": "delete",
        "_id": row["vector_record_id"],
        "source_version": row["outbox_source_version"],
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Snapshot query
# ---------------------------------------------------------------------------

SNAPSHOT_QUERY = """
    SELECT
        product.id AS product_id,
        product.vendor_id,
        product.vendor_product_id,
        product.name AS product_name,
        product.description,
        product.product_type,
        product.ingredients,
        product.allergens,
        product.dietary_tags,
        product.country_of_origin,
        product.is_organic,
        product.is_vegan,
        product.is_vegetarian,
        product.is_gluten_free,
        product.is_halal,
        product.version AS product_version,

        vendor.vendor_key,
        vendor.name AS vendor_name,

        brand.name AS brand_name,

        category.name AS category_name,
        category.slug AS category_slug,

        parent_category.name
            AS parent_category_name,

        variant.id AS variant_id,
        variant.vendor_variant_id,
        variant.vector_record_id,
        variant.sku,
        variant.barcode,
        variant.size_value,
        variant.size_unit,
        variant.pack_count,
        variant.display_size,
        variant.version AS variant_version,

        GREATEST(
            product.updated_at,
            variant.updated_at
        ) AS source_updated_at

    FROM product_variants AS variant

    INNER JOIN products AS product
        ON product.id = variant.product_id

    INNER JOIN vendors AS vendor
        ON vendor.id = product.vendor_id

    INNER JOIN brands AS brand
        ON brand.id = product.brand_id

    INNER JOIN categories AS category
        ON category.id = product.category_id

    LEFT JOIN categories AS parent_category
        ON parent_category.id = category.parent_id

    WHERE product.active = 1
      AND product.deleted_at IS NULL
      AND variant.active = 1
      AND variant.deleted_at IS NULL
      AND vendor.active = 1

    ORDER BY variant.id
"""


def iterate_snapshot_records(
    connection: Any,
    aliases_by_product: dict[int, list[str]],
) -> Iterator[dict[str, Any]]:
    cursor = connection.cursor(
        dictionary=True,
        buffered=False,
    )

    try:
        cursor.execute(SNAPSHOT_QUERY)

        while True:
            rows = cursor.fetchmany(FETCH_BATCH_SIZE)

            if not rows:
                break

            for row in rows:
                source_version = (
                    f"p{row['product_version']}"
                    f"-v{row['variant_version']}"
                )

                aliases = aliases_by_product.get(
                    int(row["product_id"]),
                    [],
                )

                yield build_upsert_record(
                    row,
                    aliases,
                    source_version=source_version,
                )

    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Pending changes query
# ---------------------------------------------------------------------------

PENDING_CHANGES_QUERY = """
    SELECT
        outbox.event_id,
        outbox.vector_record_id,
        outbox.vendor_id
            AS outbox_vendor_id,
        outbox.entity_type,
        outbox.entity_id,
        outbox.operation
            AS outbox_operation,
        outbox.source_version
            AS outbox_source_version,

        product.id AS product_id,
        product.vendor_id,
        product.vendor_product_id,
        product.name AS product_name,
        product.description,
        product.product_type,
        product.ingredients,
        product.allergens,
        product.dietary_tags,
        product.country_of_origin,
        product.is_organic,
        product.is_vegan,
        product.is_vegetarian,
        product.is_gluten_free,
        product.is_halal,
        product.active AS product_active,
        product.version AS product_version,

        vendor.vendor_key,
        vendor.name AS vendor_name,

        brand.name AS brand_name,

        category.name AS category_name,
        category.slug AS category_slug,

        parent_category.name
            AS parent_category_name,

        variant.id AS variant_id,
        variant.vendor_variant_id,
        variant.sku,
        variant.barcode,
        variant.size_value,
        variant.size_unit,
        variant.pack_count,
        variant.display_size,
        variant.active AS variant_active,
        variant.version AS variant_version,

        GREATEST(
            product.updated_at,
            variant.updated_at
        ) AS source_updated_at

    FROM catalog_outbox AS outbox

    INNER JOIN (
        SELECT
            vector_record_id,
            MAX(event_id) AS latest_event_id
        FROM catalog_outbox
        WHERE processed_at IS NULL
          AND available_at <= CURRENT_TIMESTAMP(6)
        GROUP BY vector_record_id
    ) AS latest_event
        ON latest_event.latest_event_id =
            outbox.event_id

    LEFT JOIN product_variants AS variant
        ON variant.vector_record_id =
            outbox.vector_record_id

    LEFT JOIN products AS product
        ON product.id = variant.product_id

    LEFT JOIN vendors AS vendor
        ON vendor.id = product.vendor_id

    LEFT JOIN brands AS brand
        ON brand.id = product.brand_id

    LEFT JOIN categories AS category
        ON category.id = product.category_id

    LEFT JOIN categories AS parent_category
        ON parent_category.id =
            category.parent_id

    ORDER BY outbox.event_id
"""


def iterate_pending_change_records(
    connection: Any,
    aliases_by_product: dict[int, list[str]],
) -> Iterator[dict[str, Any]]:
    cursor = connection.cursor(
        dictionary=True,
        buffered=False,
    )

    try:
        cursor.execute(PENDING_CHANGES_QUERY)

        while True:
            rows = cursor.fetchmany(FETCH_BATCH_SIZE)

            if not rows:
                break

            for row in rows:
                database_record_exists = (
                    row.get("variant_id") is not None
                    and row.get("product_id") is not None
                )

                currently_active = (
                    database_record_exists
                    and bool(row.get("product_active"))
                    and bool(row.get("variant_active"))
                )

                must_delete = (
                    row["outbox_operation"] == "DELETE"
                    or not currently_active
                )

                if must_delete:
                    yield build_delete_record(row)
                    continue

                aliases = aliases_by_product.get(
                    int(row["product_id"]),
                    [],
                )

                yield build_upsert_record(
                    row,
                    aliases,
                    source_version=(
                        row["outbox_source_version"]
                    ),
                    event_id=int(row["event_id"]),
                )

    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Atomic JSONL writer
# ---------------------------------------------------------------------------

def write_jsonl_atomically(
    output_path: Path,
    records: Iterable[dict[str, Any]],
) -> tuple[int, str]:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=str(output_path.parent),
    )

    record_count = 0
    file_hash = hashlib.sha256()

    try:
        with os.fdopen(
            descriptor,
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as output_file:
            for record in records:
                line = json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ) + "\n"

                output_file.write(line)
                file_hash.update(line.encode("utf-8"))
                record_count += 1

            output_file.flush()
            os.fsync(output_file.fileno())

        os.replace(
            temporary_path,
            output_path,
        )

        return record_count, file_hash.hexdigest()

    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    validate_configuration()

    connection = mysql.connector.connect(
        **connection_config()
    )

    try:
        timezone_cursor = connection.cursor()
        timezone_cursor.execute(
            "SET time_zone = '+00:00'"
        )
        timezone_cursor.close()

        aliases_by_product = load_aliases(connection)

        if EXPORT_FULL_SNAPSHOT:
            snapshot_records = iterate_snapshot_records(
                connection,
                aliases_by_product,
            )

            snapshot_count, snapshot_hash = (
                write_jsonl_atomically(
                    SNAPSHOT_OUTPUT,
                    snapshot_records,
                )
            )

            print(
                f"Exported {snapshot_count:,} active "
                f"records to {SNAPSHOT_OUTPUT.resolve()}"
            )
            print(
                f"Snapshot SHA-256: {snapshot_hash}"
            )

        if EXPORT_PENDING_CHANGES:
            pending_records = (
                iterate_pending_change_records(
                    connection,
                    aliases_by_product,
                )
            )

            pending_count, pending_hash = (
                write_jsonl_atomically(
                    PENDING_CHANGES_OUTPUT,
                    pending_records,
                )
            )

            print(
                f"Exported {pending_count:,} pending "
                f"changes to "
                f"{PENDING_CHANGES_OUTPUT.resolve()}"
            )
            print(
                f"Pending changes SHA-256: {pending_hash}"
            )

    finally:
        connection.close()


if __name__ == "__main__":
    main()