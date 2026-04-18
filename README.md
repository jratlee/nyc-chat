# Talk to NYC — Regulatory Intelligence Platform

A Hybrid GraphRAG platform for navigating the complex web of New York City's Charter, Administrative Code, and Rules.

## 🚀 Running the App

### Path A: Local Execution (Development)
To run the platform locally with full features (including Ollama local fallback), follow these steps:

1. **Start Neo4j**: Ensure Docker is running and launch the database:
   ```bash
   docker start nyc_legal_graph
   ```
2. **Environment**: Create a `.env` file in the root with your credentials:
   ```text
   OPENAI_API_KEY=sk-...
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_password
   ```
3. **Launch Streamlit**:
   ```bash
   streamlit run streamlit_app.py
   ```

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

## 🛠 Features
- **Hybrid Retrieval**: Merges Vector Search (semantic) with Cypher Query (graph relationship traversal).
- **Live Grounding**: Real-time web search integration via DuckDuckGo.
- **Local Resilience**: Automatic failover to local Llama/Qwen models via Ollama if OpenAI quotas are exceeded.
- **Security**: Built-in Cypher injection protection and environment-aware configuration.

## 📁 Repository Structure
- `streamlit_app.py`: The primary entry point for Streamlit.
- `legal_api_server.py`: FastAPI backend (for React-based frontend use).
- `talk-to-nyc/`: Vite/React frontend source.
- `database/`: Local graph data assets and cache.

---
*Created for NYC Regulatory Intelligence by False Dawn Industries.*
