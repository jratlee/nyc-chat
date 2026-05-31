# Talk to NYC — Regulatory Intelligence Platform

A Hybrid GraphRAG platform for navigating the complex web of New York City's Charter, Administrative Code, and Rules.

### Step 1: Create a Neo4j AuraDB Account
Before deploying, you must have a functional Neo4j database. 
1. Go to [Neo4j AuraDB](https://neo4j.com/cloud/aura-free/) and create a **Free Tier** instance.
2. Download the generated credentials `.txt` file. This contains your `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.

> [!IMPORTANT]
> Logging into the Aura **console** (e.g. via Google) is separate from your **database connection credentials**. The app authenticates with the database password from the downloaded `.txt` file — not your console login. The password is shown only once at creation time; if you lost it, open the instance in the console and use **Reset password**.

## 🚀 Running the App

### Path A: Local Execution (Development)
To run the platform locally with full features (including Ollama local fallback), follow these steps:

1. **Install dependencies** (a virtual environment is recommended):
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Environment**: Copy `.env.example` to `.env` and fill in your credentials:
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
   > Never commit your `.env` file. It is already included in the `.gitignore`.
3. **Start Neo4j**: Ensure Docker is running and launch the database from the `database/` directory:
   ```bash
   docker compose -f database/docker-compose.yml up -d
   ```
4. **Data Onboarding (Local)**: The repository includes the core XML data sources in `data/xml/`. To populate your local instance, run:
   ```bash
   python3 extract_legal_graph.py
   python3 embed_graph.py
   ```
   > [!TIP]
   > By default only the first 20 XML files per source are ingested for a fast demo.
   > Set `MAX_FILES_PER_SOURCE=0` in your `.env` to ingest everything.
5. **Launch Streamlit**:
   ```bash
   streamlit run streamlit_app.py
   ```

### Path A2: React Frontend + FastAPI Backend (Optional)
The repo also ships a Vite/React frontend backed by the FastAPI server.

1. **Start the API** (port 8005):
   ```bash
   python3 legal_api_server.py
   ```
2. **Start the frontend** (port 3005):
   ```bash
   cd talk-to-nyc
   cp .env.example .env   # set VITE_API_BASE_URL if the API is not on localhost:8005
   npm install
   npm run dev
   ```
   > [!NOTE]
   > If the frontend is served from a non-localhost origin (e.g. Codespaces), set
   > `CORS_ORIGINS` for the API and `VITE_API_BASE_URL` for the frontend so the two can talk.

### 🔐 Secrets Management
- **Local Development**: Use a `.env` file. This allows the app to load credentials using `python-dotenv`.
- **Cloud Deployment**: For platforms like **Streamlit Community Cloud**, go to your app settings -> **Secrets** and paste your credentials in TOML format. **Never** hardcode secrets in your repository.

### Path B: Streamlit Cloud Deployment
To host this platform on the web using Streamlit Cloud:

1. **Repository**: Push the code to a GitHub repository (e.g., `jratlee/nyc-chat`).
2. **Cloud Database**: You cannot use `localhost` in the cloud. You must provision a remote database (e.g., [Neo4j AuraDB Free Tier](https://neo4j.com/cloud/aura-free/)).
3. **Configure Secrets**: In the Streamlit Cloud dashboard, go to **Advanced Settings -> Secrets** and paste your `.env` variables:
   ```toml
   OPENAI_API_KEY = "sk-..."
   NEO4J_URI = "neo4j+s://your-db-id.databases.neo4j.io"
   NEO4J_USER = "neo4j"
   NEO4J_PASSWORD = "your_password"
   ```
4. **Deploy**: Point the main file path to `streamlit_app.py`.

---

## ⚙️ Configuration Reference
All settings are read from environment variables (or Streamlit secrets / a `.env` file). See `.env.example`.

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | OpenAI key for embeddings + synthesis. Falls back to Ollama if unset. |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI (use `neo4j+s://…` for AuraDB). |
| `NEO4J_USER` | `neo4j` | Neo4j username. |
| `NEO4J_PASSWORD` | `password123` | Neo4j password. |
| `OLLAMA_MODEL` | `qwen2.5` | Local Ollama model used for fallback. |
| `EMBEDDING_DIM` | `1536` | Vector index dimension. Must match the embedding model. |
| `MAX_FILES_PER_SOURCE` | `20` | XML files ingested per source (`0` = all). |
| `CORS_ORIGINS` | `http://localhost:3005,…` | Comma-separated allowed origins for the FastAPI server. |
| `CORS_ORIGIN_REGEX` | — | Optional regex for dynamic origins (e.g. Codespaces URLs). |
| `CACHE_MAX_ENTRIES` | `500` | Max entries in the API's LRU query cache. |
| `VITE_API_BASE_URL` | `http://localhost:8005` | Frontend → backend base URL (set in `talk-to-nyc/.env`). |

## 🧪 Testing
Pure-logic helpers (Cypher safety guard, LRU cache, embedding-dimension guard, citation parsing) are unit-tested and run without any external services:
```bash
pip install pytest
pytest -q
```

---

## 🛠 Features
- **Hybrid Retrieval**: Merges Vector Search (semantic) with Cypher Query (graph relationship traversal).
- **Live Grounding**: Real-time web search integration via DuckDuckGo.
- **Local Resilience**: Automatic failover to local Llama/Qwen models via Ollama if OpenAI quotas are exceeded.
- **Security**: Built-in Cypher injection protection and environment-aware configuration.

## 📁 Repository Structure
- `streamlit_app.py`: The primary entry point for Streamlit.
- `legal_api_server.py`: FastAPI backend (for React-based frontend use).
- `legal_mcp_server.py`: Model Context Protocol (MCP) server exposing the graph as a tool.
- `legal_utils.py`: Shared, side-effect-free helpers (Cypher guard, LRU cache, etc.).
- `extract_legal_graph.py`: Parses NYC XML into the Neo4j graph.
- `embed_graph.py`: Generates and stores vector embeddings + the vector index.
- `tests/`: Pytest unit tests for the pure-logic helpers.
- `talk-to-nyc/`: Vite/React frontend source.
- `database/`: Docker Compose for local Neo4j + runtime cache.

---
*Created for NYC Regulatory Intelligence by False Dawn Industries.*
