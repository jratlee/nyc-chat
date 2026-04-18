from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

# Model Configuration
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

class LegalGraphExtractor:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.processed_files = 0
        
    def close(self):
        self.driver.close()

    def run_cypher(self, query, parameters=None):
        with self.driver.session() as session:
            session.run(query, parameters)

    def extract_hierarchy(self, file_path, source_type):
        """
        source_type: 'CHARTER', 'ADMIN_CODE', 'RULES'
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Identify current section identifier from first HEADING or content
            headings = [h.text for h in root.findall(".//HEADING") if h.text]
            section_id = "UNKNOWN"
            if headings:
                # Look for patterns like § 1-101 or 11 RCNY 1-01
                match = re.search(r'§\s*([\d\-\.\w]+)', " ".join(headings))
                if match:
                    section_id = match.group(1).strip()
            
            # Create Section Node
            section_label = f"{source_type}_SECTION"
            # Node creation with merge to prevent duplicates
            self.run_cypher(f"MERGE (s:{section_label} {{ id: $id }}) SET s.source_file = $file", 
                             {"id": section_id, "file": os.path.basename(file_path)})

            # Extract Links (Edges)
            for link in root.findall(".//LINK"):
                dest = link.get("destination-name")
                if dest:
                    # Link to target section (we might not have seen it yet, so just MERGE)
                    # We often need to infer if it's Code or Rules based on context, but let's keep it generic for now
                    self.run_cypher(f"""
                        MATCH (s:{section_label} {{ id: $id }})
                        MERGE (t:PROVISION {{ id: $dest }})
                        MERGE (s)-[:CITES]->(t)
                    """, {"id": section_id, "dest": dest})

            # LLM Extraction for Exceptions
            # To avoid overwhelming the local model, we only process the text of the first few PARA tags for this prototype
            paragraphs = ["".join(p.itertext()) for p in root.findall(".//PARA")][:3]
            content_text = " ".join(paragraphs)
            
            if len(content_text) > 50 and "except" in content_text.lower():
                self.extract_exceptions_with_llm(section_id, section_label, content_text)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    def extract_exceptions_with_llm(self, section_id, section_label, text):
        prompt = f"""
        Analyze this New York City legal text from {section_id}:
        "{text}"
        
        Is there an exception to a rule mentioned here? 
        If yes, identify the target rule and the exception.
        Respond ONLY with a JSON list of objects: [{{"rule": "target rule", "exception": "brief desc"}}].
        If no exceptions, respond with [].
        """
        try:
            response = ollama.chat(model=OLLAMA_MODEL, messages=[
              {'role': 'user', 'content': prompt},
            ])
            # Basic JSON extraction (Llama 3 is usually good at this)
            found = re.search(r'\[.*\]', response['message']['content'], re.DOTALL)
            if found:
                exceptions = eval(found.group(0)) # Use json.loads in production
                for ex in exceptions:
                   self.run_cypher(f"""
                        MATCH (s:{section_label} {{ id: $id }})
                        MERGE (e:EXCEPTION {{ description: $desc }})
                        MERGE (s)-[:EXCEPTS]->(e)
                        WITH e
                        WHERE $rule <> ''
                        MERGE (r:PROVISION {{ id: $rule }})
                        MERGE (e)-[:TARGETS]->(r)
                    """, {"id": section_id, "desc": ex.get('exception', ''), "rule": ex.get('rule', '')})
        except Exception as e:
             print(f"LLM Error for {section_id}: {e}")

    def process_all(self):
        # Enforce Hierarchy Setup
        self.run_cypher("CREATE CONSTRAINT IF NOT EXISTS FOR (c:CHARTER_SECTION) REQUIRE c.id IS UNIQUE")
        self.run_cypher("CREATE CONSTRAINT IF NOT EXISTS FOR (a:ADMIN_CODE_SECTION) REQUIRE a.id IS UNIQUE")
        
        # Process NYC1 (Charter)
        print("Processing Charter...")
        for f in os.listdir("/home/lab/NYC1/XML")[:20]: # Sample 20 for speed in demo
            if f.endswith('.xml'):
                self.extract_hierarchy(os.path.join("/home/lab/NYC1/XML", f), "CHARTER")
        
        # Process NYC2 (Admin Code)
        print("Processing Admin Code...")
        for f in os.listdir("/home/lab/NYC2/XML")[:20]:
            if f.endswith('.xml'):
                self.extract_hierarchy(os.path.join("/home/lab/NYC2/XML", f), "ADMIN_CODE")
                
        # Process NYC3 (Rules)
        print("Processing Rules...")
        for f in os.listdir("/home/lab/NYC3/XML")[:20]:
            if f.endswith('.xml'):
               self.extract_hierarchy(os.path.join("/home/lab/NYC3/XML", f), "RULES")

        # Explicitly link Hierarchy: Charter -> Admin Code -> Rules
        # (This usually requires domain knowledge or explicit mapping, but for now we tag them)
        print("Finalizing Hierarchical Links...")
        self.run_cypher("""
            MATCH (c:CHARTER_SECTION), (a:ADMIN_CODE_SECTION)
            WHERE a.id CONTAINS c.id OR c.id CONTAINS a.id
            MERGE (c)-[:IMPLEMENTS]->(a)
        """)

if __name__ == "__main__":
    extractor = LegalGraphExtractor()
    extractor.process_all()
    extractor.close()
    print("Graph Extraction Complete.")
