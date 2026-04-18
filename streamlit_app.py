import streamlit as st
import os
import re
import json
import time
from neo4j import GraphDatabase
from openai import OpenAI
import ollama
from duckduckgo_search import DDGS
from dotenv import load_dotenv

# Load local .env if it exists
load_dotenv()

# --- CONFIGURATION ---
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
NEO4J_URI = st.secrets.get("NEO4J_URI") or os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = st.secrets.get("NEO4J_USER") or os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = st.secrets.get("NEO4J_PASSWORD") or os.getenv("NEO4J_PASSWORD", "password123")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5")

# --- UI SETUP ---
st.set_page_config(page_title="Talk to NYC", page_icon="🏙️", layout="wide")
st.title("🏙️ Talk to NYC")
st.markdown("*NYC Regulatory Intelligence Platform — Powered by Hybrid GraphRAG*")

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- CORE LOGIC ---
class LegalGraphClient:
    def __init__(self):
        try:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self.driver.verify_connectivity()
        except Exception as e:
            st.error(f"Neo4j Connection Failed: {e}")
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

db = LegalGraphClient()

def generate_embedding(text):
    if OPENAI_API_KEY and "sk-" in OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            res = client.embeddings.create(input=text, model="text-embedding-3-small")
            return res.data[0].embedding
        except:
             pass
    try:
        res = ollama.embeddings(model=OLLAMA_MODEL, prompt=text)
        return res['embedding']
    except:
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

if prompt := st.chat_input("Ask about NYC Charter, Code, or Rules..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        with st.status("🔍 Searching Legal Graph & Web...") as status:
            # 1. Embed & Hybrid Search
            emb = generate_embedding(prompt)
            vector_res = []
            if emb:
                vector_res = db.query(
                    "CALL db.index.vector.queryNodes('legal_vector_index', 3, $emb) YIELD node, score RETURN node.id as id, node.description as desc, score",
                    {"emb": emb}
                )
            
            # 2. Cypher Fallback/Search
            cypher = f"MATCH (n) WHERE n.id CONTAINS '{prompt[-5:]}' OR n.id CONTAINS '28-' RETURN n.id as id, n.description as desc LIMIT 3"
            graph_res = db.query(cypher)
            context_nodes = vector_res + graph_res
            
            # 3. Web search if enabled
            web_context = perform_web_search(prompt)
            status.update(label="✅ Context Found. Synthesizing Answer...", state="complete")

        # 4. Stream Synthesis
        history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages[-5:]])
        system_prompt = f"""
        You are a helpful NYC legal assistant. 
        HISTORY: {history}
        CONTEXT (Graph): {json.dumps(context_nodes[:5])}
        CONTEXT (Web): {web_context}
        
        Answer the question accurately. Cite citation IDs where available.
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
            else:
                stream = ollama.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': system_prompt + "\n\nUser: " + prompt}], stream=True)
                for chunk in stream:
                    full_response += chunk['message']['content']
                    response_placeholder.markdown(full_response + "▌")
        except Exception as e:
            full_response = f"Error: {e}"
            
        response_placeholder.markdown(full_response)
        st.session_state.messages.append({"role": "assistant", "content": full_response})
