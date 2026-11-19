"""Сборка, загрузка индекса и поиск — контракт C1 из docs/checkpoint-2.md."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from search import config
from search.bm25 import BM25Index
from search.chunker import chunk_document
from search.tokenizer import tokenize


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    title: str
    discipline: str
    page: int
    score: float
    text: str
    page_end: int = 0
    coverage: float = 0.0

    def source(self) -> str:
        """Строка источника для ответа: «Название, стр. N»."""
        pages = f"стр. {self.page}" if self.page_end in (0, self.page) else f"стр. {self.page}–{self.page_end}"
        return f"{self.title}, {pages}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchIndex:
    bm25: BM25Index
    chunks: list[dict]
    documents: dict[str, dict]
    settings: dict = field(default_factory=dict)

    def tokenize(self, text: str) -> list[str]:
        return tokenize(text, self.settings.get("lemmatize", True), self.settings.get("remove_stopwords", True))


def build_index(
    manifest_path: Path = config.MANIFEST_PATH,
    processed_dir: Path = config.PROCESSED_DIR,
    *,
    k1: float = config.K1,
    b: float = config.B,
    chunk_chars: int = config.CHUNK_CHARS,
    chunk_min_chars: int = config.CHUNK_MIN_CHARS,
    add_title: bool = config.ADD_TITLE,
    lemmatize: bool = config.LEMMATIZE,
    remove_stopwords: bool = config.REMOVE_STOPWORDS,
) -> SearchIndex:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    documents = {d["doc_id"]: d for d in manifest["documents"]}
    chunks: list[dict] = []
    for doc_id, doc in documents.items():
        path = Path(processed_dir) / f"{doc_id}.jsonl"
        pages = []
        # split("\n"), а не splitlines(): в тексте бывают U+2028 и другие разделители
        for line in path.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                row = json.loads(line)
                pages.append((row["page"], row["text"]))
        for chunk in chunk_document(doc_id, pages, chunk_chars, chunk_min_chars):
            chunks.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": doc_id,
                    "page": chunk.page,
                    "page_end": chunk.page_end,
                    "text": chunk.text,
                }
            )

    settings = {
        "corpus_version": manifest.get("corpus_version"),
        "k1": k1,
        "b": b,
        "chunk_chars": chunk_chars,
        "chunk_min_chars": chunk_min_chars,
        "add_title": add_title,
        "lemmatize": lemmatize,
        "remove_stopwords": remove_stopwords,
    }
    tokenized = []
    for chunk in chunks:
        title = documents[chunk["doc_id"]]["title"]
        text = f"{title}\n{chunk['text']}" if add_title else chunk["text"]
        tokenized.append(tokenize(text, lemmatize, remove_stopwords))
    bm25 = BM25Index(k1=k1, b=b).fit(tokenized)
    return SearchIndex(bm25=bm25, chunks=chunks, documents=documents, settings=settings)


def save_index(index: SearchIndex, path: Path = config.INDEX_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "settings": index.settings,
        "documents": index.documents,
        "chunks": index.chunks,
        "bm25": index.bm25.to_dict(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def load_index(path: Path | str = config.INDEX_PATH) -> SearchIndex:
    path = Path(path)
    if path.is_dir():
        path = path / "bm25.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return SearchIndex(
        bm25=BM25Index.from_dict(data["bm25"]),
        chunks=data["chunks"],
        documents=data["documents"],
        settings=data["settings"],
    )


def _hit(index: SearchIndex, number: int, score: float, terms: list[str]) -> Hit:
    chunk = index.chunks[number]
    doc = index.documents[chunk["doc_id"]]
    return Hit(
        chunk_id=chunk["chunk_id"],
        doc_id=chunk["doc_id"],
        title=doc["title"],
        discipline=doc.get("discipline", ""),
        page=chunk["page"],
        page_end=chunk.get("page_end", chunk["page"]),
        score=round(score, 4),
        text=chunk["text"],
        coverage=round(index.bm25.coverage(terms, number), 4),
    )


def retrieve(index: SearchIndex, query: str, k: int = config.TOP_K) -> list[Hit]:
    """Top-k фрагментов по убыванию BM25. Пустой запрос → пустой список."""
    terms = index.tokenize(query)
    if not terms:
        return []
    return [_hit(index, number, score, terms) for number, score in index.bm25.search(terms, k)]


def retrieve_documents(index: SearchIndex, query: str, k: int = config.TOP_K) -> list[Hit]:
    """Top-k различных документов: документ занимает позицию своего лучшего фрагмента.

    Используется для метрик benchmark (эталоны размечены на уровне документов).
    """
    terms = index.tokenize(query)
    if not terms:
        return []
    seen: set[str] = set()
    result: list[Hit] = []
    for number, score in index.bm25.search(terms):
        doc_id = index.chunks[number]["doc_id"]
        if doc_id in seen:
            continue
        seen.add(doc_id)
        result.append(_hit(index, number, score, terms))
        if len(result) == k:
            break
    return result


def has_context(hits: list[Hit], min_coverage: float = config.NO_CONTEXT_MIN_COVERAGE) -> bool:
    """Есть ли в выдаче фрагмент, по которому можно отвечать (иначе — отказ no_context)."""
    return bool(hits) and max(h.coverage for h in hits) >= min_coverage
