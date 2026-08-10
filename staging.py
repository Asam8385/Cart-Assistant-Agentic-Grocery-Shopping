from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import mysql.connector


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent
    / "data"
    / "products.jsonl"
)


def database_name() -> str:
    value = os.getenv("MYSQL_DATABASE", "shopping_agent")
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise SystemExit(
            "MYSQL_DATABASE may contain only letters, digits, and underscores."
        )
    return value


def connection_kwargs() -> dict[str, Any]:
    password = os.getenv("MYSQL_PASSWORD")
    if not password:
        raise SystemExit("MYSQL_PASSWORD is required.")

    config: dict[str, Any] = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": password,
        "database": database_name(),
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


def decode_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return json.loads(value)
    return value


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def parse_since(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def load_aliases(connection: Any) -> dict[int, list[str]]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT product_id, alias
        FROM product_aliases
        ORDER BY product_id, alias
        """
    )

    aliases: dict[int, list[str]] = defaultdict(list)
    for product_id, alias in cursor:
        aliases[int(product_id)].append(str(alias))

    cursor.close()
    return dict(aliases)


def build_chunk_text(
    row: dict[str, Any],
    aliases: list[str],
    dietary_tags: list[str],
    allergens: list[str],
) -> str:
    category_path = " > ".join(
        value
        for value in (
            row["parent_category_name"],
            row["category_name"],
        )
        if value
    )

    parts = [
        f"Product: {row['brand_name']} {row['product_name']}.",
        f"Category: {category_path}.",
        f"Variant size: {row['display_size']}.",
        f"Identifiers: SKU {row['sku']}; barcode {row['barcode']}.",
    ]

    if aliases:
        parts.append(f"Also known as: {', '.join(aliases)}.")

    if row["description"]:
        parts.append(f"Description: {row['description']}")

    if row["ingredients"]:
        parts.append(f"Ingredients: {row['ingredients']}.")

    if dietary_tags:
        parts.append(
            f"Dietary and product tags: {', '.join(dietary_tags)}."
        )

    if allergens:
        parts.append(f"Contains or may contain: {', '.join(allergens)}.")
    elif row["product_type"] == "grocery":
        parts.append("Declared allergens: none.")

    return " ".join(parts)


def build_record(
    row: dict[str, Any],
    aliases: list[str],
) -> dict[str, Any]:
    dietary_tags = [
        str(value)
        for value in decode_json(row["dietary_tags"], [])
    ]
    allergens = [
        str(value)
        for value in decode_json(row["allergens"], [])
    ]

    category_path = " > ".join(
        value
        for value in (
            row["parent_category_name"],
            row["category_name"],
        )
        if value
    )

    chunk_text = build_chunk_text(
        row,
        aliases,
        dietary_tags,
        allergens,
    )

    content_hash = hashlib.sha256(
        chunk_text.encode("utf-8")
    ).hexdigest()

    size_value = row["size_value"]
    if isinstance(size_value, Decimal):
        size_value = float(size_value)

    metadata: dict[str, Any] = {
        "schema_version": "1.0",
        "source": "mysql",
        "document_type": "product_variant",
        "product_id": str(row["product_id"]),
        "variant_id": str(row["variant_id"]),
        "product_key": row["product_key"],
        "variant_key": row["variant_key"],
        "sku": row["sku"],
        "barcode": row["barcode"],
        "brand": row["brand_name"],
        "category": row["category_name"],
        "category_slug": row["category_slug"],
        "parent_category": row["parent_category_name"],
        "category_path": category_path,
        "product_type": row["product_type"],
        "size_value": size_value,
        "size_unit": row["size_unit"],
        "pack_count": int(row["pack_count"]),
        "display_size": row["display_size"],
        "country_of_origin": row["country_of_origin"] or "",
        "is_organic": bool(row["is_organic"]),
        "is_vegan": bool(row["is_vegan"]),
        "is_vegetarian": bool(row["is_vegetarian"]),
        "is_gluten_free": bool(row["is_gluten_free"]),
        "is_halal": bool(row["is_halal"]),
        "dietary_tags": dietary_tags,
        "allergens": allergens,
        "aliases": aliases,
        "source_updated_at": iso_utc(row["source_updated_at"]),
        "content_hash": content_hash,
    }

    return {
        "_id": row["variant_key"],
        "chunk_text": chunk_text,
        "metadata": metadata,
    }


def export_jsonl(
    output_path: Path,
    batch_size: int,
    since: datetime | None,
    limit: int | None,
) -> tuple[int, str]:
    connection = mysql.connector.connect(**connection_kwargs())
    temporary_path: str | None = None

    try:
        timezone_cursor = connection.cursor()
        timezone_cursor.execute("SET time_zone = '+00:00'")
        timezone_cursor.close()

        aliases_by_product = load_aliases(connection)

        where_clauses = [
            "p.active = 1",
            "v.active = 1",
            "p.deleted_at IS NULL",
            "v.deleted_at IS NULL",
        ]
        parameters: list[Any] = []

        if since is not None:
            where_clauses.append(
                "GREATEST(p.updated_at, v.updated_at) >= %s"
            )
            parameters.append(since)

        query = f"""
            SELECT
                p.id AS product_id,
                p.product_key,
                p.name AS product_name,
                p.description,
                p.product_type,
                p.ingredients,
                p.allergens,
                p.dietary_tags,
                p.country_of_origin,
                p.is_organic,
                p.is_vegan,
                p.is_vegetarian,
                p.is_gluten_free,
                p.is_halal,

                b.name AS brand_name,

                c.name AS category_name,
                c.slug AS category_slug,
                parent_category.name AS parent_category_name,

                v.id AS variant_id,
                v.variant_key,
                v.sku,
                v.barcode,
                v.size_value,
                v.size_unit,
                v.pack_count,
                v.display_size,

                GREATEST(
                    p.updated_at,
                    v.updated_at
                ) AS source_updated_at

            FROM product_variants AS v
            INNER JOIN products AS p
                ON p.id = v.product_id
            INNER JOIN brands AS b
                ON b.id = p.brand_id
            INNER JOIN categories AS c
                ON c.id = p.category_id
            LEFT JOIN categories AS parent_category
                ON parent_category.id = c.parent_id

            WHERE {" AND ".join(where_clauses)}
            ORDER BY v.id
        """

        if limit is not None:
            query += " LIMIT %s"
            parameters.append(limit)

        cursor = connection.cursor(
            dictionary=True,
            buffered=False,
        )
        cursor.execute(query, tuple(parameters))

        output_path.parent.mkdir(parents=True, exist_ok=True)

        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=str(output_path.parent),
        )

        record_count = 0
        export_hash = hashlib.sha256()

        with os.fdopen(
            file_descriptor,
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as output_file:
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break

                for row in rows:
                    product_id = int(row["product_id"])
                    record = build_record(
                        row,
                        aliases_by_product.get(product_id, []),
                    )
                    line = json.dumps(
                        record,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ) + "\n"

                    output_file.write(line)
                    export_hash.update(line.encode("utf-8"))
                    record_count += 1

            output_file.flush()
            os.fsync(output_file.fileno())

        cursor.close()

        os.replace(temporary_path, output_path)
        temporary_path = None

        return record_count, export_hash.hexdigest()
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stream active product variants from MySQL into "
            "Pinecone-ready JSONL."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output file. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Rows fetched from MySQL per batch. Default: 1000.",
    )
    parser.add_argument(
        "--since",
        help=(
            "Optional ISO-8601 timestamp for incremental export, "
            "for example 2026-08-10T00:00:00Z."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of records for testing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive.")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive.")

    since = parse_since(args.since)

    count, digest = export_jsonl(
        output_path=args.output.resolve(),
        batch_size=args.batch_size,
        since=since,
        limit=args.limit,
    )

    print(f"Exported {count:,} records to {args.output.resolve()}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()