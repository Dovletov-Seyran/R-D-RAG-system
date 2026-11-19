"""Настройки backend. Значения по умолчанию — для ноутбука защиты; меняются переменными окружения."""

import os

# LLM (Ollama)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "8192"))  # фрагменты top-5 ≈ 5000 символов + история

# Frontend: адреса, которым разрешены запросы (CORS), через запятую
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",")
    if origin.strip()
]

# Чат
MAX_MESSAGE_CHARS = 2000
HISTORY_MESSAGES = 6           # сколько последних сообщений диалога передаётся в LLM
FRAGMENT_MAX_CHARS = 1500      # обрезка одного фрагмента в prompt

# Ровно эту фразу LLM должна вернуть, если ответа во фрагментах нет (см. prompt в rag.py)
NO_CONTEXT_TEXT = "В документах нет этой информации."
