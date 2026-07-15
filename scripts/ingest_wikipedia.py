#!/usr/bin/env python3
"""Ingest Wikipedia page content into slowave.

Fetches a Wikipedia article and stores each paragraph (with >10 words) as a
separate memory in slowave. Each paragraph is stored with type='fact' and
scoped to 'wikipedia:<page_title>'.

Usage:
    python ingest_wikipedia.py "https://en.wikipedia.org/wiki/Artificial_intelligence"
    python ingest_wikipedia.py --scope "project:my-kb" "https://en.wikipedia.org/wiki/Python_(programming_language)"
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

# Set environment variables before heavy imports
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

# Suppress verbose library logging
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("onnxruntime").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# Add parent directory to path to import slowave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.core.paths import default_db_path
from slowave.symbolic.encoder import EncoderConfig

log = logging.getLogger(__name__)


def extract_page_title(url: str) -> str:
    """Extract the page title from a Wikipedia URL.

    Examples:
        https://en.wikipedia.org/wiki/Python_(programming_language) -> Python (programming language)
        https://en.wikipedia.org/wiki/Machine_learning -> Machine learning
    """
    parsed = urlparse(url)
    path_parts = parsed.path.split("/")

    # Typically: ['', 'wiki', 'Article_Title']
    if len(path_parts) >= 3 and path_parts[1] == "wiki":
        title = path_parts[2]
        # Decode URL encoding and replace underscores with spaces
        title = unquote(title).replace("_", " ")
        return title

    return "Unknown"


def fetch_wikipedia_content(url: str) -> str:
    """Fetch the HTML content of a Wikipedia page."""
    headers = {"User-Agent": "SlowaveWikipediaIngester/1.0 (Educational/Research Purpose)"}

    req = Request(url, headers=headers)
    with urlopen(req) as response:
        return response.read().decode("utf-8")


def extract_paragraphs(html: str, min_words: int = 10) -> list[str]:
    """Extract paragraphs from Wikipedia HTML content.

    Uses simple regex-based parsing to avoid external dependencies.
    Filters out paragraphs with fewer than min_words words.
    """
    paragraphs = []

    # Remove script and style elements
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # Find content within the main article div (id="mw-content-text")
    content_match = re.search(
        r'<div[^>]*id="mw-content-text"[^>]*>(.*?)<div[^>]*id="catlinks"', html, re.DOTALL
    )
    if content_match:
        html = content_match.group(1)

    # Extract text from <p> tags
    p_pattern = re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL)
    for match in p_pattern.finditer(html):
        p_content = match.group(1)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", p_content)

        # Decode HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Skip empty paragraphs or those with too few words
        if not text:
            continue

        word_count = len(text.split())
        if word_count >= min_words:
            paragraphs.append(text)

    return paragraphs


def build_engine(db_path: str | None = None) -> SlowaveEngine:
    """Build a SlowaveEngine instance."""
    if db_path is None:
        db_path = default_db_path()

    # Ensure directory exists
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    cfg = SlowaveConfig(
        db_path=db_path,
        dim=384,
        encoder=EncoderConfig(),
        disable_encoder=False,
    )
    return SlowaveEngine(cfg)


def ingest_wikipedia_page(
    url: str,
    *,
    scope: str | None = None,
    min_words: int = 10,
    db_path: str | None = None,
    verbose: bool = False,
) -> dict[str, any]:
    """Ingest a Wikipedia page into slowave.

    Args:
        url: Wikipedia article URL
        scope: Optional scope override (default: wikipedia:<page_title>)
        min_words: Minimum word count for a paragraph to be ingested
        db_path: Optional database path override
        verbose: Enable verbose output

    Returns:
        Dictionary with ingestion statistics
    """
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    log.info(f"Fetching: {url}")

    try:
        html = fetch_wikipedia_content(url)
    except Exception as e:
        log.error(f"Failed to fetch page: {e}")
        return {"success": False, "error": str(e)}

    page_title = extract_page_title(url)
    log.info(f"Page title: {page_title}")

    paragraphs = extract_paragraphs(html, min_words=min_words)
    log.info(f"Extracted {len(paragraphs)} paragraphs (min {min_words} words each)")

    if not paragraphs:
        log.warning("No paragraphs found meeting the criteria")
        return {"success": False, "error": "No paragraphs found"}

    # Determine scope
    if scope is None:
        scope = f"wikipedia:{page_title}"

    log.info(f"Storing to scope: {scope}")

    # Build engine and ingest
    eng = build_engine(db_path)

    stored_count = 0
    failed_count = 0

    for i, para in enumerate(paragraphs, 1):
        try:
            # Store each paragraph as a fact
            result = eng.remember(
                content=para,
                type="fact",
                scope=scope,
            )
            stored_count += 1

            if verbose:
                preview = para[:80] + "..." if len(para) > 80 else para
                log.info(f"  [{i}/{len(paragraphs)}] Stored (event_id={result}): {preview}")
        except Exception as e:
            failed_count += 1
            log.error(f"  [{i}/{len(paragraphs)}] Failed to store: {e}")

    eng.close()

    log.info("\nIngestion complete:")
    log.info(f"  - Successfully stored: {stored_count}")
    log.info(f"  - Failed: {failed_count}")
    log.info(f"  - Total paragraphs: {len(paragraphs)}")

    return {
        "success": True,
        "page_title": page_title,
        "scope": scope,
        "total_paragraphs": len(paragraphs),
        "stored_count": stored_count,
        "failed_count": failed_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Wikipedia page content into slowave memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "https://en.wikipedia.org/wiki/Artificial_intelligence"
  %(prog)s --scope "project:ai-kb" "https://en.wikipedia.org/wiki/Machine_learning"
  %(prog)s --min-words 20 --verbose "https://en.wikipedia.org/wiki/Python_(programming_language)"
  %(prog)s --db /tmp/test.db "https://en.wikipedia.org/wiki/Memory"
        """,
    )

    parser.add_argument(
        "url", help="Wikipedia article URL (e.g., https://en.wikipedia.org/wiki/Article_name)"
    )

    parser.add_argument(
        "--scope",
        help="Scope for storing memories (default: wikipedia:<page_title>)",
        default=None,
    )

    parser.add_argument(
        "--min-words",
        type=int,
        default=10,
        help="Minimum word count for a paragraph (default: 10)",
    )

    parser.add_argument(
        "--db",
        help="Database path override (default: ~/.slowave/slowave.db)",
        default=None,
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Validate URL
    if not args.url.startswith("http"):
        print(f"Error: Invalid URL: {args.url}", file=sys.stderr)
        sys.exit(1)

    result = ingest_wikipedia_page(
        args.url,
        scope=args.scope,
        min_words=args.min_words,
        db_path=args.db,
        verbose=args.verbose,
    )

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
