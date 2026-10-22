# Backend

Будущий сервис на Python 3.12 и FastAPI. Реализации пока нет.

Задачи: принять `POST /api/chat`, проверить ввод, вызвать BM25-поиск, собрать prompt, вызвать LLM через Ollama и вернуть `text`, `sources`, `finish_reason`.

Контракт — [spec/tech/api.md](../spec/tech/api.md). Архитектура — [spec/tech/architecture.md](../spec/tech/architecture.md).
