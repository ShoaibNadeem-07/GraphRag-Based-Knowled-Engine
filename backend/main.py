"""
GraphRAG Legal Contract Understanding System — FastAPI Backend
"""

import os
import shutil
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Pipeline Imports
from backend.pipeline.pdf_extractor import extract_text_from_pdf
from backend.pipeline.clause_segmenter import segment_contract
from backend.pipeline.ner_extractor import extract_entities_batch
from backend.pipeline.load_graph import load_single_contract_to_graph
from backend.pipeline.generate_embeddings import incremental_add_to_index
from backend.models.risk_classifier import predict_risk
from backend.retrieval.engine import GraphRAGRetrievalEngine
from backend.llm.synthesizer import GraphRAGSynthesizer

# Load .env from the project root (one level above backend/)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(
    title="GraphRAG Legal API",
    description="Backend for the GraphRAG-based legal contract understanding system.",
    version="0.1.0",
)

# Allow the Vite dev server (port 5173) and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_neo4j_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "graphrag2026")
    return GraphDatabase.driver(uri, auth=(user, password))

# Pydantic Models
class QueryRequest(BaseModel):
    question: str
    contract_id: Optional[str] = None

@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "service": "graphrag-legal",
        "neo4j_uri": os.getenv("NEO4J_URI", "not set"),
    }

@app.post("/contracts/upload", tags=["Upload"])
async def upload_contract(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 1. Extract Text
        extracted = extract_text_from_pdf(temp_path)
        if not extracted["full_text"].strip():
            raise HTTPException(status_code=400, detail="No extractable text found in PDF.")
            
        # Contract ID Generation (using filename without extension for simplicity)
        contract_id = os.path.splitext(file.filename)[0].replace(" ", "_")
        
        # 2. Segment Clauses
        clauses_raw = segment_contract(extracted["full_text"])
        if not clauses_raw:
            raise HTTPException(status_code=400, detail="Could not segment PDF into clauses.")
            
        # 3. NER Extraction (Batch)
        clause_texts = [c["text"] for c in clauses_raw]
        entities_batch = extract_entities_batch(clause_texts)
        
        # 4. Build Document Objects & Risk Prediction (Phase 2 Bi-LSTM)
        clauses = []
        for i, (c_raw, entities) in enumerate(zip(clauses_raw, entities_batch)):
            clause_id = f"{contract_id}_{i}"
            
            # Predict risk
            risk_pred = predict_risk(c_raw["text"])
            
            # Format entities
            formatted_ents = []
            for ent in entities:
                ent_name = ent["text"].strip()
                ent_label = ent["label"]
                ent_id = f"{ent_name}_{ent_label}"
                formatted_ents.append({
                    "id": ent_id,
                    "name": ent_name,
                    "label": ent_label
                })
                
            clauses.append({
                "id": clause_id,
                "contract_id": contract_id,
                "clause_type": "Unclassified",
                "text": c_raw["text"],
                "risk_level": risk_pred["label"],
                "entities": formatted_ents
            })
            
        # 5. Load into Neo4j
        driver = get_neo4j_driver()
        try:
            load_single_contract_to_graph(driver, contract_id, clauses)
        finally:
            driver.close()
            
        # 6. Incrementally add to FAISS
        incremental_add_to_index(clauses)
        
        return {
            "contract_id": contract_id,
            "status": "success",
            "clause_count": len(clauses)
        }
        
    finally:
        shutil.rmtree(temp_dir)

@app.post("/query", tags=["Query"])
async def query_graph(req: QueryRequest):
    synthesizer = GraphRAGSynthesizer()
    
    try:
        # Retrieve Context
        engine = GraphRAGRetrievalEngine()
        context = engine.retrieve_context(req.question, k=5, use_risk_boost=True, contract_id=req.contract_id)
        
        # If no context found
        if not context:
            return {
                "answer": "I cannot answer this based on the provided context.",
                "cited_clauses": [],
                "overall_risk_summary": {}
            }
            
        # Synthesize Answer
        answer = synthesizer.synthesize(req.question, context)
        
        # Risk Summary of retrieved clauses
        risk_summary = {"Low": 0, "Medium": 0, "High": 0, "Unknown": 0}
        for c in context:
            risk = c.get("risk_level", "Unknown")
            if risk in risk_summary:
                risk_summary[risk] += 1
            else:
                risk_summary["Unknown"] += 1
                
        return {
            "answer": answer,
            "cited_clauses": context,
            "overall_risk_summary": risk_summary
        }
    finally:
        pass # Synthesizer engine is closed within its own methods if needed

@app.get("/contracts/{id}/risk-summary", tags=["Contracts"])
async def contract_risk_summary(id: str):
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            # Aggregate stats
            stats_res = session.run("""
                MATCH (c:Contract {id: $id})-[:HAS_CLAUSE]->(cl:Clause)
                RETURN cl.risk_level AS risk, count(cl) AS count
            """, id=id)
            
            counts = {"High": 0, "Medium": 0, "Low": 0, "Unknown": 0}
            for r in stats_res:
                risk = r["risk"]
                if risk in counts:
                    counts[risk] = r["count"]
                else:
                    counts["Unknown"] = r["count"]
                    
            # High risk clauses
            high_res = session.run("""
                MATCH (c:Contract {id: $id})-[:HAS_CLAUSE]->(cl:Clause)
                WHERE cl.risk_level = 'High'
                RETURN cl.id AS id, cl.clause_type AS type, cl.text AS text
            """, id=id)
            
            high_clauses = []
            for r in high_res:
                high_clauses.append({
                    "id": r["id"],
                    "type": r["type"],
                    "short_text": r["text"][:150] + "..." if len(r["text"]) > 150 else r["text"]
                })
                
            return {
                "contract_id": id,
                "counts": counts,
                "high_risk_clauses": high_clauses
            }
    finally:
        driver.close()

@app.get("/contracts", tags=["Contracts"])
async def list_contracts():
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            res = session.run("MATCH (c:Contract) RETURN c.id AS id, c.split AS split")
            contracts = []
            for r in res:
                # Basic human-readable title extraction from ID
                title = r["id"].replace("_", " ")
                contracts.append({
                    "id": r["id"],
                    "title": title,
                    "split": r["split"]
                })
            return contracts
    finally:
        driver.close()
