"""Сборка BM25-индекса из corpus/processed.

    python -m search.build
"""

from __future__ import annotations

import sys
import time

from search import config
from search.index import build_index, save_index


def main() -> int:
    started = time.perf_counter()
    index = build_index()
    path = save_index(index)
    elapsed = time.perf_counter() - started
    print(
        f"Индекс собран: {len(index.documents)} документов, {len(index.chunks)} фрагментов, "
        f"{len(index.bm25.postings)} термов, avgdl={index.bm25.avgdl:.1f}, {elapsed:.1f} с → "
        f"{path.relative_to(config.ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
