from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_structured_response(
    response: Any,
    schema: type[ModelT],
) -> ModelT:
    value = getattr(response, "value", None)

    if isinstance(value, schema):
        return value

    if isinstance(value, BaseModel):
        return schema.model_validate(value.model_dump())

    if isinstance(value, dict):
        return schema.model_validate(value)

    text = str(getattr(response, "text", "")).strip()

    if text.startswith("```"):
        lines = text.splitlines()[1:]

        if lines and lines[-1].strip() == "```":
            lines.pop()

        text = "\n".join(lines).strip()

    first = text.find("{")
    last = text.rfind("}")

    if first >= 0 and last > first:
        text = text[first:last + 1]

    if not text:
        raise ValueError("The agent returned no structured JSON.")

    return schema.model_validate_json(text)
