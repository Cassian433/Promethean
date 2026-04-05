#!/usr/bin/env python3
"""
Promethean — Wiki Search Engine
TF-IDF based search over the wiki with optional web UI.

Usage:
    python tools/search.py "PUFA thyroid"
    python tools/search.py --serve              # Launch web UI on localhost:8877
    python tools/search.py --json "query"       # JSON output (for piping to other tools)
"""

import sys
import re
import math
import json
import argparse
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from config import WIKI_DIR, list_wiki_articles, load_article


def tokenize(text):
    """Simple tokenizer — lowercase, split on non-alphanumeric."""
    return re.findall(r'[a-z0-9]+', text.lower())


def strip_frontmatter(text):
    """Remove YAML frontmatter from article."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return text


class SearchIndex:
    """TF-IDF search index over wiki articles."""

    def __init__(self):
        self.documents = {}  # path → content
        self.doc_tokens = {}  # path → token list
        self.df = Counter()  # document frequency per term
        self.num_docs = 0

    def build(self):
        """Build the index from wiki articles."""
        articles = list_wiki_articles()
        for path in articles:
            content = load_article(path)
            if not content:
                continue
            clean = strip_frontmatter(content)
            self.documents[path] = clean
            tokens = tokenize(clean)
            self.doc_tokens[path] = tokens
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self.df[token] += 1

        self.num_docs = len(self.documents)
        return self

    def search(self, query, top_k=10):
        """Search the index, return ranked results with snippets."""
        if not self.documents:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = {}
        for path, tokens in self.doc_tokens.items():
            token_counts = Counter(tokens)
            doc_len = len(tokens)
            if doc_len == 0:
                continue

            score = 0.0
            for qt in query_tokens:
                tf = token_counts.get(qt, 0) / doc_len
                idf = math.log((self.num_docs + 1) / (self.df.get(qt, 0) + 1))
                score += tf * idf

            if score > 0:
                scores[path] = score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for path, score in ranked:
            content = self.documents[path]
            snippet = self._extract_snippet(content, query_tokens)
            title = self._extract_title(content, path)
            results.append({
                "path": path,
                "title": title,
                "score": round(score, 4),
                "snippet": snippet,
            })

        return results

    def _extract_snippet(self, content, query_tokens, context_chars=200):
        """Extract a relevant snippet containing query terms."""
        content_lower = content.lower()
        best_pos = 0
        best_count = 0

        # Find the position with the most query term hits nearby
        for i in range(0, len(content_lower), 50):
            window = content_lower[i:i + context_chars]
            count = sum(1 for qt in query_tokens if qt in window)
            if count > best_count:
                best_count = count
                best_pos = i

        start = max(0, best_pos - 20)
        end = min(len(content), best_pos + context_chars)
        snippet = content[start:end].strip()

        # Clean up
        snippet = re.sub(r'\s+', ' ', snippet)
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet

    def _extract_title(self, content, path):
        """Extract article title from content or path."""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# ") and not line.startswith("##"):
                return line[2:].strip()
        return Path(path).stem.replace("-", " ").title()


def print_results(results, query):
    """Pretty-print search results."""
    if not results:
        print(f'No results for "{query}"')
        return

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text

        console = Console()
        console.print(f'\n[bold]Search results for:[/bold] "{query}"\n')

        for i, r in enumerate(results, 1):
            console.print(f"[bold cyan]{i}.[/bold cyan] [bold]{r['title']}[/bold]")
            console.print(f"   [dim]{r['path']}[/dim] (score: {r['score']})")
            console.print(f"   {r['snippet']}\n")

    except ImportError:
        print(f'\nSearch results for: "{query}"\n')
        for i, r in enumerate(results, 1):
            print(f"{i}. {r['title']}")
            print(f"   {r['path']} (score: {r['score']})")
            print(f"   {r['snippet']}\n")


def serve_web(host="127.0.0.1", port=8877):
    """Serve a simple web search UI."""
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from urllib.parse import parse_qs, urlparse
    except ImportError:
        print("Could not import http.server")
        return

    index = SearchIndex().build()

    class SearchHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)

            if parsed.path == "/" or parsed.path == "/search":
                query_params = parse_qs(parsed.query)
                query = query_params.get("q", [""])[0]
                results = index.search(query) if query else []

                html = f"""<!DOCTYPE html>
<html><head>
<title>Promethean Search</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #1a1a2e; color: #e0e0e0; }}
h1 {{ color: #ff6b35; }}
input[type=text] {{ width: 100%; padding: 12px; font-size: 16px; border: 1px solid #444; border-radius: 6px; background: #16213e; color: #e0e0e0; }}
.result {{ margin: 20px 0; padding: 15px; background: #16213e; border-radius: 8px; border-left: 3px solid #ff6b35; }}
.result h3 {{ margin: 0 0 5px 0; color: #ff6b35; }}
.result .path {{ color: #888; font-size: 0.85em; }}
.result .snippet {{ margin-top: 8px; line-height: 1.5; }}
.score {{ color: #666; font-size: 0.8em; }}
</style>
</head><body>
<h1>🔥 Promethean Search</h1>
<form action="/search" method="get">
<input type="text" name="q" value="{query}" placeholder="Search the knowledge base..." autofocus>
</form>
"""
                if query:
                    html += f'<p>{len(results)} result(s) for "<b>{query}</b>"</p>'
                    for r in results:
                        html += f"""<div class="result">
<h3>{r['title']}</h3>
<div class="path">{r['path']} <span class="score">(score: {r['score']})</span></div>
<div class="snippet">{r['snippet']}</div>
</div>"""

                html += "</body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(html.encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress default logging

    server = HTTPServer((host, port), SearchHandler)
    print(f"Promethean Search running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="Promethean Wiki Search")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--serve", action="store_true", help="Launch web UI")
    parser.add_argument("--top", type=int, default=10, help="Number of results")
    args = parser.parse_args()

    if args.serve:
        serve_web()
        return

    if not args.query:
        print("Usage: python search.py 'query' or python search.py --serve")
        return

    index = SearchIndex().build()
    results = index.search(args.query, top_k=args.top)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_results(results, args.query)


if __name__ == "__main__":
    main()
