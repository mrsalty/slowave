"""Shared console-report banner formatting for the benchmark scripts.

Keeps the header/footer chrome consistent across LoCoMo, LongMemEval, DMR,
StaleMemory, Temporal, and WikiScenarios so `run_full_benchmark.py` output
reads the same regardless of which benchmark produced it.
"""

from __future__ import annotations

WIDTH = 72


def print_header(title: str, meta: list[str] | None = None) -> None:
    print()
    print("=" * WIDTH)
    print(f" SLOWAVE — {title}")
    print("=" * WIDTH)
    for line in meta or []:
        print(f" {line}")
    if meta:
        print()


def print_footer() -> None:
    print("=" * WIDTH)
    print()


def print_table(
    headers: list[str], rows: list[list[str]], *, total_row: list[str] | None = None
) -> None:
    """Render a table: first column left-aligned, the rest right-aligned,
    with a header separator and an optional separated total row.

    This is the one table renderer every benchmark script should use for its
    per-category/per-pattern breakdown — column widths and separator style
    are computed once here, so LoCoMo/LongMemEval/StaleMemory/DMR render
    identically instead of each hand-rolling its own printf widths (which is
    how they drifted out of sync with each other in the first place).

    Cells must already be pre-formatted strings (e.g. "86.2%", "0.793") —
    this only handles alignment, not number formatting.
    """
    all_rows = rows + ([total_row] if total_row else [])
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in all_rows)) if all_rows else len(headers[i])
        for i in range(len(headers))
    ]

    def fmt(cells: list[str]) -> str:
        first = f"{cells[0]:<{widths[0]}}"
        rest = [f"{c:>{widths[i]}}" for i, c in enumerate(cells[1:], start=1)]
        return " " + "  ".join([first] + rest)

    print(fmt(headers))
    print(" " + "  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt(row))
    if total_row:
        print(" " + "  ".join("-" * w for w in widths))
        print(fmt(total_row))
