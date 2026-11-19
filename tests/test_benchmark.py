"""Тесты benchmark: метрики, автопроверка ответа, разметка вопросов, прогон."""

import json

import pytest

from benchmark.run import (
    QUESTIONS_PATH,
    check_answer,
    compute_metrics,
    load_questions,
    reciprocal_rank,
    recall_at_k,
    run_benchmark,
)
from search import config
from search.index import build_index


# --- метрики: примеры из занятия 3 -------------------------------------------------
def test_recall_at_k_lecture_example():
    # эталон A, D, F; поиск вернул B, A, D → нашли 2 из 3
    assert recall_at_k(["A", "D", "F"], ["B", "A", "D"], 3) == pytest.approx(2 / 3)
    assert recall_at_k(["A"], ["B", "C", "A"], 2) == 0


def test_reciprocal_rank_and_mrr_lecture_example():
    assert reciprocal_rank(["A", "D", "F"], ["B", "A", "D"], 3) == 0.5
    assert reciprocal_rank(["A"], ["A", "B"], 3) == 1.0
    assert reciprocal_rank(["A"], ["B", "C", "A"], 2) == 0  # нет в top-k → 0
    rows = [
        {"type": "normal", "recall": 1, "reciprocal_rank": 0.5, "correct": True},
        {"type": "normal", "recall": 1, "reciprocal_rank": 1.0, "correct": False},
        {"type": "trap", "correct": True},
    ]
    metrics = compute_metrics(rows, "full")
    assert metrics["mrr_at_k"] == 0.75
    assert metrics["accuracy"] == 0.5
    assert metrics["correct_rejection_rate"] == 1.0


# --- автопроверка ответа ---------------------------------------------------------
QUESTION = {"type": "normal", "key_facts": ["непрерывн", "дифференцируем", "f(b)|приращени"]}
TRAP = {"type": "trap", "key_facts": []}


def test_check_answer_requires_all_key_facts():
    ok, missing = check_answer(QUESTION, "Если f непрерывна на [a,b] и дифференцируема на (a,b), то f(b) − f(a) = f'(c)(b − a).", "ok")
    assert ok and missing == []
    ok, missing = check_answer(QUESTION, "Функция должна быть непрерывной.", "ok")
    assert not ok and "дифференцируем" in missing


def test_check_answer_matches_by_lemmas():
    question = {"type": "normal", "key_facts": ["двоичный код"]}
    assert check_answer(question, "Данные хранятся в двоичных кодах.", "ok")[0]


def test_check_answer_refusals():
    assert check_answer(TRAP, "В документах нет этой информации.", "ok")[0]
    assert check_answer(TRAP, "...", "no_context")[0]
    assert not check_answer(TRAP, "Консультация в среду в 10:00.", "ok")[0]
    assert not check_answer(QUESTION, "В документах нет этой информации.", "no_context")[0]


# --- разметка вопросов ------------------------------------------------------------
def test_real_questions_are_valid():
    manifest = json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    doc_ids = {d["doc_id"] for d in manifest["documents"]}
    questions = load_questions(QUESTIONS_PATH, doc_ids)
    normal = [q for q in questions if q["type"] == "normal"]
    traps = [q for q in questions if q["type"] == "trap"]
    assert len(doc_ids) == 30
    assert len(normal) == 10 and len(traps) == 5
    assert all(len(q["relevant_doc_ids"]) >= 3 for q in normal)
    assert len({q["id"] for q in questions}) == 15
    assert len({q["discipline"] for q in normal}) >= 4  # вопросы покрывают разные дисциплины


def test_load_questions_rejects_bad_markup(tmp_path):
    path = tmp_path / "q.jsonl"
    path.write_text(json.dumps({"id": "Q1", "type": "normal", "query": "?", "relevant_doc_ids": ["D01"],
                                "reference_answer": "", "key_facts": []}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_questions(path)


# --- прогон на реальном корпусе ----------------------------------------------------
@pytest.fixture(scope="module")
def real_index():
    return build_index()


def test_retrieval_benchmark_on_real_corpus(real_index):
    result = run_benchmark(k=5, mode="retrieval", index=real_index, save=False)
    metrics = result["metrics"]
    assert result["progress"] == {"done": 15, "total": 15}
    assert metrics["accuracy"] is None
    assert metrics["recall_at_k"] >= 0.8      # регрессия поиска
    assert metrics["mrr_at_k"] >= 0.8
    assert metrics["correct_rejection_rate"] >= 0.8


def test_full_benchmark_with_stub_llm(real_index):
    """Режим full с заглушкой LLM: отвечает эталоном, на ловушках отказывается."""
    questions = {q["query"]: q for q in load_questions()}
    calls = []

    def stub_answer(question, k):
        calls.append(question)
        q = questions[question]
        if q["type"] == "trap":
            return {"text": "В документах нет этой информации.", "finish_reason": "no_context", "sources": []}
        return {"text": q["reference_answer"], "finish_reason": "ok", "sources": ["x"], "model": "stub"}

    progress = []
    result = run_benchmark(k=5, mode="full", answer_fn=stub_answer, index=real_index, save=False,
                           on_progress=lambda done, total, row: progress.append(done))
    assert len(calls) == 15 and progress == list(range(1, 16))
    assert result["metrics"]["accuracy"] == 1.0          # эталонные ответы проходят автопроверку
    assert result["metrics"]["correct_rejection_rate"] == 1.0
    assert result["params"]["model"] == "stub"


def test_full_benchmark_survives_llm_errors(real_index):
    def broken(question, k):
        raise ConnectionError("ollama недоступна")

    result = run_benchmark(k=5, mode="full", answer_fn=broken, index=real_index, save=False)
    assert result["status"] == "done"
    assert result["metrics"]["accuracy"] == 0.0
    assert all(r["error_stage"] in ("ошибка вызова LLM", "ответ на ловушку") for r in result["questions"])
