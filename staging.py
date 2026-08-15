from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import HTMLResponse
from jinja2 import Environment
from qdrant_client import QdrantClient
from starlette.concurrency import run_in_threadpool

from shoppingagent.retrieval import (
    DenseQueryEncoder,
    HuggingFaceReranker,
    HybridProductRetriever,
    ProductFilters,
    RerankerSettings,
    RetrievalSettings,
    SparseQueryEncoder,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[3]

PACKAGE_ROOT = Path(
    __file__
).resolve().parents[1]

# Supports both the recommended root .env and your current
# src/shoppingagent/.env location.
load_dotenv(
    PROJECT_ROOT / ".env",
    override=False,
)

load_dotenv(
    PACKAGE_ROOT / ".env",
    override=False,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s "
        "%(name)s: %(message)s"
    ),
)

logger = logging.getLogger(
    "shoppingagent.hosting"
)


HTML_TEMPLATE_SOURCE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <title>Shopping Agent Retrieval</title>

    <style>
        :root {
            font-family:
                Inter,
                system-ui,
                -apple-system,
                sans-serif;
            background: #f5f7fb;
            color: #172033;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
        }

        main {
            width: min(1050px, calc(100% - 32px));
            margin: 32px auto;
        }

        h1 {
            margin-bottom: 6px;
        }

        .subtitle {
            margin-top: 0;
            color: #657087;
        }

        form,
        .result,
        .message {
            background: white;
            border: 1px solid #e0e5ee;
            border-radius: 14px;
            padding: 18px;
            box-shadow:
                0 8px 28px rgb(20 32 60 / 6%);
        }

        .main-fields {
            display: grid;
            grid-template-columns:
                minmax(250px, 1fr)
                150px
                100px
                140px;
            gap: 10px;
        }

        .filters {
            display: grid;
            grid-template-columns:
                repeat(3, minmax(130px, 1fr));
            gap: 10px;
            margin-top: 12px;
        }

        input,
        select,
        button {
            width: 100%;
            min-height: 42px;
            border: 1px solid #cbd3e1;
            border-radius: 8px;
            padding: 8px 10px;
            background: white;
            font: inherit;
        }

        button {
            margin-top: 14px;
            width: auto;
            padding-inline: 24px;
            border-color: #172554;
            background: #172554;
            color: white;
            font-weight: 650;
            cursor: pointer;
        }

        .status {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 16px 0;
        }

        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 999px;
            background: #e8edff;
            color: #2849a6;
            font-size: 12px;
        }

        .status .badge {
            background: #e5f7eb;
            color: #126c38;
        }

        .summary {
            color: #657087;
            margin: 22px 0 10px;
        }

        .results {
            display: grid;
            gap: 12px;
        }

        .result h2 {
            margin: 0 0 8px;
            font-size: 19px;
        }

        .metadata {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            color: #657087;
            font-size: 14px;
        }

        .description {
            line-height: 1.55;
        }

        .scores {
            margin-top: 12px;
            color: #46516b;
            font-size: 13px;
        }

        .message {
            margin-top: 18px;
        }

        .error {
            background: #fff5f5;
            color: #992b2b;
            border-color: #efc2c2;
        }

        @media (max-width: 760px) {
            .main-fields,
            .filters {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>

<body>
<main>
    <h1>Shopping Agent Retrieval Test</h1>

    <p class="subtitle">
        Compare hybrid RRF, dense and BM25 retrieval,
        with optional MiniLM reranking.
    </p>

    <div class="status">
        <span class="badge">
            Qdrant: {{ health.status }}
        </span>

        <span class="badge">
            Collection: {{ health.collection }}
        </span>

        <span class="badge">
            Points: {{ health.points_count }}
        </span>
    </div>

    <form method="get" action="/">
        <div class="main-fields">
            <input
                type="search"
                name="q"
                value="{{ query }}"
                placeholder="Search for organic bananas..."
                required
            >

            <select name="mode">
                <option
                    value="hybrid"
                    {% if mode == "hybrid" %}
                        selected
                    {% endif %}
                >
                    Hybrid RRF
                </option>

                <option
                    value="dense"
                    {% if mode == "dense" %}
                        selected
                    {% endif %}
                >
                    Dense only
                </option>

                <option
                    value="sparse"
                    {% if mode == "sparse" %}
                        selected
                    {% endif %}
                >
                    BM25 only
                </option>
            </select>

            <input
                type="number"
                name="limit"
                value="{{ limit }}"
                min="1"
                max="50"
            >

            <select name="rerank">
                <option
                    value="true"
                    {% if rerank %}selected{% endif %}
                >
                    Rerank: on
                </option>

                <option
                    value="false"
                    {% if not rerank %}selected{% endif %}
                >
                    Rerank: off
                </option>
            </select>
        </div>

        <div class="filters">
            <input
                type="text"
                name="vendor_key"
                value="{{ vendor_key or '' }}"
                placeholder="Vendor: freshcart"
            >

            <input
                type="text"
                name="category_slug"
                value="{{ category_slug or '' }}"
                placeholder="Category: fresh-fruit"
            >

            <input
                type="text"
                name="brand"
                value="{{ brand or '' }}"
                placeholder="Brand: O Organics"
            >
        </div>

        <button type="submit">
            Search products
        </button>
    </form>

    {% if error %}
        <div class="message error">
            <strong>Search failed:</strong>
            {{ error }}
        </div>
    {% endif %}

    {% if query and not error %}
        <p class="summary">
            Found {{ results | length }} result(s)
            in {{ "%.2f" | format(elapsed_ms) }} ms.
        </p>
    {% endif %}

    {% if query and not error and not results %}
        <div class="message">
            No matching products were found.
        </div>
    {% endif %}

    <section class="results">
        {% for hit in results %}
            <article class="result">
                <h2>{{ hit.title }}</h2>

                <div class="metadata">
                    <span>
                        Vendor:
                        {{
                            hit.payload.get(
                                "vendor_name",
                                "Unknown"
                            )
                        }}
                    </span>

                    <span>
                        Brand:
                        {{
                            hit.payload.get(
                                "brand",
                                "Unknown"
                            )
                        }}
                    </span>

                    <span>
                        Size:
                        {{
                            hit.payload.get(
                                "display_size",
                                "Unknown"
                            )
                        }}
                    </span>

                    <span>
                        Category:
                        {{
                            hit.payload.get(
                                "category_path",
                                "Unknown"
                            )
                        }}
                    </span>
                </div>

                <p class="description">
                    {{
                        hit.payload.get(
                            "chunk_text",
                            ""
                        )
                    }}
                </p>

                <div>
                    {% for tag in
                        hit.payload.get(
                            "dietary_tags",
                            []
                        )
                    %}
                        <span class="badge">
                            {{ tag }}
                        </span>
                    {% endfor %}
                </div>

                <div class="scores">
                    Final:
                    {{ "%.6f" | format(hit.score) }}

                    · Qdrant:
                    {{
                        "%.6f"
                        | format(hit.qdrant_score)
                    }}

                    {% if
                        hit.reranker_score
                        is not none
                    %}
                        · Reranker:
                        {{
                            "%.6f"
                            | format(
                                hit.reranker_score
                            )
                        }}
                    {% endif %}

                    {% if hit.boost_reasons %}
                        · Boost:
                        {{
                            hit.boost_reasons
                            | join(", ")
                        }}
                    {% endif %}
                </div>
            </article>
        {% endfor %}
    </section>
</main>
</body>
</html>
"""


JINJA_ENVIRONMENT = Environment(
    autoescape=True
)

HTML_TEMPLATE = (
    JINJA_ENVIRONMENT.from_string(
        HTML_TEMPLATE_SOURCE
    )
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    settings = (
        RetrievalSettings.from_environment()
    )

    # 1. Load the dense model.
    logger.info(
        "Loading dense model: %s",
        settings.dense_model_name,
    )

    dense_encoder = DenseQueryEncoder.load(
        model_name=settings.dense_model_name,
        expected_dimension=(
            settings.dense_vector_size
        ),
        device=settings.dense_device,
    )

    logger.info("Dense model is ready.")

    # 2. Load the BM25 sparse model.
    logger.info(
        "Loading sparse model: %s",
        settings.sparse_model_name,
    )

    sparse_encoder = SparseQueryEncoder.load(
        model_name=settings.sparse_model_name,
        language=settings.bm25_language,
        average_document_length=(
            settings.bm25_average_document_length
        ),
    )

    logger.info("Sparse model is ready.")

    # 3. Load the small Hugging Face reranker.
    logger.info(
        "Loading reranker model: %s",
        settings.reranker_model_name,
    )

    reranker = HuggingFaceReranker.load(
        model_name=(
            settings.reranker_model_name
        ),
        device=settings.reranker_device,
        maximum_length=(
            settings.reranker_maximum_length
        ),
        settings=RerankerSettings(
            batch_size=(
                settings.reranker_batch_size
            ),
            maximum_candidates=(
                settings.reranker_candidate_limit
            ),
        ),
    )

    logger.info("Reranker model is ready.")

    # 4. Connect after all local models are loaded.
    qdrant_client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=settings.qdrant_timeout,
        cloud_inference=True
    )

    retriever = HybridProductRetriever(
        client=qdrant_client,
        dense_encoder=dense_encoder,
        sparse_encoder=sparse_encoder,
        reranker=reranker,
        collection_name=(
            settings.collection_name
        ),
        dense_vector_name=(
            settings.dense_vector_name
        ),
        sparse_vector_name=(
            settings.sparse_vector_name
        ),
        timeout=settings.qdrant_timeout,
        default_candidate_limit=(
            settings.reranker_candidate_limit
        ),
    )

    health = await run_in_threadpool(
        retriever.health_check
    )

    logger.info(
        "Retrieval ready: collection=%s, "
        "points=%s",
        health["collection"],
        health["points_count"],
    )

    app.state.retriever = retriever
    app.state.settings = settings
    app.state.startup_health = health

    try:
        yield
    finally:
        logger.info(
            "Closing Qdrant connection."
        )
        qdrant_client.close()


app = FastAPI(
    title="Shopping Agent Retrieval Test",
    version="0.1.0",
    lifespan=lifespan,
)


async def run_search(
    request: Request,
    *,
    query: str,
    mode: str,
    limit: int,
    rerank: bool,
    vendor_key: str | None,
    category_slug: str | None,
    brand: str | None,
) -> tuple[list[Any], float]:
    retriever: HybridProductRetriever = (
        request.app.state.retriever
    )

    filters = ProductFilters(
        vendor_key=vendor_key,
        category_slug=category_slug,
        brand=brand,
    )

    started_at = perf_counter()

    results = await run_in_threadpool(
        lambda: retriever.search(
            query,
            mode=mode,
            limit=limit,
            filters=filters,
            apply_reranker=rerank,
        )
    )

    elapsed_ms = (
        perf_counter() - started_at
    ) * 1000

    return results, elapsed_ms


@app.get(
    "/",
    response_class=HTMLResponse,
)
async def homepage(
    request: Request,
    q: str = "",
    mode: str = "hybrid",
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
    ),
    rerank: bool = True,
    vendor_key: str | None = None,
    category_slug: str | None = None,
    brand: str | None = None,
) -> HTMLResponse:
    results: list[Any] = []
    elapsed_ms = 0.0
    error: str | None = None

    if q.strip():
        try:
            results, elapsed_ms = (
                await run_search(
                    request,
                    query=q,
                    mode=mode,
                    limit=limit,
                    rerank=rerank,
                    vendor_key=vendor_key,
                    category_slug=(
                        category_slug
                    ),
                    brand=brand,
                )
            )
        except Exception as exc:
            logger.exception(
                "Retrieval request failed."
            )
            error = str(exc)

    html = HTML_TEMPLATE.render(
        query=q,
        mode=mode,
        limit=limit,
        rerank=rerank,
        vendor_key=vendor_key,
        category_slug=category_slug,
        brand=brand,
        results=results,
        elapsed_ms=elapsed_ms,
        error=error,
        health=(
            request.app.state.startup_health
        ),
    )

    return HTMLResponse(html)


@app.get("/api/search")
async def search_api(
    request: Request,
    q: str = Query(
        min_length=1,
        max_length=500,
    ),
    mode: str = "hybrid",
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
    ),
    rerank: bool = True,
    vendor_key: str | None = None,
    category_slug: str | None = None,
    brand: str | None = None,
) -> dict[str, Any]:
    try:
        results, elapsed_ms = (
            await run_search(
                request,
                query=q,
                mode=mode,
                limit=limit,
                rerank=rerank,
                vendor_key=vendor_key,
                category_slug=category_slug,
                brand=brand,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(
            "Retrieval API failed."
        )

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return {
        "query": q,
        "mode": mode,
        "reranked": rerank,
        "count": len(results),
        "elapsed_ms": round(
            elapsed_ms,
            2,
        ),
        "results": [
            result.to_dict()
            for result in results
        ],
    }


@app.get("/health")
async def health(
    request: Request,
) -> dict[str, Any]:
    retriever: HybridProductRetriever = (
        request.app.state.retriever
    )

    qdrant_health = await run_in_threadpool(
        retriever.health_check
    )

    settings: RetrievalSettings = (
        request.app.state.settings
    )

    return {
        **qdrant_health,
        "dense_model": (
            settings.dense_model_name
        ),
        "dense_dimension": (
            settings.dense_vector_size
        ),
        "sparse_model": (
            settings.sparse_model_name
        ),
        "reranker_model": (
            settings.reranker_model_name
        ),
        "candidate_limit": (
            settings.reranker_candidate_limit
        ),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "shoppingagent.hosting.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        workers=1,
    )