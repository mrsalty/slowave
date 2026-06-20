"""Wikipedia corpus for WikiScenarios benchmark.

12 pages across 4 domain clusters.  Text is pre-fetched and cached in
data/corpus_cache.json so the benchmark runs offline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

DATA_DIR = Path(__file__).parent / "data"
CACHE_FILE = DATA_DIR / "corpus_cache.json"

@dataclass(frozen=True)
class WikiPage:
    title: str   # underscore form, matches cache key
    url: str
    cluster: str  # ml | rome | music | controls
    description: str

WIKI_CORPUS: list[WikiPage] = [
    # ML cluster
    WikiPage("Machine_learning",          "https://en.wikipedia.org/wiki/Machine_learning",          "ml",       "ML paradigms and algorithms"),
    WikiPage("Deep_learning",             "https://en.wikipedia.org/wiki/Deep_learning",             "ml",       "Deep learning and neural architectures"),
    WikiPage("Artificial_neural_network", "https://en.wikipedia.org/wiki/Artificial_neural_network", "ml",       "Neural network structure and training"),
    # Rome cluster
    WikiPage("Ancient_Rome",   "https://en.wikipedia.org/wiki/Ancient_Rome",   "rome",  "Ancient Roman civilisation"),
    WikiPage("Roman_Empire",   "https://en.wikipedia.org/wiki/Roman_Empire",   "rome",  "Roman Empire expansion and governance"),
    WikiPage("Julius_Caesar",  "https://en.wikipedia.org/wiki/Julius_Caesar",  "rome",  "Julius Caesar biography"),
    # Music cluster
    WikiPage("Jazz",           "https://en.wikipedia.org/wiki/Jazz",           "music", "Jazz history and improvisation"),
    WikiPage("Blues",          "https://en.wikipedia.org/wiki/Blues",          "music", "Blues origins and influence"),
    WikiPage("Improvisation",  "https://en.wikipedia.org/wiki/Improvisation",  "music", "Musical improvisation"),
    # Controls (dissimilar)
    WikiPage("Cell_(biology)", "https://en.wikipedia.org/wiki/Cell_(biology)", "biology","Cell structure and function"),
    WikiPage("Photosynthesis", "https://en.wikipedia.org/wiki/Photosynthesis", "biology","Photosynthesis process"),
    WikiPage("Quantum_mechanics","https://en.wikipedia.org/wiki/Quantum_mechanics","physics","Quantum mechanics principles"),
]

_CACHE: dict[str, list[str]] | None = None


def _fetch_and_parse(url: str, min_words: int = 10) -> list[str]:
    """Fetch a Wikipedia page and extract paragraphs."""
    req = Request(url, headers={"User-Agent": "WikiScenariosBenchmark/2.0"})
    with urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8")

    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>",  "", html, flags=re.DOTALL | re.IGNORECASE)

    m = re.search(r'<div[^>]*id="mw-content-text"[^>]*>(.*?)<div[^>]*id="catlinks"', html, re.DOTALL)
    if m:
        html = m.group(1)

    paragraphs: list[str] = []
    for match in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.DOTALL):
        text = re.sub(r"<[^>]+>", "", match.group(1))
        for ent, rep in [("&nbsp;"," "),("&amp;","&"),("&lt;","<"),("&gt;",">"),("&quot;",'"'),("&#39;","'")]:
            text = text.replace(ent, rep)
        text = re.sub(r"\s+", " ", text).strip()
        if text and len(text.split()) >= min_words:
            paragraphs.append(text)
    return paragraphs


def load_cache() -> dict[str, list[str]]:
    """Return cached paragraphs dict {title: [para, ...]}."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not CACHE_FILE.exists():
        raise FileNotFoundError(
            f"Corpus cache not found at {CACHE_FILE}. "
            "Run:  python tests/wiki_scenarios/corpus.py  to download."
        )
    with open(CACHE_FILE) as f:
        _CACHE = json.load(f)
    return _CACHE


def paragraphs_for(title: str) -> list[str]:
    """Return cached paragraph list for a Wikipedia page title."""
    return load_cache()[title]


def pages_for_cluster(cluster: str) -> list[WikiPage]:
    return [p for p in WIKI_CORPUS if p.cluster == cluster]


# ── download / rebuild cache ────────────────────────────────────────────────

def download_corpus(force: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists() and not force:
        print(f"Cache already exists at {CACHE_FILE} (use force=True to re-download)")
        return

    cache: dict[str, list[str]] = {}
    for page in WIKI_CORPUS:
        print(f"  Fetching {page.title}...", end="", flush=True)
        try:
            paras = _fetch_and_parse(page.url)
            cache[page.title] = paras
            print(f" {len(paras)} paragraphs")
        except Exception as e:
            print(f" FAILED: {e}")
            cache[page.title] = []

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)
    total = sum(len(v) for v in cache.values())
    print(f"\nCached {total} paragraphs → {CACHE_FILE}")


if __name__ == "__main__":
    download_corpus()
