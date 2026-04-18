import streamlit as st
import os
import re
import json
import time
from neo4j import GraphDatabase
from openai import OpenAI
from duckduckgo_search import DDGS
from dotenv import load_dotenv

# Safe Ollama Import
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

# Load local .env if it exists
load_dotenv()

# --- ROBUST CONFIGURATION ---
def get_secret_or_env(key, default=None):
    """
    Safely check Streamlit secrets, then environment variables, then default.
    """
    try:
        val = st.secrets.get(key)
        if val: return val
    except Exception:
        pass
    return os.getenv(key) or default

OPENAI_API_KEY = get_secret_or_env("OPENAI_API_KEY")
NEO4J_URI = get_secret_or_env("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = get_secret_or_env("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = get_secret_or_env("NEO4J_PASSWORD", "password123")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5")

# --- UI SETUP ---
st.set_page_config(page_title="Talk to NYC", page_icon="🏙️", layout="wide")

with st.sidebar:
    st.title("🏙️ Talk to NYC")
    st.markdown("*NYC Regulatory Intelligence Platform — Powered by Hybrid GraphRAG*")
    st.divider()
    use_web_search = st.toggle("🌐 Enable Live Web Search", value=False, help="Use for extremely recent news, updates, or specific non-legal entities.")
    st.info("System Status: Operational\n\nDatabase: Local Docker / Remote AuraDB\n\nIntelligence: Hybrid Graph + OpenAI 4o / Ollama")

st.title("🏙️ NYC Regulatory Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- CORE LOGIC ---
class LegalGraphClient:
    def __init__(self):
        try:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self.driver.verify_connectivity()
        except Exception as e:
            if "localhost" in NEO4J_URI or "127.0.0.1" in NEO4J_URI:
                st.error("""
                ### 🛑 Database Connection Failed (Localhost Default)
                The application is trying to connect to a local database (`localhost:7687`), but it cannot be found.
                
                **👉 If you are running this LOCALLY:**
                Please ensure Docker is running and execute `docker-compose up -d` inside the `database/` directory.

                **👉 If you are running this in the CLOUD (Streamlit Community Cloud):**
                Streamlit Cloud cannot access your local computer's Docker. You must configure your cloud database credentials:
                1. Go to your Streamlit App Dashboard -> Settings -> Secrets
                2. Add your Neo4j AuraDB credentials:
                ```toml
                NEO4J_URI = "neo4j+s://<YOUR_AURA_DB_HASH>.databases.neo4j.io"
                NEO4J_USER = "neo4j"
                NEO4J_PASSWORD = "<YOUR_SECURE_PASSWORD>"
                OPENAI_API_KEY = "sk-..."
                ```
                """)
            else:
                st.error("### ❌ Remote Database Connection Failed\nVerify your Neo4j AuraDB credentials are correct in Streamlit Secrets, and ensure your AuraDB instance is not paused.")
            st.warning(f"Error Details: {e}")
            self.driver = None

    def query(self, cypher: str, params: dict = None):
        if not self.driver: return []
        forbidden = ["DELETE", "DETACH", "REMOVE", "DROP", "CREATE", "MERGE", "SET"]
        if any(word in cypher.upper() for word in forbidden):
            return []
        with self.driver.session() as session:
            try:
                result = session.run(cypher, params or {})
                return [record.data() for record in result]
            except Exception as e:
                return []

@st.cache_resource
def get_db():
    return LegalGraphClient()

db = get_db()

def generate_embedding(text):
    """
    Prioritize OpenAI embedding, fallback to local Ollama if available.
    """
    if OPENAI_API_KEY and "sk-" in OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            res = client.embeddings.create(input=text, model="text-embedding-3-small")
            return res.data[0].embedding
        except Exception as e:
            st.warning(f"OpenAI Embedding failed: {e}. Checking for Ollama fallback...")
    
    if OLLAMA_AVAILABLE:
        try:
            res = ollama.embeddings(model=OLLAMA_MODEL, prompt=text)
            return res['embedding']
        except Exception as e:
            st.error(f"Ollama Embedding failed: {e}")
    
    return None

def perform_web_search(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            return "\n".join([f"- {r['title']} ({r['href']}): {r['body']}" for r in results])
    except:
        return ""

# --- CHAT INTERFACE ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "citations" in msg:
            with st.expander("📚 View References & Citations"):
                for cite in msg["citations"]:
                    st.markdown(cite)

# Graceful input handling
if db.driver is None:
    st.info("💡 **Chat Disabled**: Please resolve the database connection issue above to start querying NYC legal data.")
    prompt = None
else:
    prompt = st.chat_input("Ask about NYC Charter, Code, or Rules...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        context_nodes = []
        web_context = ""
        
        # 1. Context Retrieval (Status Block)
        status_label = "🔍 Searching Legal Graph & Web..." if use_web_search else "🔍 Searching NYC Legal Graph..."
        with st.status(status_label) as status:
            # A. Embed & Hybrid Search
            emb = generate_embedding(prompt)
            vector_res = []
            if emb:
                vector_res = db.query(
                    "CALL db.index.vector.queryNodes('legal_vector_index', 3, $emb) YIELD node, score RETURN node.id as id, node.description as desc, score",
                    {"emb": emb}
                )
            
            # 2. Cypher Fallback/Search (Refined Keyword Matching)
            # Grab the longest word from the prompt to use as a fuzzy keyword fallback
            words = sorted(prompt.split(), key=len, reverse=True)
            search_term = words[0] if words else prompt
            
            cypher = """
            MATCH (n) 
            WHERE toLower(n.id) CONTAINS toLower($search_term) 
               OR toLower(n.description) CONTAINS toLower($search_term)
            RETURN n.id as id, n.description as desc 
            LIMIT 3
            """
            graph_res = db.query(cypher, {"search_term": search_term})
            
            # Combine and deduplicate context nodes
            seen_ids = set()
            context_nodes = []
            for node in (vector_res + graph_res):
                if node.get('id') not in seen_ids:
                    seen_ids.add(node.get('id'))
                    context_nodes.append(node)
            
            # C. Web search if toggled
            if use_web_search:
                web_context = perform_web_search(prompt)
            
            status.update(label="✅ Context Retrieved", state="complete")

        # 2. Stream Synthesis (Outside status block)
        history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages[-5:]])
        system_prompt = f"""
        You are a helpful NYC legal assistant. 
        
        STRICT RULES:
        1. Explicitly distinguish between information from the NYC Legal Graph and Web Search.
        2. If Web context is used, prefix those statements with: "According to recent web search outcomes..."
        3. Always cite node IDs (e.g., 28-320) directly for graph-sourced data.
        4. Be precise and avoid legal advice.
        
        HISTORY: {history}
        CONTEXT (Graph): {json.dumps(context_nodes[:5])}
        CONTEXT (Web): {web_context}
        """
        
        try:
            if OPENAI_API_KEY:
                client = OpenAI(api_key=OPENAI_API_KEY)
                stream = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                    stream=True
                )
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                        response_placeholder.markdown(full_response + "▌")
            elif OLLAMA_AVAILABLE:
                stream = ollama.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': system_prompt + "\n\nUser: " + prompt}], stream=True)
                for chunk in stream:
                    full_response += chunk['message']['content']
                    response_placeholder.markdown(full_response + "▌")
            else:
                st.error("No LLM Provider Available. Please configure an OpenAI API Key in Streamlit Secrets for cloud deployment, or install and run Ollama for local execution.")
                full_response = "Platform Error: No LLM configuration found."
        except Exception as e:
            full_response = f"Error: {e}"
            
        response_placeholder.markdown(full_response)
        
        # 3. Citation Expander
        with st.expander("📚 View References & Citations"):
            for n in context_nodes:
                # Safely handle missing IDs or descriptions
                node_id = n.get('id') or "Unknown Citation"
                node_desc = n.get('desc') or "No summary available in the legal graph."
                
                # Safely slice the description string
                short_desc = node_desc[:250] + "..." if len(node_desc) > 250 else node_desc
                st.markdown(f"- **{node_id}**: {short_desc}")
            
            if use_web_search and web_context:
                st.markdown("---")
                st.markdown("**Web Search Context:**")
                st.markdown(web_context)
        
        # We store citations as context_nodes for session history consistency
        st.session_state.messages.append({"role": "assistant", "content": full_response, "citations": context_nodes})
