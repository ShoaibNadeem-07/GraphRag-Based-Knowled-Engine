# GraphRAG Legal — Contract Intelligence

A GraphRAG-powered legal contract analysis system that combines semantic search, knowledge graph retrieval, and a locally-hosted LLM to answer natural-language questions about contracts — with clause-level citations and risk classification.

Built as a final-year dissertation project.

---

## Features

- **Risk Classification** — Bi-LSTM classifier (Sentence-BERT embeddings) assigns Low / Medium / High risk to every clause at ingest. ~87.5% accuracy on the held-out CUAD test set.
- **GraphRAG Retrieval** — FAISS semantic search + Neo4j 1-hop graph expansion via shared named entities, with risk-aware re-ranking.
- **Grounded LLM Answers** — llama3.1 (local, via Ollama) answers questions strictly from retrieved context with numbered citations [1]–[5]. Refuses when context does not address the question.
- **Contract Upload** — Upload any PDF contract for segmentation, NER, risk classification, and graph indexing.
- **React Frontend** — Contract picker, risk dashboard, and query agent with clickable citation cards that expand to full clause text.

---

## Architecture

```
PDF Upload
    │
    ▼
pdf_extractor.py  ──►  clause_segmenter.py  ──►  ner_extractor.py
                                │
                                ▼
                    Bi-LSTM Risk Classifier (SBERT embeddings)
                                │
                    ┌───────────▼───────────┐
                    │   Neo4j Knowledge     │◄── load_graph.py (CUAD)
                    │   Graph               │
                    │   Contract→Clause     │
                    │         →Entity       │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  FAISS Vector Index   │◄── generate_embeddings.py
                    └───────────┬───────────┘
                                │
                    GraphRAG Retrieval Engine
                    (FAISS + graph expansion + risk re-rank)
                                │
                    llama3.1 Synthesizer (Ollama)
                                │
                    FastAPI Backend  ◄──►  React Frontend
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker + Docker Compose | Runs Neo4j and the FastAPI backend |
| Node.js ≥ 18 | Runs the Vite/React frontend |
| Python ≥ 3.10 | For pipeline scripts (run outside Docker) |
| [Ollama](https://ollama.com) | Local LLM runtime — install and `ollama pull llama3.1` |
| CUAD dataset | Download from [CUAD on Hugging Face](https://huggingface.co/datasets/theatticusproject/cuad) — place `CUAD_v1.json` in `data/` |

---

## Quickstart

### 1. Clone and configure

```bash
git clone https://github.com/your-username/graphrag-legal.git
cd graphrag-legal
cp .env.example .env
# Edit .env if you need to change the Neo4j password or Ollama endpoint
```

### 2. Start infrastructure

```bash
docker-compose up -d
```

This starts Neo4j (port 7474/7687) and the FastAPI backend (port 8000).

### 3. Pull the LLM

```bash
ollama pull llama3.1
```

### 4. Run the data pipeline (first time only)

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Parse CUAD dataset
python -m backend.pipeline.cuad_parser

# Split into train/val/test
python -m backend.pipeline.split_dataset

# Train risk classifier (~10 min on CPU)
python -m backend.pipeline.train_bilstm

# Load graph into Neo4j
python -m backend.pipeline.load_graph

# Generate FAISS embeddings
python -m backend.pipeline.generate_embeddings
```

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Project Structure

```
graphrag-legal/
├── backend/
│   ├── Dockerfile
│   ├── main.py                  # FastAPI app — /upload, /query, /risk-summary, /contracts
│   ├── requirements.txt
│   ├── pipeline/
│   │   ├── cuad_parser.py       # Parse CUAD_v1.json → JSONL
│   │   ├── split_dataset.py     # Train/val/test split
│   │   ├── train_bilstm.py      # Train Bi-LSTM risk classifier
│   │   ├── load_graph.py        # Load clauses + entities into Neo4j
│   │   ├── generate_embeddings.py # Build FAISS index
│   │   ├── clause_segmenter.py  # Rule-based clause segmentation (PDF uploads)
│   │   ├── pdf_extractor.py     # PyMuPDF text extraction
│   │   ├── ner_extractor.py     # Named entity recognition (spaCy)
│   │   └── risk_mapping.py      # CUAD category → Low/Medium/High mapping
│   ├── retrieval/
│   │   └── engine.py            # GraphRAG retrieval: FAISS + graph expansion + re-rank
│   └── llm/
│       └── synthesizer.py       # Ollama LLM answer synthesis
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Shell + navigation
│   │   ├── ContractPicker.jsx   # Upload + contract list
│   │   ├── RiskDashboard.jsx    # Risk summary + high-risk clause list
│   │   ├── QueryScreen.jsx      # Query agent + citation cards
│   │   ├── api.js               # API client
│   │   └── index.css            # Design system (palette, typography, components)
│   └── index.html
├── data/
│   └── processed/
│       └── risk_mapping.json    # Hand-authored CUAD category → risk mapping
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/contracts` | List all contracts in the graph |
| `POST` | `/contracts/upload` | Upload a PDF contract for processing |
| `GET` | `/contracts/{id}/risk-summary` | Risk counts + High-risk clause list for a contract |
| `POST` | `/query` | Ask a question (optionally scoped to a contract) |
| `GET` | `/health` | Health check |

Full interactive docs at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Results

Evaluated on held-out CUAD test set (never seen during training):

| Metric | Score |
|---|---|
| Accuracy | **87.47%** |
| Macro-F1 | **86.99%** |

Using frozen Sentence-BERT embeddings (all-MiniLM-L6-v2) as Bi-LSTM input eliminates out-of-vocabulary collapse on new uploads — a key advantage over a learned embedding table.

---

## Known Limitations

- **CUAD annotation stubs**: 186 clauses in the graph are bare header lines (e.g., "The Distributor shall not:") from CUAD annotator artifacts. These are filtered at the retrieval layer (< 40 chars) and never reach the LLM.
- **LLM latency**: Cold-start query generation takes 30–90s on a mid-range CPU. Acceptable for demo, not production.
- **FAISS scoped search**: Contracts not well-represented in the global top-1000 FAISS results fall back to Neo4j word-overlap ranking for scoped queries.
- **Risk mapping**: The Low/Medium/High mapping of 41 CUAD categories reflects one legal perspective; different teams may disagree on specific categories.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

- [CUAD Dataset](https://www.atticusprojectai.org/cuad) — Atticus Project, CC BY 4.0
- [Sentence-Transformers](https://www.sbert.net/) — `all-MiniLM-L6-v2`
- [Ollama](https://ollama.com) — local LLM runtime
- [Neo4j](https://neo4j.com) — graph database
- [FAISS](https://github.com/facebookresearch/faiss) — Facebook AI Similarity Search
