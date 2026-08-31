import os
import requests
import json
from typing import Dict, Any, List

class GraphRAGSynthesizer:
    def __init__(self):
        # Ollama endpoint inside docker using host.docker.internal to reach host machine
        self.ollama_endpoint = os.environ.get("LLM_ENDPOINT", "http://host.docker.internal:11434")
        self.model = "llama3.1"
        
        self.system_prompt = """You are a highly precise legal AI assistant. Answer the user's question based STRICTLY on the numbered contract clauses provided below.

Rules:
- Base your answer only on the provided clauses. Do NOT use outside knowledge or speculate beyond what the text says.
- You MAY reason about related concepts when the context clearly addresses the question using different words. For example: if the user asks about "breach" and the clauses describe termination rights triggered by a violation of the agreement, that is a valid answer — you are not required to find the exact word "breach" in the text. Similarly, "default" and "non-compliance" may describe the same concept as "breach". Use legal common sense about synonymous concepts.
- You MUST refuse with exactly "I cannot answer this based on the provided context." ONLY when the clauses genuinely do not address the question or any closely related concept — for example, if the user asks a general knowledge question (like geography or science) or asks about a topic the contract simply does not cover.
- Write your answer in clean, natural prose. Do NOT include full clause IDs or long identifiers in the answer text.
- Cite sources using only short numbered markers matching the clause numbers in the context, e.g. [1], [2]. Place the marker immediately after the relevant claim.
- Only use numbers that appear in the provided context. Do not invent numbers.

Context:
---
{context}
---"""

    def synthesize(self, query: str, clauses: List[Dict[str, Any]]) -> str:
        """Generates an answer from pre-retrieved context clauses.
        
        Args:
            query: The user's question.
            clauses: Pre-retrieved list of clause dicts from GraphRAGRetrievalEngine.
            
        Returns:
            The synthesized answer string.
        """
        if not clauses:
            return "I cannot answer this based on the provided context."
            
        # Format numbered context blocks so LLM uses [1], [2] etc. in its answer
        context_blocks = []
        for i, c in enumerate(clauses, start=1):
            block = (
                f"[{i}] Risk Level: {c.get('risk_level', 'Unknown')} | "
                f"Contract: {c.get('contract_id', 'Unknown')}\n"
                f"Text: {c['text']}"
            )
            context_blocks.append(block)
            
        formatted_context = "\n\n".join(context_blocks)
        sys_prompt = self.system_prompt.replace("{context}", formatted_context)
        
        # Call Ollama
        url = f"{self.ollama_endpoint}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": query}
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_ctx": 8192
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "Error: No content in response.")
        except requests.exceptions.RequestException as e:
            return f"Error connecting to Ollama at {self.ollama_endpoint}: {str(e)}"
