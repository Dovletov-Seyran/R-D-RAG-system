"""Вызов локальной LLM через Ollama: POST /api/chat без потоковой передачи."""

from __future__ import annotations

import re

import httpx

from backend.app import config

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMUnavailable(Exception):
    """Ollama не запущена, модель не скачана или не уложилась в таймаут → HTTP 503."""


def chat(messages: list[dict], model: str | None = None) -> str:
    """Отправляет диалог в Ollama и возвращает текст ответа модели."""
    payload = {
        "model": model or config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": config.LLM_TEMPERATURE, "num_ctx": config.LLM_NUM_CTX},
    }
    try:
        response = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=config.OLLAMA_TIMEOUT)
    except httpx.TimeoutException as error:
        raise LLMUnavailable(f"Ollama не ответила за {config.OLLAMA_TIMEOUT:.0f} с") from error
    except httpx.HTTPError as error:
        raise LLMUnavailable(f"Ollama недоступна по адресу {config.OLLAMA_URL}: {error}") from error
    if response.status_code != 200:
        raise LLMUnavailable(f"Ollama вернула {response.status_code}: {response.text[:200]}")
    text = response.json().get("message", {}).get("content", "")
    # модели с режимом рассуждений (qwen3) могут вернуть блок <think> — пользователю он не нужен
    return THINK_BLOCK.sub("", text).strip()


def status(model: str | None = None) -> str:
    """Для /api/health: available, model_missing или unavailable."""
    model = model or config.OLLAMA_MODEL
    try:
        response = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError:
        return "unavailable"
    names = {m.get("name") for m in response.json().get("models", [])}
    if model in names or f"{model}:latest" in names:
        return "available"
    return "model_missing"
