"""Эксперименты с поиском: меняем одну настройку за раз на том же корпусе и вопросах.

    python -m benchmark.experiments

E1 — лемматизация и стоп-слова, E2 — размер фрагмента, E3 — заголовок документа
в тексте фрагмента, E4 — параметры BM25 k1 и b. Метрики — режим retrieval (k = 5).
Результат печатается и сохраняется в benchmark/results/<дата>_experiments.md.
"""

from __future__ import annotations

import sys
from datetime import datetime

from benchmark.run import RESULTS_DIR, run_benchmark
from search import config
from search.index import build_index

BASE = dict(
    k1=config.K1, b=config.B, chunk_chars=config.CHUNK_CHARS, add_title=config.ADD_TITLE,
    lemmatize=config.LEMMATIZE, remove_stopwords=config.REMOVE_STOPWORDS,
)

EXPERIMENTS = [
    ("База", {}),
    ("E1: без лемматизации", {"lemmatize": False}),
    ("E1: без удаления стоп-слов", {"remove_stopwords": False}),
    ("E1: без лемматизации и стоп-слов", {"lemmatize": False, "remove_stopwords": False}),
    ("E2: фрагменты 500 символов", {"chunk_chars": 500}),
    ("E2: фрагменты 1500 символов", {"chunk_chars": 1500}),
    ("E3: без заголовка документа", {"add_title": False}),
    ("E4: k1 = 2.0", {"k1": 2.0}),
    ("E4: b = 0 (без нормализации длины)", {"b": 0.0}),
    ("E4: b = 1", {"b": 1.0}),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    lines = [
        f"# Эксперименты с поиском {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "Корпус и вопросы одинаковые, меняется одна настройка. Режим retrieval, k = 5. "
        "CRR — доля ловушек, отклонённых порогом покрытия "
        f"{config.NO_CONTEXT_MIN_COVERAGE}.",
        "",
        "| Вариант | Recall@5 | MRR@5 | CRR (порог) | Фрагментов |",
        "| --- | --- | --- | --- | --- |",
    ]
    print(f"{'Вариант':40} {'Recall@5':>8} {'MRR@5':>6} {'CRR':>5} {'Фрагм.':>7}")
    for name, change in EXPERIMENTS:
        params = {**BASE, **change}
        index = build_index(**params)
        m = run_benchmark(k=5, mode="retrieval", index=index, save=False)["metrics"]
        print(f"{name:40} {m['recall_at_k']:8.3f} {m['mrr_at_k']:6.3f} {m['correct_rejection_rate']:5.2f} {len(index.chunks):7}")
        lines.append(f"| {name} | {m['recall_at_k']:.3f} | {m['mrr_at_k']:.3f} | {m['correct_rejection_rate']:.2f} | {len(index.chunks)} |")
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{datetime.now():%Y-%m-%dT%H-%M-%S}_experiments.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Сохранено: {path.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
