"""
CUAD Pipeline Orchestrator

Runs the full data ingestion pipeline:
1. Parse CUAD_v1.json + NER + Risk Mapping -> cuad_full.jsonl
2. Split dataset -> train.jsonl, val.jsonl, test.jsonl
"""

import os
import sys
import time

from backend.pipeline.cuad_parser import parse_cuad_dataset
from backend.pipeline.split_dataset import split_dataset

def main():
    print("="*60)
    print("GraphRAG Legal - CUAD Ingestion Pipeline")
    print("="*60)
    
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    json_path = os.path.join(root, "data", "CUAD_v1.json")
    out_dir = os.path.join(root, "data", "processed")
    full_out = os.path.join(out_dir, "cuad_full.jsonl")
    
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        sys.exit(1)
        
    start_time = time.time()
    
    print("\n[1/2] Parsing CUAD dataset and extracting entities...")
    print("      (This may take a minute depending on NER speed)")
    parse_cuad_dataset(json_path, full_out)
    
    print("\n[2/2] Splitting dataset by contract...")
    split_dataset(full_out, out_dir, train_ratio=0.70, val_ratio=0.15)
    
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print(f"Pipeline complete in {elapsed:.1f} seconds!")
    print(f"Outputs saved to: {out_dir}")
    print("="*60)

if __name__ == "__main__":
    main()
