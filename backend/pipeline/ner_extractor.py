"""
Task 3 — spaCy NER extraction for legal entities.

Extracts entities from clause text:
  ORG    → parties / organizations
  PERSON → individual parties
  DATE   → dates
  MONEY  → monetary values
  GPE    → jurisdictions (states, countries)
  LAW    → legal references
"""

import os
import sys

import spacy

# Legal entity labels we care about
LEGAL_ENTITY_LABELS = {"ORG", "PERSON", "DATE", "MONEY", "GPE", "LAW"}

# Deny-list for common legal defined terms that are not real-world entities
DENY_LIST = {
    "party", "parties", "buyer", "seller", "company", "agreement", 
    "effective date", "operating company", "purchaser", "vendor", 
    "contractor", "client", "customer", "supplier", "distributor",
    "the state of", "the effective date", "this agreement",
    "group company", "restricted business", "prospective customer",
    "restricted territory", "termination date", "the termination date",
    "the company", "any group company", "the restricted business",
    "the restricted territory"
}

# Singleton model cache
_nlp = None

def _get_nlp():
    """Load spaCy model (cached)."""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp

def _is_valid_entity(ent) -> bool:
    """Apply rule-based cleanup to filter false positives."""
    text_lower = ent.text.strip().lower()
    
    # 1. Deny-list check
    # Remove quotes, punctuation, etc before checking
    clean_text = text_lower.replace('"', '').replace("'", "").strip()
    if clean_text in DENY_LIST:
        return False
        
    # 2. Filter obvious span-boundary errors for ORG/PERSON
    # e.g., "the State of" (stops at preposition)
    if ent.label_ in {"ORG", "PERSON"}:
        words = text_lower.split()
        if len(words) <= 2:
            # If it's just "the [word]" or "[word] of", probably cut off
            if words[0] == "the" or words[-1] in {"of", "to", "for", "and", "or"}:
                return False
                
    return True

def extract_entities(text: str) -> list[dict]:
    """
    Run spaCy NER on text and return legal entities, filtering boilerplate.
    """
    nlp = _get_nlp()
    
    # spaCy has a max length; truncate very long texts
    max_len = nlp.max_length
    if len(text) > max_len:
        text = text[:max_len]

    doc = nlp(text)
    entities = []
    seen = set()

    for ent in doc.ents:
        if ent.label_ in LEGAL_ENTITY_LABELS and _is_valid_entity(ent):
            key = (ent.text.strip(), ent.label_, ent.start_char)
            if key not in seen:
                seen.add(key)
                entities.append({
                    "text": ent.text.strip(),
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                })
        
    return entities

def extract_entities_batch(texts: list[str], batch_size: int = 64) -> list[list[dict]]:
    """Batch NER extraction for efficiency, filtering boilerplate."""
    nlp = _get_nlp()
    max_len = nlp.max_length
    truncated = [t[:max_len] if len(t) > max_len else t for t in texts]

    results = []
    for doc in nlp.pipe(truncated, batch_size=batch_size):
        entities = []
        seen = set()
        for ent in doc.ents:
            if ent.label_ in LEGAL_ENTITY_LABELS and _is_valid_entity(ent):
                key = (ent.text.strip(), ent.label_, ent.start_char)
                if key not in seen:
                    seen.add(key)
                    entities.append({
                        "text": ent.text.strip(),
                        "label": ent.label_,
                        "start": ent.start_char,
                        "end": ent.end_char,
                    })
        results.append(entities)

    return results

if __name__ == "__main__":
    import json
    sample = (
        "This Agreement is entered into as of January 15, 2023, "
        "by and between Acme Corporation. The total consideration is $5,000,000."
    )
    print("Sample text:", sample[:100], "...")
    entities = extract_entities(sample)
    print(f"\nFound {len(entities)} entities (regex fallback):")
    for e in entities:
        print(f"  [{e['label']:>6}] {e['text']}")
