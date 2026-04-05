#!/usr/bin/env python3
"""
Promethean — Wiki Compiler
Reads raw/ sources and compiles them into a structured wiki/ using Claude.

Usage:
    python tools/compile.py                # Full rebuild
    python tools/compile.py --incremental  # Only new/changed sources
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    get_client, load_all_raw, load_wiki_index, list_wiki_articles,
    load_article, WIKI_DIR, RAW_DIR, MODEL, MAX_TOKENS, SYSTEM_PROMPT,
    frontmatter, timestamp
)

COMPILE_SYSTEM = """You are the Promethean wiki compiler. Your job is to take raw source articles about Ray Peat's bioenergetic framework and compile them into structured, interlinked wiki articles.

Rules:
1. Each wiki article covers ONE concept, practice, or person
2. Use Obsidian-compatible markdown:
   - [[wikilinks]] to reference other articles (use the filename without extension)
   - > [!summary] callouts for key takeaways
   - YAML frontmatter (title, tags, sources, related, last_compiled)
3. Categorize articles into: concepts/, practical/, or people/
4. Be thorough but concise — every sentence should add value
5. Include practical implications and actionable advice where relevant
6. Maintain a direct, conversational tone — not academic
7. Cross-reference heavily — connect ideas across articles"""


def compile_full(client):
    """Full compilation: read all raw sources, generate/update all wiki articles."""
    raw_articles = load_all_raw()
    if not raw_articles:
        print("No raw articles found in raw/. Add some first.")
        return

    print(f"Found {len(raw_articles)} raw source articles.")

    # Step 1: Plan the wiki structure
    print("\n[1/3] Planning wiki structure...")
    source_summaries = ""
    for path, content in raw_articles.items():
        # Take first 500 chars as preview
        preview = content[:500].replace("\n", " ")
        source_summaries += f"\n- **{path}**: {preview}...\n"

    plan_response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=COMPILE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"""Here are summaries of all raw source articles:

{source_summaries}

Plan the wiki structure. For each article you'll create, specify:
1. Category (concepts/, practical/, or people/)
2. Filename (kebab-case.md)
3. Title
4. Which raw sources it draws from
5. Key [[wikilinks]] it should contain to other planned articles

Also plan the _index.md and _concepts.md files.

Return as JSON with this structure:
{{
  "articles": [
    {{
      "category": "concepts",
      "filename": "example-topic.md",
      "title": "Example Topic",
      "sources": ["articles/source1.md", "articles/source2.md"],
      "wikilinks": ["other-topic", "another-topic"],
      "tags": ["metabolism", "hormones"]
    }}
  ]
}}

Return ONLY the JSON, no other text."""
        }]
    )

    try:
        plan_text = plan_response.content[0].text
        # Try to extract JSON from the response
        if "```json" in plan_text:
            plan_text = plan_text.split("```json")[1].split("```")[0]
        elif "```" in plan_text:
            plan_text = plan_text.split("```")[1].split("```")[0]
        plan = json.loads(plan_text.strip())
    except (json.JSONDecodeError, IndexError) as e:
        print(f"Error parsing plan: {e}")
        print("Raw response:", plan_response.content[0].text[:500])
        return

    articles_plan = plan.get("articles", [])
    print(f"Planned {len(articles_plan)} wiki articles.")

    # Step 2: Generate each article
    print("\n[2/3] Generating wiki articles...")
    generated = []

    for i, article_info in enumerate(articles_plan):
        category = article_info["category"]
        filename = article_info["filename"]
        title = article_info["title"]
        sources = article_info.get("sources", [])
        wikilinks = article_info.get("wikilinks", [])
        tags = article_info.get("tags", [])

        print(f"  [{i+1}/{len(articles_plan)}] {category}/{filename}")

        # Gather source content
        source_content = ""
        for src in sources:
            content = raw_articles.get(src, "")
            if content:
                source_content += f"\n\n## Source: {src}\n{content}"

        if not source_content:
            # If no specific sources matched, use all raw content
            for path, content in raw_articles.items():
                if any(keyword in path.lower() for keyword in filename.replace(".md", "").split("-")):
                    source_content += f"\n\n## Source: {path}\n{content}"

        # Generate the article
        article_response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=COMPILE_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"""Write a wiki article with these specs:

Title: {title}
Category: {category}
Should link to: {', '.join(f'[[{w}]]' for w in wikilinks)}
Tags: {', '.join(tags)}

Source material:
{source_content if source_content else 'Use your knowledge of Ray Peat framework for: ' + title}

Requirements:
1. Start with YAML frontmatter (title, tags, sources as list of raw file paths, related as list of linked article filenames without .md, last_compiled as today's date)
2. After frontmatter, a > [!summary] callout with 2-3 sentence overview
3. Well-structured sections with ## headers
4. Use [[wikilinks]] to reference other articles (by filename without extension, e.g. [[thyroid-function]])
5. End with a "## See Also" section listing related [[wikilinks]]
6. Be thorough, practical, and direct

Write the complete article now."""
            }]
        )

        article_content = article_response.content[0].text

        # Ensure directory exists and write
        article_dir = WIKI_DIR / category
        article_dir.mkdir(parents=True, exist_ok=True)
        article_path = article_dir / filename
        article_path.write_text(article_content)
        generated.append(f"{category}/{filename}")

    # Step 3: Generate index and concept map
    print("\n[3/3] Building index and concept map...")

    # Read all generated articles for the index
    all_articles_summary = ""
    for path in generated:
        content = load_article(path)
        if content:
            first_lines = content.split("\n")[:10]
            all_articles_summary += f"\n- **{path}**: {' '.join(first_lines[:3])}\n"

    # Generate _index.md
    index_response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=COMPILE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"""Generate the master index file (_index.md) for the Promethean wiki.

Articles that exist:
{chr(10).join(f'- {a}' for a in generated)}

Format:
# Promethean Wiki — Index

Brief intro paragraph about what this knowledge base covers.

## Concepts
| Article | Summary |
|---------|---------|
| [[article-name]] | One-line summary |

## Practical Guides
(same table format)

## People
(same table format)

## Queries
(note that this section grows as you use ask.py --file)

Keep summaries to ONE concise line each. Use [[wikilinks]] for article names (filename without extension and without category prefix)."""
        }]
    )
    (WIKI_DIR / "_index.md").write_text(index_response.content[0].text)

    # Generate _concepts.md
    concepts_response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=COMPILE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"""Generate a concept relationship map (_concepts.md) for the Promethean wiki.

Articles:
{chr(10).join(f'- {a}' for a in generated)}

Format:
# Concept Map

Show how concepts relate to each other. Group them into clusters:

## Core Metabolism
- [[oxidative-metabolism]] → foundation for everything
  - Supported by: [[thyroid-function]], [[carbon-dioxide]]
  - Suppressed by: [[polyunsaturated-fats]], [[estrogen-dominance]]

## Hormones
(etc.)

## Practical
(etc.)

Use arrows (→, ←, ↔) to show relationships. Use [[wikilinks]] throughout."""
        }]
    )
    (WIKI_DIR / "_concepts.md").write_text(concepts_response.content[0].text)

    print(f"\nDone! Compiled {len(generated)} articles + index + concept map.")
    print(f"Wiki location: {WIKI_DIR}")


def compile_incremental(client):
    """Incremental: only compile new or changed raw sources."""
    raw_articles = load_all_raw()
    existing = set(list_wiki_articles())

    # Check which raw files are new or modified
    new_sources = []
    for path in raw_articles:
        # Simple check: if no wiki article seems to reference this source
        is_referenced = False
        for wiki_path in existing:
            content = load_article(wiki_path) or ""
            if path in content:
                is_referenced = True
                break
        if not is_referenced:
            new_sources.append(path)

    if not new_sources:
        print("No new sources to compile. Wiki is up to date.")
        return

    print(f"Found {len(new_sources)} new source(s) to compile:")
    for s in new_sources:
        print(f"  - {s}")

    # For each new source, generate appropriate wiki articles
    for source_path in new_sources:
        content = raw_articles[source_path]
        print(f"\nCompiling: {source_path}")

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=COMPILE_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"""A new raw source has been added to the knowledge base:

**Source:** {source_path}
**Content:**
{content}

**Existing wiki articles:** {', '.join(existing)}

Determine what wiki articles to create or update from this source. Return JSON:
{{
  "create": [
    {{
      "category": "concepts|practical|people",
      "filename": "article-name.md",
      "title": "Article Title"
    }}
  ],
  "update": ["existing/article-to-update.md"]
}}

Only create new articles for topics not already covered. Suggest updates for existing articles that should incorporate this new source material. Return ONLY JSON."""
            }]
        )

        try:
            resp_text = response.content[0].text
            if "```json" in resp_text:
                resp_text = resp_text.split("```json")[1].split("```")[0]
            elif "```" in resp_text:
                resp_text = resp_text.split("```")[1].split("```")[0]
            actions = json.loads(resp_text.strip())
        except (json.JSONDecodeError, IndexError):
            print(f"  Could not parse response, skipping.")
            continue

        # Create new articles
        for new_article in actions.get("create", []):
            cat = new_article["category"]
            fname = new_article["filename"]
            title = new_article["title"]
            print(f"  Creating: {cat}/{fname}")

            gen_response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=COMPILE_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": f"""Write a wiki article:

Title: {title}
Category: {cat}
Source material:
{content}

Existing articles to link to: {', '.join(f'[[{Path(a).stem}]]' for a in existing)}

Include YAML frontmatter, > [!summary] callout, sections, [[wikilinks]], and ## See Also."""
                }]
            )

            article_dir = WIKI_DIR / cat
            article_dir.mkdir(parents=True, exist_ok=True)
            (article_dir / fname).write_text(gen_response.content[0].text)
            existing.add(f"{cat}/{fname}")

    # Regenerate index
    print("\nRegenerating index...")
    all_articles = list_wiki_articles()
    index_content = f"# Promethean Wiki — Index\n\nLast updated: {timestamp()[:10]}\n\n"
    for article in sorted(all_articles):
        if article.startswith("_"):
            continue
        name = Path(article).stem
        index_content += f"- [[{name}]] ({article})\n"
    (WIKI_DIR / "_index.md").write_text(index_content)

    print("Done! Run a full compile for a more thorough rebuild.")


def main():
    parser = argparse.ArgumentParser(description="Promethean Wiki Compiler")
    parser.add_argument("--incremental", action="store_true",
                        help="Only compile new/changed sources")
    args = parser.parse_args()

    client = get_client()

    if args.incremental:
        compile_incremental(client)
    else:
        compile_full(client)


if __name__ == "__main__":
    main()
