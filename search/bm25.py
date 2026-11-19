"""Собственная реализация BM25 (Okapi) на обратном индексе.

Готовые поисковые индексы (rank-bm25 и т. п.) не используются — требование
методических указаний к НИРС, раздел 2.

    IDF(t)     = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
    BM25(q, d) = sum_{t in q} IDF(t) * tf(t,d) * (k1 + 1) /
                 (tf(t,d) + k1 * (1 - b + b * |d| / avgdl))

Термы запроса берутся без повторов (как в разборе на занятии 3).
Равные баллы упорядочиваются по номеру документа — результат детерминирован.
"""

from __future__ import annotations

import math
from collections import Counter


class BM25Index:
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.postings: dict[str, dict[int, int]] = {}  # терм -> {номер документа: tf}
        self.lengths: list[int] = []
        self.avgdl = 0.0

    # --- построение -------------------------------------------------------
    def fit(self, documents: list[list[str]]) -> "BM25Index":
        self.postings = {}
        self.lengths = []
        for doc_id, terms in enumerate(documents):
            self.lengths.append(len(terms))
            for term, tf in Counter(terms).items():
                self.postings.setdefault(term, {})[doc_id] = tf
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        return self

    @property
    def n_docs(self) -> int:
        return len(self.lengths)

    def idf(self, term: str) -> float:
        df = len(self.postings.get(term, {}))
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

    # --- поиск ------------------------------------------------------------
    def scores(self, query_terms: list[str]) -> dict[int, float]:
        """Баллы BM25 всех документов, где есть хотя бы один терм запроса."""
        result: dict[int, float] = {}
        if not self.n_docs:
            return result
        for term in dict.fromkeys(query_terms):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self.idf(term)
            for doc_id, tf in postings.items():
                norm = self.k1 * (1 - self.b + self.b * self.lengths[doc_id] / self.avgdl)
                result[doc_id] = result.get(doc_id, 0.0) + idf * tf * (self.k1 + 1) / (tf + norm)
        return result

    def search(self, query_terms: list[str], k: int | None = None) -> list[tuple[int, float]]:
        """Документы по убыванию балла: [(номер, балл), ...]."""
        scored = self.scores(query_terms)
        ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
        return ranked if k is None else ranked[:k]

    def coverage(self, query_terms: list[str], doc_id: int) -> float:
        """Доля веса запроса (сумма IDF), термы которого есть в документе.

        Используется для отказа: если у лучшего фрагмента покрытие низкое,
        вопрос, скорее всего, не про корпус. Термы, которых нет в корпусе,
        входят в знаменатель с максимальным IDF (df = 0): вопрос про «numpy»
        или «TCP» почти целиком состоит из неизвестных корпусу слов.
        """
        unique = list(dict.fromkeys(query_terms))
        total = sum(self.idf(t) for t in unique)
        if total == 0:
            return 0.0
        found = sum(self.idf(t) for t in unique if doc_id in self.postings.get(t, {}))
        return found / total

    # --- сохранение -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "k1": self.k1,
            "b": self.b,
            "lengths": self.lengths,
            "postings": {term: {str(d): tf for d, tf in p.items()} for term, p in self.postings.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BM25Index":
        index = cls(k1=data["k1"], b=data["b"])
        index.lengths = list(data["lengths"])
        index.postings = {term: {int(d): tf for d, tf in p.items()} for term, p in data["postings"].items()}
        index.avgdl = (sum(index.lengths) / len(index.lengths)) if index.lengths else 0.0
        return index
