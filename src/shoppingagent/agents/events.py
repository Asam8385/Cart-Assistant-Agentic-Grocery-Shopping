from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    sequence: int = Field(ge=1)
    event: str
    stage: str
    message: str
    item_id: str | None = None
    tool_name: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    def to_sse(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return (
            f"id: {self.trace_id}:{self.sequence}\n"
            f"event: {self.event}\n"
            f"data: {payload}\n\n"
        )


class EventFactory:
    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or str(uuid4())
        self._sequence = 0

    def create(
        self,
        event: str,
        *,
        stage: str,
        message: str,
        item_id: str | None = None,
        tool_name: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> StreamEvent:
        self._sequence += 1

        return StreamEvent(
            trace_id=self.trace_id,
            sequence=self._sequence,
            event=event,
            stage=stage,
            message=message,
            item_id=item_id,
            tool_name=tool_name,
            data=data or {},
            created_at=datetime.now(UTC),
        )
