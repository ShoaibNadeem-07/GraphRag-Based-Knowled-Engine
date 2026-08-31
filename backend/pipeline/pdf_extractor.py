"""
Task 1 — PyMuPDF-based PDF text extraction.

Extracts text from contract PDFs in full_contract_pdf/.
Simulates what happens when a new, unlabeled contract is uploaded.
"""

import os
import sys
import fitz  # pymupdf


def extract_text_from_pdf(pdf_path: str) -> dict:
    """
    Extract text from a single PDF file.

    Returns:
        {
            "filename": str,
            "full_text": str,
            "num_pages": int,
            "pages": [{"page_num": int, "text": str}, ...]
        }
    """
    doc = fitz.open(pdf_path)
    pages = []
    full_text_parts = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        pages.append({"page_num": page_num + 1, "text": text})
        full_text_parts.append(text)

    doc.close()

    return {
        "filename": os.path.basename(pdf_path),
        "full_text": "\n\n".join(full_text_parts),
        "num_pages": len(pages),
        "pages": pages,
    }


def find_all_pdfs(base_dir: str) -> list[str]:
    """
    Recursively find all PDF files under base_dir.
    Handles the nested Part_I/Part_II/Part_III/category/ structure.
    """
    pdf_paths = []
    for root, _dirs, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_paths.append(os.path.join(root, f))
    pdf_paths.sort()
    return pdf_paths


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Extract text from a contract PDF")
    parser.add_argument("--pdf", type=str, help="Path to a single PDF file")
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List all PDFs in data/full_contract_pdf/",
    )
    args = parser.parse_args()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    if args.list_all:
        pdf_dir = os.path.join(project_root, "data", "full_contract_pdf")
        pdfs = find_all_pdfs(pdf_dir)
        print(f"Found {len(pdfs)} PDFs")
        for p in pdfs[:5]:
            print(f"  {p}")
        if len(pdfs) > 5:
            print(f"  ... and {len(pdfs) - 5} more")
        sys.exit(0)

    if args.pdf:
        result = extract_text_from_pdf(args.pdf)
        print(f"File: {result['filename']}")
        print(f"Pages: {result['num_pages']}")
        print(f"Text length: {len(result['full_text'])} chars")
        print("--- First 500 chars ---")
        print(result["full_text"][:500])
    else:
        parser.print_help()
