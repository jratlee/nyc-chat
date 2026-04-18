import os
import re
import json
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase
from dotenv import load_dotenv
from openai import OpenAI
import ollama
import asyncio
import time
from duckduckgo_search import DDGS  # pip install duckduckgo-search

# Load environment variables
load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Providers
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5")
CYPHER_MODEL = os.getenv("CYPHER_MODEL", "gpt-4o-mini")
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "gpt-4o")

# Database Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

FEW_SHOT_CYPHER_PROMPT = """
You are a Neo4j Cypher Expert for New York City legal data.
Translate the user's question into a clean Cypher query based on the following schema:

NODES:
- CHARTER_SECTION {{id: "..."}}
- ADMIN_CODE_SECTION {{id: "..."}}
- RULES_SECTION {{id: "..."}}
- PROVISION {{id: "..."}}
- EXCEPTION {{id: "...", description: "..."}}

RELATIONSHIPS:
- [:CITES] ->
- [:IMPLEMENTS] ->
- [:EXCEPTS] ->
- [:TARGETS] ->

GUIDELINES:
1. Always include `LIMIT 5` at the end of the query.
2. Use `CONTAINS` for ID matching to be robust (e.g., WHERE n.id CONTAINS '28-320').
3. NEVER use unbounded variable-length paths like `[*]`. Use `[*1..3]` if needed.
4. Return ONLY the Cypher query text. No markdown, no preamble.

EXAMPLES:
Q: What sections implement LL97 building emissions?
A: MATCH (c:CHARTER_SECTION)-[:IMPLEMENTS]->(a:ADMIN_CODE_SECTION) WHERE a.id CONTAINS '28-320' RETURN a LIMIT 5

Q: Are there exceptions to sidewalk shed requirements?
A: MATCH (s:RULES_SECTION)-[:EXCEPTS]->(e:EXCEPTION) WHERE s.id CONTAINS '3307' RETURN e LIMIT 5

Q: Find rules cited by Charter 255.
A: MATCH (c:CHARTER_SECTION {{id: '255'}})-[:CITES]->(r:RULES_SECTION) RETURN r LIMIT 5

User Question: {question}
"""

app = FastAPI()

# Enable CORS for the Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3005"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UnifiedLLM:
    def __init__(self):
        self.use_openai = bool(OPENAI_API_KEY and "sk-" in OPENAI_API_KEY)
        if self.use_openai:
            # Disable retries to ensure immediate fallback on quota error
            self.client = OpenAI(api_key=OPENAI_API_KEY, max_retries=0)
            logger.info("UnifiedLLM initialized with OpenAI (Streaming Enabled)")
        else:
            logger.info(f"UnifiedLLM initialized with local Ollama ({OLLAMA_MODEL})")

    async def stream_chat(self, prompt: str, model_type: str = "synthesis"):
        """
        Async generator for streaming text tokens.
        """
        if self.use_openai:
            model = CYPHER_MODEL if model_type == "cypher" else SYNTHESIS_MODEL
            try:
                # Use the synchronous client but in a thread pool or just iteration
                # OpenAI client's stream is a generator
                stream = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1 if model_type == "cypher" else 0.7,
                    stream=True
                )
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as e:
                logger.error(f"OpenAI Stream Error: {str(e)}. Falling back to Ollama.")

        # Ollama Streaming Fallback
        try:
            stream = ollama.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': prompt}], stream=True)
            for chunk in stream:
                yield chunk['message']['content']
        except Exception as e:
            logger.error(f"Ollama Stream Error: {str(e)}")
            yield f"Error in synthesis: {str(e)}"

    def chat_sync(self, prompt: str, model_type: str = "cypher"):
        """
        Sync chat for non-streaming parts (like Cypher generation or setup).
        """
        if self.use_openai:
            model = CYPHER_MODEL if model_type == "cypher" else SYNTHESIS_MODEL
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1 if model_type == "cypher" else 0.7
                )
                return response.choices[0].message.content
            except Exception:
                pass
        
        # Ollama Fallback (Fast)
        try:
            response = ollama.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': prompt}])
            return response['message']['content']
        except Exception as e:
            logger.error(f"Ollama Sync Error: {str(e)}")
            return "MATCH (n) RETURN n LIMIT 1" # Safe fallback

llm = UnifiedLLM()

class QueryRequest(BaseModel):
    question: str
    session_id: str = None
    use_search: bool = False

# Memory and Search Configuration
CHAT_HISTORY = {}  # {session_id: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
SEARCH_LIMIT = 5

def perform_web_search(query: str) -> str:
    """
    Live web search for NYC legal news and updates using DuckDuckGo.
    """
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=3)
            if not results:
                return ""
            
            context = "Recent Web Context:\n"
            for r in results:
                context += f"- {r['title']} ({r['href']}): {r['body'][:200]}...\n"
            return context
    except Exception as e:
        logger.error(f"DuckDuckGo Search Error: {str(e)}")
        return ""

def generate_question_embedding(text: str) -> list[float]:
    """
    Generate embedding for the user's question, preferring OpenAI with Ollama fallback.
    """
    if OPENAI_API_KEY and "sk-" in OPENAI_API_KEY:
        try:
            openai_client = OpenAI(api_key=OPENAI_API_KEY, max_retries=0)
            response = openai_client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            if "insufficient_quota" in str(e).lower() or "429" in str(e):
                logger.warning("OpenAI Embedding Quota Exceeded. Falling back to local Ollama.")
            else:
                logger.error(f"OpenAI Embedding Error: {str(e)}")

    # Ollama Embedding Fallback
    try:
        response = ollama.embeddings(model=OLLAMA_MODEL, prompt=text)
        return response['embedding']
    except Exception as e:
        logger.error(f"Ollama Embedding Error: {str(e)}")
        return []

class LegalGraphClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def query(self, cypher: str, params: dict = None):
        # Security Guard: Block destructive commands
        forbidden = ["DELETE", "DETACH", "REMOVE", "DROP", "CREATE", "MERGE", "SET"]
        if any(word in cypher.upper() for word in forbidden):
            logger.warning(f"BLOCKED destructive/writing Cypher query: {cypher}")
            return []

        with self.driver.session() as session:
            logger.info(f"Executing Cypher: {cypher}")
            try:
                result = session.run(cypher, params or {})
                return [record.data() for record in result]
            except Exception as e:
                logger.error(f"Cypher Execution Error: {str(e)}")
                return []

db = LegalGraphClient()

import time

# Cache Configuration
CACHE_FILE = "./database/query_cache.json"
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        query_cache = json.load(f)
else:
    # Ensure database dir exists
    os.makedirs("./database", exist_ok=True)
    query_cache = {}

def update_chat_history(session_id: str, user_q: str, bot_a: str):
    if not session_id: return
    if session_id not in CHAT_HISTORY:
        CHAT_HISTORY[session_id] = []
    CHAT_HISTORY[session_id].append({"role": "user", "content": user_q})
    CHAT_HISTORY[session_id].append({"role": "assistant", "content": bot_a})
    # Limit history to last 5 exchanges (10 messages)
    if len(CHAT_HISTORY[session_id]) > 10:
        CHAT_HISTORY[session_id] = CHAT_HISTORY[session_id][-10:]
    logger.info(f"Chat history updated for session: {session_id}")

def update_cache_and_history(question: str, data: dict, session_id: str):
    # Update Cache
    query_cache[question] = data
    with open(CACHE_FILE, "w") as f:
        json.dump(query_cache, f)
    # Update History
    update_chat_history(session_id, question, data["response"])

@app.get("/api/random_penalty")
async def get_random_penalty():
    """
    Fetch a random rule violation or exception from Neo4j.
    """
    cypher = """
    MATCH (n) 
    WHERE (n:PROVISION OR n:EXCEPTION) AND n.id IS NOT NULL 
    WITH n, rand() as r 
    ORDER BY r 
    LIMIT 1 
    RETURN n.id as citation, labels(n)[0] as title, 
           coalesce(n.description, "Violation of " + n.id) as desc, 
           toInteger(rand() * 10000 + 500) as fine
    """
    results = db.query(cypher)
    if results:
        return results[0]
    return {
        "title": "Code Violation",
        "fine": 500,
        "desc": "General administrative violation of NYC Building Code.",
        "citation": "28-101.1"
    }

@app.post("/query")
async def handle_query(request: QueryRequest, background_tasks: BackgroundTasks):
    start_time = time.time()
    question = request.question.strip().lower()
    session_id = request.session_id
    logger.info(f"Received question: {question} (Session: {session_id})")
    
    # 1. Check Cache
    if not session_id:
        cached_response = query_cache.get(question)
        if cached_response:
            logger.info(f"Cache hit (SSE) for: {question}")
            async def cached_stream():
                yield f"data: {cached_response['response']}\n\n"
                metadata = {"citations": cached_response["citations"], "debug": {**cached_response["debug"], "cache": "hit"}}
                yield f"data: {json.dumps(metadata)}\n\n"
            return StreamingResponse(cached_stream(), media_type="text/event-stream")

    # 2. Hybrid Step 1: Generate Vector Embedding
    try:
        question_embedding = generate_question_embedding(question)
        vector_results = []
        if question_embedding:
            vector_cypher = """
            CALL db.index.vector.queryNodes('legal_vector_index', 3, $question_embedding) 
            YIELD node, score 
            RETURN node.id as id, labels(node)[0] as type, node.description as desc, score
            """
            vector_results = db.query(vector_cypher, params={"question_embedding": question_embedding})
            logger.info(f"Vector search found {len(vector_results)} nodes.")

        # 3. Hybrid Step 2: Cypher Graph Search
        graph_results = []
        try:
            cypher_start = time.time()
            cypher_prompt = FEW_SHOT_CYPHER_PROMPT.format(question=question)
            raw_cypher = llm.chat_sync(cypher_prompt, model_type="cypher")
            
            cypher_match = re.search(r'MATCH.*?(?=;|$)', raw_cypher, re.DOTALL | re.IGNORECASE)
            cypher = cypher_match.group(0).strip() if cypher_match else raw_cypher.strip()
            cypher = re.sub(r'```(cypher)?', '', cypher).strip()
            
            graph_results = db.query(cypher)
            if not graph_results:
                 fallback_cypher = f"MATCH (n) WHERE n.id CONTAINS '{question[-5:]}' OR n.id CONTAINS '28-' RETURN n LIMIT 5"
                 graph_results = db.query(fallback_cypher)
            logger.info(f"Graph search found {len(graph_results)} nodes.")
        except Exception as e:
            logger.error(f"Cypher generation failed: {str(e)}")

        # 4. Combine Results
        combined_results = vector_results + graph_results
        
        # 5. Optional Web Search
        web_context = ""
        if request.use_search:
            web_context = perform_web_search(question)
            logger.info("Live web search context injected.")
        
        # 6. History Retrieval
        history_text = ""
        if session_id and session_id in CHAT_HISTORY:
            history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in CHAT_HISTORY[session_id]])
            logger.info(f"Memory injected ({len(CHAT_HISTORY[session_id])} messages).")

        # 7. SSE Streaming Generator
        async def sse_generator():
            accumulated_text = ""
            synth_start = time.time()
            
            summary_prompt = f"""
            SYSTEM: You are a helpful NYC legal assistant.
            HISTORY:
            {history_text}
            
            CONTEXT (Legal Graph - Hybrid): {json.dumps(combined_results[:6])}
            CONTEXT (Web Grounding): {web_context}
            
            USER QUESTION: {question}
            
            Summarize the NYC legal context and web info to answer accurately. 
            Cite citation IDs (e.g., 28-320) where available.
            """
            
            async for token in llm.stream_chat(summary_prompt, model_type="synthesis"):
                accumulated_text += token
                yield f"data: {token}\n\n"
                await asyncio.sleep(0.01)
            
            total_time = time.time() - start_time
            debug_info = {
                "latency": f"{total_time:.2f}s",
                "source": "hybrid (vector+graph)",
                "search": "active" if request.use_search else "none"
            }
            
            metadata = {"citations": combined_results[:10], "debug": debug_info}
            yield f"data: {json.dumps(metadata)}\n\n"
            
            background_tasks.add_task(update_cache_and_history, question, {
                "response": accumulated_text,
                "citations": combined_results[:10],
                "debug": debug_info
            }, session_id)

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Execution Error: {str(e)}")
        async def error_stream():
            yield f"data: Error processing your request: {str(e)}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
