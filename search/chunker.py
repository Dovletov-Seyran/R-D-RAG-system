"""Разбиение страниц документа на фрагменты.

- Фрагмент не пересекает границу страницы, если страница достаточно длинная:
  номер страницы в источнике точный.
- Короткие страницы (слайды лекций) склеиваются подряд до CHUNK_MIN_CHARS;
  у такого фрагмента есть page и page_end.
- Длинная страница режется по строкам/абзацам на куски ~CHUNK_CHARS.
- chunk_id = "<doc_id>-p<page>-c<номер на странице>" — стабилен при повторной сборке.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    page: int
    page_end: int
    text: str


def _split_long(text: str, size: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > size * 1.5:  # очень длинная строка без переносов
            cut = line.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:cut])
            line = line[cut:].lstrip()
        if current and len(current) + len(line) + 1 > size:
            parts.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        if parts and len(current) < size // 4:
            parts[-1] = f"{parts[-1]}\n{current}"
        else:
            parts.append(current)
    return parts


def chunk_document(doc_id: str, pages: list[tuple[int, str]], size: int = 1000, min_size: int = 300) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[tuple[int, str]] = []

    def flush() -> None:
        if not buffer:
            return
        first, last = buffer[0][0], buffer[-1][0]
        text = "\n".join(t for _, t in buffer)
        chunks.append(Chunk(f"{doc_id}-p{first}-c1", doc_id, first, last, text))
        buffer.clear()

    for number, text in pages:
        text = text.strip()
        if not text:
            continue
        if len(text) < min_size:
            buffer.append((number, text))
            if sum(len(t) for _, t in buffer) >= min_size:
                flush()
            continue
        flush()
        for i, part in enumerate(_split_long(text, size), 1):
            chunks.append(Chunk(f"{doc_id}-p{number}-c{i}", doc_id, number, number, part))
    flush()
    return chunks
