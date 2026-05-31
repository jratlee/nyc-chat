# Talk to NYC

Talk to NYC is a question-answering system for New York City's legal corpus: the City Charter, the Administrative Code, and the Rules of the City of New York. It reads the official XML versions of those documents, turns them into a searchable knowledge graph, and lets you ask plain-English questions like "Can I keep bees in Queens?" or "What's the fine for not curbing my dog?"

It is built as a Hybrid GraphRAG system, which means it combines two kinds of retrieval before it answers:

- **Vector search** finds passages that are semantically similar to your question, even when they don't share the same words.
- **Graph traversal** follows the citations and cross-references between sections, so the system can tell you not just what a rule says but which other rules point to it.

The retrieved context is then handed to a language model (OpenAI by default, with a local Ollama fallback) to write the final answer, and every answer keeps its source citations attached.

## How it was built

The project grew out of a simple problem: NYC's law is published as thousands of small XML files, and the relationships between them (a Charter section authorizing a Rule, a Rule citing a Code provision) are hard to follow by reading alone. The pipeline below was built to make those relationships queryable.

### 1. Parsing the XML into a graph

`extract_legal_graph.py` walks the XML files in `data/xml/` (NYC1 is the Charter, NYC2 is the Administrative Code, NYC3 is the Rules). For each file it pulls out the section identifier from the heading, creates a node in Neo4j, and reads the `<LINK>` tags to build `CITES` edges between sections. Where a section mentions an exception, a local Llama/Qwen model is used to extract it into a structured `EXCEPTION` node.

The resulting graph uses these node types and relationships:

- Nodes: `CHARTER_SECTION`, `ADMIN_CODE_SECTION`, `RULES_SECTION`, `PROVISION`, `EXCEPTION`
- Relationships: `CITES`, `IMPLEMENTS`, `EXCEPTS`, `TARGETS`

### 2. Embedding the nodes

`embed_graph.py` reads the section nodes back out of Neo4j, generates an embedding for each one with OpenAI's `text-embedding-3-small` model, and writes the vector back onto the node. It then creates a Neo4j vector index (`legal_vector_index`) so the app can run nearest-neighbor searches at query time. The embedding dimension is configurable, so you can swap in a different model.

### 3. Answering questions

At query time the app works in three steps:

1. Embed the user's question and run a vector search against the index, keeping only the closer matches.
2. Run a keyword Cypher query as a fallback so plain term matches aren't missed.
3. Merge and de-duplicate the two result sets, optionally add live web results, and pass everything to the language model with instructions to cite section IDs and clearly separate graph-sourced facts from web-sourced ones.

The shared, dependency-free pieces of this logic (the Cypher safety guard that blocks write operations, the LRU query cache, the embedding-dimension check, and the search-term extractor) live in `legal_utils.py` and are covered by unit tests.

### 4. Three ways to use it

The same graph is exposed through three front ends:

- **Streamlit app** (`streamlit_app.py`) is the main interface and the easiest to deploy.
- **FastAPI backend** (`legal_api_server.py`) serves a Vite/React frontend in `talk-to-nyc/`, which has a chat tab plus two experimental views: "Penalty Poker" and a "Red Tape Timeline".
- **MCP server** (`legal_mcp_server.py`) exposes the graph as a Model Context Protocol tool, so other AI agents can query NYC law directly.

## What you can do with it

- Ask whether something is allowed and get an answer grounded in the actual Charter, Code, or Rules, with the section numbers to check.
- Look up penalties and requirements without reading through the raw legal text.
- Trace how regulations connect by following the citation graph from one section to the next.
- Toggle live web search when you need recent news or updates that aren't in the static corpus.
- Plug the MCP server into another agent and let it answer NYC legal questions as part of a larger workflow.

It is a research and exploration tool, not a source of legal advice.

## Setup

### Step 1: Create a Neo4j AuraDB account

Before deploying you need a working Neo4j database.

1. Go to [Neo4j AuraDB](https://neo4j.com/cloud/aura-free/) and create a Free Tier instance.
2. Download the generated credentials `.txt` file. It contains your `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.

> [!IMPORTANT]
> Logging into the Aura console (for example, via Google) is separate from your database connection credentials. The app authenticates with the database password from the downloaded `.txt` file, not your console login. That password is shown only once at creation time. If you lost it, open the instance in the console and use **Reset password**.

## Running the app

### Path A: Local execution (development)

To run the platform locally with full features (including the Ollama local fallback):

1. Install dependencies (a virtual environment is recommended):
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
   ```text
   OPENAI_API_KEY=sk-...
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_password
   ```
   > [!IMPORTANT]
   > Never commit your `.env` file. It is already listed in `.gitignore`.
3. Start Neo4j. Make sure Docker is running and launch the database from the `database/` directory:
   ```bash
   docker compose -f database/docker-compose.yml up -d
   ```
4. Load the data. The repository includes the core XML sources in `data/xml/`. To populate your local instance, run:
   ```bash
   python3 extract_legal_graph.py
   python3 embed_graph.py
   ```
   > [!TIP]
   > By default only the first 20 XML files per source are ingested for a fast demo. Set `MAX_FILES_PER_SOURCE=0` in your `.env` to ingest everything.
5. Launch Streamlit:
   ```bash
   streamlit run streamlit_app.py
   ```

### Path A2: React frontend + FastAPI backend (optional)

The repo also ships a Vite/React frontend backed by the FastAPI server.

1. Start the API (port 8005):
   ```bash
   python3 legal_api_server.py
   ```
2. Start the frontend (port 3005):
   ```bash
   cd talk-to-nyc
   cp .env.example .env   # set VITE_API_BASE_URL if the API is not on localhost:8005
   npm install
   npm run dev
   ```
   > [!NOTE]
   > If the frontend is served from a non-localhost origin (for example, Codespaces), set `CORS_ORIGINS` for the API and `VITE_API_BASE_URL` for the frontend so the two can talk.

### Secrets management

- **Local development**: use a `.env` file so the app can load credentials with `python-dotenv`.
- **Cloud deployment**: on platforms like Streamlit Community Cloud, go to your app settings, then **Secrets**, and paste your credentials in TOML format. Never hardcode secrets in your repository.

### Path B: Streamlit Cloud deployment

To host this on the web with Streamlit Cloud:

1. Push the code to a GitHub repository (for example, `jratlee/nyc-chat`).
2. Provision a remote database. You cannot use `localhost` in the cloud, so use something like the [Neo4j AuraDB Free Tier](https://neo4j.com/cloud/aura-free/).
3. In the Streamlit Cloud dashboard, go to **Advanced Settings**, then **Secrets**, and paste your variables:
   ```toml
   OPENAI_API_KEY = "sk-..."
   NEO4J_URI = "neo4j+s://your-db-id.databases.neo4j.io"
   NEO4J_USER = "neo4j"
   NEO4J_PASSWORD = "your_password"
   ```
4. Point the main file path to `streamlit_app.py` and deploy.

## Configuration reference

All settings are read from environment variables (or Streamlit secrets, or a `.env` file). See `.env.example`.

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | (none) | OpenAI key for embeddings and synthesis. Falls back to Ollama if unset. |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI (use `neo4j+s://...` for AuraDB). |
| `NEO4J_USER` | `neo4j` | Neo4j username. |
| `NEO4J_PASSWORD` | `password123` | Neo4j password. |
| `OLLAMA_MODEL` | `qwen2.5` | Local Ollama model used for fallback. |
| `EMBEDDING_DIM` | `1536` | Vector index dimension. Must match the embedding model. |
| `MAX_FILES_PER_SOURCE` | `20` | XML files ingested per source (`0` = all). |
| `CORS_ORIGINS` | `http://localhost:3005,...` | Comma-separated allowed origins for the FastAPI server. |
| `CORS_ORIGIN_REGEX` | (none) | Optional regex for dynamic origins (for example, Codespaces URLs). |
| `CACHE_MAX_ENTRIES` | `500` | Max entries in the API's LRU query cache. |
| `VITE_API_BASE_URL` | `http://localhost:8005` | Frontend-to-backend base URL (set in `talk-to-nyc/.env`). |

## Testing

The pure-logic helpers (Cypher safety guard, LRU cache, embedding-dimension guard, citation parsing) are unit-tested and run without any external services:

```bash
pip install pytest
pytest -q
```

## Features

- **Hybrid retrieval**: merges vector search (semantic) with Cypher graph traversal (relationships).
- **Live grounding**: optional real-time web search through DuckDuckGo.
- **Local resilience**: automatic failover to local Llama/Qwen models through Ollama when OpenAI is unavailable.
- **Safety**: built-in Cypher injection protection and environment-aware configuration.

## Repository structure

- `streamlit_app.py`: the primary Streamlit entry point.
- `legal_api_server.py`: FastAPI backend for the React frontend.
- `legal_mcp_server.py`: Model Context Protocol server that exposes the graph as a tool.
- `legal_utils.py`: shared, side-effect-free helpers (Cypher guard, LRU cache, and so on).
- `extract_legal_graph.py`: parses NYC XML into the Neo4j graph.
- `embed_graph.py`: generates vector embeddings and builds the vector index.
- `tests/`: Pytest unit tests for the pure-logic helpers.
- `talk-to-nyc/`: Vite/React frontend source.
- `database/`: Docker Compose for local Neo4j plus the runtime cache.
