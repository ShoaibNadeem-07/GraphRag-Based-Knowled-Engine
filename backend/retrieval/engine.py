import os
import json
import faiss
import numpy as np
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from neo4j import GraphDatabase

class GraphRAGRetrievalEngine:
    def __init__(self):
        # Risk Multipliers (softened to break ties rather than override relevance)
        self.risk_weights = {
            "High": 1.10,
            "Medium": 1.05,
            "Unknown": 1.00,
            "Low": 0.95
        }
        
        # Load Model
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Load FAISS
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        processed_dir = os.path.join(root_dir, "data", "processed")
        
        index_path = os.path.join(processed_dir, "faiss.index")
        mapping_path = os.path.join(processed_dir, "faiss_mapping.json")
        
        if not os.path.exists(index_path):
            raise FileNotFoundError(f"FAISS index missing at {index_path}. Run generate_embeddings.py first.")
            
        self.index = faiss.read_index(index_path)
        with open(mapping_path, "r", encoding="utf-8") as f:
            self.id_mapping = json.load(f)
            
        # Connect to Neo4j
        uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "graphrag2026")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
        # Cache contract IDs for fast inference
        self.contract_ids = []
        with self.driver.session() as session:
            res = session.run("MATCH (c:Contract) RETURN c.id AS id")
            for r in res:
                self.contract_ids.append(r["id"])

    def _infer_contract(self, query: str) -> str:
        """Fuzzy match query text to known contract IDs (e.g. 'bravatek' -> 'BravatekSolutionsInc...')."""
        import re
        # Find all words >= 5 characters
        words = re.findall(r'\b[a-z]{5,}\b', query.lower())
        
        # Ignore common generic query words
        ignore = {'agreement', 'contract', 'termination', 'conditions', 'what', 'where', 'when', 'clause', 'clauses', 'restrictions', 'payment', 'terms', 'confidential', 'information', 'summarize'}
        candidates = [w for w in words if w not in ignore]
        
        for w in candidates:
            for cid in self.contract_ids:
                if w in cid.lower():
                    return cid
        return None

    def _neo4j_contract_fallback(self, contract_id: str, query: str, k: int) -> List[Dict[str, Any]]:
        """Fallback: directly fetch clauses from Neo4j for a specific contract and rank
        by word overlap with the query. Used when FAISS scoped search yields zero results."""
        query_words = set(w.lower() for w in query.split() if len(w) > 3)
        results = []
        with self.driver.session() as session:
            res = session.run("""
                MATCH (c:Contract {id: $id})-[:HAS_CLAUSE]->(cl:Clause)
                OPTIONAL MATCH (cl)-[:MENTIONS]->(e:Entity)
                RETURN cl.id AS id, cl.text AS text, cl.clause_type AS type,
                       cl.risk_level AS risk, c.id AS contract_id, collect(e.name) AS entities
            """, id=contract_id)
            for r in res:
                text_lower = r["text"].lower()
                overlap = sum(1 for w in query_words if w in text_lower)
                results.append({
                    "id": r["id"],
                    "text": r["text"],
                    "clause_type": r["type"],
                    "risk_level": r["risk"],
                    "contract_id": r["contract_id"],
                    "entities": r["entities"],
                    "source": "[NEO4J FALLBACK]",
                    "raw_score": 0.4 + (overlap * 0.05),  # Modest synthetic score
                    "final_score": 0.4 + (overlap * 0.05),
                })
        results.sort(key=lambda x: x["raw_score"], reverse=True)
        # Filter out stub clauses before returning — stubs must not reach the LLM as context
        results = [r for r in results if len(r["text"].strip()) >= 40]
        return results[:k]

    def retrieve_context(self, query: str, k: int = 5, use_risk_boost: bool = True, contract_id: str = None) -> List[Dict[str, Any]]:
        # 1. Infer contract if not explicitly provided
        if not contract_id:
            contract_id = self._infer_contract(query)
            
        # 2. Embed query
        # Must normalize to match the index normalization (for FlatIP to act as Cosine)
        q_emb = self.model.encode([query], normalize_embeddings=True)
        
        # 3. Semantic Search (FAISS)
        # Fetch a large pool if we need to filter by contract
        semantic_k = 1000 if contract_id else k * 2
        D, I = self.index.search(np.array(q_emb, dtype=np.float32), semantic_k)
        
        semantic_results = {}
        for score, idx in zip(D[0], I[0]):
            clause_id = self.id_mapping[idx]
            
            # Filter by contract if scoped
            if contract_id and not clause_id.startswith(contract_id):
                continue
                
            semantic_results[clause_id] = float(score)
            if len(semantic_results) >= (k * 2): # Stop once we have enough for expansion
                break

        # 3b. If scoped search found nothing, fall back to Neo4j direct clause fetch
        if contract_id and len(semantic_results) == 0:
            return self._neo4j_contract_fallback(contract_id, query, k)
                
        # 4. Graph Expansion
        # Query Neo4j to get the semantic clauses AND their 1-hop expanded clauses
        clause_ids_list = list(semantic_results.keys())
        
        expanded_candidates = {}
        
        with self.driver.session() as session:
            # Query the semantic clauses directly to get their data
            base_res = session.run("""
                MATCH (c:Contract)-[:HAS_CLAUSE]->(cl:Clause)
                WHERE cl.id IN $ids
                OPTIONAL MATCH (cl)-[:MENTIONS]->(e:Entity)
                RETURN cl.id AS id, cl.text AS text, cl.clause_type AS type, cl.risk_level AS risk, c.id AS contract_id, collect(e.name) AS entities
            """, ids=clause_ids_list)
            
            for r in base_res:
                cid = r["id"]
                score = semantic_results[cid]
                expanded_candidates[cid] = {
                    "id": cid,
                    "text": r["text"],
                    "clause_type": r["type"],
                    "risk_level": r["risk"],
                    "contract_id": r["contract_id"],
                    "entities": r["entities"],
                    "source": "[SEMANTIC]",
                    "raw_score": score
                }
                
            # Now run 1-hop expansion through entities, capped by fan-out (max 20 clauses per entity)
            # and capped to limit overall graph explosion.
            expand_res = session.run("""
                MATCH (cl_base:Clause)-[:MENTIONS]->(e:Entity)<-[:MENTIONS]-(cl_exp:Clause)
                WHERE cl_base.id IN $ids AND NOT cl_exp.id IN $ids
                
                // Calculate fan-out: how many clauses does this entity connect to?
                WITH cl_base, e, cl_exp
                MATCH (e)<-[:MENTIONS]-(any_cl:Clause)
                WITH cl_base, e, cl_exp, count(any_cl) AS degree
                WHERE degree <= 20
                
                // Fetch the expanded clause details
                MATCH (c:Contract)-[:HAS_CLAUSE]->(cl_exp)
                
                // Return unique expanded clauses, mapped back to the base clause that triggered them
                RETURN cl_exp.id AS id, cl_exp.text AS text, cl_exp.clause_type AS type, 
                       cl_exp.risk_level AS risk, c.id AS contract_id, collect(e.name) AS connection_entities,
                       cl_base.id AS parent_id
            """, ids=clause_ids_list)
            
            for r in expand_res:
                cid = r["id"]
                parent_id = r["parent_id"]
                parent_score = semantic_results[parent_id]
                
                # Apply 0.85 decay for 1-hop distance
                decayed_score = parent_score * 0.85
                
                # Deduplication: keep the highest score if multiple paths reached this clause
                if cid in expanded_candidates:
                    if decayed_score > expanded_candidates[cid]["raw_score"]:
                        expanded_candidates[cid]["raw_score"] = decayed_score
                        expanded_candidates[cid]["source"] = f"[GRAPH EXPANSION via {', '.join(r['connection_entities'])}]"
                else:
                    expanded_candidates[cid] = {
                        "id": cid,
                        "text": r["text"],
                        "clause_type": r["type"],
                        "risk_level": r["risk"],
                        "contract_id": r["contract_id"],
                        "entities": r["connection_entities"],
                        "source": f"[GRAPH EXPANSION via {', '.join(r['connection_entities'])}]",
                        "raw_score": decayed_score
                    }
                    
        # 4. Risk-Aware Re-ranking
        results = list(expanded_candidates.values())
        
        for res in results:
            risk = res["risk_level"]
            multiplier = self.risk_weights.get(risk, 1.0)
            
            res["risk_multiplier"] = multiplier
            
            # Only apply boost if the clause is at least moderately relevant (raw score >= 0.50)
            if use_risk_boost and res["raw_score"] >= 0.50:
                res["final_score"] = res["raw_score"] * multiplier
            else:
                res["final_score"] = res["raw_score"]
                
        # 5. Sort, filter stubs, and cap at k
        # Stubs (< 40 chars) are filtered here — before the LLM ever sees them as context
        results.sort(key=lambda x: x["final_score"], reverse=True)
        results = [r for r in results if len(r["text"].strip()) >= 40]
        return results[:k]
        
    def close(self):
        self.driver.close()
