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
