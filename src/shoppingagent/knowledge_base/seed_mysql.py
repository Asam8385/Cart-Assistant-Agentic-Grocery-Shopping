from __future__ import annotations

import hashlib
import json
import os
import random
import re
import uuid
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence

import mysql.connector
from mysql.connector import MySQLConnection


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "8385")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "shopping_agent")

PRODUCT_COUNT = 5000
VARIANTS_PER_PRODUCT = 2
BATCH_SIZE = 500
RANDOM_SEED = 20260810

# Set True only when you intentionally want to delete and rebuild
# the synthetic catalog tables.
RESET_TABLES = False


# ---------------------------------------------------------------------------
# Synthetic catalog configuration
# ---------------------------------------------------------------------------

VENDORS = (
    ("freshcart", "FreshCart Market", "USD"),
    ("quickbasket", "QuickBasket", "USD"),
    ("dailygrocer", "Daily Grocer", "USD"),
    ("urbanfoods", "Urban Foods", "USD"),
)

STORES = (
    (
        "freshcart",
        "freshcart-austin",
        "FreshCart Austin",
        "Austin",
        "US",
        30.2672,
        -97.7431,
    ),
    (
        "freshcart",
        "freshcart-seattle",
        "FreshCart Seattle",
        "Seattle",
        "US",
        47.6062,
        -122.3321,
    ),
    (
        "quickbasket",
        "quickbasket-new-york",
        "QuickBasket New York",
        "New York",
        "US",
        40.7128,
        -74.0060,
    ),
    (
        "quickbasket",
        "quickbasket-boston",
        "QuickBasket Boston",
        "Boston",
        "US",
        42.3601,
        -71.0589,
    ),
    (
        "dailygrocer",
        "dailygrocer-chicago",
        "Daily Grocer Chicago",
        "Chicago",
        "US",
        41.8781,
        -87.6298,
    ),
    (
        "dailygrocer",
        "dailygrocer-denver",
        "Daily Grocer Denver",
        "Denver",
        "US",
        39.7392,
        -104.9903,
    ),
    (
        "urbanfoods",
        "urbanfoods-miami",
        "Urban Foods Miami",
        "Miami",
        "US",
        25.7617,
        -80.1918,
    ),
    (
        "urbanfoods",
        "urbanfoods-portland",
        "Urban Foods Portland",
        "Portland",
        "US",
        45.5152,
        -122.6784,
    ),
)

ROOT_CATEGORIES = (
    ("fresh-food", "Fresh Food"),
    ("dairy-bakery", "Dairy & Bakery"),
    ("pantry", "Pantry"),
    ("snacks-drinks", "Snacks & Drinks"),
    ("frozen-meat", "Frozen, Meat & Seafood"),
    ("personal-household", "Personal & Household"),
)

STYLES = (
    "Classic",
    "Original",
    "Select",
    "Signature",
    "Everyday",
    "Family Choice",
    "Premium",
    "Value Pack",
)

CATALOG: tuple[dict[str, Any], ...] = (
    {
        "slug": "fresh-fruit",
        "parent": "fresh-food",
        "name": "Fresh Fruit",
        "items": (
            "Banana",
            "Apple",
            "Avocado",
            "Orange",
            "Mango",
            "Strawberry",
            "Blueberry",
            "Grapes",
            "Pineapple",
            "Watermelon",
            "Pear",
            "Kiwi",
        ),
        "brands": (
            "O Organics",
            "FreshFields",
            "Nature Basket",
            "Green Valley",
            "Daily Harvest",
        ),
        "modifiers": (
            "Organic",
            "Fresh",
            "Ripe",
            "Premium",
            "Farm Fresh",
            "Local",
        ),
        "sizes": (
            ("1", "kg"),
            ("500", "g"),
            ("4", "ct"),
            ("6", "ct"),
        ),
        "price": ("1.50", "9.00"),
        "aisle": "Produce",
        "product_type": "grocery",
    },
    {
        "slug": "fresh-vegetables",
        "parent": "fresh-food",
        "name": "Fresh Vegetables",
        "items": (
            "Potato",
            "Tomato",
            "Onion",
            "Carrot",
            "Broccoli",
            "Spinach",
            "Cucumber",
            "Bell Pepper",
            "Cauliflower",
            "Cabbage",
            "Garlic",
            "Sweet Potato",
        ),
        "brands": (
            "O Organics",
            "FreshFields",
            "Green Valley",
            "Farmstead",
            "Nature Basket",
        ),
        "modifiers": (
            "Organic",
            "Fresh",
            "Local",
            "Premium",
            "Farm Fresh",
            "Washed",
        ),
        "sizes": (
            ("1", "kg"),
            ("500", "g"),
            ("3", "ct"),
            ("6", "ct"),
        ),
        "price": ("1.00", "8.00"),
        "aisle": "Produce",
        "product_type": "grocery",
    },
    {
        "slug": "milk-eggs-chilled",
        "parent": "dairy-bakery",
        "name": "Milk, Eggs & Chilled",
        "items": (
            "Whole Milk",
            "Low Fat Milk",
            "Skim Milk",
            "Greek Yogurt",
            "Plain Yogurt",
            "Cheddar Cheese",
            "Mozzarella Cheese",
            "Salted Butter",
            "Free Range Eggs",
            "Cream Cheese",
            "Chocolate Milk",
            "Fresh Cream",
        ),
        "brands": (
            "O Organics",
            "MeadowFresh",
            "DairyPure",
            "Happy Farms",
            "Morning Valley",
        ),
        "modifiers": (
            "Organic",
            "Fresh",
            "Reduced Fat",
            "Premium",
            "Lactose Free",
            "Farm Fresh",
        ),
        "sizes": (
            ("1", "l"),
            ("500", "ml"),
            ("200", "g"),
            ("12", "ct"),
        ),
        "price": ("2.00", "12.00"),
        "aisle": "Chilled",
        "product_type": "grocery",
    },
    {
        "slug": "rice-pasta-pantry",
        "parent": "pantry",
        "name": "Rice, Pasta & Pantry",
        "items": (
            "Basmati Rice",
            "Jasmine Rice",
            "Brown Rice",
            "White Rice",
            "Spaghetti",
            "Penne Pasta",
            "Macaroni",
            "Rolled Oats",
            "Quinoa",
            "Chickpeas",
            "Kidney Beans",
            "Peanut Butter",
        ),
        "brands": (
            "Golden Grain",
            "Pantry Select",
            "O Organics",
            "Kitchen Harvest",
            "Daily Choice",
        ),
        "modifiers": (
            "Premium",
            "Organic",
            "Whole Grain",
            "Classic",
            "Quick Cook",
            "Family",
        ),
        "sizes": (
            ("500", "g"),
            ("1", "kg"),
            ("2", "kg"),
            ("5", "kg"),
        ),
        "price": ("2.00", "25.00"),
        "aisle": "Pantry",
        "product_type": "grocery",
    },
    {
        "slug": "snacks-beverages",
        "parent": "snacks-drinks",
        "name": "Snacks & Beverages",
        "items": (
            "Potato Chips",
            "Tortilla Chips",
            "Salted Crackers",
            "Chocolate Cookies",
            "Granola Bars",
            "Mixed Nuts",
            "Popcorn",
            "Orange Juice",
            "Apple Juice",
            "Mineral Water",
            "Ground Coffee",
            "Green Tea",
        ),
        "brands": (
            "SnackTime",
            "Daily Refresh",
            "O Organics",
            "Happy Bites",
            "FreshSip",
        ),
        "modifiers": (
            "Classic",
            "Lightly Salted",
            "Organic",
            "Premium",
            "No Added Sugar",
            "Family",
        ),
        "sizes": (
            ("200", "g"),
            ("500", "ml"),
            ("1", "l"),
            ("12", "ct"),
        ),
        "price": ("1.00", "18.00"),
        "aisle": "Snacks and Drinks",
        "product_type": "grocery",
    },
    {
        "slug": "frozen-meat-seafood",
        "parent": "frozen-meat",
        "name": "Frozen, Meat & Seafood",
        "items": (
            "Frozen Mixed Vegetables",
            "French Fries",
            "Frozen Pizza",
            "Chicken Nuggets",
            "Chicken Breast",
            "Whole Chicken",
            "Ground Beef",
            "Beef Steak",
            "Salmon Fillet",
            "Tuna Steak",
            "Shrimp",
            "Fish Fingers",
        ),
        "brands": (
            "FreezerFresh",
            "Butcher Select",
            "Ocean Catch",
            "Halal Harvest",
            "QuickMeal",
        ),
        "modifiers": (
            "Fresh",
            "Premium",
            "Halal Certified",
            "Farm Raised",
            "Wild Caught",
            "Family",
        ),
        "sizes": (
            ("250", "g"),
            ("500", "g"),
            ("1", "kg"),
            ("4", "ct"),
        ),
        "price": ("4.00", "40.00"),
        "aisle": "Frozen and Meat",
        "product_type": "grocery",
    },
    {
        "slug": "personal-care",
        "parent": "personal-household",
        "name": "Personal Care",
        "items": (
            "Sensitive Toothpaste",
            "Whitening Toothpaste",
            "Fluoride Toothpaste",
            "Soft Toothbrush",
            "Mouthwash",
            "Dental Floss",
            "Body Wash",
            "Shampoo",
            "Conditioner",
            "Hand Soap",
            "Deodorant",
            "Face Cleanser",
        ),
        "brands": (
            "Sensodyne",
            "Colgate",
            "Oral-B",
            "CareWell",
            "FreshCare",
        ),
        "modifiers": (
            "Clinical",
            "Gentle",
            "Fresh Mint",
            "Advanced",
            "Daily",
            "Intensive",
        ),
        "sizes": (
            ("75", "ml"),
            ("100", "ml"),
            ("250", "ml"),
            ("2", "ct"),
        ),
        "price": ("2.00", "18.00"),
        "aisle": "Personal Care",
        "product_type": "personal_care",
    },
    {
        "slug": "household",
        "parent": "personal-household",
        "name": "Household",
        "items": (
            "Laundry Detergent",
            "Dishwashing Liquid",
            "All Purpose Cleaner",
            "Bathroom Cleaner",
            "Glass Cleaner",
            "Disinfecting Wipes",
            "Paper Towels",
            "Toilet Paper",
            "Trash Bags",
            "Aluminum Foil",
            "Food Storage Bags",
            "Kitchen Sponges",
        ),
        "brands": (
            "CleanHome",
            "BrightDay",
            "HomeGuard",
            "EcoLiving",
            "Daily Choice",
        ),
        "modifiers": (
            "Original",
            "Lemon Fresh",
            "Eco Friendly",
            "Heavy Duty",
            "Sensitive",
            "Value",
        ),
        "sizes": (
            ("500", "ml"),
            ("1", "l"),
            ("6", "ct"),
            ("12", "ct"),
        ),
        "price": ("2.00", "25.00"),
        "aisle": "Household",
        "product_type": "household",
    },
)

COMMON_ALIASES: dict[str, tuple[str, ...]] = {
    "Banana": ("bananas",),
    "Avocado": ("avocados",),
    "Potato": ("potatoes",),
    "Tomato": ("tomatoes",),
    "Whole Milk": ("milk", "full cream milk", "fresh milk"),
    "Low Fat Milk": ("low-fat milk", "reduced fat milk"),
    "Sensitive Toothpaste": (
        "toothpaste for sensitive teeth",
        "sensitivity toothpaste",
        "sensitive teeth paste",
    ),
    "Free Range Eggs": ("eggs", "free-range eggs"),
    "Ground Beef": ("minced beef", "beef mince"),
    "Shrimp": ("prawns",),
}


# ---------------------------------------------------------------------------
# General helpers
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

    if PRODUCT_COUNT < 1:
        raise SystemExit("PRODUCT_COUNT must be positive.")

    if not 1 <= VARIANTS_PER_PRODUCT <= 5:
        raise SystemExit("VARIANTS_PER_PRODUCT must be between 1 and 5.")


def connection_config(
    *,
    include_database: bool,
    autocommit: bool = False,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
        "charset": "utf8mb4",
        "connection_timeout": 15,
        "autocommit": autocommit,
    }

    if include_database:
        config["database"] = MYSQL_DATABASE

    ssl_ca = os.getenv("MYSQL_SSL_CA")
    if ssl_ca:
        config.update(
            ssl_ca=ssl_ca,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )

    return config


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: Any) -> str:
    serialized = compact_json(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def ean13(base: str) -> str:
    if len(base) != 12 or not base.isdigit():
        raise ValueError("EAN-13 base must contain exactly 12 digits.")

    weighted_sum = sum(
        int(character) * (1 if index % 2 == 0 else 3)
        for index, character in enumerate(base)
    )
    checksum = (10 - weighted_sum % 10) % 10
    return f"{base}{checksum}"


def format_size(value: Decimal, unit: str) -> str:
    return f"{format(value.normalize(), 'f')} {unit}"


def execute_batches(
    cursor: Any,
    statement: str,
    rows: Sequence[tuple[Any, ...]],
) -> None:
    for start in range(0, len(rows), BATCH_SIZE):
        cursor.executemany(
            statement,
            rows[start : start + BATCH_SIZE],
        )


def aliases_for(item: str) -> list[str]:
    aliases = {item.casefold()}
    aliases.update(
        alias.casefold()
        for alias in COMMON_ALIASES.get(item, ())
    )
    return sorted(aliases)


def product_flags(
    *,
    category_slug: str,
    modifier: str,
    brand: str,
    product_type: str,
) -> dict[str, bool]:
    food = product_type == "grocery"

    plant_categories = {
        "fresh-fruit",
        "fresh-vegetables",
        "rice-pasta-pantry",
        "snacks-beverages",
    }

    return {
        "is_organic": (
            "organic" in normalize(modifier)
            or brand == "O Organics"
        ),
        "is_vegan": category_slug in plant_categories,
        "is_vegetarian": (
            food and category_slug != "frozen-meat-seafood"
        ),
        "is_gluten_free": (
            category_slug
            in {
                "fresh-fruit",
                "fresh-vegetables",
                "milk-eggs-chilled",
                "frozen-meat-seafood",
            }
            or "gluten free" in normalize(modifier)
        ),
        "is_halal": (
            "halal" in normalize(modifier)
            or brand == "Halal Harvest"
        ),
    }


def allergens_for(item: str) -> list[str]:
    text = normalize(item)
    allergens: set[str] = set()

    if any(
        value in text
        for value in (
            "milk",
            "yogurt",
            "cheese",
            "butter",
            "cream",
        )
    ):
        allergens.add("milk")

    if "egg" in text:
        allergens.add("eggs")

    if any(
        value in text
        for value in (
            "pasta",
            "cracker",
            "cookie",
            "pizza",
        )
    ):
        allergens.add("wheat")

    if "peanut" in text:
        allergens.add("peanuts")

    if "nuts" in text:
        allergens.add("tree nuts")

    if "shrimp" in text:
        allergens.add("shellfish")

    if any(
        value in text
        for value in (
            "salmon",
            "tuna",
            "fish",
        )
    ):
        allergens.add("fish")

    return sorted(allergens)


# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

def create_database() -> None:
    connection = mysql.connector.connect(
        **connection_config(include_database=False)
    )

    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`
            CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
            """
        )
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def create_schema(
    connection: MySQLConnection,
    *,
    reset_tables: bool,
) -> None:
    cursor = connection.cursor()

    if reset_tables:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        try:
            for table_name in (
                "kb_index_state",
                "catalog_outbox",
                "store_offers",
                "product_aliases",
                "product_variants",
                "products",
                "vendor_sync_runs",
                "stores",
                "brands",
                "categories",
                "vendors",
            ):
                cursor.execute(
                    f"DROP TABLE IF EXISTS `{table_name}`"
                )
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    statements = (
        """
        CREATE TABLE IF NOT EXISTS vendors (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            vendor_key VARCHAR(120) NOT NULL,
            name VARCHAR(180) NOT NULL,
            currency CHAR(3) NOT NULL,
            active TINYINT(1) NOT NULL DEFAULT 1,
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),

            PRIMARY KEY (id),
            UNIQUE KEY uq_vendors_key (vendor_key)
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS vendor_sync_runs (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            sync_id CHAR(36) NOT NULL,
            vendor_id BIGINT UNSIGNED NOT NULL,
            status ENUM(
                'RUNNING',
                'COMPLETED',
                'FAILED'
            ) NOT NULL,
            products_seen INT UNSIGNED NOT NULL DEFAULT 0,
            variants_seen INT UNSIGNED NOT NULL DEFAULT 0,
            error_message TEXT NULL,
            started_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            completed_at DATETIME(6) NULL,

            PRIMARY KEY (id),
            UNIQUE KEY uq_vendor_sync_id (sync_id),
            KEY ix_vendor_sync_vendor (vendor_id, started_at),

            CONSTRAINT fk_vendor_sync_vendor
                FOREIGN KEY (vendor_id)
                REFERENCES vendors(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS categories (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            parent_id BIGINT UNSIGNED NULL,
            slug VARCHAR(120) NOT NULL,
            name VARCHAR(160) NOT NULL,
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),

            PRIMARY KEY (id),
            UNIQUE KEY uq_categories_slug (slug),
            KEY ix_categories_parent (parent_id),

            CONSTRAINT fk_categories_parent
                FOREIGN KEY (parent_id)
                REFERENCES categories(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS brands (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            brand_code VARCHAR(120) NOT NULL,
            name VARCHAR(160) NOT NULL,
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),

            PRIMARY KEY (id),
            UNIQUE KEY uq_brands_code (brand_code),
            UNIQUE KEY uq_brands_name (name)
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS stores (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            vendor_id BIGINT UNSIGNED NOT NULL,
            store_key VARCHAR(120) NOT NULL,
            name VARCHAR(180) NOT NULL,
            city VARCHAR(120) NOT NULL,
            country_code CHAR(2) NOT NULL,
            latitude DECIMAL(9,6) NULL,
            longitude DECIMAL(9,6) NULL,
            currency CHAR(3) NOT NULL,
            active TINYINT(1) NOT NULL DEFAULT 1,
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),

            PRIMARY KEY (id),
            UNIQUE KEY uq_stores_key (store_key),
            KEY ix_stores_vendor_active (vendor_id, active),

            CONSTRAINT fk_stores_vendor
                FOREIGN KEY (vendor_id)
                REFERENCES vendors(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS products (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            vendor_id BIGINT UNSIGNED NOT NULL,
            vendor_product_id VARCHAR(160) NOT NULL,
            product_key VARCHAR(200) NOT NULL,
            category_id BIGINT UNSIGNED NOT NULL,
            brand_id BIGINT UNSIGNED NOT NULL,
            name VARCHAR(255) NOT NULL,
            normalized_name VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            product_type VARCHAR(64) NOT NULL,
            ingredients TEXT NULL,
            allergens JSON NOT NULL,
            dietary_tags JSON NOT NULL,
            search_keywords JSON NOT NULL,
            attributes JSON NOT NULL,
            country_of_origin CHAR(2) NULL,
            is_organic TINYINT(1) NOT NULL DEFAULT 0,
            is_vegan TINYINT(1) NOT NULL DEFAULT 0,
            is_vegetarian TINYINT(1) NOT NULL DEFAULT 0,
            is_gluten_free TINYINT(1) NOT NULL DEFAULT 0,
            is_halal TINYINT(1) NOT NULL DEFAULT 0,
            active TINYINT(1) NOT NULL DEFAULT 1,
            deleted_at DATETIME(6) NULL,
            last_seen_sync_id CHAR(36) NULL,
            source_hash CHAR(64) NOT NULL,
            version BIGINT UNSIGNED NOT NULL DEFAULT 1,
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),

            PRIMARY KEY (id),
            UNIQUE KEY uq_vendor_product (
                vendor_id,
                vendor_product_id
            ),
            UNIQUE KEY uq_products_key (product_key),
            KEY ix_products_vendor_active (
                vendor_id,
                active
            ),
            KEY ix_products_vendor_sync (
                vendor_id,
                last_seen_sync_id
            ),
            KEY ix_products_updated (updated_at),
            FULLTEXT KEY ft_products_search (
                name,
                description,
                ingredients
            ),

            CONSTRAINT fk_products_vendor
                FOREIGN KEY (vendor_id)
                REFERENCES vendors(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE,

            CONSTRAINT fk_products_category
                FOREIGN KEY (category_id)
                REFERENCES categories(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE,

            CONSTRAINT fk_products_brand
                FOREIGN KEY (brand_id)
                REFERENCES brands(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS product_variants (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            product_id BIGINT UNSIGNED NOT NULL,
            vendor_variant_id VARCHAR(180) NOT NULL,
            vector_record_id VARCHAR(300) NOT NULL,
            sku VARCHAR(100) NOT NULL,
            barcode VARCHAR(32) NULL,
            size_value DECIMAL(12,3) NOT NULL,
            size_unit VARCHAR(24) NOT NULL,
            pack_count INT UNSIGNED NOT NULL DEFAULT 1,
            display_size VARCHAR(80) NOT NULL,
            attributes JSON NOT NULL,
            active TINYINT(1) NOT NULL DEFAULT 1,
            deleted_at DATETIME(6) NULL,
            last_seen_sync_id CHAR(36) NULL,
            source_hash CHAR(64) NOT NULL,
            version BIGINT UNSIGNED NOT NULL DEFAULT 1,
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),

            PRIMARY KEY (id),
            UNIQUE KEY uq_product_vendor_variant (
                product_id,
                vendor_variant_id
            ),
            UNIQUE KEY uq_vector_record_id (
                vector_record_id
            ),
            UNIQUE KEY uq_variants_sku (sku),
            UNIQUE KEY uq_variants_barcode (barcode),
            KEY ix_variants_product_active (
                product_id,
                active
            ),
            KEY ix_variants_sync (
                last_seen_sync_id
            ),

            CONSTRAINT fk_variants_product
                FOREIGN KEY (product_id)
                REFERENCES products(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS product_aliases (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            product_id BIGINT UNSIGNED NOT NULL,
            alias VARCHAR(255) NOT NULL,
            normalized_alias VARCHAR(255) NOT NULL,
            locale VARCHAR(16) NOT NULL DEFAULT 'en',
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),

            PRIMARY KEY (id),
            UNIQUE KEY uq_product_alias (
                product_id,
                normalized_alias,
                locale
            ),
            KEY ix_alias_normalized (normalized_alias),

            CONSTRAINT fk_alias_product
                FOREIGN KEY (product_id)
                REFERENCES products(id)
                ON DELETE CASCADE
                ON UPDATE CASCADE
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS store_offers (
            store_id BIGINT UNSIGNED NOT NULL,
            variant_id BIGINT UNSIGNED NOT NULL,
            price DECIMAL(12,2) NOT NULL,
            compare_at_price DECIMAL(12,2) NULL,
            currency CHAR(3) NOT NULL,
            stock_quantity INT UNSIGNED NOT NULL DEFAULT 0,
            is_available TINYINT(1) NOT NULL DEFAULT 0,
            min_order_quantity INT UNSIGNED NOT NULL DEFAULT 1,
            max_order_quantity INT UNSIGNED NOT NULL DEFAULT 1,
            aisle_location VARCHAR(120) NULL,
            last_checked_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),

            PRIMARY KEY (store_id, variant_id),
            KEY ix_offers_variant_available (
                variant_id,
                is_available,
                price
            ),

            CONSTRAINT fk_offers_store
                FOREIGN KEY (store_id)
                REFERENCES stores(id)
                ON DELETE CASCADE
                ON UPDATE CASCADE,

            CONSTRAINT fk_offers_variant
                FOREIGN KEY (variant_id)
                REFERENCES product_variants(id)
                ON DELETE CASCADE
                ON UPDATE CASCADE
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS catalog_outbox (
            event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            vector_record_id VARCHAR(300) NOT NULL,
            vendor_id BIGINT UNSIGNED NOT NULL,
            entity_type VARCHAR(40) NOT NULL,
            entity_id BIGINT UNSIGNED NOT NULL,
            operation ENUM(
                'UPSERT',
                'DELETE'
            ) NOT NULL,
            changed_fields JSON NOT NULL,
            source_version VARCHAR(64) NOT NULL,
            attempts INT UNSIGNED NOT NULL DEFAULT 0,
            available_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),
            processed_at DATETIME(6) NULL,
            last_error TEXT NULL,
            created_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6),

            PRIMARY KEY (event_id),
            UNIQUE KEY uq_outbox_record_version (
                vector_record_id,
                source_version,
                operation
            ),
            KEY ix_outbox_pending (
                processed_at,
                available_at,
                event_id
            )
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_index_state (
            vector_record_id VARCHAR(300) NOT NULL,
            source_version VARCHAR(64) NOT NULL,
            content_hash CHAR(64) NULL,
            metadata_hash CHAR(64) NULL,
            dense_model VARCHAR(120) NULL,
            sparse_model VARCHAR(120) NULL,
            dense_indexed_at DATETIME(6) NULL,
            sparse_indexed_at DATETIME(6) NULL,
            last_event_id BIGINT UNSIGNED NOT NULL,
            last_error TEXT NULL,
            updated_at DATETIME(6) NOT NULL
                DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),

            PRIMARY KEY (vector_record_id),
            KEY ix_kb_state_event (last_event_id)
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4
          COLLATE=utf8mb4_unicode_ci
        """,
    )

    for statement in statements:
        cursor.execute(statement)

    connection.commit()
    cursor.close()


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

def seed_reference_data(
    connection: MySQLConnection,
) -> tuple[
    dict[str, int],
    dict[str, int],
    dict[str, int],
    dict[str, list[int]],
]:
    cursor = connection.cursor()

    cursor.executemany(
        """
        INSERT INTO vendors (
            vendor_key,
            name,
            currency,
            active
        )
        VALUES (%s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            currency = VALUES(currency),
            active = 1
        """,
        VENDORS,
    )

    cursor.execute(
        "SELECT id, vendor_key FROM vendors"
    )
    vendor_ids = {
        vendor_key: int(vendor_id)
        for vendor_id, vendor_key in cursor.fetchall()
    }

    cursor.executemany(
        """
        INSERT INTO categories (
            slug,
            name,
            parent_id
        )
        VALUES (%s, %s, NULL)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name)
        """,
        ROOT_CATEGORIES,
    )

    cursor.execute(
        """
        SELECT id, slug
        FROM categories
        WHERE parent_id IS NULL
        """
    )
    root_ids = {
        slug: int(category_id)
        for category_id, slug in cursor.fetchall()
    }

    leaf_rows = [
        (
            config["slug"],
            config["name"],
            root_ids[config["parent"]],
        )
        for config in CATALOG
    ]

    cursor.executemany(
        """
        INSERT INTO categories (
            slug,
            name,
            parent_id
        )
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            parent_id = VALUES(parent_id)
        """,
        leaf_rows,
    )

    cursor.execute("SELECT id, slug FROM categories")
    category_ids = {
        slug: int(category_id)
        for category_id, slug in cursor.fetchall()
    }

    brand_names = sorted(
        {
            brand
            for config in CATALOG
            for brand in config["brands"]
        }
    )

    brand_rows = [
        (slugify(name), name)
        for name in brand_names
    ]

    cursor.executemany(
        """
        INSERT INTO brands (
            brand_code,
            name
        )
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name)
        """,
        brand_rows,
    )

    cursor.execute("SELECT id, name FROM brands")
    brand_ids = {
        name: int(brand_id)
        for brand_id, name in cursor.fetchall()
    }

    vendor_currency = {
        vendor_key: currency
        for vendor_key, _, currency in VENDORS
    }

    store_rows = [
        (
            vendor_ids[vendor_key],
            store_key,
            store_name,
            city,
            country,
            latitude,
            longitude,
            vendor_currency[vendor_key],
        )
        for (
            vendor_key,
            store_key,
            store_name,
            city,
            country,
            latitude,
            longitude,
        ) in STORES
    ]

    cursor.executemany(
        """
        INSERT INTO stores (
            vendor_id,
            store_key,
            name,
            city,
            country_code,
            latitude,
            longitude,
            currency,
            active
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, 1
        )
        ON DUPLICATE KEY UPDATE
            vendor_id = VALUES(vendor_id),
            name = VALUES(name),
            city = VALUES(city),
            country_code = VALUES(country_code),
            latitude = VALUES(latitude),
            longitude = VALUES(longitude),
            currency = VALUES(currency),
            active = 1
        """,
        store_rows,
    )

    cursor.execute(
        """
        SELECT
            s.id,
            v.vendor_key
        FROM stores AS s
        INNER JOIN vendors AS v
            ON v.id = s.vendor_id
        WHERE s.active = 1
        """
    )

    store_ids_by_vendor: dict[str, list[int]] = defaultdict(list)

    for store_id, vendor_key in cursor.fetchall():
        store_ids_by_vendor[vendor_key].append(int(store_id))

    cursor.close()

    return (
        vendor_ids,
        category_ids,
        brand_ids,
        dict(store_ids_by_vendor),
    )


# ---------------------------------------------------------------------------
# Catalog generation
# ---------------------------------------------------------------------------

def create_sync_runs(
    cursor: Any,
    vendor_ids: dict[str, int],
) -> dict[str, str]:
    sync_ids = {
        vendor_key: str(uuid.uuid4())
        for vendor_key in vendor_ids
    }

    rows = [
        (
            sync_id,
            vendor_ids[vendor_key],
            "RUNNING",
        )
        for vendor_key, sync_id in sync_ids.items()
    ]

    cursor.executemany(
        """
        INSERT INTO vendor_sync_runs (
            sync_id,
            vendor_id,
            status
        )
        VALUES (%s, %s, %s)
        """,
        rows,
    )

    return sync_ids


def build_products(
    sync_ids: dict[str, str],
) -> list[dict[str, Any]]:
    vendor_keys = tuple(vendor[0] for vendor in VENDORS)
    products: list[dict[str, Any]] = []

    for index in range(PRODUCT_COUNT):
        vendor_key = vendor_keys[index % len(vendor_keys)]

        category_index = (
            index // len(vendor_keys)
        ) % len(CATALOG)

        category = CATALOG[category_index]

        serial = index // (
            len(vendor_keys) * len(CATALOG)
        )

        item = category["items"][
            serial % len(category["items"])
        ]

        modifier = category["modifiers"][
            (
                serial // len(category["items"])
            )
            % len(category["modifiers"])
        ]

        style = STYLES[
            (serial * 5 + category_index) % len(STYLES)
        ]

        brand = category["brands"][
            (
                serial * 3
                + category_index
                + index
            )
            % len(category["brands"])
        ]

        vendor_sequence = (
            index // len(vendor_keys)
        ) + 1

        vendor_product_id = (
            f"{vendor_key.upper()}-P-"
            f"{vendor_sequence:08d}"
        )

        product_key = (
            f"{vendor_key}:{vendor_product_id}"
        )

        name = f"{modifier} {item} {style}"
        aliases = aliases_for(item)

        flags = product_flags(
            category_slug=category["slug"],
            modifier=modifier,
            brand=brand,
            product_type=category["product_type"],
        )

        dietary_tags = sorted(
            key.removeprefix("is_").replace("_", "-")
            for key, enabled in flags.items()
            if enabled
        )

        allergens = allergens_for(item)

        ingredients = None
        if category["product_type"] == "grocery":
            ingredients = (
                f"{item}; see package label for complete "
                "ingredient and allergen information"
            )

        description = (
            f"{modifier} {item.lower()} from {brand}. "
            f"Part of the {style.lower()} range in "
            f"{category['name'].lower()}."
        )

        search_keywords = sorted(
            {
                normalize(item),
                normalize(name),
                normalize(brand),
                normalize(category["name"]),
                *[
                    normalize(alias)
                    for alias in aliases
                ],
            }
        )

        hash_payload = {
            "vendor_key": vendor_key,
            "vendor_product_id": vendor_product_id,
            "category": category["slug"],
            "brand": brand,
            "name": name,
            "description": description,
            "ingredients": ingredients,
            "allergens": allergens,
            "dietary_tags": dietary_tags,
            "search_keywords": search_keywords,
            "flags": flags,
        }

        products.append(
            {
                "ordinal": index + 1,
                "serial": serial,
                "vendor_key": vendor_key,
                "vendor_product_id": vendor_product_id,
                "product_key": product_key,
                "sync_id": sync_ids[vendor_key],
                "category": category,
                "brand": brand,
                "item": item,
                "name": name,
                "description": description,
                "ingredients": ingredients,
                "allergens": allergens,
                "dietary_tags": dietary_tags,
                "search_keywords": search_keywords,
                "aliases": aliases,
                "flags": flags,
                "source_hash": content_hash(hash_payload),
            }
        )

    return products


def seed_products(
    cursor: Any,
    *,
    products: list[dict[str, Any]],
    vendor_ids: dict[str, int],
    category_ids: dict[str, int],
    brand_ids: dict[str, int],
) -> None:
    rows: list[tuple[Any, ...]] = []

    for product in products:
        category = product["category"]
        flags = product["flags"]

        rows.append(
            (
                vendor_ids[product["vendor_key"]],
                product["vendor_product_id"],
                product["product_key"],
                category_ids[category["slug"]],
                brand_ids[product["brand"]],
                product["name"],
                normalize(product["name"]),
                product["description"],
                category["product_type"],
                product["ingredients"],
                compact_json(product["allergens"]),
                compact_json(product["dietary_tags"]),
                compact_json(product["search_keywords"]),
                compact_json(
                    {
                        "catalog_source": "synthetic_seed",
                        "seed_version": 2,
                    }
                ),
                "US",
                int(flags["is_organic"]),
                int(flags["is_vegan"]),
                int(flags["is_vegetarian"]),
                int(flags["is_gluten_free"]),
                int(flags["is_halal"]),
                product["sync_id"],
                product["source_hash"],
            )
        )

    execute_batches(
        cursor,
        """
        INSERT INTO products (
            vendor_id,
            vendor_product_id,
            product_key,
            category_id,
            brand_id,
            name,
            normalized_name,
            description,
            product_type,
            ingredients,
            allergens,
            dietary_tags,
            search_keywords,
            attributes,
            country_of_origin,
            is_organic,
            is_vegan,
            is_vegetarian,
            is_gluten_free,
            is_halal,
            last_seen_sync_id,
            source_hash,
            active
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, 1
        )
        ON DUPLICATE KEY UPDATE
            version = IF(
                source_hash <> VALUES(source_hash)
                OR active = 0,
                version + 1,
                version
            ),
            updated_at = IF(
                source_hash <> VALUES(source_hash)
                OR active = 0,
                CURRENT_TIMESTAMP(6),
                updated_at
            ),
            category_id = VALUES(category_id),
            brand_id = VALUES(brand_id),
            name = VALUES(name),
            normalized_name = VALUES(normalized_name),
            description = VALUES(description),
            product_type = VALUES(product_type),
            ingredients = VALUES(ingredients),
            allergens = VALUES(allergens),
            dietary_tags = VALUES(dietary_tags),
            search_keywords = VALUES(search_keywords),
            attributes = VALUES(attributes),
            country_of_origin = VALUES(country_of_origin),
            is_organic = VALUES(is_organic),
            is_vegan = VALUES(is_vegan),
            is_vegetarian = VALUES(is_vegetarian),
            is_gluten_free = VALUES(is_gluten_free),
            is_halal = VALUES(is_halal),
            active = 1,
            deleted_at = NULL,
            last_seen_sync_id = VALUES(last_seen_sync_id),
            source_hash = VALUES(source_hash)
        """,
        rows,
    )


def load_product_state(
    cursor: Any,
) -> dict[tuple[str, str], dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            p.id,
            p.vendor_product_id,
            p.version,
            v.vendor_key
        FROM products AS p
        INNER JOIN vendors AS v
            ON v.id = p.vendor_id
        """
    )

    return {
        (vendor_key, vendor_product_id): {
            "id": int(product_id),
            "version": int(version),
        }
        for (
            product_id,
            vendor_product_id,
            version,
            vendor_key,
        ) in cursor.fetchall()
    }


def seed_aliases(
    cursor: Any,
    *,
    products: list[dict[str, Any]],
    product_state: dict[
        tuple[str, str],
        dict[str, Any],
    ],
    vendor_ids: dict[str, int],
) -> None:
    placeholders = ", ".join(
        ["%s"] * len(vendor_ids)
    )

    cursor.execute(
        f"""
        DELETE pa
        FROM product_aliases AS pa
        INNER JOIN products AS p
            ON p.id = pa.product_id
        WHERE p.vendor_id IN ({placeholders})
        """,
        tuple(vendor_ids.values()),
    )

    rows: list[tuple[Any, ...]] = []

    for product in products:
        key = (
            product["vendor_key"],
            product["vendor_product_id"],
        )
        product_id = product_state[key]["id"]

        aliases = {
            *product["aliases"],
            (
                f"{product['brand']} "
                f"{product['item']}"
            ).casefold(),
        }


        seen_normalized: dict[str, str] = {}
        for alias in sorted(aliases):
            normalized_alias = normalize(alias)
            seen_normalized.setdefault(normalized_alias, alias)

        for normalized_alias, alias in sorted(seen_normalized.items()):
            rows.append(
                (
                    product_id,
                    alias,
                    normalized_alias,
                    "en",
                )
            )

    execute_batches(
        cursor,
        """
        INSERT INTO product_aliases (
            product_id,
            alias,
            normalized_alias,
            locale
        )
        VALUES (%s, %s, %s, %s)
        """,
        rows,
    )


def seed_variants(
    cursor: Any,
    *,
    products: list[dict[str, Any]],
    product_state: dict[
        tuple[str, str],
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    rows: list[tuple[Any, ...]] = []
    variant_specs: list[dict[str, Any]] = []

    for product in products:
        product_key = (
            product["vendor_key"],
            product["vendor_product_id"],
        )
        product_id = product_state[product_key]["id"]
        category = product["category"]

        low_price = Decimal(category["price"][0])
        high_price = Decimal(category["price"][1])

        for variant_number in range(
            1,
            VARIANTS_PER_PRODUCT + 1,
        ):
            size_text, unit = category["sizes"][
                (
                    product["serial"]
                    + variant_number
                    - 1
                )
                % len(category["sizes"])
            ]

            size_value = Decimal(size_text)
            pack_count = (
                int(size_value)
                if unit == "ct"
                else 1
            )

            vendor_variant_id = (
                f"{product['vendor_product_id']}"
                f"-V{variant_number}"
            )

            vector_record_id = (
                f"vendor-product:"
                f"{product['vendor_key']}:"
                f"{vendor_variant_id}"
            )

            category_code = re.sub(
                r"[^A-Z0-9]",
                "",
                category["slug"].upper(),
            )[:5]

            sku = (
                f"SA-{product['vendor_key'][:4].upper()}-"
                f"{category_code}-"
                f"{product['ordinal']:07d}-"
                f"{variant_number:02d}"
            )

            barcode_base = (
                f"29"
                f"{product['ordinal']:07d}"
                f"{variant_number:03d}"
            )
            barcode = ean13(barcode_base)

            ratio = Decimal(
                (
                    product["ordinal"] * 37
                    + variant_number * 17
                )
                % 1000
            ) / Decimal("999")

            base_price = (
                low_price
                + (high_price - low_price) * ratio
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            display = format_size(
                size_value,
                unit,
            )

            hash_payload = {
                "vendor_variant_id": vendor_variant_id,
                "vector_record_id": vector_record_id,
                "sku": sku,
                "barcode": barcode,
                "size_value": str(size_value),
                "size_unit": unit,
                "pack_count": pack_count,
                "display_size": display,
            }

            source_hash = content_hash(hash_payload)

            rows.append(
                (
                    product_id,
                    vendor_variant_id,
                    vector_record_id,
                    sku,
                    barcode,
                    size_value,
                    unit,
                    pack_count,
                    display,
                    compact_json(
                        {
                            "catalog_source": "synthetic_seed",
                            "package_unit": unit,
                        }
                    ),
                    product["sync_id"],
                    source_hash,
                )
            )

            variant_specs.append(
                {
                    "vendor_key": product["vendor_key"],
                    "vector_record_id": vector_record_id,
                    "sync_id": product["sync_id"],
                    "base_price": base_price,
                    "aisle": category["aisle"],
                    "ordinal": product["ordinal"],
                }
            )

    execute_batches(
        cursor,
        """
        INSERT INTO product_variants (
            product_id,
            vendor_variant_id,
            vector_record_id,
            sku,
            barcode,
            size_value,
            size_unit,
            pack_count,
            display_size,
            attributes,
            last_seen_sync_id,
            source_hash,
            active
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, 1
        )
        ON DUPLICATE KEY UPDATE
            version = IF(
                source_hash <> VALUES(source_hash)
                OR active = 0,
                version + 1,
                version
            ),
            updated_at = IF(
                source_hash <> VALUES(source_hash)
                OR active = 0,
                CURRENT_TIMESTAMP(6),
                updated_at
            ),
            vector_record_id = VALUES(vector_record_id),
            sku = VALUES(sku),
            barcode = VALUES(barcode),
            size_value = VALUES(size_value),
            size_unit = VALUES(size_unit),
            pack_count = VALUES(pack_count),
            display_size = VALUES(display_size),
            attributes = VALUES(attributes),
            active = 1,
            deleted_at = NULL,
            last_seen_sync_id = VALUES(last_seen_sync_id),
            source_hash = VALUES(source_hash)
        """,
        rows,
    )

    return variant_specs


def reconcile_missing_catalog_records(
    cursor: Any,
    *,
    vendor_ids: dict[str, int],
    sync_ids: dict[str, str],
) -> None:
    for vendor_key, vendor_id in vendor_ids.items():
        sync_id = sync_ids[vendor_key]

        # Products not seen in this completed vendor feed are soft-deleted.
        cursor.execute(
            """
            UPDATE products
            SET
                active = 0,
                deleted_at = CURRENT_TIMESTAMP(6),
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP(6)
            WHERE vendor_id = %s
              AND active = 1
              AND (
                  last_seen_sync_id IS NULL
                  OR last_seen_sync_id <> %s
              )
            """,
            (vendor_id, sync_id),
        )

        # Variants belonging to a deleted product are soft-deleted.
        cursor.execute(
            """
            UPDATE product_variants AS pv
            INNER JOIN products AS p
                ON p.id = pv.product_id
            SET
                pv.active = 0,
                pv.deleted_at = CURRENT_TIMESTAMP(6),
                pv.version = pv.version + 1,
                pv.updated_at = CURRENT_TIMESTAMP(6)
            WHERE p.vendor_id = %s
              AND p.active = 0
              AND pv.active = 1
            """,
            (vendor_id,),
        )

        # Variants missing from the latest feed are also soft-deleted.
        cursor.execute(
            """
            UPDATE product_variants AS pv
            INNER JOIN products AS p
                ON p.id = pv.product_id
            SET
                pv.active = 0,
                pv.deleted_at = CURRENT_TIMESTAMP(6),
                pv.version = pv.version + 1,
                pv.updated_at = CURRENT_TIMESTAMP(6)
            WHERE p.vendor_id = %s
              AND p.active = 1
              AND pv.active = 1
              AND (
                  pv.last_seen_sync_id IS NULL
                  OR pv.last_seen_sync_id <> %s
              )
            """,
            (vendor_id, sync_id),
        )

    # Retain historical offers but make deleted variants unavailable.
    cursor.execute(
        """
        UPDATE store_offers AS so
        INNER JOIN product_variants AS pv
            ON pv.id = so.variant_id
        INNER JOIN products AS p
            ON p.id = pv.product_id
        SET
            so.stock_quantity = 0,
            so.is_available = 0,
            so.updated_at = CURRENT_TIMESTAMP(6)
        WHERE pv.active = 0
           OR p.active = 0
        """
    )


def load_variant_ids(
    cursor: Any,
) -> dict[str, int]:
    cursor.execute(
        """
        SELECT id, vector_record_id
        FROM product_variants
        """
    )

    return {
        vector_record_id: int(variant_id)
        for variant_id, vector_record_id
        in cursor.fetchall()
    }


def seed_store_offers(
    cursor: Any,
    *,
    variant_specs: list[dict[str, Any]],
    variant_ids: dict[str, int],
    store_ids_by_vendor: dict[str, list[int]],
) -> None:
    rng = random.Random(RANDOM_SEED)
    rows: list[tuple[Any, ...]] = []

    vendor_currency = {
        vendor_key: currency
        for vendor_key, _, currency in VENDORS
    }

    for variant in variant_specs:
        variant_id = variant_ids[
            variant["vector_record_id"]
        ]

        for store_index, store_id in enumerate(
            store_ids_by_vendor[
                variant["vendor_key"]
            ]
        ):
            stock_quantity = (
                0
                if rng.random() < 0.08
                else rng.randint(3, 120)
            )

            is_available = int(
                stock_quantity > 0
            )

            price_factor = Decimal(
                str(rng.uniform(0.96, 1.12))
            )

            price = (
                variant["base_price"] * price_factor
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            compare_at_price: Decimal | None = None

            if (
                is_available
                and rng.random() < 0.18
            ):
                discount = Decimal(
                    str(rng.uniform(0.05, 0.20))
                )
                compare_at_price = (
                    price
                    / (
                        Decimal("1.00")
                        - discount
                    )
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

            aisle_location = (
                f"{variant['aisle']} "
                f"{1 + ((variant['ordinal'] + store_index) % 12)}"
            )

            rows.append(
                (
                    store_id,
                    variant_id,
                    price,
                    compare_at_price,
                    vendor_currency[
                        variant["vendor_key"]
                    ],
                    stock_quantity,
                    is_available,
                    1,
                    min(
                        max(stock_quantity, 1),
                        24,
                    ),
                    aisle_location,
                )
            )

    execute_batches(
        cursor,
        """
        INSERT INTO store_offers (
            store_id,
            variant_id,
            price,
            compare_at_price,
            currency,
            stock_quantity,
            is_available,
            min_order_quantity,
            max_order_quantity,
            aisle_location,
            last_checked_at
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            CURRENT_TIMESTAMP(6)
        )
        ON DUPLICATE KEY UPDATE
            price = VALUES(price),
            compare_at_price = VALUES(compare_at_price),
            currency = VALUES(currency),
            stock_quantity = VALUES(stock_quantity),
            is_available = VALUES(is_available),
            min_order_quantity = VALUES(min_order_quantity),
            max_order_quantity = VALUES(max_order_quantity),
            aisle_location = VALUES(aisle_location),
            last_checked_at = CURRENT_TIMESTAMP(6),
            updated_at = CURRENT_TIMESTAMP(6)
        """,
        rows,
    )


def create_outbox_events(
    cursor: Any,
    vendor_ids: dict[str, int],
) -> None:
    placeholders = ", ".join(
        ["%s"] * len(vendor_ids)
    )

    cursor.execute(
        f"""
        INSERT INTO catalog_outbox (
            vector_record_id,
            vendor_id,
            entity_type,
            entity_id,
            operation,
            changed_fields,
            source_version
        )
        SELECT
            pv.vector_record_id,
            p.vendor_id,
            'product_variant',
            pv.id,
            CASE
                WHEN p.active = 1
                 AND pv.active = 1
                THEN 'UPSERT'
                ELSE 'DELETE'
            END,
            JSON_ARRAY('catalog_sync'),
            CONCAT(
                'p',
                p.version,
                '-v',
                pv.version
            )
        FROM product_variants AS pv
        INNER JOIN products AS p
            ON p.id = pv.product_id
        WHERE p.vendor_id IN ({placeholders})
        ON DUPLICATE KEY UPDATE
            vector_record_id = VALUES(vector_record_id)
        """,
        tuple(vendor_ids.values()),
    )


def complete_sync_runs(
    cursor: Any,
    *,
    sync_ids: dict[str, str],
) -> None:
    for vendor_key, sync_id in sync_ids.items():
        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT p.id),
                COUNT(pv.id)
            FROM products AS p
            LEFT JOIN product_variants AS pv
                ON pv.product_id = p.id
               AND pv.last_seen_sync_id = %s
            INNER JOIN vendors AS v
                ON v.id = p.vendor_id
            WHERE v.vendor_key = %s
              AND p.last_seen_sync_id = %s
            """,
            (
                sync_id,
                vendor_key,
                sync_id,
            ),
        )

        product_count, variant_count = cursor.fetchone()

        cursor.execute(
            """
            UPDATE vendor_sync_runs
            SET
                status = 'COMPLETED',
                products_seen = %s,
                variants_seen = %s,
                completed_at = CURRENT_TIMESTAMP(6)
            WHERE sync_id = %s
            """,
            (
                int(product_count),
                int(variant_count),
                sync_id,
            ),
        )


def seed_catalog(
    connection: MySQLConnection,
) -> None:
    cursor = connection.cursor()

    try:
        (
            vendor_ids,
            category_ids,
            brand_ids,
            store_ids_by_vendor,
        ) = seed_reference_data(connection)

        sync_ids = create_sync_runs(
            cursor,
            vendor_ids,
        )

        products = build_products(sync_ids)

        seed_products(
            cursor,
            products=products,
            vendor_ids=vendor_ids,
            category_ids=category_ids,
            brand_ids=brand_ids,
        )

        product_state = load_product_state(cursor)

        seed_aliases(
            cursor,
            products=products,
            product_state=product_state,
            vendor_ids=vendor_ids,
        )

        variant_specs = seed_variants(
            cursor,
            products=products,
            product_state=product_state,
        )

        reconcile_missing_catalog_records(
            cursor,
            vendor_ids=vendor_ids,
            sync_ids=sync_ids,
        )

        variant_ids = load_variant_ids(cursor)

        seed_store_offers(
            cursor,
            variant_specs=variant_specs,
            variant_ids=variant_ids,
            store_ids_by_vendor=store_ids_by_vendor,
        )

        create_outbox_events(
            cursor,
            vendor_ids,
        )

        complete_sync_runs(
            cursor,
            sync_ids=sync_ids,
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Explicit vendor deletion helper
# ---------------------------------------------------------------------------

def soft_delete_vendor_product(
    connection: MySQLConnection,
    *,
    vendor_key: str,
    vendor_product_id: str,
) -> bool:
    """
    Use this from the future vendor ingestion service when a vendor
    explicitly sends a product deletion event.

    It soft-deletes the product and variants and creates DELETE outbox events.
    """

    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        cursor.execute(
            """
            SELECT
                p.id,
                p.vendor_id
            FROM products AS p
            INNER JOIN vendors AS v
                ON v.id = p.vendor_id
            WHERE v.vendor_key = %s
              AND p.vendor_product_id = %s
              AND p.active = 1
            FOR UPDATE
            """,
            (
                vendor_key,
                vendor_product_id,
            ),
        )

        product = cursor.fetchone()

        if product is None:
            connection.rollback()
            return False

        product_id = int(product["id"])

        cursor.execute(
            """
            UPDATE products
            SET
                active = 0,
                deleted_at = CURRENT_TIMESTAMP(6),
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP(6)
            WHERE id = %s
            """,
            (product_id,),
        )

        cursor.execute(
            """
            UPDATE product_variants
            SET
                active = 0,
                deleted_at = CURRENT_TIMESTAMP(6),
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP(6)
            WHERE product_id = %s
              AND active = 1
            """,
            (product_id,),
        )

        cursor.execute(
            """
            UPDATE store_offers AS so
            INNER JOIN product_variants AS pv
                ON pv.id = so.variant_id
            SET
                so.stock_quantity = 0,
                so.is_available = 0,
                so.updated_at = CURRENT_TIMESTAMP(6)
            WHERE pv.product_id = %s
            """,
            (product_id,),
        )

        cursor.execute(
            """
            INSERT INTO catalog_outbox (
                vector_record_id,
                vendor_id,
                entity_type,
                entity_id,
                operation,
                changed_fields,
                source_version
            )
            SELECT
                pv.vector_record_id,
                p.vendor_id,
                'product_variant',
                pv.id,
                'DELETE',
                JSON_ARRAY(
                    'active',
                    'deleted_at'
                ),
                CONCAT(
                    'p',
                    p.version,
                    '-v',
                    pv.version
                )
            FROM product_variants AS pv
            INNER JOIN products AS p
                ON p.id = pv.product_id
            WHERE p.id = %s
            ON DUPLICATE KEY UPDATE
                vector_record_id =
                    VALUES(vector_record_id)
            """,
            (product_id,),
        )

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def print_summary(
    connection: MySQLConnection,
) -> None:
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM products
        WHERE active = 1
        """
    )
    active_products = int(cursor.fetchone()[0])

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM products
        WHERE active = 0
        """
    )
    deleted_products = int(cursor.fetchone()[0])

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM product_variants
        WHERE active = 1
        """
    )
    active_variants = int(cursor.fetchone()[0])

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM catalog_outbox
        WHERE processed_at IS NULL
        """
    )
    pending_events = int(cursor.fetchone()[0])

    cursor.close()

    print(f"Active products: {active_products:,}")
    print(f"Soft-deleted products: {deleted_products:,}")
    print(f"Active variants: {active_variants:,}")
    print(f"Pending vector events: {pending_events:,}")


def main() -> None:
    validate_configuration()
    create_database()

    connection = mysql.connector.connect(
        **connection_config(
            include_database=True,
            autocommit=False,
        )
    )

    try:
        timezone_cursor = connection.cursor()
        timezone_cursor.execute(
            "SET time_zone = '+00:00'"
        )
        timezone_cursor.close()

        create_schema(
            connection,
            reset_tables=RESET_TABLES,
        )

        seed_catalog(connection)
        print_summary(connection)

    finally:
        connection.close()


if __name__ == "__main__":
    main()