"""Shared, side-effect-free helpers for the NYC legal platform.

This module deliberately has no Streamlit / FastAPI / network imports so it can
be unit-tested in isolation and reused by both the Streamlit app and the
FastAPI server.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional

# Cypher keywords that indicate a write/destructive or otherwise disallowed
# operation. Matched as whole words to avoid false positives like "asset" or
# "preset" (which contain "SET").
FORBIDDEN_CYPHER_KEYWORDS = frozenset(
    {"DELETE", "DETACH", "REMOVE", "DROP", "CREATE", "MERGE", "SET", "CALL", "LOAD"}
)

# Read-only procedure calls that are explicitly allowed despite using CALL.
ALLOWED_CALL_SIGNATURES = ("db.index.vector.queryNodes",)


def is_cypher_safe(cypher: str) -> bool:
    """Return True if the query contains no disallowed (write) keywords.

    A read-only ``CALL db.index.vector.queryNodes`` is permitted.
    """
    tokens = set(re.findall(r"[A-Za-z]+", (cypher or "").upper()))
    blocked = tokens & FORBIDDEN_CYPHER_KEYWORDS
    if "CALL" in blocked and any(sig in (cypher or "") for sig in ALLOWED_CALL_SIGNATURES):
        blocked.discard("CALL")
    return not blocked


def extract_search_term(prompt: str) -> str:
    """Pick a robust keyword from a user prompt.

    Strips punctuation and returns the longest token (good for matching legal
    citation fragments). Falls back to the cleaned prompt if there are no words.
    """
    clean = re.sub(r"[^\w\s]", "", prompt or "")
    words = sorted(clean.split(), key=len, reverse=True)
    return words[0] if words else clean.strip()


def citation_id(node: Any) -> Optional[str]:
    """Extract a citation id from a result node in any of its known shapes.

    Handles flat rows ({"id": ...}) and wrapped rows ({"n": {"id": ...}}).
    """
    if not isinstance(node, dict):
        return None
    if node.get("id"):
        return str(node["id"])
    for wrapper in ("n", "m", "node"):
        inner = node.get(wrapper)
        if isinstance(inner, dict) and inner.get("id"):
            return str(inner["id"])
    return None


def dedupe_nodes(nodes: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate result nodes by their citation id, preserving order."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for node in nodes:
        cid = citation_id(node)
        key = cid if cid is not None else id(node)
        if key not in seen:
            seen.add(key)
            out.append(node)
    return out


def embedding_matches_index(embedding: Optional[List[float]], expected_dim: int) -> bool:
    """Return True if an embedding is non-empty and matches the index dimension."""
    return bool(embedding) and len(embedding) == expected_dim


class LRUCache:
    """A minimal bounded LRU cache backed by an OrderedDict.

    Used to keep the on-disk query cache from growing without bound.
    """

    def __init__(self, max_entries: int = 500, initial: Optional[dict] = None):
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self.max_entries = max_entries
        self._data: "OrderedDict[str, Any]" = OrderedDict(initial or {})
        self._evict()

    def _evict(self) -> None:
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def get(self, key: str) -> Any:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        self._evict()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def keys(self):
        return self._data.keys()

    def as_dict(self) -> dict:
        return dict(self._data)
