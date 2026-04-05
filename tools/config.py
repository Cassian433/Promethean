"""
Promethean — Configuration & Shared Utilities
"""

import os
import json
from pathlib import Path
from datetime import datetime

# Paths
ROOT_DIR = Path(__file__).parent.parent
RAW_DIR = ROOT_DIR / "raw"
WIKI_DIR = ROOT_DIR / "wiki"
TOOLS_DIR = ROOT_DIR / "tools"
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"

# Ensure directories exist
for d in [RAW_DIR, WIKI_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# API Configuration
def get_api_key():
    """Get Anthropic API key from environment."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError(
            "ANTHROPIC_API_KEY not set. Export it:\n"
            "  export ANTHROPIC_API_KEY='your-key-here'"
        )
    return key

MODEL = os.environ.get("PROMETHEAN_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("PROMETHEAN_MAX_TOKENS", "4096"))

# System prompt — the Peat-grounded persona
SYSTEM_PROMPT = """You are Promethean, an AI assistant deeply grounded in Ray Peat's bioenergetic framework. You answer all health, nutrition, hormone, and metabolism questions through the lens of Peat's published work and the researchers he referenced (Broda Barnes, Albert Szent-Györgyi, Derrick Lonsdale, William Koch, etc.).

Core principles you operate from:
- Oxidative metabolism (glucose + oxygen → CO2 + energy) is the foundation of health
- Polyunsaturated fats (PUFAs) suppress mitochondrial respiration and accumulate in tissues
- Thyroid hormone (T3) is the master metabolic regulator
- Estrogen, serotonin, prolactin, and cortisol are stress signals, not beneficial hormones
- Sugar (glucose/fructose) is protective, not harmful — it supports oxidative metabolism
- DHT is the primary androgen; testosterone is largely a prohormone
- Learned helplessness is a metabolic state, not merely psychological
- Aging is primarily energy decline from PUFA/iron accumulation, not genetic destiny
- CO2 is pro-metabolic (Bohr effect), not just a waste product
- Light, warmth, and adequate nutrition restore cellular energy production

When answering:
- Ground responses in Peat's framework and cite relevant concepts
- Be practical — give actionable advice, not just theory
- Use [[wikilinks]] when referencing concepts that exist in the knowledge base
- Be direct and conversational, not academic
- When mainstream medicine contradicts Peat, explain both positions and why Peat disagreed"""


def get_client():
    """Create and return an Anthropic client."""
    from anthropic import Anthropic
    return Anthropic(api_key=get_api_key())


def load_wiki_index():
    """Load the master index file content."""
    index_path = WIKI_DIR / "_index.md"
    if index_path.exists():
        return index_path.read_text()
    return ""


def load_wiki_concepts_map():
    """Load the concept relationship map."""
    concepts_path = WIKI_DIR / "_concepts.md"
    if concepts_path.exists():
        return concepts_path.read_text()
    return ""


def load_article(path):
    """Load a single wiki article."""
    full_path = WIKI_DIR / path if not Path(path).is_absolute() else Path(path)
    if full_path.exists():
        return full_path.read_text()
    return None


def list_wiki_articles():
    """List all .md files in the wiki directory recursively."""
    articles = []
    for md_file in sorted(WIKI_DIR.rglob("*.md")):
        rel_path = md_file.relative_to(WIKI_DIR)
        articles.append(str(rel_path))
    return articles


def list_raw_articles():
    """List all .md files in the raw directory recursively."""
    articles = []
    for md_file in sorted(RAW_DIR.rglob("*.md")):
        rel_path = md_file.relative_to(RAW_DIR)
        articles.append(str(rel_path))
    return articles


def load_raw_article(path):
    """Load a single raw source article."""
    full_path = RAW_DIR / path if not Path(path).is_absolute() else Path(path)
    if full_path.exists():
        return full_path.read_text()
    return None


def load_all_raw():
    """Load all raw articles as a dict of {path: content}."""
    articles = {}
    for name in list_raw_articles():
        content = load_raw_article(name)
        if content:
            articles[name] = content
    return articles


def load_relevant_wiki_context(question, max_articles=10):
    """
    Load wiki articles most relevant to a question.
    Uses the index to find relevant articles, then loads them.
    """
    index = load_wiki_index()
    articles = list_wiki_articles()

    if not articles:
        return "No wiki articles found. Run compile.py first."

    # Simple keyword matching — load index + top relevant articles
    question_lower = question.lower()
    scored = []
    for article_path in articles:
        if article_path.startswith("_"):
            continue
        name = Path(article_path).stem.replace("-", " ")
        score = sum(1 for word in question_lower.split() if word in name)
        scored.append((score, article_path))

    scored.sort(reverse=True)
    top_articles = [path for _, path in scored[:max_articles]]

    # Always include index
    context_parts = []
    if index:
        context_parts.append(f"## Wiki Index\n{index}")

    for path in top_articles:
        content = load_article(path)
        if content:
            context_parts.append(f"## {path}\n{content}")

    return "\n\n---\n\n".join(context_parts)


def timestamp():
    """Current ISO timestamp."""
    return datetime.now().isoformat()


def frontmatter(title, tags=None, sources=None, related=None):
    """Generate YAML frontmatter for a wiki article."""
    fm = {
        "title": title,
        "tags": tags or [],
        "sources": sources or [],
        "related": related or [],
        "last_compiled": timestamp()[:10],
    }
    lines = ["---"]
    for key, val in fm.items():
        if isinstance(val, list):
            if val:
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines)
