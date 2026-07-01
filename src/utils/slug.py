import re


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug."""
    if not name:
        return ""

    slug = name.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-_\s]+", "-", slug)
    slug = slug.strip("-")

    return slug[:100]


def normalize_for_comparison(text: str) -> str:
    if not text:
        return ""

    return text.lower().strip()
