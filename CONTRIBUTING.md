# Совместная работа

## Порядок SDD

Перед кодом описать поведение и способ проверки в соответствующей спецификации (`spec/`). Изменение API сопровождается обновлением [spec/tech/api.md](spec/tech/api.md) и кода потребителей. Небольшое исправление уже принятой спецификации не требует переписывать всю документацию.

Задача → ветка → спецификация → код → проверки → Pull Request → review коллегой → merge в `main`.

## Ветки

Постоянная ветка — `main`. Для каждой задачи создаётся короткая временная ветка с префиксом по типу работы:

| Префикс | Когда |
| --- | --- |
| `feat/` | Новая функциональность: `feat/bm25-index` |
| `fix/` | Исправление ошибки: `fix/chat-history-delete` |
| `docs/` | Документация и спецификации: `docs/rag-spec` |
| `chore/` | Инфраструктура, CI, зависимости |

Ветки «по участнику навсегда» и отдельная `develop` не используются.

## Команды одной задачи

```bash
git clone https://github.com/Dovletov-Seyran/R-D-RAG-system.git
cd R-D-RAG-system
git switch main
git pull --ff-only
git switch -c docs/rag-spec
```

После изменения проверить `git status`, `git diff`, `git diff --check` и `python3 scripts/check_docs.py`. Добавлять конкретные файлы:

```bash
git add spec/tech/rag.md
git commit -m "docs: describe chunking of methodical guides"
git push -u origin HEAD
```

На GitHub открыть Pull Request в `main`, заполнить шаблон и запросить review другого участника. После merge удалить ветку и обновить локальный `main`.

## Сообщения коммитов

Формат `тип: что сделано`, где тип — `feat`, `fix`, `docs`, `chore`, `refactor`, `test`. Сообщение отвечает на вопрос «что изменилось», а не «что я делал сегодня». Примеры: `feat: add BM25 search endpoint`, `docs: add user scenarios`.

## Правила для кода

- Не коммитить секреты, токены, пароли, личные данные студентов. Демо-логин `admin/admin` в прототипе — только для показа.
- Текст модели не вставляется в страницу как HTML: используется `textContent` или безопасный Markdown-рендер.
- Если поиск не нашёл контекст, backend возвращает явный отказ, а не ответ «из головы» модели.
- Демо-режим всегда помечен в интерфейсе; нельзя незаметно подменять работу RAG заготовленным ответом.
- Смена технологии записывается в [журнал решений](spec/decisions.md) с причиной.

## Зоны ответственности

| Каталог | Ведущий |
| --- | --- |
| `frontend/`, `spec/product/` | Frontend |
| `backend/`, `spec/tech/api.md`, `spec/tech/architecture.md`, `.github/`, `scripts/` | Backend и интеграция |
| `search/`, `corpus/`, `benchmark/`, `spec/tech/rag.md`, `spec/tech/testing.md` | RAG |
| `README.md`, `CONTRIBUTING.md`, `CHANGE_HISTORY.md`, `spec/plan.md` | Общие правки по согласованию |

Состав команды — [spec/team.md](spec/team.md).

## Review

Проверяющий оценивает соответствие задаче и спецификации, отсутствие секретов и результат проверок. Автор исправляет замечания. Одобрение собственного PR не заменяет review коллеги.

Не удалять чужие изменения, не делать force-push в `main`, не переписывать опубликованную историю.

## Готовность изменения

Спецификация и код согласованы, `python3 scripts/check_docs.py` и `node --check frontend/script.js` проходят, основной сценарий пройден в браузере, README и [CHANGE_HISTORY.md](CHANGE_HISTORY.md) обновлены при необходимости. В PR указаны пропуски и ограничения. Результаты тестов и benchmark не выдумываются.
