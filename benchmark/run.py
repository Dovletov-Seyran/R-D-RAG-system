"""Benchmark RAG-системы: прогон вопросов в рантайме и 4 метрики.

Режимы:
  retrieval — только поиск BM25: Recall@k и MRR@k по обычным вопросам,
              Correct Rejection Rate по ловушкам через порог отказа поиска.
              Без LLM, отрабатывает за секунды.
  full      — поиск + ответ LLM: дополнительно Accuracy ответов, а отказ на
              ловушках определяется по ответу системы (finish_reason / текст).

Ответ в режиме full берётся:
  --api URL  → POST URL/api/chat запущенного backend;
  иначе      → функция backend.app.rag.answer (контракт C4 из docs/checkpoint-2.md).

Примеры:
    python -m benchmark.run                      # retrieval, k = 5
    python -m benchmark.run --mode full          # нужен backend и Ollama
    python -m benchmark.run --mode full --api http://localhost:8000

Из кода (контракт C3):
    from benchmark.run import run_benchmark
    result = run_benchmark(k=5, mode="full", answer_fn=answer, on_progress=callback)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from search import config
from search.index import SearchIndex, has_context, load_index, retrieve, retrieve_documents
from search.tokenizer import tokenize

BENCH_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = BENCH_DIR / "questions.jsonl"
RESULTS_DIR = BENCH_DIR / "results"

REFUSAL_PATTERNS = re.compile(
    r"нет (этой|такой|нужной|подходящей)?\s*информации|нет сведений|не (содержится|найден[аоы]?|удалось найти)|"
    r"в (документах|материалах|источниках|фрагментах) (нет|не)",
    re.IGNORECASE,
)

AnswerFn = Callable[[str, int], Any]
ProgressFn = Callable[[int, int, dict], None]


# --- данные ---------------------------------------------------------------
def load_questions(path: Path = QUESTIONS_PATH, known_docs: set[str] | None = None) -> list[dict]:
    """Читает вопросы и проверяет разметку: у обычного вопроса ≥ 3 релевантных документа."""
    questions = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").split("\n"), 1):
        if not line.strip():
            continue
        q = json.loads(line)
        if q["type"] not in ("normal", "trap"):
            raise ValueError(f"строка {number}: type должен быть normal или trap")
        if q["type"] == "normal" and len(q["relevant_doc_ids"]) < 3:
            raise ValueError(f"{q['id']}: у обычного вопроса должно быть не меньше 3 релевантных документов")
        if q["type"] == "trap" and q["relevant_doc_ids"]:
            raise ValueError(f"{q['id']}: у ловушки не должно быть релевантных документов")
        if known_docs is not None:
            unknown = set(q["relevant_doc_ids"]) - known_docs
            if unknown:
                raise ValueError(f"{q['id']}: нет таких документов в корпусе: {sorted(unknown)}")
        questions.append(q)
    return questions


# --- метрики ---------------------------------------------------------------
def recall_at_k(relevant: list[str], retrieved: list[str], k: int) -> float:
    """|R ∩ Top_k| / |R|."""
    if not relevant:
        return 0.0
    return len(set(relevant) & set(retrieved[:k])) / len(set(relevant))


def reciprocal_rank(relevant: list[str], retrieved: list[str], k: int) -> float:
    """1 / позиция первого релевантного документа в top-k; 0, если его нет."""
    for position, doc_id in enumerate(retrieved[:k], 1):
        if doc_id in relevant:
            return 1.0 / position
    return 0.0


def is_refusal(text: str, finish_reason: str | None) -> bool:
    return finish_reason == "no_context" or bool(REFUSAL_PATTERNS.search(text or ""))


def _fact_found(fact: str, answer_lower: str, answer_lemmas: set[str]) -> bool:
    for alternative in fact.split("|"):
        alternative = alternative.strip()
        if not alternative:
            continue
        if alternative.lower() in answer_lower:
            return True
        lemmas = tokenize(alternative)
        if lemmas and all(lemma in answer_lemmas for lemma in lemmas):
            return True
    return False


def check_answer(question: dict, text: str, finish_reason: str | None) -> tuple[bool, list[str]]:
    """Автопроверка ответа.

    Обычный вопрос: верно, если система не отказалась и в ответе есть все ключевые
    факты (каждый факт — варианты через «|», сравнение подстрокой или по леммам).
    Ловушка: верно, если система отказалась.
    Возвращает (верно, список ненайденных фактов).
    """
    refused = is_refusal(text, finish_reason)
    if question["type"] == "trap":
        return refused, []
    if refused:
        return False, list(question.get("key_facts", []))
    lower = (text or "").lower().replace("ё", "е")
    lemmas = set(tokenize(text or ""))
    missing = [fact for fact in question.get("key_facts", []) if not _fact_found(fact.replace("ё", "е"), lower, lemmas)]
    return not missing, missing


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# --- ответ через API backend -----------------------------------------------
def api_answer_fn(base_url: str, timeout: float = 300.0) -> AnswerFn:
    url = base_url.rstrip("/") + "/api/chat"

    def answer(question: str, k: int) -> dict:
        body = json.dumps({"message": question, "history": []}).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    return answer


def default_answer_fn() -> AnswerFn:
    try:
        from backend.app.rag import answer  # контракт C4, реализация — backend
    except ImportError as error:
        raise RuntimeError(
            "Режим full: не найдена функция backend.app.rag.answer. Запустите backend и укажите "
            "--api http://localhost:8000 или используйте --mode retrieval."
        ) from error

    return lambda question, k: answer(question, history=[], k=k)


# --- прогон ------------------------------------------------------------------
def _commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=BENCH_DIR, capture_output=True, text=True, timeout=5
        ).stdout.strip() or None
    except Exception:
        return None


def run_benchmark(
    k: int = config.TOP_K,
    mode: str = "retrieval",
    answer_fn: AnswerFn | None = None,
    on_progress: ProgressFn | None = None,
    index: SearchIndex | None = None,
    questions_path: Path = QUESTIONS_PATH,
    model: str | None = None,
    save: bool = True,
) -> dict:
    """Прогоняет все вопросы и возвращает результат в формате контракта C3."""
    if mode not in ("retrieval", "full"):
        raise ValueError("mode: retrieval или full")
    started_at = datetime.now()
    started = time.perf_counter()
    index = index or load_index()
    questions = load_questions(questions_path, set(index.documents))
    if mode == "full" and answer_fn is None:
        answer_fn = default_answer_fn()

    rows: list[dict] = []
    for number, q in enumerate(questions, 1):
        t0 = time.perf_counter()
        doc_hits = retrieve_documents(index, q["query"], k)
        chunk_hits = retrieve(index, q["query"], k)
        retrieved = [h.doc_id for h in doc_hits]
        row: dict[str, Any] = {
            "id": q["id"],
            "type": q["type"],
            "discipline": q.get("discipline"),
            "query": q["query"],
            "relevant_doc_ids": q["relevant_doc_ids"],
            "retrieved_doc_ids": retrieved,
            "retrieved": [
                {"doc_id": h.doc_id, "title": h.title, "page": h.page, "score": h.score, "relevant": h.doc_id in q["relevant_doc_ids"]}
                for h in doc_hits
            ],
            "top_coverage": max((h.coverage for h in chunk_hits), default=0.0),
            "search_has_context": has_context(chunk_hits),
            "reference_answer": q["reference_answer"],
        }
        if q["type"] == "normal":
            row["recall"] = round(recall_at_k(q["relevant_doc_ids"], retrieved, k), 4)
            row["reciprocal_rank"] = round(reciprocal_rank(q["relevant_doc_ids"], retrieved, k), 4)

        if mode == "full":
            try:
                reply = answer_fn(q["query"], k)
                row["answer"] = _get(reply, "text", "")
                row["finish_reason"] = _get(reply, "finish_reason")
                row["sources"] = list(_get(reply, "sources", []) or [])
                model = model or _get(reply, "model")
                row["correct"], row["missing_facts"] = check_answer(q, row["answer"], row["finish_reason"])
            except Exception as error:  # ошибка одного вопроса не останавливает прогон
                row.update(answer="", finish_reason="error", sources=[], correct=False, missing_facts=[], error=str(error))
        else:
            # без LLM ловушка «отклонена», если поиск не нашёл достаточного контекста
            if q["type"] == "trap":
                row["correct"] = not row["search_has_context"]
        row["error_stage"] = _error_stage(row, mode)
        row["time_s"] = round(time.perf_counter() - t0, 2)
        rows.append(row)
        if on_progress:
            on_progress(number, len(questions), row)

    result = {
        "run_id": started_at.strftime("%Y-%m-%dT%H-%M-%S"),
        "status": "done",
        "progress": {"done": len(rows), "total": len(questions)},
        "params": {
            "k": k,
            "mode": mode,
            "model": model if mode == "full" else None,
            "corpus_version": index.settings.get("corpus_version"),
            "commit": _commit(),
            "index": {key: index.settings.get(key) for key in ("k1", "b", "chunk_chars", "add_title", "lemmatize", "remove_stopwords")},
            "no_context_min_coverage": config.NO_CONTEXT_MIN_COVERAGE,
            "documents": len(index.documents),
            "chunks": len(index.chunks),
        },
        "metrics": compute_metrics(rows, mode),
        "questions": rows,
        "duration_s": round(time.perf_counter() - started, 2),
    }
    if save:
        result["saved_to"] = [str(p.relative_to(config.ROOT)) for p in save_result(result)]
    return result


def _error_stage(row: dict, mode: str) -> str | None:
    """Где потеряли информацию (по схеме занятия 3): поиск, ответ или ловушка."""
    if row["type"] == "trap":
        if row.get("correct"):
            return None
        return "ответ на ловушку" if mode == "full" else "поиск: нет отказа по порогу"
    if row["recall"] == 0:
        return "поиск: релевантных нет в top-k"
    if mode == "full" and not row.get("correct"):
        if row.get("finish_reason") == "error":
            return "ошибка вызова LLM"
        if is_refusal(row.get("answer", ""), row.get("finish_reason")):
            return "ответ: ложный отказ"
        return "ответ: нет ключевых фактов"
    if row["recall"] < 1:
        return "поиск: найдены не все релевантные"
    return None


def compute_metrics(rows: list[dict], mode: str) -> dict:
    normal = [r for r in rows if r["type"] == "normal"]
    traps = [r for r in rows if r["type"] == "trap"]

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    return {
        "recall_at_k": mean([r["recall"] for r in normal]),
        "mrr_at_k": mean([r["reciprocal_rank"] for r in normal]),
        "accuracy": mean([1.0 if r.get("correct") else 0.0 for r in normal]) if mode == "full" else None,
        "correct_rejection_rate": mean([1.0 if r.get("correct") else 0.0 for r in traps]),
        "normal_questions": len(normal),
        "trap_questions": len(traps),
    }


# --- отчёт --------------------------------------------------------------------
def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def to_markdown(result: dict) -> str:
    p, m = result["params"], result["metrics"]
    lines = [
        f"# Benchmark {result['run_id']}",
        "",
        f"Режим `{p['mode']}`, k = {p['k']}, модель: {p['model'] or '—'}, корпус {p['corpus_version']} "
        f"({p['documents']} документов, {p['chunks']} фрагментов), commit {p['commit'] or '—'}, "
        f"время {result['duration_s']} с.",
        "",
        "| Метрика | Значение | На каких вопросах |",
        "| --- | --- | --- |",
        f"| Recall@{p['k']} | {_fmt(m['recall_at_k'])} | {m['normal_questions']} обычных |",
        f"| MRR@{p['k']} | {_fmt(m['mrr_at_k'])} | {m['normal_questions']} обычных |",
        f"| Accuracy | {_fmt(m['accuracy'])} | {m['normal_questions']} обычных{'' if p['mode'] == 'full' else ' (только в режиме full)'} |",
        f"| Correct Rejection Rate | {_fmt(m['correct_rejection_rate'])} | {m['trap_questions']} ловушек"
        f"{'' if p['mode'] == 'full' else ' (по порогу поиска)'} |",
        "",
        "## По вопросам",
        "",
        "| ID | Вопрос | Релевантные | Найдено (top-k) | Recall | RR | Итог | Где ошибка |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in result["questions"]:
        found = ", ".join(f"**{d}**" if d in r["relevant_doc_ids"] else d for d in r["retrieved_doc_ids"])
        verdict = "✓" if r.get("correct") else ("✗" if "correct" in r else "")
        lines.append(
            f"| {r['id']} | {r['query']} | {', '.join(r['relevant_doc_ids']) or '—'} | {found} | "
            f"{_fmt(r.get('recall'))} | {_fmt(r.get('reciprocal_rank'))} | {verdict} | {r['error_stage'] or ''} |"
        )
    if p["mode"] == "full":
        lines += ["", "## Ответы", ""]
        for r in result["questions"]:
            lines += [f"**{r['id']}. {r['query']}**", "", f"Ответ ({r.get('finish_reason')}): {r.get('answer', '')}", ""]
            if r.get("missing_facts"):
                lines += [f"Не найдены ключевые факты: {', '.join(r['missing_facts'])}", ""]
            lines += [f"Эталон: {r['reference_answer']}", ""]
    return "\n".join(lines) + "\n"


def save_result(result: dict) -> list[Path]:
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = RESULTS_DIR / f"{result['run_id']}_{result['params']['mode']}"
    json_path, md_path = stem.with_suffix(".json"), stem.with_suffix(".md")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(result), encoding="utf-8")
    return [json_path, md_path]


def print_report(result: dict) -> None:
    p, m = result["params"], result["metrics"]
    print()
    print(f"{'ID':4} {'Recall':>6} {'RR':>5} {'Итог':>4}  Найдено (* — релевантный)")
    for r in result["questions"]:
        found = " ".join(f"{d}*" if d in r["relevant_doc_ids"] else d for d in r["retrieved_doc_ids"])
        verdict = "✓" if r.get("correct") else ("✗" if "correct" in r else "")
        print(f"{r['id']:4} {_fmt(r.get('recall')):>6} {_fmt(r.get('reciprocal_rank')):>5} {verdict:>4}  {found}"
              + (f"   [{r['error_stage']}]" if r["error_stage"] else ""))
    print()
    print(f"Режим {p['mode']}, k = {p['k']}, модель {p['model'] or '—'}, {result['duration_s']} с")
    print(f"  Recall@{p['k']}:               {_fmt(m['recall_at_k'])}")
    print(f"  MRR@{p['k']}:                  {_fmt(m['mrr_at_k'])}")
    print(f"  Accuracy:               {_fmt(m['accuracy'])}")
    print(f"  Correct Rejection Rate: {_fmt(m['correct_rejection_rate'])}")
    if result.get("saved_to"):
        print("Сохранено: " + ", ".join(result["saved_to"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark RAG-системы (запуск в рантайме)")
    parser.add_argument("--mode", choices=["retrieval", "full"], default="retrieval")
    parser.add_argument("--k", type=int, default=config.TOP_K)
    parser.add_argument("--api", help="адрес backend для режима full, например http://localhost:8000")
    parser.add_argument("--model", help="подпись модели в отчёте")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    parser.add_argument("--no-save", action="store_true", help="не сохранять результат в benchmark/results")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    def progress(done: int, total: int, row: dict) -> None:
        print(f"[{done:2}/{total}] {row['id']} {row['time_s']:5.1f} с  {row['query'][:70]}", flush=True)

    answer_fn = api_answer_fn(args.api) if args.api else None
    try:
        result = run_benchmark(
            k=args.k, mode=args.mode, answer_fn=answer_fn, on_progress=progress,
            questions_path=args.questions, model=args.model, save=not args.no_save,
        )
    except (RuntimeError, FileNotFoundError, ValueError, urllib.error.URLError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    print_report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
