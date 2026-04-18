# Talk to NYC — Regulatory Intelligence Platform

A Hybrid GraphRAG platform for navigating the complex web of New York City's Charter, Administrative Code, and Rules.

### Step 1: Create a Neo4j AuraDB Account
Before deploying, you must have a functional Neo4j database. 
1. Go to [Neo4j AuraDB](https://neo4j.com/cloud/aura-free/) and create a **Free Tier** instance.
2. Download the generated credentials `.txt` file. This contains your `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.

## 🚀 Running the App

### Path A: Local Execution (Development)
To run the platform locally with full features (including Ollama local fallback), follow these steps:

1. **Start Neo4j**: Ensure Docker is running and launch the database:
   ```bash
   docker-compose up -d
   ```
2. **Data Onboarding (Local)**: The repository now includes the core XML data sources in `data/xml/`. To populate your local instance, run:
   ```bash
   python3 extract_legal_graph.py
   python3 embed_graph.py
   ```
3. **Environment**: Create a `.env` file in the root with your credentials:
   ```text
   OPENAI_API_KEY=sk-...
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_password
   ```
   > [!IMPORTANT]
   > Never commit your `.env` file. It is already included in the `.gitignore`.

3. **Launch Streamlit**:
   ```bash
   streamlit run streamlit_app.py
   ```

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
