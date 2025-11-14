from difflib import SequenceMatcher
from typing import Any

from src.utils.slug import generate_slug, normalize_for_comparison


def calculate_similarity(input_text: str, target_text: str) -> float:
    """Calculate similarity score between two strings."""
    if not input_text or not target_text:
        return 0.0

    input_slug = generate_slug(input_text)
    target_slug = generate_slug(target_text)
    slug_similarity = SequenceMatcher(None, input_slug, target_slug).ratio()

    input_norm = normalize_for_comparison(input_text)
    target_norm = normalize_for_comparison(target_text)
    name_similarity = SequenceMatcher(None, input_norm, target_norm).ratio()

    return max(slug_similarity, name_similarity)


def find_similar_groups(
    input_name: str,
    existing_groups: list[dict[str, Any]],
    threshold: float = 0.8,
    limit: int = 3,
) -> list[tuple[dict[str, Any], float]]:
    """Find similar group names using fuzzy matching."""
    if not input_name or not existing_groups:
        return []

    similarities: list[tuple[dict[str, Any], float]] = []
    for group in existing_groups:
        if "name" not in group:
            continue

        similarity = calculate_similarity(input_name, group["name"])

        if similarity >= threshold:
            similarities.append((group, similarity))

    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:limit]


def format_similarity_percentage(similarity: float) -> str:
    """Format similarity score as percentage."""
    return f"{int(similarity * 100)}%"
