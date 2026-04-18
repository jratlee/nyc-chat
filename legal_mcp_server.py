from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

# Model Configuration
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Initialize FastMCP
mcp = FastMCP("NYC Legal Graph Server")

class LegalGraphClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def query_graph(self, cypher_query: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            result = session.run(cypher_query, parameters)
            return [record.data() for record in result]

client = LegalGraphClient()

@mcp.tool()
def query_legal_graph(question: str) -> str:
    """
    Translates a natural language legal question into a Cypher query, 
    traverses the NYC legal knowledge graph, and returns structured context.
    """
    # 1. Translate to Cypher using Local Llama 3
    prompt = f"""
    You are a Legal Graph Engineer. Translate the following user question into a Neo4j Cypher query.
    The graph has nodes: CHARTER_SECTION, ADMIN_CODE_SECTION, RULES_SECTION, EXCEPTION, PROVISION.
    Relationships: CITES, IMPLEMENTS, EXCEPTS, TARGETS.
    
    Question: "{question}"
    
    Return ONLY the Cypher query. No explanations.
    """
    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': prompt}])
        cypher = response['message']['content'].strip()
        # Clean up code blocks if LLM adds them
        cypher = re.sub(r'```(cypher)?', '', cypher).strip()
        
        # 2. Execute Cypher
        data = client.query_graph(cypher)
        
        # 3. Format result
        if not data:
            return "No matching legal references found in the current graph snapshot."
            
        return json.dumps(data, indent=2)
    except Exception as e:
        return f"Error querying legal graph: {str(e)}"

if __name__ == "__main__":
    # Start the MCP server using stdio
    mcp.run()
