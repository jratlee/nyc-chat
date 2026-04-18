# NYC Intelligence Platform: Regulatory GraphRAG

This project is a high-fidelity intelligence platform for New York City's regulatory landscape. It uses a **GraphRAG** pipeline to traverse the NYC Charter, Administrative Code, and Rules of the City of New York.

## Project Structure

- **`frontend/`**: A Vite + React application styled in an "Only NY" heritage aesthetic.
- **`backend/`**: 
  - `legal_api_server.py`: The FastAPI bridge that translates natural language to Cypher and synthesizes answers. Supports multi-turn memory.
  - `extract_legal_graph.py`: The ETL pipeline that parses 1,236 legislative XML files into Neo4j.
  - `embed_graph.py`: Standalone script for generating OpenAI vector embeddings for provisions.
  - `legal_mcp_server.py`: MCP server implementation for agentic interactions.
- **`database/`**:
  - `docker-compose.yml`: Infrastructure for Neo4j with APOC.
  - `query_cache.json`: Pre-warmed knowledge base of 0ms latency legal answers.
- **`config/`**:
  - `.env`: Environment variables (OpenAI, Neo4j credentials).

## Key Features

### 1. Conversational Memory
The platform now supports multi-turn dialogue. It tracks `session_id` and injects conversation history into the synthesis pipeline, allowing users to ask follow-up questions like "How does this rule apply to my building?".

### 2. "Penalty Poker" Integration
The dashboard's Penalty Poker game is now dynamic, pulling real legal violations and fines from the Neo4j graph in real-time.

### 3. Web Search Grounding
Optional grounding with external web context to blend static legal code with current regulatory updates.

### 4. Hybrid Search Readiness
Includes a dedicated embedding pipeline (`embed_graph.py`) to prepare the knowledge graph for semantic vector search.

---
*Created for the NYC Regulatory Intelligence Project*
