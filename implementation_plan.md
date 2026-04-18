### Phase 7: Hybrid RAG (Vector + Graph + Live Search)

This phase integrates semantic retrieval and real-time grounding into the core query pipeline.

#### [MODIFY] [legal_api_server.py](file:///home/lab/backend/legal_api_server.py)
- **Live Search**: Replace mock with `duckduckgo_search` library.
- **Vector Search**: Implement `generate_question_embedding` and semantic retrieval from `legal_vector_index`.
- **Hybrid Context**: Merge Vector and Cypher results before synthesis.
- **Safety**: Preserve all existing Cypher guardrails and streaming logic.

---

### Phase 9: Critical Architectural & Safety Fixes

This phase addresses critical vulnerabilities and stability issues identified during the review.

#### [MODIFY] [legal_api_server.py](file:///home/lab/backend/legal_api_server.py)
- **CORS Fix**: Explicitly allow `http://localhost:3005` to permit credentialed requests.
- **Portability**: Change `CACHE_FILE` to `./database/query_cache.json`.

#### [MODIFY] [.env](file:///home/lab/config/.env)
- **Sanitization**: Remove bad prefixes from `OPENAI_API_KEY`.

#### [MODIFY] [Chat.jsx](file:///home/lab/talk-to-nyc/src/components/Chat.jsx)
- **Robust SSE**: Implement buffer-based chunk parsing to prevent token dropping.

---

### Phase 10: Final Verification

## Verification Plan

### Automated Tests
-   Verify `/query` responsiveness with `use_search=true`.
-   Check logs for `Vector results: 3 nodes found`.
-   Verify `pip install duckduckgo-search` is documented.

### Manual Verification
-   Ask about recent NYC news or specific regulations and check for live citations.
