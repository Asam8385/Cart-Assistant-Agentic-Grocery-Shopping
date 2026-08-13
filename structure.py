from __future__ import annotations

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

# Set True to preview without creating anything.
DRY_RUN = False


DIRECTORIES = (
    # GitHub Actions
    ".github/workflows",

    # Microsoft Foundry local metadata/cache
    ".foundry/suites",
    ".foundry/datasets",
    ".foundry/evaluators",
    ".foundry/results",

    # Evaluation source
    "evaluations/datasets",
    "evaluations/assets/handwritten_lists",
    "evaluations/evaluators",
    "evaluations/suites",

    # Deployment and operational scripts
    "infra/modules",
    "scripts",

    # Application packages
    "src/shoppingagent/config",
    "src/shoppingagent/domain",
    "src/shoppingagent/agents/prompts",
    "src/shoppingagent/workflows",
    "src/shoppingagent/retrieval",
    "src/shoppingagent/tools",
    "src/shoppingagent/guardrails",
    "src/shoppingagent/observability",
    "src/shoppingagent/hosting",
    "src/shoppingagent/mcp/tools",
    "src/shoppingagent/knowledge_base/data",

    # Tests
    "tests/unit",
    "tests/integration",
    "tests/contract",
    "tests/fixtures",
)


FILES = (
    # GitHub Actions
    ".github/workflows/ci.yml",
    ".github/workflows/agent-eval.yml",
    ".github/workflows/deploy-staging.yml",
    ".github/workflows/promote-production.yml",

    # Foundry configuration/cache
    ".foundry/agent-metadata.yaml",
    ".foundry/agent-metadata.prod.yaml",
    ".foundry/suites/.gitkeep",
    ".foundry/datasets/.gitkeep",
    ".foundry/evaluators/.gitkeep",
    ".foundry/results/.gitkeep",

    # Evaluation datasets
    "evaluations/datasets/smoke.jsonl",
    "evaluations/datasets/shopping_requests.jsonl",
    "evaluations/datasets/image_extraction.jsonl",
    "evaluations/datasets/retrieval_gold.jsonl",
    "evaluations/datasets/tool_calls.jsonl",
    "evaluations/datasets/catalog_sync.jsonl",
    "evaluations/datasets/safety_adversarial.jsonl",
    "evaluations/assets/handwritten_lists/.gitkeep",

    # Evaluation code
    "evaluations/evaluators/__init__.py",
    "evaluations/evaluators/extraction_accuracy.py",
    "evaluations/evaluators/retrieval_metrics.py",
    "evaluations/evaluators/constraint_compliance.py",
    "evaluations/evaluators/tool_call_accuracy.py",
    "evaluations/evaluators/catalog_freshness.py",
    "evaluations/evaluators/response_quality.py",
    "evaluations/suites/smoke.yaml",
    "evaluations/suites/regression.yaml",
    "evaluations/suites/retrieval.yaml",
    "evaluations/run_evaluations.py",

    # Infrastructure
    "infra/main.bicep",
    "infra/main.parameters.json",
    "infra/modules/.gitkeep",

    # Operational scripts
    "scripts/run_local.py",
    "scripts/run_evaluation.py",
    "scripts/smoke_test.py",
    "scripts/sync_catalog.py",
    "scripts/verify_qdrant.py",

    # Configuration
    "src/shoppingagent/config/__init__.py",
    "src/shoppingagent/config/settings.py",
    "src/shoppingagent/config/logging.py",

    # Domain models
    "src/shoppingagent/domain/__init__.py",
    "src/shoppingagent/domain/shopping_item.py",
    "src/shoppingagent/domain/product_match.py",
    "src/shoppingagent/domain/cart.py",
    "src/shoppingagent/domain/vendor.py",

    # Agents
    "src/shoppingagent/agents/__init__.py",
    "src/shoppingagent/agents/root_agent.py",
    "src/shoppingagent/agents/image_analyzer_agent.py",
    "src/shoppingagent/agents/data_collector_agent.py",
    "src/shoppingagent/agents/agent_factory.py",

    # Agent prompts
    "src/shoppingagent/agents/prompts/__init__.py",
    "src/shoppingagent/agents/prompts/root_agent.md",
    "src/shoppingagent/agents/prompts/image_analyzer.md",
    "src/shoppingagent/agents/prompts/data_collector.md",

    # Agent Framework workflow
    "src/shoppingagent/workflows/__init__.py",
    "src/shoppingagent/workflows/shopping_workflow.py",
    "src/shoppingagent/workflows/routing.py",

    # Online retrieval
    "src/shoppingagent/retrieval/__init__.py",
    "src/shoppingagent/retrieval/hybrid_retriever.py",
    "src/shoppingagent/retrieval/dense_encoder.py",
    "src/shoppingagent/retrieval/sparse_encoder.py",
    "src/shoppingagent/retrieval/query_normalizer.py",
    "src/shoppingagent/retrieval/filters.py",
    "src/shoppingagent/retrieval/reranker.py",

    # Agent tools
    "src/shoppingagent/tools/__init__.py",
    "src/shoppingagent/tools/search_catalog.py",
    "src/shoppingagent/tools/inspect_product.py",
    "src/shoppingagent/tools/create_cart.py",

    # Guardrails
    "src/shoppingagent/guardrails/__init__.py",
    "src/shoppingagent/guardrails/input_filter.py",
    "src/shoppingagent/guardrails/prompt_injection.py",
    "src/shoppingagent/guardrails/pii_filter.py",
    "src/shoppingagent/guardrails/output_validator.py",

    # Observability
    "src/shoppingagent/observability/__init__.py",
    "src/shoppingagent/observability/telemetry.py",
    "src/shoppingagent/observability/metrics.py",
    "src/shoppingagent/observability/tracing.py",

    # Hosted-agent entry point
    "src/shoppingagent/hosting/__init__.py",
    "src/shoppingagent/hosting/app.py",

    # MCP server
    "src/shoppingagent/mcp/__init__.py",
    "src/shoppingagent/mcp/server.py",
    "src/shoppingagent/mcp/schemas.py",
    "src/shoppingagent/mcp/database_tool.py",
    "src/shoppingagent/mcp/tools/__init__.py",
    "src/shoppingagent/mcp/tools/product_lookup.py",
    "src/shoppingagent/mcp/tools/availability.py",
    "src/shoppingagent/mcp/tools/cart_operations.py",

    # Existing knowledge-base package
    "src/shoppingagent/knowledge_base/__init__.py",

    # Tests
    "tests/__init__.py",
    "tests/unit/__init__.py",
    "tests/unit/test_schemas.py",
    "tests/unit/test_prompts.py",
    "tests/unit/test_query_normalizer.py",
    "tests/unit/test_point_id_stability.py",

    "tests/integration/__init__.py",
    "tests/integration/test_mysql_export.py",
    "tests/integration/test_qdrant_retrieval.py",
    "tests/integration/test_mcp_server.py",

    "tests/contract/__init__.py",
    "tests/contract/test_agent_output_contract.py",
    "tests/contract/test_mcp_tool_contracts.py",

    "tests/fixtures/products_small.jsonl",
    "tests/fixtures/pending_changes_small.jsonl",

    # Root configuration
    "azure.yaml",
    "eval.yaml",
    "Dockerfile",
    ".dockerignore",
    ".env.example",
)


WORKFLOW_NAMES = {
    ".github/workflows/ci.yml": "Shopping Agent CI",
    ".github/workflows/agent-eval.yml": "Shopping Agent Evaluation",
    ".github/workflows/deploy-staging.yml": "Deploy Shopping Agent to Staging",
    ".github/workflows/promote-production.yml": "Promote Shopping Agent to Production",
}


# ---------------------------------------------------------------------------
# Placeholder content
# ---------------------------------------------------------------------------

def workflow_placeholder(name: str) -> str:
    """
    Create a valid, manually triggered, disabled GitHub workflow.

    It will not execute deployment or CI work until the placeholder job is
    replaced.
    """
    return f"""name: {name}

on:
  workflow_dispatch:

jobs:
  placeholder:
    if: ${{{{ false }}}}
    runs-on: ubuntu-latest
    steps:
      - name: Placeholder
        run: echo "Replace this placeholder with the real workflow."
"""


def initial_content(relative_path: str) -> str:
    path = Path(relative_path)
    suffix = path.suffix.lower()

    if relative_path in WORKFLOW_NAMES:
        return workflow_placeholder(WORKFLOW_NAMES[relative_path])

    if path.name == "__init__.py":
        return '"""Package initialization."""\n'

    if relative_path == "azure.yaml":
        return """# yaml-language-server: $schema=https://raw.githubusercontent.com/Azure/azure-dev/main/schemas/v1.0/azure.yaml.json

name: shopping-agent

# Add the Microsoft Foundry project and hosted-agent services here.
services: {}
"""

    if relative_path == "eval.yaml":
        return """name: shopping-agent-evaluation

agent:
  name: shopping-agent

dataset:
  local_uri: evaluations/datasets/smoke.jsonl

evaluators: []

options:
  pass_threshold: 0.80
  max_samples: 25
"""

    if relative_path == ".foundry/agent-metadata.yaml":
        return """defaultEnvironment: dev

environments:
  dev:
    evaluationSuites: []
"""

    if relative_path == ".foundry/agent-metadata.prod.yaml":
        return """defaultEnvironment: prod

environments:
  prod:
    evaluationSuites: []
"""

    if relative_path == ".env.example":
        return """# Microsoft Foundry / model
AZURE_AI_PROJECT_ENDPOINT=
AZURE_AI_MODEL_DEPLOYMENT_NAME=

# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=shopping_agent

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=shopping-products-v1

# OpenTelemetry
ENABLE_INSTRUMENTATION=true
ENABLE_SENSITIVE_DATA=false
OTEL_SERVICE_NAME=shopping-agent
OTEL_EXPORTER_OTLP_ENDPOINT=
APPLICATIONINSIGHTS_CONNECTION_STRING=
"""

    if relative_path == ".dockerignore":
        return """.git
.github
.venv
__pycache__
*.pyc
.env
.foundry/results
evaluations/assets
src/shoppingagent/knowledge_base/data/*.jsonl
tests
docs
"""

    if relative_path == "Dockerfile":
        return """# Placeholder.
# Add a production Dockerfile after selecting Foundry code deployment
# or container deployment.
"""

    if relative_path == "infra/main.parameters.json":
        return "{}\n"

    if suffix == ".py":
        return (
            '"""Scaffold placeholder.\n\n'
            "Implement this module before enabling it in the application.\n"
            '"""\n'
        )

    if suffix == ".md":
        title = path.stem.replace("_", " ").title()
        return f"# {title}\n\nTODO: Add the versioned agent instructions.\n"

    if suffix in {".yaml", ".yml"}:
        return "# Scaffold placeholder. Add configuration before use.\n"

    if suffix == ".bicep":
        return "// Scaffold placeholder. Add infrastructure definitions here.\n"

    # JSONL and .gitkeep files remain empty.
    return ""


# ---------------------------------------------------------------------------
# Safe creation
# ---------------------------------------------------------------------------

def safe_project_path(relative_path: str) -> Path:
    """
    Resolve a relative path and ensure it remains inside PROJECT_ROOT.

    This also protects against an existing symlink redirecting creation
    outside the repository.
    """
    candidate = (PROJECT_ROOT / relative_path).resolve(strict=False)
    root = PROJECT_ROOT.resolve()

    normalized_root = os.path.normcase(str(root))
    normalized_candidate = os.path.normcase(str(candidate))

    if os.path.commonpath(
        [normalized_root, normalized_candidate]
    ) != normalized_root:
        raise ValueError(
            f"Refusing to access a path outside the project: {relative_path}"
        )

    return candidate


def create_directory(
    relative_path: str,
    created: list[str],
    skipped: list[str],
) -> None:
    path = safe_project_path(relative_path)

    if path.exists():
        if not path.is_dir():
            raise FileExistsError(
                f"Expected a directory but found a file: {path}"
            )

        skipped.append(relative_path)
        return

    if not DRY_RUN:
        path.mkdir(parents=True, exist_ok=False)

    created.append(relative_path)


def create_file(
    relative_path: str,
    created: list[str],
    skipped: list[str],
) -> None:
    path = safe_project_path(relative_path)

    if path.exists():
        if not path.is_file():
            raise FileExistsError(
                f"Expected a file but found a directory: {path}"
            )

        # Existing file contents are never opened for writing.
        skipped.append(relative_path)
        return

    if not DRY_RUN:
        path.parent.mkdir(parents=True, exist_ok=True)

        # "x" means exclusive creation and fails if the file suddenly exists.
        with path.open(
            mode="x",
            encoding="utf-8",
            newline="\n",
        ) as file:
            file.write(initial_content(relative_path))

    created.append(relative_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not (PROJECT_ROOT / "pyproject.toml").is_file():
        raise SystemExit(
            "Place this script in the shoppingAgent repository root, "
            "next to pyproject.toml."
        )

    created: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for relative_path in DIRECTORIES:
        try:
            create_directory(relative_path, created, skipped)
        except (OSError, ValueError) as exc:
            errors.append(f"{relative_path}: {exc}")

    for relative_path in FILES:
        try:
            create_file(relative_path, created, skipped)
        except (OSError, ValueError) as exc:
            errors.append(f"{relative_path}: {exc}")

    mode = "DRY RUN" if DRY_RUN else "CREATION COMPLETE"

    print()
    print(mode)
    print("=" * len(mode))
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Created: {len(created)}")
    print(f"Skipped existing: {len(skipped)}")
    print(f"Errors: {len(errors)}")

    if created:
        print("\nCreated paths:")
        for relative_path in created:
            print(f"  + {relative_path}")

    if skipped:
        print("\nExisting paths left unchanged:")
        for relative_path in skipped:
            print(f"  = {relative_path}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  ! {error}")

        raise SystemExit(1)

    print("\nNo existing file content was changed.")


if __name__ == "__main__":
    main()