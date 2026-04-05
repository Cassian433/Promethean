#!/usr/bin/env python3
"""
Promethean — Source Ingestion Helper
Fetch URLs or local files and add them to raw/ as clean markdown.

Usage:
    python tools/ingest.py https://raypeat.com/articles/articles/sugar-issues.shtml
    python tools/ingest.py /path/to/local/article.pdf
    python tools/ingest.py --list                    # List all raw sources
"""

import sys
import re
import argparse
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from config import RAW_DIR, list_raw_articles


def slugify(text, max_len=60):
    """Convert text to a filename-safe slug."""
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower())
    return slug[:max_len].strip('-')


def fetch_url(url):
    """Fetch a URL and return clean text content."""
    import urllib.request
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text_parts = []
            self.skip_tags = {'script', 'style', 'nav', 'header', 'footer'}
            self.current_skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in self.skip_tags:
                self.current_skip += 1
            if tag in ('p', 'br', 'div', 'h1', 'h2', 'h3', 'h4', 'li'):
                self.text_parts.append('\n')
            if tag in ('h1', 'h2', 'h3'):
                level = int(tag[1])
                self.text_parts.append('#' * level + ' ')

        def handle_endtag(self, tag):
            if tag in self.skip_tags:
                self.current_skip -= 1
            if tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'li'):
                self.text_parts.append('\n')

        def handle_data(self, data):
            if self.current_skip <= 0:
                self.text_parts.append(data)

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; Promethean/1.0)'
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return None, None

    # Extract title
    title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else urlparse(url).path.split('/')[-1]

    # Extract text
    extractor = TextExtractor()
    extractor.feed(html)
    text = ''.join(extractor.text_parts)

    # Clean up
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return title, text


def ingest_url(url):
    """Ingest a URL into raw/articles/."""
    print(f"Fetching: {url}")
    title, content = fetch_url(url)

    if not content:
        print("Failed to fetch content.")
        return None

    # Generate filename
    slug = slugify(title)
    filename = f"{slug}.md"
    filepath = RAW_DIR / "articles" / filename

    # Build the markdown document
    md = f"""---
title: "{title}"
source_url: {url}
ingested: {datetime.now().isoformat()[:10]}
type: article
---

# {title}

> Source: {url}
> Ingested: {datetime.now().isoformat()[:10]}

{content}
"""

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(md)
    print(f"Saved to: raw/articles/{filename}")
    print(f"Title: {title}")
    print(f"Length: {len(content)} characters")
    print(f"\nRun 'python tools/compile.py --incremental' to add to wiki.")
    return filepath


def ingest_local(path):
    """Ingest a local file into raw/."""
    src = Path(path)
    if not src.exists():
        print(f"File not found: {path}")
        return None

    content = src.read_text(errors='replace')
    filename = src.name
    if not filename.endswith('.md'):
        filename = src.stem + '.md'

    dest = RAW_DIR / "articles" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Add ingestion metadata if it's not already markdown with frontmatter
    if not content.startswith("---"):
        content = f"""---
title: "{src.stem.replace('-', ' ').title()}"
source_file: {path}
ingested: {datetime.now().isoformat()[:10]}
type: local
---

{content}
"""

    dest.write_text(content)
    print(f"Saved to: raw/articles/{filename}")
    print(f"Run 'python tools/compile.py --incremental' to add to wiki.")
    return dest


def list_sources():
    """List all raw source articles."""
    articles = list_raw_articles()
    if not articles:
        print("No raw sources found. Use 'python tools/ingest.py <url>' to add some.")
        return

    print(f"Raw sources ({len(articles)}):\n")
    for a in articles:
        path = RAW_DIR / a
        size = path.stat().st_size if path.exists() else 0
        print(f"  {a} ({size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Promethean Source Ingestion")
    parser.add_argument("source", nargs="?", help="URL or local file path to ingest")
    parser.add_argument("--list", action="store_true", help="List all raw sources")
    args = parser.parse_args()

    if args.list:
        list_sources()
        return

    if not args.source:
        print("Usage:")
        print("  python tools/ingest.py <url>           # Fetch and save a web article")
        print("  python tools/ingest.py <file>           # Copy a local file")
        print("  python tools/ingest.py --list           # List raw sources")
        return

    source = args.source
    if source.startswith("http://") or source.startswith("https://"):
        ingest_url(source)
    else:
        ingest_local(source)


if __name__ == "__main__":
    main()
