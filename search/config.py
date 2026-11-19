"""Параметры поиска. Значения выбраны по benchmark, см. spec/tech/rag.md."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "search" / "index" / "bm25.json"
MANIFEST_PATH = ROOT / "corpus" / "manifest.json"
PROCESSED_DIR = ROOT / "corpus" / "processed"

# BM25
K1 = 1.2
B = 0.75
TOP_K = 5

# Фрагменты
CHUNK_CHARS = 1000      # целевой размер фрагмента
CHUNK_MIN_CHARS = 300   # короткие страницы (слайды) склеиваются до этого размера
ADD_TITLE = True        # добавлять название документа в индексируемый текст

# Предобработка
LEMMATIZE = True
REMOVE_STOPWORDS = True

# Отказ без вызова LLM: если доля веса запроса (сумма IDF его термов), найденная
# в лучшем фрагменте top-k, ниже порога — считаем, что в корпусе нет ответа.
# Подобран по benchmark 2026-11-19: у обычных вопросов покрытие ≥ 0.50,
# у ловушек ≤ 0.43; порог — середина зазора. См. benchmark/README.md.
NO_CONTEXT_MIN_COVERAGE = 0.46
