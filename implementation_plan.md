### Phase 7: Hybrid RAG (Vector + Graph + Live Search)

This phase integrates semantic retrieval and real-time grounding into the core query pipeline.

#### [MODIFY] [legal_api_server.py](file:///home/lab/backend/legal_api_server.py)
- **Live Search**: Replace mock with `duckduckgo_search` library.
- **Vector Search**: Implement `generate_question_embedding` and semantic retrieval from `legal_vector_index`.
- **Hybrid Context**: Merge Vector and Cypher results before synthesis.
- **Safety**: Preserve all existing Cypher guardrails and streaming logic.

---

### Phase 8: Verification

- Verify that questions with semantic nuance (e.g., "Tell me about building emission rules") return relevant provisions via Vector Search even if the exact Cypher match is narrow.
- Verify that "Search" toggle results include live titles and URLs from DuckDuckGo.
- Confirm persistent SSE streaming and BackgroundTask caching.

## Verification Plan

### Automated Tests
-   Verify `/query` responsiveness with `use_search=true`.
-   Check logs for `Vector results: 3 nodes found`.
-   Verify `pip install duckduckgo-search` is documented.

### Manual Verification
-   Ask about recent NYC news or specific regulations and check for live citations.
