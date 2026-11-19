# RAG-ассистент кафедры ИУ-5

Русскоязычный чат-помощник по учебно-методической документации кафедры ИУ-5 МГТУ им. Н. Э. Баумана: поиск фрагментов методичек через BM25 и ответ локальной LLM со ссылкой на источник.

![Экран чата](docs/images/chat.png)

## Тема и пользователь

**Тема НИРС:** исследование эффективности RAG-системы для поиска и обработки учебно-методической документации кафедры ИУ-5.

**Пользователь:** студент кафедры, которому нужно быстро найти требования к лабораторной работе, курсовому проекту или дисциплине и проверить ответ по исходной методичке. Дополнительно — преподаватель, который хочет понять, что ассистент отвечает студентам.

Пример задачи: «Какие разделы должны быть в отчёте по лабораторной работе №3?». Студент входит в систему, задаёт вопрос, получает краткий ответ и видит источник: название методички и страницу.

## Что готово сейчас

| Материал | Статус |
| --- | --- |
| Продуктовые и технические спецификации | Подготовлены, см. [spec/](spec/) |
| Интерфейс | Статический прототип: вход, чат, история диалогов, адаптивная вёрстка — [frontend/](frontend/) |
| Контракт API чата | Описан в [spec/tech/api.md](spec/tech/api.md); точка подключения в `frontend/script.js` |
| Корпус | 30 документов `D01…D30` (1 курс, 1 семестр), извлечённый текст — [corpus/](corpus/) |
| BM25-поиск | Собственный индекс, лемматизация, отказ без контекста — [search/](search/), 24 теста |
| Benchmark | 10 вопросов + 5 ловушек, запуск в рантайме из консоли и через API: Recall@5 = 0.960, MRR@5 = 1.000, Accuracy = 1.000, Correct Rejection Rate = 1.000 — [benchmark/](benchmark/) |
| Backend, LLM | FastAPI + Ollama (`qwen3:4b-instruct`): чат с источниками, отказ без контекста, запуск benchmark через API — [backend/](backend/), 23 теста |

Ответы в прототипе — демонстрационные: они явно помечены как «демо-ответ» и не являются работой RAG.

**Сейчас идёт работа над второй контрольной точкой** (RAG и benchmark). Задачи каждого участника, контракты между частями и чек-лист — в [ТЗ точки 2](docs/checkpoint-2.md).

## Запуск прототипа

Внешние зависимости не нужны. Достаточно открыть `frontend/index.html` в современном браузере или поднять локальный сервер:

```bash
python3 -m http.server 8080 --directory frontend
```

Затем открыть http://localhost:8080 и войти с демо-учётной записью **admin / admin**. История диалогов хранится в `localStorage` браузера.

| Вход | Новый диалог |
| --- | --- |
| ![Вход](docs/images/login.png) | ![Новый диалог](docs/images/welcome.png) |

## Запуск системы

Нужны Python 3.12+ и [Ollama](https://ollama.com/). Все команды — из корня репозитория.

**1. Зависимости и индекс** (один раз):

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python -m search.build             # BM25-индекс из corpus/processed (~1 с)
```

**2. Модель** (один раз, ~2.5 ГБ):

```bash
ollama pull qwen3:4b-instruct
```

**3. Запуск** — в трёх окнах терминала:

```bash
ollama serve                                   # если Ollama не запущена как приложение
uvicorn backend.app.main:app --port 8000       # backend
python3 -m http.server 8080 --directory frontend   # интерфейс: http://localhost:8080
```

Проверка готовности: http://localhost:8000/api/health — `"status": "ok"`, `"index_loaded": true`, `"llm": "available"`. Документация API в браузере — http://localhost:8000/docs.

Вопрос из консоли:

```bash
curl -s localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"message": "Что такое дополнительный код?"}'
```

Модель и адреса меняются переменными окружения: `OLLAMA_MODEL`, `OLLAMA_URL`, `OLLAMA_TIMEOUT`, `CORS_ORIGINS` — см. [backend/README.md](backend/README.md).

## Повтор проверки (benchmark)

```bash
python -m benchmark.run                                        # только поиск: Recall@5, MRR@5 — секунды
python -m benchmark.run --mode full --api http://localhost:8000    # с ответами LLM: все 4 метрики, ~2 мин
python -m pytest                                               # тесты поиска, benchmark и API
```

Тот же прогон через API — так benchmark запускается на защите:

```bash
curl -s -X POST localhost:8000/api/benchmark/run -H 'Content-Type: application/json' -d '{"k": 5, "mode": "full"}'
curl -s localhost:8000/api/benchmark/runs/<run_id>             # статус, прогресс, затем метрики
```

Результаты сохраняются в `benchmark/results/`. Подробности — [benchmark/README.md](benchmark/README.md), [search/README.md](search/README.md), [corpus/README.md](corpus/README.md).

## Архитектура рабочей версии

| Сервис | Технология | Назначение |
| --- | --- | --- |
| frontend | HTML, CSS, JavaScript (текущий прототип) | Вход, чат, история, отображение источников |
| backend | Python 3.12, FastAPI | API чата, сборка контекста, вызов поиска и LLM |
| search | Python, rank-bm25, pymorphy3 | Индекс фрагментов методичек, BM25-поиск |
| llm | Ollama, открытая instruct-модель (выбирается по benchmark) | Генерация ответа по найденным фрагментам |
| corpus | PDF/DOCX → Markdown → фрагменты + metadata | Подготовленная база знаний кафедры |

Путь запроса: браузер → backend → BM25-поиск → backend (prompt) → LLM → backend → браузер с ответом и источниками. Подробнее — [spec/tech/architecture.md](spec/tech/architecture.md).

```mermaid
flowchart LR
    U["Студент в браузере"] --> F["frontend"]
    F -->|POST /api/chat| B["backend: FastAPI"]
    B --> S["search: BM25"]
    S --> I["Индекс фрагментов методичек"]
    B --> L["LLM: Ollama"]
    B -->|ответ + источники| F
```

## Структура репозитория

```text
.
├── README.md               описание проекта и запуск
├── CONTRIBUTING.md         правила проекта: ветки, Pull Request, review
├── CHANGE_HISTORY.md       журнал значимых изменений
├── frontend/               статический прототип интерфейса
├── backend/                FastAPI: чат, вызов поиска и LLM, запуск benchmark
├── search/                 собственный BM25, токенизатор, фрагменты
├── corpus/                 30 документов: manifest и извлечённый текст
├── benchmark/              вопросы, прогон и 4 метрики, сохранённые результаты
├── tests/                  pytest: поиск, benchmark, API
├── spec/
│   ├── product/            продукт, сценарии, интерфейс
│   ├── tech/               архитектура, API, RAG, проверка
│   ├── team.md             команда и зоны ответственности
│   ├── plan.md             план и контрольные точки
│   └── decisions.md        журнал решений
├── docs/                   чек-лист точки, сценарий показа, источники, проверка
├── scripts/check_docs.py   проверка структуры и ссылок документации
└── .github/                шаблон PR и workflow проверки документации
```

Подробнее — [docs/repository-structure.md](docs/repository-structure.md).

## Документация

| Раздел | Документ |
| --- | --- |
| Продукт | [Спецификация продукта](spec/product/product.md) · [Сценарии](spec/product/scenarios.md) · [Интерфейс](spec/product/interface.md) |
| Техника | [Архитектура](spec/tech/architecture.md) · [API](spec/tech/api.md) · [RAG и BM25](spec/tech/rag.md) · [Способ проверки](spec/tech/testing.md) |
| Организация | [Команда](spec/team.md) · [План](spec/plan.md) · [Решения](spec/decisions.md) · [Правила работы](CONTRIBUTING.md) |
| Контрольная точка | [Чек-лист](docs/checkpoint-1.md) · [Сценарий показа](docs/demo-script.md) · [Проверка](docs/verification.md) · [Источники](docs/sources.md) |

## Проверка документации

```bash
python3 scripts/check_docs.py
```

Скрипт проверяет наличие обязательных файлов и что все локальные ссылки в Markdown ведут на существующие файлы. На каждый push в `main` и Pull Request GitHub Actions запускает этот скрипт, проверку синтаксиса JavaScript, сборку индекса и все тесты `pytest` (без LLM).

## Команда

| Участник | GitHub | Зона ответственности |
| --- | --- | --- |
| Сейран Довлетов | [@Dovletov-Seyran](https://github.com/Dovletov-Seyran) | Backend и интеграция |
| Темирлан Ашкеров | [@ashkerov](https://github.com/ashkerov) | RAG: корпус, BM25, benchmark |
| Анна Гремина | [@Creature547](https://github.com/Creature547) | Frontend и интерфейс |

Подробное распределение — [spec/team.md](spec/team.md).
