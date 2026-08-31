"""
Task 5 — Risk-level mapping for CUAD clause categories.

Loads the approved 41-category → High/Medium/Low mapping from
data/processed/risk_mapping.json and provides lookup functions.
"""

import json
import os

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_PATH = os.path.join(_PROJECT_ROOT, "data", "processed", "risk_mapping.json")

_mapping: dict[str, str] | None = None


def _load_mapping(path: str = _DEFAULT_PATH) -> dict[str, str]:
    """Load risk mapping from JSON file."""
    global _mapping
    if _mapping is None:
        with open(path, encoding="utf-8") as f:
            _mapping = json.load(f)
    return _mapping


def get_risk_level(clause_type: str, path: str = _DEFAULT_PATH) -> str:
    """
    Look up risk level for a CUAD clause category.

    Performs case-insensitive matching with title-case normalization.

    Returns:
        "High", "Medium", or "Low".
        Returns "Unknown" if the category is not found.
    """
    mapping = _load_mapping(path)

    # Direct match
    if clause_type in mapping:
        return mapping[clause_type]

    # Case-insensitive match via title-case
    normalized = clause_type.strip().title()
    if normalized in mapping:
        return mapping[normalized]

    # Fuzzy: try matching ignoring case entirely
    lower_map = {k.lower(): v for k, v in mapping.items()}
    lower_key = clause_type.strip().lower()
    if lower_key in lower_map:
        return lower_map[lower_key]

    return "Unknown"


def get_all_mappings(path: str = _DEFAULT_PATH) -> dict[str, str]:
    """Return the full mapping dict."""
    return dict(_load_mapping(path))


if __name__ == "__main__":
    mapping = get_all_mappings()
    counts = {"High": 0, "Medium": 0, "Low": 0}
    for cat, level in sorted(mapping.items()):
        print(f"  {level:>6}  {cat}")
        counts[level] = counts.get(level, 0) + 1
    print(f"\nDistribution: {counts}")
