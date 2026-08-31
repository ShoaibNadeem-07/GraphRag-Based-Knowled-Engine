"""
Task 2 — Rule-based clause segmentation.

Segments extracted contract text into clauses using:
  1. Heading / numbering patterns (regex-based)
  2. Sentence-boundary fallback (for blocks without clear headings)
"""

import re


# ---------------------------------------------------------------------------
# Heading / numbering patterns (ordered by specificity)
# ---------------------------------------------------------------------------
_HEADING_PATTERNS = [
    # ARTICLE I, ARTICLE 1, Article 1.
    re.compile(
        r"^[ \t]*(?:ARTICLE|Article)\s+[IVXLCDM\d]+\.?\s*[\.:\-—]?\s*(.*)$",
        re.MULTILINE,
    ),
    # SECTION 1.1, Section 1.01, SECTION 1
    re.compile(
        r"^[ \t]*(?:SECTION|Section)\s+\d+(?:\.\d+)*\.?\s*[\.:\-—]?\s*(.*)$",
        re.MULTILINE,
    ),
    # Numbered: 1., 1.1, 1.1.1, 10.2.3
    re.compile(
        r"^[ \t]*(\d{1,3}(?:\.\d{1,3}){0,3})\.?\s+[A-Z]",
        re.MULTILINE,
    ),
    # Lettered subsections: (a), (b), (i), (ii)
    re.compile(
        r"^[ \t]*\([a-z]{1,4}\)\s+",
        re.MULTILINE,
    ),
    # EXHIBIT A, SCHEDULE 1, APPENDIX B
    re.compile(
        r"^[ \t]*(?:EXHIBIT|SCHEDULE|APPENDIX|ANNEX)\s+[A-Z0-9]+",
        re.MULTILINE,
    ),
    # ALL-CAPS headings on their own line (≥3 words, ≤80 chars)
    re.compile(
        r"^[ \t]*([A-Z][A-Z\s\-/&,]{5,78})$",
        re.MULTILINE,
    ),
]


def _find_heading_splits(text: str) -> list[int]:
    """Find character positions where headings / numbered sections start."""
    positions = set()
    for pattern in _HEADING_PATTERNS:
        for m in pattern.finditer(text):
            positions.add(m.start())
    return sorted(positions)


def _sentence_split(text: str) -> list[str]:
    """
    Simple sentence-boundary splitter as fallback.
    Splits on period/question-mark/exclamation followed by whitespace + uppercase.
    Keeps sentences together that are short (< 40 chars) to avoid over-splitting.
    """
    # Split on sentence boundaries
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)

    # Merge very short fragments with the next sentence
    merged = []
    buffer = ""
    for s in raw:
        if buffer:
            buffer = buffer + " " + s
            if len(buffer) >= 40:
                merged.append(buffer.strip())
                buffer = ""
        elif len(s) < 40:
            buffer = s
        else:
            merged.append(s.strip())
    if buffer:
        merged.append(buffer.strip())

    return [s for s in merged if s.strip()]


def segment_contract(text: str, min_clause_len: int = 50) -> list[dict]:
    """
    Segment contract text into clauses.

    Returns a list of dicts:
        {
            "clause_index": int,
            "heading": str | None,
            "text": str,
            "start_char": int,
            "end_char": int
        }
    """
    splits = _find_heading_splits(text)

    if not splits:
        # No headings found — fall back to sentence splitting
        sentences = _sentence_split(text)
        clauses = []
        offset = 0
        for i, sent in enumerate(sentences):
            start = text.find(sent, offset)
            if start == -1:
                start = offset
            end = start + len(sent)
            clauses.append({
                "clause_index": i,
                "heading": None,
                "text": sent.strip(),
                "start_char": start,
                "end_char": end,
            })
            offset = end
        return [c for c in clauses if len(c["text"]) >= min_clause_len]

    # Add start and end boundaries
    if splits[0] != 0:
        splits.insert(0, 0)

    clauses = []
    for i, start in enumerate(splits):
        end = splits[i + 1] if i + 1 < len(splits) else len(text)
        chunk = text[start:end]

        # Try to extract heading from first line
        first_line = chunk.strip().split("\n")[0].strip()
        heading = None
        if len(first_line) < 120 and (
            first_line.isupper()
            or re.match(r"^(?:ARTICLE|SECTION|EXHIBIT|SCHEDULE)", first_line, re.I)
            or re.match(r"^\d{1,3}[\.\)]", first_line)
        ):
            heading = first_line

        clause_text = chunk.strip()
        if len(clause_text) < min_clause_len:
            continue

        clauses.append({
            "clause_index": len(clauses),
            "heading": heading,
            "text": clause_text,
            "start_char": start,
            "end_char": end,
        })

    # Merge colon-terminated header chunks with ALL following sub-item chunks.
    # Pattern: "The Distributor shall not:\n(a)...\n(b)...\n(c)..." should be one clause.
    # We absorb consecutive chunks that start with a lettered/numbered sub-item marker.
    _SUBITEM_START = re.compile(r"^\s*(?:\([a-z]{1,4}\)|\([ivx]+\)|\d{1,2}[\.\)])\s+")
    
    merged_chunks = []
    i = 0
    while i < len(clauses):
        c = clauses[i]
        # If this chunk ends with a colon, absorb all immediately following sub-items
        if c["text"].rstrip().endswith(":"):
            j = i + 1
            while j < len(clauses) and _SUBITEM_START.match(clauses[j]["text"]):
                c["text"] = c["text"].rstrip() + "\n" + clauses[j]["text"]
                c["end_char"] = clauses[j]["end_char"]
                j += 1
            i = j
        else:
            i += 1
        merged_chunks.append(c)

    return [c for c in merged_chunks if len(c["text"]) >= min_clause_len]


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    clauses = segment_contract(text)
    print(f"Found {len(clauses)} clauses")
    for c in clauses[:5]:
        print(json.dumps({
            "idx": c["clause_index"],
            "heading": c["heading"],
            "chars": len(c["text"]),
            "preview": c["text"][:80] + "...",
        }, indent=2))
