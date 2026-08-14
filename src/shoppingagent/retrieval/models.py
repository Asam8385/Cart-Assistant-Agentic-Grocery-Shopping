from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchHit:
    point_id: str
    record_id: str
    title: str

    # Final score used to order the results.
    score: float

    # Original Qdrant dense/sparse/RRF score.
    qdrant_score: float

    # Cross-encoder relevance probability.
    reranker_score: float | None

    payload: dict[str, Any]
    boost_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "record_id": self.record_id,
            "title": self.title,
            "score": self.score,
            "qdrant_score": self.qdrant_score,
            "reranker_score": self.reranker_score,
            "boost_reasons": list(self.boost_reasons),
            "payload": self.payload,
        }