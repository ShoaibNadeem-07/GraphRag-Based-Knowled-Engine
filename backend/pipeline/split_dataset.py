"""
Task 6 — Contract-level train/val/test split.

Splits data/processed/cuad_full.jsonl into train.jsonl, val.jsonl, test.jsonl
ensuring all clauses for a given contract_id stay in the same split to prevent leakage.
"""

import json
import os
import random
from collections import defaultdict


def _get_contract_type(contract_id: str) -> str:
    """
    Extract a rough contract type from the ID for stratified splitting.
    CUAD IDs typically have the contract type at the end (e.g., "...-AGREEMENT").
    """
    parts = contract_id.split("-")
    if len(parts) > 1:
        return parts[-1].upper()
    return "UNKNOWN"


def split_dataset(
    full_jsonl: str,
    out_dir: str,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    seed: int = 42
) -> None:
    """Split dataset at the contract level."""
    random.seed(seed)
    
    # 1. Read all records and group by contract_id
    contract_records = defaultdict(list)
    total_records = 0
    with open(full_jsonl, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            contract_id = rec["contract_id"]
            contract_records[contract_id].append(line)
            total_records += 1
            
    print(f"Loaded {total_records} records across {len(contract_records)} contracts.")

    # 2. Perform global split
    cids = list(contract_records.keys())
    random.shuffle(cids)
    
    n = len(cids)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    
    train_ids = cids[:n_train]
    val_ids = cids[n_train:n_train+n_val]
    test_ids = cids[n_train+n_val:]
        
    print(f"Split contract counts -> Train: {len(train_ids)}, Val: {len(val_ids)}, Test: {len(test_ids)}")
    
    # 4. Write output files
    split_files = {
        "train": (train_ids, os.path.join(out_dir, "train.jsonl")),
        "val": (val_ids, os.path.join(out_dir, "val.jsonl")),
        "test": (test_ids, os.path.join(out_dir, "test.jsonl")),
    }
    
    manifest = {}
    
    for split_name, (cids, path) in split_files.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        count = 0
        with open(path, "w", encoding="utf-8") as out_f:
            for cid in cids:
                manifest[cid] = split_name
                for line in contract_records[cid]:
                    out_f.write(line)
                    count += 1
        print(f"Wrote {count} records to {path}")
        
    # 5. Write manifest
    manifest_path = os.path.join(out_dir, "split_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved manifest to {manifest_path}")


if __name__ == "__main__":
    import sys
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    
    if len(sys.argv) > 2:
        full_path = sys.argv[1]
        out_path = sys.argv[2]
    else:
        full_path = os.path.join(root, "data", "processed", "cuad_full.jsonl")
        out_path = os.path.join(root, "data", "processed")
        
    if not os.path.exists(full_path):
        print(f"Error: {full_path} not found. Run cuad_parser.py first.")
        sys.exit(1)
        
    split_dataset(full_path, out_path)
