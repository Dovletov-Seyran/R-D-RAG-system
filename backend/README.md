# Backend

Сервис на Python 3.12 и FastAPI: принимает вопрос, ищет фрагменты собственным BM25 (`search/`), передаёт их локальной LLM через Ollama и возвращает ответ с источниками. Отсюда же запускается benchmark — прямо во время защиты.

| Файл | Назначение |
| --- | --- |
| `app/main.py` | HTTP API: `POST /api/chat`, `GET /api/health`, `POST /api/benchmark/run`, `GET /api/benchmark/runs/{run_id}` |
| `app/rag.py` | `answer()` — контракт C4: поиск → проверка контекста → prompt → LLM → проверка отказа |
| `app/llm.py` | Запрос к Ollama `POST /api/chat`, статус модели для `/api/health` |
| `app/config.py` | Настройки и переменные окружения |
| `requirements.txt` | FastAPI, Uvicorn, httpx + общий `requirements.txt` |

## Запуск

```bash
pip install -r backend/requirements.txt
python -m search.build
ollama pull qwen3:4b-instruct
uvicorn backend.app.main:app --port 8000
```

Интерактивная документация API — http://localhost:8000/docs. Контракт — [spec/tech/api.md](../spec/tech/api.md).

## Настройки

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `OLLAMA_URL` | `http://localhost:11434` | Адрес Ollama |
| `OLLAMA_MODEL` | `qwen3:4b-instruct` | Модель, выбор — решение D14 в [журнале](../spec/decisions.md) |
| `OLLAMA_TIMEOUT` | `180` | Таймаут ответа модели, секунды; превышение → 503 |
| `LLM_TEMPERATURE` | `0.1` | Низкая температура: ответ ближе к тексту фрагментов |
| `LLM_NUM_CTX` | `8192` | Окно контекста модели: 5 фрагментов + история |
| `CORS_ORIGINS` | `http://localhost:8080,http://127.0.0.1:8080` | Адреса frontend, которым разрешены запросы |

## Как строится ответ

1. BM25 возвращает top-5 фрагментов. Если покрытие запроса у лучшего фрагмента ниже порога `NO_CONTEXT_MIN_COVERAGE` из `search/config.py`, сразу возвращается отказ `no_context` — LLM не вызывается.
2. Уточняющий вопрос («а как тогда получить обратный код?») сам по себе слишком короткий. Если прошлый вопрос пользователя был по корпусу, поиск идёт по обоим вопросам вместе.
3. Prompt: роль ассистента кафедры, фрагменты `[1]…[5]` с названием документа и страницей, последние 6 сообщений диалога, вопрос. Модель обязана отвечать только по фрагментам, ставить ссылки `[n]` и при отсутствии ответа написать ровно «В документах нет этой информации.».
4. Если модель так ответила — `finish_reason = no_context`.
5. `sources` собираются из metadata фрагментов, на которые модель сослалась (`[n]`); если ссылок нет — из всех переданных. Текст модели источником не считается.

## Тесты

`tests/test_api.py` — LLM подменяется заглушкой, индекс строится из маленького тестового корпуса, Ollama не нужна:

```bash
python -m pytest tests/test_api.py
```
