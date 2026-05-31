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

# Embedding dimension used to build the vector index. Must match the model:
# OpenAI text-embedding-3-small = 1536. Keep in sync with legal_api_server.py.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

# Lazily create the OpenAI client so importing this module does not require an
# API key (the client constructor raises immediately when the key is missing).
_client = None


def get_openai_client():
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Set it in your environment or .env "
                "file before running embeddings."
            )
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


class GraphEmbedder:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def get_nodes_to_embed(self, batch_size: int = 100):
        """
        Retrieve a batch of nodes that need embeddings.
        Focusing on PROVISION and SECTION nodes.
        """
        query = """
        MATCH (n)
        WHERE (n:PROVISION OR n:CHARTER_SECTION OR n:ADMIN_CODE_SECTION OR n:RULES_SECTION)
          AND n.embedding IS NULL
        RETURN id(n) as node_id, n.id as citation, labels(n)[0] as type, n.description as desc
        LIMIT $batch_size
        """
        with self.driver.session() as session:
            result = session.run(query, batch_size=batch_size)
            return [record.data() for record in result]

    def generate_embedding(self, text: str):
        try:
            response = get_openai_client().embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI Embedding Error: {str(e)}")
            return None

    def store_embedding(self, node_id, embedding):
        # Tag every embedded node with a shared :Embeddable label so a single
        # vector index can cover PROVISION and all *_SECTION nodes.
        query = """
        MATCH (n) WHERE id(n) = $node_id
        SET n.embedding = $embedding
        SET n:Embeddable
        """
        with self.driver.session() as session:
            session.run(query, node_id=node_id, embedding=embedding)

    def create_vector_index(self):
        """
        Create the vector index in Neo4j if it doesn't exist.
        """
        # Note: Syntax varies by Neo4j version (this is for 5.x+).
        # Index on the shared :Embeddable label so section nodes are also searchable.
        query = """
        CREATE VECTOR INDEX legal_vector_index IF NOT EXISTS
        FOR (n:Embeddable) ON (n.embedding)
        OPTIONS {indexConfig: {
          `vector.dimensions`: $dim,
          `vector.similarity_function`: 'cosine'
        }}
        """.replace("$dim", str(EMBEDDING_DIM))
        with self.driver.session() as session:
            try:
                session.run(query)
                logger.info("Vector index created/verified on :Embeddable nodes.")
            except Exception as e:
                logger.error(f"Error creating index: {str(e)}")

    def run(self):
        self.create_vector_index()

        total = 0
        # Process in batches until no unembedded nodes remain.
        while True:
            nodes = self.get_nodes_to_embed(batch_size=100)
            if not nodes:
                break

            logger.info(f"Processing batch of {len(nodes)} nodes for embeddings...")
            for node in nodes:
                # Combine citation and description for a rich embedding
                text_to_embed = f"{node['type']} {node['citation']}: {node['desc'] or ''}"
                embedding = self.generate_embedding(text_to_embed)
                if embedding and len(embedding) != EMBEDDING_DIM:
                    logger.error(
                        f"Embedding dim {len(embedding)} != index dim {EMBEDDING_DIM} "
                        f"for {node['citation']}. Skipping to keep index consistent."
                    )
                    continue
                if embedding:
                    self.store_embedding(node['node_id'], embedding)
                    total += 1
                    logger.info(f"Stored embedding for {node['citation']}")

        if total == 0:
            logger.info("No nodes found that require embeddings.")
        else:
            logger.info(f"Done. Stored {total} embeddings.")

if __name__ == "__main__":
    embedder = GraphEmbedder()
    try:
        embedder.run()
    finally:
        embedder.close()
