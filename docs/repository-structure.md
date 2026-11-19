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
| `backend/` | FastAPI: чат, вызов поиска и LLM, запуск benchmark — `app/`, `requirements.txt` |
| `search/` | Собственный BM25, токенизатор, фрагменты; собранный индекс `search/index/` в Git не хранится |
| `corpus/` | `manifest.json`, извлечённый текст 30 документов, скрипт извлечения |
| `benchmark/` | 15 вопросов, прогон и метрики, эксперименты, сохранённые результаты |
| `tests/` | pytest: поиск, benchmark, API |
| `requirements.txt` | Зависимости поиска и benchmark |
| `scripts/check_docs.py` | Проверка обязательных файлов и ссылок |
| `.github/workflows/docs-check.yml` | GitHub Actions: проверка документации, сборка индекса, тесты `pytest` |
| `.github/pull_request_template.md` | Шаблон Pull Request |

## Дальше

- `frontend/` — подключение к API и страница benchmark (задачи F1–F2).
- `benchmark/` — отдельный контрольный набор вопросов (holdout) к точке 3.

Папки без реальной роли не создаются ради объёма.
