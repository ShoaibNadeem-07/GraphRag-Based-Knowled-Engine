import json
import os
import argparse
from neo4j import GraphDatabase

def _get_neo4j_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "graphrag2026")
    return GraphDatabase.driver(uri, auth=(user, password))

def init_constraints(session):
    """Create uniqueness constraints (idempotent)."""
    constraints = [
        "CREATE CONSTRAINT contract_id IF NOT EXISTS FOR (c:Contract) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT clause_id IF NOT EXISTS FOR (cl:Clause) REQUIRE cl.id IS UNIQUE",
        "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE"
    ]
    for q in constraints:
        session.run(q)

def load_graph(driver, jsonl_path: str, manifest_path: str, test_contract: str = None):
    # 1. Load split manifest
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # 2. Prepare data batches
    contracts_map = {}  # id -> {id, split}
    clauses = []
    
    with open(jsonl_path, encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if not line.strip(): continue
            rec = json.loads(line)
            
            # Filter impossible clauses
            if rec.get("is_impossible"):
                continue
                
            cid = rec["contract_id"]
            text = rec.get("clause_text") or ""
            
            # Skip stubs: empty text or annotation artifacts shorter than a meaningful clause
            if len(text.strip()) < 30:
                continue
            
            if test_contract and cid != test_contract:
                continue
                
            contracts_map[cid] = {
                "id": cid,
                "split": manifest.get(cid, "unknown")
            }
            
            # Build clean clause record
            clause_id = f"{cid}_{idx}"
            clause_record = {
                "id": clause_id,
                "contract_id": cid,
                "clause_type": rec["clause_type"],
                "text": rec["clause_text"],
                "risk_level": rec.get("risk_level", "Unknown"),
                "entities": []
            }
            
            # Build unique entities
            for ent in rec.get("entities", []):
                ent_name = ent["text"].strip()
                ent_label = ent["label"]
                ent_id = f"{ent_name}_{ent_label}"
                clause_record["entities"].append({
                    "id": ent_id,
                    "name": ent_name,
                    "label": ent_label
                })
                
            clauses.append(clause_record)

    # 3. Write via UNWIND in batches
    BATCH_SIZE = 500
    
    with driver.session() as session:
        init_constraints(session)
        
        # Load Contracts
        contract_list = list(contracts_map.values())
        print(f"Loading {len(contract_list)} Contracts...")
        for i in range(0, len(contract_list), BATCH_SIZE):
            batch = contract_list[i:i+BATCH_SIZE]
            session.run("""
                UNWIND $batch AS c
                MERGE (node:Contract {id: c.id})
                SET node.split = c.split
            """, batch=batch)

        # Load Clauses and Entities
        print(f"Loading {len(clauses)} Clauses + Entities...")
        for i in range(0, len(clauses), BATCH_SIZE):
            batch = clauses[i:i+BATCH_SIZE]
            session.run("""
                UNWIND $batch AS cl
                
                // 1. Merge Clause
                MERGE (clause:Clause {id: cl.id})
                SET clause.clause_type = cl.clause_type,
                    clause.text = cl.text,
                    clause.risk_level = cl.risk_level
                
                // 2. Link to Contract
                WITH cl, clause
                MATCH (contract:Contract {id: cl.contract_id})
                MERGE (contract)-[:HAS_CLAUSE]->(clause)
                
                // 3. Merge Entities and Link
                WITH cl, clause
                UNWIND cl.entities AS ent
                MERGE (e:Entity {id: ent.id})
                ON CREATE SET e.name = ent.name, e.label = ent.label
                MERGE (clause)-[:MENTIONS]->(e)
            """, batch=batch)

def load_single_contract_to_graph(driver, contract_id: str, clauses: list):
    """
    Load a single newly uploaded contract and its clauses into the Neo4j graph.
    clauses is a list of dicts: {"id": str, "clause_type": str, "text": str, "risk_level": str, "entities": [{"id", "name", "label"}]}
    """
    with driver.session() as session:
        init_constraints(session)
        
        # 1. Merge Contract Node
        session.run("""
            MERGE (c:Contract {id: $cid})
            ON CREATE SET c.split = "uploaded"
        """, cid=contract_id)
        
        # 2. Merge Clauses and Entities
        # We can reuse the same UNWIND logic
        BATCH_SIZE = 500
        for i in range(0, len(clauses), BATCH_SIZE):
            batch = clauses[i:i+BATCH_SIZE]
            
            # Inject contract_id into each clause for the query
            for cl in batch:
                cl["contract_id"] = contract_id
                
            session.run("""
                UNWIND $batch AS cl
                
                // 1. Merge Clause
                MERGE (clause:Clause {id: cl.id})
                SET clause.clause_type = cl.clause_type,
                    clause.text = cl.text,
                    clause.risk_level = cl.risk_level
                
                // 2. Link to Contract
                WITH cl, clause
                MATCH (contract:Contract {id: cl.contract_id})
                MERGE (contract)-[:HAS_CLAUSE]->(clause)
                
                // 3. Merge Entities and Link
                WITH cl, clause
                UNWIND cl.entities AS ent
                MERGE (e:Entity {id: ent.id})
                ON CREATE SET e.name = ent.name, e.label = ent.label
                MERGE (clause)-[:MENTIONS]->(e)
            """, batch=batch)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-contract", type=str, help="Only load this contract ID")
    args = parser.parse_args()
    
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    jsonl_path = os.path.join(root, "data", "processed", "cuad_full.jsonl")
    manifest_path = os.path.join(root, "data", "processed", "split_manifest.json")
    
    driver = _get_neo4j_driver()
    try:
        load_graph(driver, jsonl_path, manifest_path, args.test_contract)
        print("Done.")
    finally:
        driver.close()
