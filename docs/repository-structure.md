# Структура репозитория

## Сейчас

| Путь | Содержимое |
| --- | --- |
| `README.md`, `CONTRIBUTING.md`, `CHANGE_HISTORY.md` | Описание проекта, правила работы, журнал изменений |
| `frontend/` | Прототип интерфейса: `index.html`, `styles.css`, `script.js` |
| `spec/product/` | Продукт, сценарии, интерфейс |
| `spec/tech/` | Архитектура, API, RAG, способ проверки |
| `spec/team.md`, `spec/plan.md`, `spec/decisions.md` | Команда, план, журнал решений |
| `docs/` | Чек-лист точки, сценарий показа, источники, отчёт проверки |
| `docs/images/` | Скриншоты интерфейса |
| `backend/`, `search/` | README с границами будущей реализации |
| `corpus/`, `benchmark/` | Форматы данных и пример вопросов |
| `scripts/check_docs.py` | Проверка обязательных файлов и ссылок |
| `.github/workflows/docs-check.yml` | Запуск проверки документации в GitHub Actions |
| `.github/pull_request_template.md` | Шаблон Pull Request |

## При реализации

- `backend/` — приложение FastAPI, `requirements.txt`, тесты.
- `search/` — токенизатор, индексатор, BM25, тесты.
- `corpus/` — `manifest.json`, извлечённые документы.
- `benchmark/` — размеченные вопросы и отчёты экспериментов.

Папки без реальной роли не создаются ради объёма. README в пока пустых каталогах честно показывает, что там будет.
