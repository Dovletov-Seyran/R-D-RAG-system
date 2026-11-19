# Search

Поиск по корпусу: токенизатор с лемматизацией, разбиение на фрагменты и **собственный** BM25-индекс. Готовые поисковые индексы (`rank-bm25` и т. п.) не используются — требование методических указаний к НИРС (решение D10).

| Файл | Назначение |
| --- | --- |
| `tokenizer.py` | Нижний регистр, токены-слова и числа, лемматизация `pymorphy3`, стоп-слова |
| `chunker.py` | Фрагменты ~1000 символов по страницам; короткие слайды склеиваются |
| `bm25.py` | Обратный индекс `терм → {фрагмент: tf}`, формула BM25, покрытие запроса |
| `index.py` | Сборка, сохранение, загрузка индекса; `retrieve`, `retrieve_documents`, `has_context` |
| `build.py` | `python -m search.build` — собрать индекс в `search/index/bm25.json` |
| `config.py` | Параметры: `K1`, `B`, `TOP_K`, размер фрагментов, порог отказа |

## Использование (контракт C1)

```python
from search import load_index, retrieve, has_context

index = load_index()                      # search/index/bm25.json, один раз при старте
hits = retrieve(index, "Что такое дополнительный код?", k=5)
if not has_context(hits):
    ...                                   # отказ no_context без вызова LLM
for hit in hits:
    print(hit.source(), hit.score)        # «Лекция 4. Системы счисления. Машинные коды, стр. 10»
```

`Hit`: `chunk_id`, `doc_id`, `title`, `discipline`, `page`, `page_end`, `score`, `text` (исходный текст, не леммы), `coverage`. `retrieve_documents()` возвращает top-k различных документов — по нему считаются метрики benchmark.

## Формула

```text
IDF(t)     = ln(1 + (N − df(t) + 0,5) / (df(t) + 0,5))
BM25(q, d) = Σ_{t ∈ q} IDF(t) · tf(t,d) · (k1 + 1) / (tf(t,d) + k1 · (1 − b + b · |d| / avgdl))
```

`k1 = 1,2`, `b = 0,75`. Термы запроса берутся без повторов. Равные баллы упорядочиваются по номеру фрагмента — выдача детерминирована. Тест `tests/test_search.py` сверяет реализацию с ручным расчётом из занятия 3 (документ A = 0,940).

## Отказ без контекста

`coverage` — доля веса запроса (сумма IDF его термов), термы которой есть во фрагменте. Слова, которых нет в корпусе, входят в знаменатель с максимальным IDF. Если у лучшего фрагмента top-k покрытие ниже `NO_CONTEXT_MIN_COVERAGE = 0.46`, `has_context()` возвращает `False` и backend отвечает `no_context`, не вызывая LLM. Порог подобран по benchmark — [benchmark/README.md](../benchmark/README.md#порог-отказа).

Обоснование предобработки — [spec/tech/rag.md](../spec/tech/rag.md#токенизация).
