"""Тесты поиска: токенизатор, собственный BM25, фрагменты, индекс."""

import json
import math
import re

import pytest

from search.bm25 import BM25Index
from search.chunker import chunk_document
from search.index import build_index, has_context, retrieve, retrieve_documents
from search.tokenizer import tokenize


# --- BM25: пример из занятия 3 ----------------------------------------------
def simple_tokens(text: str) -> list[str]:
    """Токены как на слайдах: нижний регистр, без пунктуации, без лемматизации."""
    return re.findall(r"\w+", text.lower())


LECTURE_DOCS = ["Возврат оплаты на карту.", "Статус оплаты в приложении.", "Возврат билета через кассу."]


def test_bm25_matches_manual_calculation_from_lecture():
    index = BM25Index(k1=1.2, b=0.75).fit([simple_tokens(d) for d in LECTURE_DOCS])
    assert index.avgdl == 4
    assert index.idf("возврат") == pytest.approx(math.log(1 + (3 - 2 + 0.5) / (2 + 0.5)))
    assert index.idf("возврат") == pytest.approx(0.470, abs=1e-3)

    ranked = index.search(simple_tokens("Как происходит возврат оплаты?"))
    assert [doc for doc, _ in ranked] == [0, 1, 2]  # A, затем B и C с равным баллом — по номеру
    scores = dict(ranked)
    assert scores[0] == pytest.approx(0.940, abs=1e-3)
    assert scores[1] == pytest.approx(0.470, abs=1e-3)
    assert scores[2] == pytest.approx(0.470, abs=1e-3)


def test_bm25_length_normalization_and_saturation():
    index = BM25Index(k1=1.2, b=0.75).fit([["граф"], ["граф", "граф"], ["граф", "вершина", "ребро", "путь"], ["матрица"]])
    scores = index.scores(["граф"])
    assert scores[1] > scores[0]            # больше вхождений — выше балл
    assert scores[1] < 2 * scores[0]        # но рост насыщается (k1)
    assert scores[0] > scores[2]            # длинный документ штрафуется (b)
    assert 3 not in scores                  # документ без терма не попадает в выдачу


def test_bm25_empty_and_unknown_query():
    index = BM25Index().fit([["граф"], ["матрица"]])
    assert index.search([]) == []
    assert index.search(["несуществующий"]) == []
    assert BM25Index().fit([]).search(["граф"]) == []


def test_bm25_roundtrip():
    index = BM25Index(k1=1.5, b=0.5).fit([simple_tokens(d) for d in LECTURE_DOCS])
    restored = BM25Index.from_dict(json.loads(json.dumps(index.to_dict())))
    query = simple_tokens("возврат оплаты")
    assert restored.search(query) == index.search(query)


def test_coverage_counts_unknown_terms():
    index = BM25Index().fit([["установить", "программа"], ["граф"]])
    assert index.coverage(["установить", "программа"], 0) == pytest.approx(1.0)
    partial = index.coverage(["установить", "numpy", "python"], 0)
    assert 0 < partial < 0.5


# --- токенизатор ----------------------------------------------------------------
def test_tokenizer_lemmatizes_and_removes_stopwords():
    assert tokenize("Пределы и предела последовательностей") == ["предел", "предел", "последовательность"]
    assert "на" not in tokenize("Возврат оплаты на карту")


def test_tokenizer_keeps_codes_and_numbers():
    tokens = tokenize("Требования ГОСТ 7.32 к отчёту по ЛР3, вариант 2")
    assert "7.32" in tokens and "лр3" in tokens and "2" in tokens
    assert "гост" in tokens and "отчет" in tokens  # ё → е


def test_tokenizer_same_for_query_and_document():
    assert tokenize("Указатели в языке Си") == tokenize("указатель в язык си")


def test_tokenizer_without_lemmatization():
    assert tokenize("Пределы функций", lemmatize=False) == ["пределы", "функций"]


# --- фрагменты --------------------------------------------------------------
def test_chunker_keeps_pages_and_merges_short_slides():
    pages = [(1, "а" * 100), (2, "б" * 250), (3, "в" * 2500), (4, "г" * 50)]
    chunks = chunk_document("D01", pages, size=1000, min_size=300)
    assert all(c.text.strip() for c in chunks)
    assert chunks[0].page == 1 and chunks[0].page_end == 2      # слайды 1–2 склеены
    assert {c.page for c in chunks if c.text.startswith("в")} == {3}
    assert sum(1 for c in chunks if c.page == 3) >= 2           # длинная страница разрезана
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert ids == [c.chunk_id for c in chunk_document("D01", pages, size=1000, min_size=300)]  # стабильны


# --- индекс на маленьком корпусе ------------------------------------------------
@pytest.fixture()
def tiny_index(tmp_path):
    docs = {
        "D01": ("Лекции по матанализу", ["Число a называется пределом последовательности, если для любого ε найдётся номер N."]),
        "D02": ("Методичка по графикам", ["Наклонная асимптота графика функции y = kx + b существует, если есть пределы k и b."]),
        "D03": ("Лекции по языку Си", ["Указатель хранит адрес переменной. Адрес получают операцией &."]),
    }
    manifest = {"corpus_version": "test", "documents": []}
    processed = tmp_path / "processed"
    processed.mkdir()
    for doc_id, (title, pages) in docs.items():
        manifest["documents"].append({"doc_id": doc_id, "title": title, "discipline": "Тест", "doc_type": "lecture"})
        with (processed / f"{doc_id}.jsonl").open("w", encoding="utf-8") as handle:
            for number, text in enumerate(pages, 1):
                handle.write(json.dumps({"doc_id": doc_id, "page": number, "text": text}, ensure_ascii=False) + "\n")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return build_index(manifest_path, processed)


def test_retrieve_returns_hits_with_metadata(tiny_index):
    hits = retrieve(tiny_index, "Что такое предел последовательности?", k=2)
    assert hits[0].doc_id == "D01"
    assert hits[0].title == "Лекции по матанализу" and hits[0].page == 1
    assert hits[0].source() == "Лекции по матанализу, стр. 1"
    assert hits == retrieve(tiny_index, "Что такое предел последовательности?", k=2)  # детерминизм


def test_retrieve_empty_and_no_match(tiny_index):
    assert retrieve(tiny_index, "", k=5) == []
    assert retrieve(tiny_index, "и в на", k=5) == []          # только стоп-слова
    assert retrieve(tiny_index, "квантовая хромодинамика", k=5) == []


def test_retrieve_documents_unique(tiny_index):
    docs = [h.doc_id for h in retrieve_documents(tiny_index, "адрес указателя и предел", k=5)]
    assert len(docs) == len(set(docs))


def test_has_context(tiny_index):
    assert has_context(retrieve(tiny_index, "адрес указателя", k=3))
    assert not has_context(retrieve(tiny_index, "как установить numpy для python через pip", k=3))
    assert not has_context([])
