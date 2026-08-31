"""
Task 4 — CUAD JSON Parser

Parses CUAD_v1.json to build a clean JSONL dataset.
For each contract, extracts QAs (clauses), applies NER, and looks up risk levels.
"""

import json
import os
import re

from backend.pipeline.ner_extractor import extract_entities
from backend.pipeline.risk_mapping import get_risk_level


def _extract_category_name(question: str) -> str:
    """
    CUAD questions are formatted like:
    'Highlight the parts (if any) of this contract related to "Document Name" that should be...'
    Extract the category name inside quotes.
    """
    m = re.search(r'"([^"]+)"', question)
    if m:
        return m.group(1).title()  # Normalize to title case for matching
    return "Unknown"


def parse_cuad_dataset(
    json_path: str,
    output_path: str,
    max_contracts: int | None = None
) -> None:
    """
    Parse CUAD_v1.json and write structured JSONL records to output_path.
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    
    contracts = data.get("data", [])
    if max_contracts:
        contracts = contracts[:max_contracts]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    total_written = 0
    with open(output_path, "w", encoding="utf-8") as out_f:
        for contract in contracts:
            contract_id = contract["title"]
            
            for para in contract.get("paragraphs", []):
                for qa in para.get("qas", []):
                    is_impossible = qa.get("is_impossible", False)
                    category_raw = _extract_category_name(qa["question"])
                    
                    # Normalize category names to match our risk mapping keys
                    # e.g., "Rofr/Rofo/Rofn" -> "Rofr/Rofo/Rofn"
                    if "Rofr" in category_raw:
                        category = "Rofr/Rofo/Rofn"
                    else:
                        category = category_raw

                    risk = get_risk_level(category)
                    
                    if is_impossible:
                        # Contract does not contain this clause
                        record = {
                            "contract_id": contract_id,
                            "clause_type": category,
                            "clause_text": None,
                            "answer": None,
                            "is_impossible": True,
                            "entities": [],
                            "risk_level": risk
                        }
                        out_f.write(json.dumps(record) + "\n")
                        total_written += 1
                    else:
                        # Contract has one or more answers for this clause
                        for ans in qa.get("answers", []):
                            text = ans.get("text", "").strip()
                            
                            # Skip empty answers
                            if not text:
                                continue
                                
                            entities = extract_entities(text)
                            
                            record = {
                                "contract_id": contract_id,
                                "clause_type": category,
                                "clause_text": text,
                                "answer": text,  # In CUAD, the answer is the clause span
                                "is_impossible": False,
                                "entities": entities,
                                "risk_level": risk
                            }
                            out_f.write(json.dumps(record) + "\n")
                            total_written += 1

    print(f"Parsed {len(contracts)} contracts, wrote {total_written} records to {output_path}")

if __name__ == "__main__":
    import sys
    
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    json_path = os.path.join(root, "data", "CUAD_v1.json")
    out_path = os.path.join(root, "data", "processed", "cuad_full.jsonl")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--sample":
        print("Running in sample mode (5 contracts)...")
        parse_cuad_dataset(json_path, out_path, max_contracts=5)
    else:
        parse_cuad_dataset(json_path, out_path)
