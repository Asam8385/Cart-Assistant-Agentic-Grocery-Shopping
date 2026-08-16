from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel


ModelT = TypeVar(
    "ModelT",
    bound=BaseModel,
)


def parse_structured_response(
    response: Any,
    schema: type[ModelT],
) -> ModelT:
    value = getattr(
        response,
        "value",
        None,
    )

    if isinstance(value, schema):
        return value

    if isinstance(value, BaseModel):
        return schema.model_validate(
            value.model_dump()
        )

    if isinstance(value, dict):
        return schema.model_validate(value)

    text = str(
        getattr(
            response,
            "text",
            "",
        )
    ).strip()

    if not text:
        raise ValueError(
            "The agent returned no structured value or text."
        )

    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if first_brace >= 0 and last_brace > first_brace:
        text = text[
            first_brace:last_brace + 1
        ]

    return schema.model_validate_json(text)