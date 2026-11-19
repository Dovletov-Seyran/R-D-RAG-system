"""Тесты backend: answer() и HTTP API. LLM подменяется заглушкой, индекс — маленький корпус в tmp."""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import config, llm, main, rag
from backend.app.llm import LLMUnavailable
from search.index import build_index

DOCS = {
    "D01": ("Лекции по информатике", [
        (1, "Дополнительный код отрицательного числа получают так: инвертируют все разряды прямого кода "
            "модуля числа и прибавляют единицу к младшему разряду."),
        (2, "Системы счисления бывают позиционные и непозиционные. В позиционной системе значение цифры "
            "зависит от её позиции в записи числа."),
    ]),
    "D02": ("Лекции по математическому анализу", [
        (5, "Предел функции в точке — число, к которому стремится значение функции, когда аргумент "
            "стремится к этой точке. Определение предела по Коши использует эпсилон и дельта."),
    ]),
}


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    processed = root / "processed"
    processed.mkdir()
    documents = []
    for doc_id, (title, pages) in DOCS.items():
        documents.append({"doc_id": doc_id, "title": title, "discipline": "Тест", "doc_type": "lecture"})
        rows = [json.dumps({"doc_id": doc_id, "page": page, "text": text}, ensure_ascii=False) for page, text in pages]
        (processed / f"{doc_id}.jsonl").write_text("\n".join(rows), encoding="utf-8")
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"corpus_version": "test", "documents": documents}, ensure_ascii=False), encoding="utf-8")
    return build_index(manifest, processed)


@pytest.fixture
def client(index, monkeypatch):
    rag.set_index(index)
    monkeypatch.setattr(llm, "status", lambda model=None: "available")
    yield TestClient(main.app)
    rag.set_index(None)


@pytest.fixture
def fake_llm(monkeypatch):
    """Заглушка Ollama: запоминает prompt и возвращает заданный текст."""
    calls = []

    def set_reply(text):
        def chat(messages, model=None):
            calls.append(messages)
            return text
        monkeypatch.setattr(llm, "chat", chat)
        return calls

    return set_reply


QUESTION = "Как получить дополнительный код отрицательного числа?"


# --- answer() --------------------------------------------------------------
def test_answer_uses_fragments_and_sources_from_metadata(index, fake_llm):
    calls = fake_llm("Нужно инвертировать разряды и прибавить единицу [1].")
    result = rag.answer(QUESTION, index=index)
    assert result.finish_reason == "ok"
    assert result.sources == [result.hits[0].source()]
    assert result.sources[0].startswith("Лекции по информатике, стр. 1")
    prompt = calls[0][-1]["content"]
    assert f"[1] {result.hits[0].source()}" in prompt
    assert prompt.endswith(f"Вопрос: {QUESTION}")


def test_answer_drops_trailing_citation_only_line(index, fake_llm):
    fake_llm("Прибавить единицу к обратному коду [1].\n\n[1]")
    result = rag.answer(QUESTION, index=index)
    assert result.text == "Прибавить единицу к обратному коду [1]."


def test_answer_without_citations_lists_all_fragments(index, fake_llm):
    fake_llm("Инвертировать разряды и прибавить единицу.")
    result = rag.answer(QUESTION, index=index)
    assert result.sources == list(dict.fromkeys(h.source() for h in result.hits))


def test_answer_refuses_without_llm_when_no_context(index, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("LLM не должна вызываться без контекста")

    monkeypatch.setattr(llm, "chat", fail)
    result = rag.answer("Во сколько консультация по физкультуре?", index=index)
    assert result.finish_reason == "no_context"
    assert result.text == config.NO_CONTEXT_TEXT
    assert result.sources == []


def test_answer_turns_llm_refusal_into_no_context(index, fake_llm):
    fake_llm("К сожалению, в документах нет этой информации.")
    result = rag.answer(QUESTION, index=index)
    assert (result.finish_reason, result.text, result.sources) == ("no_context", config.NO_CONTEXT_TEXT, [])


def test_follow_up_question_uses_previous_question(index, fake_llm):
    calls = fake_llm("Прибавить единицу [1].")
    history = [{"role": "user", "text": QUESTION}, {"role": "assistant", "text": "Инвертировать разряды."}]
    result = rag.answer("А что потом прибавляют?", history=history, index=index)
    assert result.finish_reason == "ok"
    assert result.hits[0].doc_id == "D01"
    assert [m["role"] for m in calls[0]] == ["system", "user", "assistant", "user"]


# --- /api/chat ---------------------------------------------------------------
def test_chat_returns_text_sources_finish_reason(client, fake_llm):
    fake_llm("Инвертировать разряды и прибавить единицу [1].")
    response = client.post("/api/chat", json={"message": QUESTION, "history": []})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"text", "sources", "finish_reason"}
    assert body["text"] == "Инвертировать разряды и прибавить единицу [1]."
    assert body["finish_reason"] == "ok"
    assert len(body["sources"]) == 1 and body["sources"][0].startswith("Лекции по информатике, стр. 1")


def test_follow_up_after_off_topic_question_still_refuses(index, monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **kw: pytest.fail("LLM не должна вызываться"))
    history = [{"role": "user", "text": "Во сколько консультация по физкультуре?"}]
    assert rag.answer("А в субботу?", history=history, index=index).finish_reason == "no_context"


def test_chat_accepts_frontend_history_format(client, fake_llm):
    fake_llm("Ответ [1].")
    history = [{"role": "user", "text": "Привет", "createdAt": 1760000000000}]
    assert client.post("/api/chat", json={"message": QUESTION, "history": history}).status_code == 200


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "   "}, {"message": "а" * 2001}, {}, {"message": 5}])
def test_chat_rejects_invalid_message(client, body):
    response = client.post("/api/chat", json=body)
    assert response.status_code == 400
    assert response.json()["error"] == "message_invalid"


def test_chat_returns_503_when_llm_unavailable(client, monkeypatch):
    def down(*args, **kwargs):
        raise LLMUnavailable("Ollama недоступна")

    monkeypatch.setattr(llm, "chat", down)
    response = client.post("/api/chat", json={"message": QUESTION})
    assert response.status_code == 503
    assert response.json()["error"] == "service_unavailable"


def test_chat_returns_503_without_index(client, monkeypatch):
    def missing():
        raise FileNotFoundError

    monkeypatch.setattr(rag, "get_index", missing)
    assert client.post("/api/chat", json={"message": QUESTION}).status_code == 503


def test_chat_returns_500_on_internal_error(index, monkeypatch):
    rag.set_index(index)

    def broken(*args, **kwargs):
        raise RuntimeError("сбой")

    monkeypatch.setattr(rag, "answer", broken)
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.post("/api/chat", json={"message": QUESTION})
    rag.set_index(None)
    assert (response.status_code, response.json()["error"]) == (500, "internal")


def test_cors_allows_only_frontend_origin(client, fake_llm):
    fake_llm("Ответ [1].")
    allowed = client.post("/api/chat", json={"message": QUESTION}, headers={"Origin": "http://localhost:8080"})
    other = client.post("/api/chat", json={"message": QUESTION}, headers={"Origin": "http://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:8080"
    assert "access-control-allow-origin" not in other.headers


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["index_loaded"] is True
    assert body["documents"] == 2
    assert body["llm"] == "available"


# --- benchmark через API ---------------------------------------------------------
def test_benchmark_run_status_and_conflict(client, monkeypatch):
    release = threading.Event()

    def fake_run(k, mode, answer_fn, on_progress, index, model):
        on_progress(1, 2, {})
        release.wait(5)
        on_progress(2, 2, {})
        return {"run_id": "inner", "status": "done", "progress": {"done": 2, "total": 2},
                "params": {"k": k, "mode": mode}, "metrics": {"recall_at_k": 1.0}, "questions": []}

    monkeypatch.setattr(main, "run_benchmark", fake_run)
    started = client.post("/api/benchmark/run", json={"k": 5, "mode": "retrieval"})
    assert started.status_code == 202
    run_id = started.json()["run_id"]

    assert client.post("/api/benchmark/run", json={"k": 5, "mode": "retrieval"}).status_code == 409
    running = client.get(f"/api/benchmark/runs/{run_id}").json()
    assert running["status"] == "running"

    release.set()
    for _ in range(50):
        body = client.get(f"/api/benchmark/runs/{run_id}").json()
        if body["status"] != "running":
            break
        time.sleep(0.05)
    assert body["status"] == "done"
    assert body["run_id"] == run_id
    assert body["progress"] == {"done": 2, "total": 2}
    assert body["metrics"] == {"recall_at_k": 1.0}


def test_benchmark_error_is_reported_in_status(client, monkeypatch):
    def broken(**kwargs):
        raise ValueError("нет вопросов")

    monkeypatch.setattr(main, "run_benchmark", broken)
    run_id = client.post("/api/benchmark/run", json={"mode": "retrieval"}).json()["run_id"]
    for _ in range(50):
        body = client.get(f"/api/benchmark/runs/{run_id}").json()
        if body["status"] != "running":
            break
        time.sleep(0.05)
    assert body["status"] == "error"
    assert "нет вопросов" in body["error"]


def test_benchmark_full_mode_needs_llm(client, monkeypatch):
    monkeypatch.setattr(llm, "status", lambda model=None: "unavailable")
    assert client.post("/api/benchmark/run", json={"mode": "full"}).status_code == 503


def test_benchmark_unknown_run_and_invalid_request(client):
    assert client.get("/api/benchmark/runs/nope").status_code == 404
    assert client.post("/api/benchmark/run", json={"mode": "fast"}).status_code == 400
