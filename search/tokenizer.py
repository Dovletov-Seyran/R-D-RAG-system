"""Токенизатор: одна и та же предобработка для корпуса и запроса.

Шаги:
1. Нижний регистр, «ё» → «е».
2. Разбиение регулярным выражением на слова и числа. Сохраняются числа и
   обозначения из букв и цифр («лр3», «7.32», «ansi»), дефисные слова.
3. Лемматизация русских слов через pymorphy3 («пределы», «предела» → «предел»).
4. Удаление стоп-слов: служебные части речи (предлоги, союзы, частицы,
   междометия) по разбору pymorphy3 и короткий список частых слов.
5. Одиночные буквы отбрасываются (переменные формул x, y, f дают шум);
   одиночные цифры остаются («ЛР 2», «РК 1»).
"""

from __future__ import annotations

import re
from functools import lru_cache

TOKEN_RE = re.compile(r"[0-9a-zа-я]+(?:[.\-][0-9a-zа-я]+)*")
CYRILLIC_RE = re.compile(r"[а-я]")

STOP_POS = {"PREP", "CONJ", "PRCL", "INTJ"}
STOP_WORDS = {
    # местоимения и частые слова без смысла для поиска
    "я", "мы", "ты", "вы", "он", "она", "оно", "они", "это", "этот", "тот", "такой",
    "какой", "который", "весь", "свой", "сам", "самый", "себя", "кто", "что", "где",
    "когда", "как", "так", "также", "тоже", "быть", "являться", "мочь", "есть",
    "нет", "очень", "можно", "нужно", "надо", "его", "её", "их", "мой", "наш",
    "ваш", "твой", "один", "другой", "каждый", "любой", "иной", "если", "или",
    "и", "а", "но", "в", "на", "с", "по", "к", "из", "за", "от", "до", "о", "об",
    "для", "при", "не", "ли", "же", "бы", "то", "уже", "ещё", "еще", "лишь",
    "the", "a", "an", "of", "to", "in", "is", "and", "or",
}


@lru_cache(maxsize=1)
def _morph():
    import pymorphy3

    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=200_000)
def _lemma(word: str) -> tuple[str, str | None]:
    parse = _morph().parse(word)[0]
    return parse.normal_form.replace("ё", "е"), parse.tag.POS


def tokenize(text: str, lemmatize: bool = True, remove_stopwords: bool = True) -> list[str]:
    """Возвращает список термов текста."""
    text = text.lower().replace("ё", "е")
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(text):
        if len(raw) == 1 and not raw.isdigit():
            continue
        word, pos = raw, None
        if CYRILLIC_RE.search(raw) and not any(ch.isdigit() for ch in raw):
            if lemmatize:
                word, pos = _lemma(raw)
            elif remove_stopwords:
                pos = _lemma(raw)[1]
        if remove_stopwords and (word in STOP_WORDS or raw in STOP_WORDS or pos in STOP_POS):
            continue
        tokens.append(word)
    return tokens
