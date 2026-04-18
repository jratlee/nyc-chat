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
\n\n--- FRONTEND: Chat.jsx ---\n\n
import React, { useState, useRef, useEffect } from 'react'

const MOCK_BOT_RESPONSES = [
    {
        keywords: ['bee', 'queens', 'honey'],
        response: "According to the NYC Health Code (part of Rules Title 24), you can keep honey bees (Apis mellifera) in New York City, including Queens. However, you must register your hives with the Department of Health and Mental Hygiene (DOHMH) and follow specific hive maintenance rules to prevent public nuisance. (Ref: NYC Rules Title 24, §161.25)"
    },
    {
        keywords: ['dog', 'curb', 'poop', 'fine'],
        response: "NYC Administrative Code §16-121 requires dog owners to remove any feces left by their dog on any public or private property. Failure to do so (the 'Pooper Scooper Law') can result in a fine of $250. This is enforced by both the Department of Sanitation and NYC Parks. (Ref: Admin Code §16-121)"
    },
    {
        keywords: ['sidewalk', 'shed', 'scaffold'],
        response: "Sidewalk sheds are required per Building Code §3307 when a building is undergoing facade work (FISP) or is deemed unsafe. They must be inspected daily by a competent person. As of 2024, the City is transitioning to 'Get Sheds Down' initiatives to replace scaffolding with safety netting where appropriate. (Ref: Admin Code §28-302.2)"
    }
]

function Chat({ sources, search }) {
    const [messages, setMessages] = useState([
        { type: 'bot', text: 'Talk to NYC. What can I help you find today?' }
    ])
    const [input, setInput] = useState('')
    const [isTyping, setIsTyping] = useState(false)
    const messagesEndRef = useRef(null)
    const [sessionId] = useState(crypto.randomUUID())

    const [typingMessage, setTypingMessage] = useState('Analyzing NYC Codes...')

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }

    useEffect(() => {
        scrollToBottom()
    }, [messages])

    useEffect(() => {
        let interval
        if (isTyping) {
            const messages = [
                'Consulting Neo4j legal graph...',
                'Traversing Charter hierarchy...',
                'Mapping Administrative Code exceptions...',
                'Synthesizing LLM-grounded response...'
            ]
            let counter = 0
            interval = setInterval(() => {
                setTypingMessage(messages[counter % messages.length])
                counter++
            }, 3000)
        }
        return () => clearInterval(interval)
    }, [isTyping])

    const handleSend = async () => {
        if (!input.trim()) return

        const userMsg = { type: 'user', text: input }
        setMessages(prev => [...prev, userMsg])
        setInput('')
        setIsTyping(true)

        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 180000)

        try {
            const response = await fetch('http://localhost:8005/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: input,
                    session_id: sessionId,
                    use_search: search
                }),
                signal: controller.signal
            })

            clearTimeout(timeoutId)
            if (!response.ok) throw new Error('Network response was not ok')

            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            let accumulatedText = ''
            let botMessageCreated = false

            let buffer = ''
            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n\n')
                buffer = lines.pop() // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.trim().startsWith('data: ')) {
                        const data = line.trim().slice(6)
                        if (!data) continue

                        // Check if it's JSON (metadata) or a text token
                        if (data.startsWith('{') && data.endsWith('}')) {
                            try {
                                const metadata = JSON.parse(data)
                                if (metadata.citations) {
                                    let citationText = `\n\nVerified Citations: ${metadata.citations.map(c => c.n?.id || c.m?.id).filter(id => id).slice(0, 3).join(', ')}`
                                    setMessages(prev => {
                                        const last = prev[prev.length - 1]
                                        if (last && last.type === 'bot') {
                                            return [...prev.slice(0, -1), { ...last, text: last.text + citationText, debug: metadata.debug }]
                                        }
                                        return prev
                                    })
                                }
                            } catch (e) {
                                accumulatedText += data
                            }
                        } else {
                            accumulatedText += data
                            setMessages(prev => {
                                if (!botMessageCreated) {
                                    botMessageCreated = true
                                    setIsTyping(false)
                                    return [...prev, { type: 'bot', text: accumulatedText }]
                                }
                                const last = prev[prev.length - 1]
                                return [...prev.slice(0, -1), { ...last, text: accumulatedText }]
                            })
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error:', error)
            const errorMsg = error.name === 'AbortError'
                ? "The NYC Legal Graph is deep, and our local LLM is working hard on this complex query."
                : "Error: Could not reach the NYC Regulatory Intelligence Server."
            setMessages(prev => [...prev, { type: 'bot', text: errorMsg }])
        } finally {
            setIsTyping(false)
        }
    }

    return (
        <div className="chat-container">
            <div className="chat-messages">
                {messages.map((m, i) => (
                    <div key={i} className={`message ${m.type}`}>
                        <div style={{ fontSize: '0.65rem', fontWeight: 800, marginBottom: '0.5rem', opacity: 0.5 }}>
                            {m.type === 'user' ? 'YOU' : 'CITY OF NEW YORK'}
                        </div>
                        <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
                    </div>
                ))}
                {isTyping && <div className="message bot" style={{ opacity: 0.5, fontWeight: 700 }}>{typingMessage}</div>}
                <div ref={messagesEndRef} />
            </div>
            <div className="chat-input-area">
                <input
                    type="text"
                    placeholder="Ask a question about the Charter, Code, or Rules..."
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSend()}
                />
                <button className="btn btn-green" onClick={handleSend}>Query</button>
            </div>
        </div>
    )
}

export default Chat
\n\n--- FRONTEND: Poker.jsx ---\n\n
import React, { useState } from 'react'

const ASSETS = ["Elevator", "Low-Pressure Boiler", "Facade (Pre-War)", "Commercial Kitchen", "Street Tree"]

function Poker() {
    const [budget, setBudget] = useState(50000)
    const [dealtCards, setDealtCards] = useState([])
    const [selectedAssets, setSelectedAssets] = useState([])
    const [gameOver, setGameOver] = useState(false)

    const startGame = () => {
        setBudget(50000)
        setDealtCards([])
        setSelectedAssets([])
        setGameOver(false)
    }

    const addAsset = async (asset) => {
        if (selectedAssets.includes(asset)) return
        setSelectedAssets(prev => [...prev, asset])

        try {
            const response = await fetch('http://localhost:8005/api/random_penalty')
            const penalty = await response.json()

            setDealtCards(prev => [...prev, { ...penalty, id: Date.now() }])
            setBudget(prev => {
                const newBudget = prev - penalty.fine
                if (newBudget <= 0) setGameOver(true)
                return newBudget
            })
        } catch (error) {
            console.error("Error fetching random penalty:", error)
        }
    }

    return (
        <div style={{ border: '2px solid black', padding: '2rem', background: 'white' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '2rem' }}>
                <div>
                    <h2 style={{ color: 'var(--color-burgundy)' }}>PENALTY POKER</h2>
                    <p style={{ fontWeight: 600 }}>SURVIVE THE REGULATORY BLUFF. YOUR BUDGET IS YOUR LIFE.</p>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '2rem', fontWeight: 800, color: budget > 10000 ? 'var(--color-green)' : 'var(--color-red)' }}>
                        ${budget.toLocaleString()}
                    </div>
                    <div style={{ fontSize: '0.75rem', fontWeight: 800 }}>REMAINING OPERATING BUDGET</div>
                </div>
            </div>

            {!gameOver ? (
                <>
                    <div style={{ marginBottom: '2rem' }}>
                        <h3 style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>ADD ASSETS TO YOUR PORTFOLIO:</h3>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                            {ASSETS.map(a => (
                                <button
                                    key={a}
                                    className="btn btn-outline"
                                    onClick={() => addAsset(a)}
                                    disabled={selectedAssets.includes(a)}
                                >
                                    + {a}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <h3 style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>ACTIVE VIOLATIONS (YOUR HAND):</h3>
                        <div className="poker-deck">
                            {dealtCards.map(c => (
                                <div key={c.id} className="card penalty">
                                    <div>
                                        <div style={{ fontSize: '0.75rem', fontWeight: 800 }}>VIOLATION</div>
                                        <h2 style={{ fontSize: '1.25rem', margin: '0.5rem 0' }}>{c.title}</h2>
                                        <p style={{ fontSize: '0.75rem', color: 'black' }}>{c.desc}</p>
                                    </div>
                                    <div style={{ borderTop: '1px solid currentColor', paddingTop: '1rem' }}>
                                        <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>-${c.fine}</div>
                                        <div style={{ fontSize: '0.6rem', color: 'black' }}>REF: {c.citation}</div>
                                    </div>
                                </div>
                            ))}
                            {selectedAssets.length === 0 && (
                                <div style={{ opacity: 0.3, border: '2px dashed black', padding: '4rem', width: '100%', textAlign: 'center' }}>
                                    SELECT AN ASSET TO BEGIN INSPECTION
                                </div>
                            )}
                        </div>
                    </div>
                </>
            ) : (
                <div style={{ textAlign: 'center', padding: '4rem 0' }}>
                    <h1 style={{ color: 'var(--color-red)' }}>INSOLVENT</h1>
                    <p style={{ fontWeight: 600, marginBottom: '2rem' }}>YOU HAVE BEEN BURIED IN RED TAPE. TOTAL PENALTIES EXCEEDED BUDGET.</p>
                    <button className="btn btn-green" onClick={startGame}>RE-INCORPORATE</button>
                </div>
            )}
        </div>
    )
}

export default Poker
\n\n--- ETL: embed_graph.py ---\n\n
import os
import json
import logging
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Providers & DB
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

client = OpenAI(api_key=OPENAI_API_KEY)

class GraphEmbedder:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def get_nodes_to_embed(self):
        """
        Retrieve nodes that need embeddings. 
        Focusing on PROVISION and SECTION nodes.
        """
        query = """
        MATCH (n)
        WHERE (n:PROVISION OR n:CHARTER_SECTION OR n:ADMIN_CODE_SECTION OR n:RULES_SECTION)
          AND n.embedding IS NULL
        RETURN id(n) as node_id, n.id as citation, labels(n)[0] as type, n.description as desc
        LIMIT 100
        """
        with self.driver.session() as session:
            result = session.run(query)
            return [record.data() for record in result]

    def generate_embedding(self, text: str):
        try:
            response = client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI Embedding Error: {str(e)}")
            return None

    def store_embedding(self, node_id, embedding):
        query = """
        MATCH (n) WHERE id(n) = $node_id
        SET n.embedding = $embedding
        """
        with self.driver.session() as session:
            session.run(query, node_id=node_id, embedding=embedding)

    def create_vector_index(self):
        """
        Create the vector index in Neo4j if it doesn't exist.
        """
        # Note: Syntax varies by Neo4j version (this is for 5.x+)
        query = """
        CREATE VECTOR INDEX legal_vector_index IF NOT EXISTS
        FOR (n:PROVISION) ON (n.embedding)
        OPTIONS {indexConfig: {
          `vector.dimensions`: 1536,
          `vector.similarity_function`: 'cosine'
        }}
        """
        with self.driver.session() as session:
            try:
                session.run(query)
                logger.info("Vector index created/verified on PROVISION nodes.")
            except Exception as e:
                logger.error(f"Error creating index: {str(e)}")

    def run(self):
        self.create_vector_index()
        nodes = self.get_nodes_to_embed()
        if not nodes:
            logger.info("No nodes found that require embeddings.")
            return

        logger.info(f"Processing {len(nodes)} nodes for embeddings...")
        for node in nodes:
            # Combine citation and description for a rich embedding
            text_to_embed = f"{node['type']} {node['citation']}: {node['desc'] or ''}"
            embedding = self.generate_embedding(text_to_embed)
            if embedding:
                self.store_embedding(node['node_id'], embedding)
                logger.info(f"Stored embedding for {node['citation']}")

if __name__ == "__main__":
    embedder = GraphEmbedder()
    try:
        embedder.run()
    finally:
        embedder.close()
