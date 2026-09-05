"""Deterministic policy for inert legacy .ai content.

This module deliberately never executes, moves, deletes, or deserializes files.
It only classifies bounded inventory entries so callers can preserve inert data
without treating it as Hiker authority.
"""
from __future__ import annotations

from pathlib import Path

SAFE_PRESERVED_CONTENT = "SAFE_PRESERVED_CONTENT"
UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"

# Names that are known engineering memory, but are never Active State writers.
KNOWN_INERT_DIRS = {"architecture", "requirements", "evidence", "knowledge", "logs", "tmp", "archive"}
AUTHORITATIVE_DIRS = {"governance", "runtime", "workspace", "tasks", "context"}


def classify(relative_path: str) -> str:
    """Classify a relative .ai path without trusting its extension or contents."""
    path = Path(relative_path.replace("\\", "/"))
    parts = {part.lower() for part in path.parts}
    if not path.parts or path.is_absolute() or ".." in path.parts:
        return UNKNOWN_REQUIRES_REVIEW
    if parts & AUTHORITATIVE_DIRS:
        return UNKNOWN_REQUIRES_REVIEW
    if path.parts[0].lower() in KNOWN_INERT_DIRS:
        return SAFE_PRESERVED_CONTENT
    return UNKNOWN_REQUIRES_REVIEW


def is_inert(relative_path: str) -> bool:
    return classify(relative_path) == SAFE_PRESERVED_CONTENT
