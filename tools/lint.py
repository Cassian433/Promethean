#!/usr/bin/env python3
"""
Promethean — Wiki Linter / Health Checker
Find broken links, inconsistencies, gaps, and suggest improvements.

Usage:
    python tools/lint.py              # Run all checks
    python tools/lint.py --fix        # Auto-fix simple issues
    python tools/lint.py --suggest    # Use LLM to suggest new articles and connections
"""

import sys
import re
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    get_client, list_wiki_articles, load_article, list_raw_articles,
    WIKI_DIR, MODEL, MAX_TOKENS, SYSTEM_PROMPT
)


def extract_wikilinks(content):
    """Extract all [[wikilinks]] from content."""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def extract_frontmatter(content):
    """Extract frontmatter as dict-like structure."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    fm_text = parts[1]
    fm = {}
    current_key = None
    current_list = []
    for line in fm_text.strip().split("\n"):
        if line.startswith("  - "):
            current_list.append(line.strip("  - ").strip())
        elif ": " in line:
            if current_key and current_list:
                fm[current_key] = current_list
                current_list = []
            key, val = line.split(": ", 1)
            current_key = key.strip()
            fm[current_key] = val.strip()
        elif line.endswith(":"):
            if current_key and current_list:
                fm[current_key] = current_list
                current_list = []
            current_key = line.rstrip(":")
            current_list = []
    if current_key and current_list:
        fm[current_key] = current_list
    return fm


class LintResults:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []

    def error(self, msg):
        self.errors.append(msg)

    def warning(self, msg):
        self.warnings.append(msg)

    def note(self, msg):
        self.info.append(msg)

    def print_report(self):
        try:
            from rich.console import Console
            from rich.panel import Panel
            console = Console()

            if self.errors:
                console.print(f"\n[bold red]ERRORS ({len(self.errors)}):[/bold red]")
                for e in self.errors:
                    console.print(f"  [red]✗[/red] {e}")

            if self.warnings:
                console.print(f"\n[bold yellow]WARNINGS ({len(self.warnings)}):[/bold yellow]")
                for w in self.warnings:
                    console.print(f"  [yellow]![/yellow] {w}")

            if self.info:
                console.print(f"\n[bold blue]INFO ({len(self.info)}):[/bold blue]")
                for i in self.info:
                    console.print(f"  [blue]ℹ[/blue] {i}")

            total = len(self.errors) + len(self.warnings)
            if total == 0:
                console.print("\n[bold green]✓ Wiki is healthy![/bold green]")
            else:
                console.print(f"\n[bold]Total: {len(self.errors)} errors, {len(self.warnings)} warnings[/bold]")

        except ImportError:
            if self.errors:
                print(f"\nERRORS ({len(self.errors)}):")
                for e in self.errors:
                    print(f"  ✗ {e}")
            if self.warnings:
                print(f"\nWARNINGS ({len(self.warnings)}):")
                for w in self.warnings:
                    print(f"  ! {w}")
            if self.info:
                print(f"\nINFO ({len(self.info)}):")
                for i in self.info:
                    print(f"  ℹ {i}")


def check_broken_links(results):
    """Find [[wikilinks]] that point to non-existent articles."""
    articles = list_wiki_articles()
    stems = {Path(a).stem for a in articles}

    for path in articles:
        content = load_article(path)
        if not content:
            continue
        links = extract_wikilinks(content)
        for link in links:
            if link not in stems:
                results.error(f"Broken link [[{link}]] in {path}")


def check_orphan_articles(results):
    """Find articles not linked from anywhere else."""
    articles = list_wiki_articles()
    all_links = set()

    for path in articles:
        content = load_article(path)
        if not content:
            continue
        links = extract_wikilinks(content)
        all_links.update(links)

    for path in articles:
        if path.startswith("_"):
            continue
        stem = Path(path).stem
        if stem not in all_links:
            results.warning(f"Orphan article (not linked from anywhere): {path}")


def check_missing_frontmatter(results):
    """Check articles have proper frontmatter."""
    for path in list_wiki_articles():
        if path.startswith("_"):
            continue
        content = load_article(path)
        if not content:
            continue
        if not content.startswith("---"):
            results.warning(f"Missing frontmatter: {path}")
        else:
            fm = extract_frontmatter(content)
            if "title" not in fm:
                results.warning(f"Missing title in frontmatter: {path}")
            if "tags" not in fm:
                results.warning(f"Missing tags in frontmatter: {path}")


def check_missing_sources(results):
    """Check if articles reference their raw sources."""
    for path in list_wiki_articles():
        if path.startswith("_"):
            continue
        content = load_article(path)
        if not content:
            continue
        fm = extract_frontmatter(content)
        sources = fm.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        if not sources or sources == ["[]"]:
            results.note(f"No raw sources linked: {path}")


def check_raw_coverage(results):
    """Check if all raw sources are compiled into wiki articles."""
    raw_articles = list_raw_articles()
    wiki_articles = list_wiki_articles()

    # Check if raw sources are referenced
    all_wiki_content = ""
    for path in wiki_articles:
        content = load_article(path) or ""
        all_wiki_content += content

    for raw_path in raw_articles:
        if raw_path not in all_wiki_content:
            results.note(f"Raw source not referenced in wiki: {raw_path}")


def check_duplicate_topics(results):
    """Look for articles that might cover the same topic."""
    articles = list_wiki_articles()
    titles = {}
    for path in articles:
        if path.startswith("_"):
            continue
        content = load_article(path) or ""
        fm = extract_frontmatter(content)
        title = fm.get("title", Path(path).stem)
        if isinstance(title, str):
            title_lower = title.lower().strip('"').strip("'")
            if title_lower in titles:
                results.warning(f"Possible duplicate: {path} and {titles[title_lower]} (same title)")
            titles[title_lower] = path


def suggest_improvements(client, results):
    """Use LLM to suggest new articles, connections, and improvements."""
    articles = list_wiki_articles()
    article_summaries = []
    for path in articles:
        if path.startswith("_"):
            continue
        content = load_article(path) or ""
        # Just get first 200 chars
        preview = content[:200].replace("\n", " ")
        article_summaries.append(f"- {path}: {preview}")

    raw = list_raw_articles()
    raw_list = "\n".join(f"- {r}" for r in raw)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"""Analyze this Ray Peat knowledge base and suggest improvements.

Wiki articles:
{chr(10).join(article_summaries)}

Raw sources:
{raw_list}

Current lint issues:
- Errors: {len(results.errors)}
- Warnings: {len(results.warnings)}

Suggest:
1. Missing topics that should have their own article (based on Ray Peat's framework)
2. Connections between existing articles that should be linked
3. Questions worth investigating that would enhance the knowledge base
4. Any inconsistencies you can spot from the summaries

Be specific and actionable."""
        }]
    )

    print("\n" + "=" * 60)
    print("  LLM SUGGESTIONS")
    print("=" * 60)
    try:
        from rich.console import Console
        from rich.markdown import Markdown
        Console().print(Markdown(response.content[0].text))
    except ImportError:
        print(response.content[0].text)


def fix_broken_links(results):
    """Auto-fix: create stub articles for broken links."""
    articles = list_wiki_articles()
    stems = {Path(a).stem for a in articles}
    fixed = 0

    for path in articles:
        content = load_article(path)
        if not content:
            continue
        links = extract_wikilinks(content)
        for link in links:
            if link not in stems:
                # Create a stub in concepts/
                stub_path = WIKI_DIR / "concepts" / f"{link}.md"
                if not stub_path.exists():
                    stub_path.parent.mkdir(parents=True, exist_ok=True)
                    stub_path.write_text(f"""---
title: {link.replace('-', ' ').title()}
tags: [stub]
sources: []
related: []
last_compiled: {Path(path).stem}
---

# {link.replace('-', ' ').title()}

> [!summary]
> This is a stub article. Run `compile.py` to flesh it out.

*This article needs content. Add raw sources about this topic and recompile.*
""")
                    fixed += 1
                    print(f"  Created stub: concepts/{link}.md")

    print(f"Fixed {fixed} broken links by creating stubs.")


def main():
    parser = argparse.ArgumentParser(description="Promethean Wiki Linter")
    parser.add_argument("--fix", action="store_true", help="Auto-fix simple issues")
    parser.add_argument("--suggest", action="store_true",
                        help="Use LLM to suggest improvements")
    args = parser.parse_args()

    results = LintResults()

    print("Running wiki health checks...\n")

    check_broken_links(results)
    check_orphan_articles(results)
    check_missing_frontmatter(results)
    check_missing_sources(results)
    check_raw_coverage(results)
    check_duplicate_topics(results)

    results.print_report()

    if args.fix:
        print("\nApplying auto-fixes...")
        fix_broken_links(results)

    if args.suggest:
        print("\nGetting LLM suggestions...")
        client = get_client()
        suggest_improvements(client, results)


if __name__ == "__main__":
    main()
