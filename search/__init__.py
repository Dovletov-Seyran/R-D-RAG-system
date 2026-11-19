"""Поиск по корпусу методичек: токенизатор, собственный BM25, индекс.

Контракт C1 (docs/checkpoint-2.md):

    from search import load_index, retrieve
    index = load_index()
    hits = retrieve(index, "Как найти предел функции?", k=5)
"""

from search.index import (  # noqa: F401
    Hit,
    SearchIndex,
    build_index,
    has_context,
    load_index,
    retrieve,
    retrieve_documents,
    save_index,
)
