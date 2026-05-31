"""Unit tests for the pure-logic helpers in legal_utils.

These run without Neo4j, OpenAI, Ollama, Streamlit, or FastAPI.
"""
import pytest

from legal_utils import (
    LRUCache,
    citation_id,
    dedupe_nodes,
    embedding_matches_index,
    extract_search_term,
    is_cypher_safe,
)


# --- Cypher safety guard -------------------------------------------------

@pytest.mark.parametrize("query", [
    "MATCH (n) RETURN n LIMIT 5",
    "MATCH (n) WHERE n.id CONTAINS '28-320' RETURN n",
    "CALL db.index.vector.queryNodes('legal_vector_index', 5, $emb) YIELD node RETURN node",
])
def test_safe_queries_allowed(query):
    assert is_cypher_safe(query) is True


@pytest.mark.parametrize("query", [
    "MATCH (n) DELETE n",
    "MATCH (n) DETACH DELETE n",
    "CREATE (n:Foo)",
    "MERGE (n:Foo {id: '1'})",
    "MATCH (n) SET n.x = 1",
    "DROP INDEX legal_vector_index",
    "MATCH (n) REMOVE n.x RETURN n",
    "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
    "CALL dbms.security.createUser('x', 'y')",
])
def test_write_queries_blocked(query):
    assert is_cypher_safe(query) is False


def test_no_false_positive_on_words_containing_keywords():
    # "asset" and "preset" contain SET; "increment" contains... nothing forbidden
    assert is_cypher_safe("MATCH (n) WHERE n.text CONTAINS 'asset' RETURN n")
    assert is_cypher_safe("MATCH (n) WHERE n.desc CONTAINS 'preset value' RETURN n")


def test_empty_query_is_safe():
    assert is_cypher_safe("") is True
    assert is_cypher_safe(None) is True


# --- Search term extraction ---------------------------------------------

def test_extract_search_term_longest_word():
    # "section" (7) is longer than "28320" (5) after punctuation is stripped.
    assert extract_search_term("What is section 28-320?") == "section"


def test_extract_search_term_strips_punctuation():
    assert extract_search_term("bee-keeping!!!") == "beekeeping"


def test_extract_search_term_empty():
    assert extract_search_term("") == ""
    assert extract_search_term("   ") == ""


# --- Citation id extraction ---------------------------------------------

def test_citation_id_flat():
    assert citation_id({"id": "28-320", "desc": "x"}) == "28-320"


def test_citation_id_wrapped():
    assert citation_id({"n": {"id": "255"}}) == "255"
    assert citation_id({"m": {"id": "3307"}}) == "3307"


def test_citation_id_missing():
    assert citation_id({"desc": "no id"}) is None
    assert citation_id("not a dict") is None
    assert citation_id({"n": {"desc": "no id"}}) is None


# --- Dedupe --------------------------------------------------------------

def test_dedupe_preserves_order_and_removes_dupes():
    nodes = [
        {"id": "a", "score": 1},
        {"id": "b"},
        {"id": "a", "score": 2},  # duplicate id
        {"n": {"id": "b"}},        # duplicate via wrapper
        {"id": "c"},
    ]
    result = dedupe_nodes(nodes)
    ids = [citation_id(n) for n in result]
    assert ids == ["a", "b", "c"]


def test_dedupe_keeps_idless_nodes_distinct():
    nodes = [{"desc": "x"}, {"desc": "y"}]
    assert len(dedupe_nodes(nodes)) == 2


# --- Embedding dimension guard ------------------------------------------

def test_embedding_matches_index():
    assert embedding_matches_index([0.0] * 1536, 1536) is True


def test_embedding_dim_mismatch():
    assert embedding_matches_index([0.0] * 768, 1536) is False
    assert embedding_matches_index([], 1536) is False
    assert embedding_matches_index(None, 1536) is False


# --- LRU cache -----------------------------------------------------------

def test_lru_basic_set_get():
    c = LRUCache(max_entries=3)
    c.set("a", 1)
    c.set("b", 2)
    assert c.get("a") == 1
    assert c.get("missing") is None
    assert len(c) == 2


def test_lru_evicts_oldest():
    c = LRUCache(max_entries=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)  # should evict "a"
    assert "a" not in c
    assert "b" in c
    assert "c" in c
    assert len(c) == 2


def test_lru_access_refreshes_recency():
    c = LRUCache(max_entries=2)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")       # "a" is now most-recent
    c.set("c", 3)    # should evict "b", not "a"
    assert "a" in c
    assert "b" not in c
    assert "c" in c


def test_lru_trims_oversized_initial():
    c = LRUCache(max_entries=2, initial={"a": 1, "b": 2, "c": 3})
    assert len(c) == 2


def test_lru_rejects_bad_capacity():
    with pytest.raises(ValueError):
        LRUCache(max_entries=0)
