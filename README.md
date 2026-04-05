# Promethean

An LLM-powered personal knowledge base on Ray Peat's bioenergetic framework.

Named after Prometheus, who stole fire for humanity. Peat's whole framework is about restoring cellular fire — oxidative metabolism.

## Architecture

```
raw/          → Source documents (articles, papers, transcripts)
wiki/         → LLM-compiled knowledge base (Obsidian vault)
tools/        → CLI tools for compilation, Q&A, search, linting
data/logs/    → Daily tracking logs
```

The LLM owns the wiki. You read it, query it, file answers back into it — but you rarely edit it directly. Your explorations always add up.

## Setup

```bash
# Install dependencies
pip install -r promethean/tools/requirements.txt

# Set your API key
export ANTHROPIC_API_KEY='your-key-here'

# Optional: use a different model (default: claude-sonnet-4-6)
export PROMETHEAN_MODEL='claude-sonnet-4-6'
```

## Usage

### Compile raw sources into wiki

```bash
# Full rebuild — reads all raw/, generates entire wiki/
python promethean/tools/compile.py

# Incremental — only process new/changed sources
python promethean/tools/compile.py --incremental
```

### Ask questions

```bash
# Single question
python promethean/tools/ask.py "why does Peat recommend aspirin?"

# Interactive mode (conversation with follow-ups)
python promethean/tools/ask.py

# Ask and file the answer into wiki/queries/ (your explorations add up)
python promethean/tools/ask.py --file "what's the connection between PUFA and depression?"
```

### Search the wiki

```bash
# CLI search
python promethean/tools/search.py "thyroid DHT"

# JSON output (pipe to other tools)
python promethean/tools/search.py --json "estrogen prolactin"

# Web UI on localhost:8877
python promethean/tools/search.py --serve
```

### Lint / health check

```bash
# Run all checks (broken links, orphans, missing frontmatter)
python promethean/tools/lint.py

# Auto-fix simple issues (create stubs for broken links)
python promethean/tools/lint.py --fix

# Get LLM suggestions for new articles, connections, gaps
python promethean/tools/lint.py --suggest
```

### Ingest new sources

```bash
# From a URL
python promethean/tools/ingest.py https://raypeat.com/articles/articles/sugar-issues.shtml

# From a local file
python promethean/tools/ingest.py /path/to/article.md

# List all raw sources
python promethean/tools/ingest.py --list
```

## Obsidian

The `wiki/` directory is an Obsidian-compatible vault. Open it in Obsidian to:
- Browse articles with rendered markdown
- See the graph view of concept relationships
- Follow `[[wikilinks]]` between articles
- View your filed queries in `queries/`

## Workflow

1. **Ingest** sources into `raw/` (web clipper, manual copy, `ingest.py`)
2. **Compile** raw sources into wiki articles (`compile.py`)
3. **Query** the knowledge base (`ask.py`) — file interesting answers back
4. **Search** when you need something specific (`search.py`)
5. **Lint** periodically to find gaps and keep quality high (`lint.py`)
6. Repeat — the knowledge base grows with every interaction

## Core Framework (TL;DR)

Cells that can oxidize glucose in the presence of oxygen are healthy. Everything that interferes with that — PUFAs, estrogen, serotonin, low thyroid, darkness, cold — pushes you toward stress metabolism, aging, and disease. Restoring cellular fire is the whole game.
