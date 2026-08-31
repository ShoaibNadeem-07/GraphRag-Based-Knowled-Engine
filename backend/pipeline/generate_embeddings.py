import os
import json
import faiss
import numpy as np
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

def get_neo4j_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "graphrag2026")
    return GraphDatabase.driver(uri, auth=(user, password))

def generate_embeddings():
    print("Initializing embedding model (all-MiniLM-L6-v2)...")
    # Using L2 normalization for cosine similarity compatibility with FlatIP
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    driver = get_neo4j_driver()
    
    # 1. Fetch all clauses
    print("Fetching clauses from Neo4j...")
    clauses = []
    with driver.session() as session:
        res = session.run("MATCH (cl:Clause) RETURN cl.id AS id, cl.text AS text")
        for r in res:
            clauses.append((r["id"], r["text"]))
            
    print(f"Loaded {len(clauses)} clauses.")
    
    # 2. Extract texts and IDs
    ids = [c[0] for c in clauses]
    texts = [c[1] for c in clauses]
    
    # 3. Generate embeddings
    print("Generating embeddings... (this may take a few minutes)")
    # Normalize embeddings to ensure Inner Product == Cosine Similarity
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True)
    
    # 4. Create FAISS IndexFlatIP
    print("Building FAISS index...")
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(np.array(embeddings, dtype=np.float32))
    
    # 5. Save everything
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    out_dir = os.path.join(root_dir, "data", "processed")
    os.makedirs(out_dir, exist_ok=True)
    
    index_path = os.path.join(out_dir, "faiss.index")
    mapping_path = os.path.join(out_dir, "faiss_mapping.json")
    
    faiss.write_index(index, index_path)
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(ids, f)
        
    print(f"Saved FAISS index to {index_path} ({index.ntotal} vectors).")
    print(f"Saved ID mapping to {mapping_path}.")
    
    driver.close()

def incremental_add_to_index(clauses: list[dict]):
    """
    Incrementally add new clauses to the FAISS index and ID mapping.
    clauses: [{"id": str, "text": str}]
    """
    if not clauses:
        return
        
    print(f"Incrementally adding {len(clauses)} clauses to FAISS index...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    out_dir = os.path.join(root_dir, "data", "processed")
    index_path = os.path.join(out_dir, "faiss.index")
    mapping_path = os.path.join(out_dir, "faiss_mapping.json")
    
    # Load existing
    index = faiss.read_index(index_path)
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)
        
    texts = [c["text"] for c in clauses]
    ids = [c["id"] for c in clauses]
    
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
    index.add(np.array(embeddings, dtype=np.float32))
    mapping.extend(ids)
    
    # Save back
    faiss.write_index(index, index_path)
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f)
        
    print(f"Updated FAISS index to {index.ntotal} vectors.")

if __name__ == "__main__":
    generate_embeddings()
