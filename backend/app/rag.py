"""Ответ RAG — контракт C4 из docs/checkpoint-2.md.

    from backend.app.rag import answer
    a = answer("Как найти предел функции?", history=[], k=5)
    # a.text, a.sources, a.finish_reason ("ok" | "no_context"), a.hits, a.model

Путь вопроса: BM25 (search) → проверка контекста → prompt с фрагментами → LLM → проверка отказа.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from backend.app import config, llm
from search import config as search_config
from search.index import Hit, SearchIndex, has_context, load_index, retrieve

SYSTEM_PROMPT = f"""Ты — учебный ассистент кафедры ИУ-5 МГТУ им. Н. Э. Баумана. Отвечаешь студентам 1 курса по учебным материалам.

Правила:
1. Отвечай только по приведённым фрагментам документов. Не добавляй сведений, которых во фрагментах нет.
2. Если во фрагментах нет ответа на вопрос, ответь ровно: «{config.NO_CONTEXT_TEXT}» — и больше ничего.
3. Отвечай на русском языке, кратко и по существу: определение, формулировка или алгоритм.
4. После утверждений указывай номер фрагмента в квадратных скобках, например [1] или [2].
5. Не решай за студента домашние задания и варианты контрольных — объясняй теорию и порядок решения.
6. Формулы пиши обычным текстом с символами Unicode (ε, δ, ∞, →, ≤, √, x²), без LaTeX и знаков $ — ответ показывается как простой текст."""

REFUSAL = re.compile(r"в\s+документах\s+нет\s+(этой\s+)?информации", re.IGNORECASE)
CITATION = re.compile(r"\[(\d+)\]")
CITATION_ONLY_LINE = re.compile(r"^[\s\[\]\d,]*$")


@dataclass
class Answer:
    text: str
    sources: list[str]
    finish_reason: str                 # "ok" | "no_context"
    hits: list[Hit] = field(default_factory=list)
    model: str | None = None


# --- индекс: загружается один раз --------------------------------------------
_index: SearchIndex | None = None
_index_lock = threading.Lock()


def get_index() -> SearchIndex:
    """Индекс BM25 из search/index/bm25.json; FileNotFoundError, если не собран (python -m search.build)."""
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = load_index()
    return _index


def set_index(index: SearchIndex | None) -> None:
    """Подменить индекс (тесты, повторная загрузка)."""
    global _index
    _index = index


# --- поиск -----------------------------------------------------------------
def _last_user_question(history: list[dict]) -> str | None:
    for message in reversed(history):
        if message.get("role") == "user" and (message.get("text") or "").strip():
            return message["text"].strip()
    return None


def search(question: str, history: list[dict], k: int, index: SearchIndex) -> list[Hit]:
    """Поиск по вопросу; для уточнения («а что потом?») — вместе с прошлым вопросом пользователя.

    Уточнение коротко и само по себе не проходит порог покрытия. Если прошлый вопрос был
    по корпусу, ищем по обоим вопросам и считаем контекст найденным; есть ли в нём ответ,
    решает LLM (второй уровень отказа).
    """
    hits = retrieve(index, question, k)
    if has_context(hits):
        return hits
    previous = _last_user_question(history)
    if previous and previous != question and has_context(retrieve(index, previous, k)):
        combined = retrieve(index, f"{previous} {question}", k)
        for hit in combined:
            hit.coverage = max(hit.coverage, search_config.NO_CONTEXT_MIN_COVERAGE)
        return combined
    return hits


# --- prompt ------------------------------------------------------------------
def build_messages(question: str, hits: list[Hit], history: list[dict]) -> list[dict]:
    fragments = "\n\n".join(
        f"[{number}] {hit.source()}\n{hit.text[: config.FRAGMENT_MAX_CHARS]}" for number, hit in enumerate(hits, 1)
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for message in history[-config.HISTORY_MESSAGES :]:
        role = "assistant" if message.get("role") == "assistant" else "user"
        text = (message.get("text") or "").strip()
        if text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": f"Фрагменты документов:\n\n{fragments}\n\nВопрос: {question}"})
    return messages


def collect_sources(text: str, hits: list[Hit]) -> list[str]:
    """Источники из metadata фрагментов: те, на которые сослалась модель, иначе все переданные."""
    cited = [int(n) for n in CITATION.findall(text)]
    chosen = [hits[n - 1] for n in dict.fromkeys(cited) if 1 <= n <= len(hits)] or hits
    return list(dict.fromkeys(hit.source() for hit in chosen))


# --- ответ -------------------------------------------------------------------
def answer(
    question: str,
    history: list[dict] | None = None,
    k: int = search_config.TOP_K,
    index: SearchIndex | None = None,
) -> Answer:
    """Ответ на вопрос по корпусу. LLMUnavailable — если Ollama недоступна."""
    history = history or []
    index = index or get_index()
    hits = search(question, history, k, index)

    # отказ без вызова LLM: поиск не нашёл фрагмента, достаточно покрывающего вопрос
    if not has_context(hits):
        return Answer(config.NO_CONTEXT_TEXT, [], "no_context", hits, None)

    text = llm.chat(build_messages(question, hits, history))
    # модель иногда дописывает в конце строку из одних ссылок «[3]» — убираем её
    lines = text.splitlines()
    while lines and CITATION_ONLY_LINE.match(lines[-1]):
        lines.pop()
    text = "\n".join(lines).strip()
    if not text or REFUSAL.search(text):
        return Answer(config.NO_CONTEXT_TEXT, [], "no_context", hits, config.OLLAMA_MODEL)
    return Answer(text, collect_sources(text, hits), "ok", hits, config.OLLAMA_MODEL)
