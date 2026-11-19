"""Извлечение текста документов корпуса.

Читает corpus/manifest.json, для каждого документа открывает исходный файл
из папки --source, извлекает текст постранично и пишет corpus/processed/Dxx.jsonl
(одна строка = одна страница: doc_id, page, text). В manifest дописываются
sha256 исходника, число страниц и символов.

PDF извлекается постранично (pypdf), номера страниц совпадают с оригиналом.
DOCX не хранит страниц, поэтому абзацы группируются в блоки ~2500 символов;
номер блока используется как «страница» (в manifest: page_kind = "block").

Запуск:
    python -m corpus.extract --source "../1 курс/1сем"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
MANIFEST = CORPUS_DIR / "manifest.json"
PROCESSED = CORPUS_DIR / "processed"

DOCX_BLOCK_CHARS = 2500


# Водяной знак «МГТУ ФН-12» в лекциях по ангему извлекается как латиница-1: «ÌÃÒÓ ÔÍ-12».
WATERMARK = re.compile(r"[À-ÿ]{2,}(?:-\d+)?")
# Строки с номером учебной группы (ИУ5-11Б, РК6-12 и т. п.) обычно содержат ФИО
# студента — в корпус они не попадают (правило: без персональных данных).
PERSONAL_LINE = re.compile(r"^.*[А-Я]{2,4}\d{1,2}-\d{2,3}[БМ]?.*$", re.MULTILINE)


def clean_text(text: str) -> str:
    """Нормализует пробелы, склеивает переносы, убирает водяные знаки и строки с ФИО."""
    text = text.replace("­", "").replace(" ", " ").replace("\x00", "")
    text = WATERMARK.sub(" ", text)
    text = PERSONAL_LINE.sub("", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_noise_page(text: str) -> bool:
    """Страница без содержательного текста: пустая или только номер."""
    letters = sum(ch.isalpha() for ch in text)
    return letters < 20


def extract_pdf(path: Path) -> tuple[list[tuple[int, str]], int]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for number, page in enumerate(reader.pages, 1):
        try:
            raw = page.extract_text() or ""
        except Exception:  # битая страница не должна ронять весь документ
            raw = ""
        text = clean_text(raw)
        if not is_noise_page(text):
            pages.append((number, text))
    return pages, len(reader.pages)


def docx_paragraphs(path: Path) -> list[str]:
    import docx

    document = docx.Document(str(path))
    parts: list[str] = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = "".join(node.text or "" for node in child.iter() if node.tag.endswith("}t"))
            if text.strip():
                parts.append(text.strip())
        elif tag == "tbl":
            for row in child.iter():
                if not row.tag.endswith("}tr"):
                    continue
                cells = []
                for cell in row.iter():
                    if cell.tag.endswith("}tc"):
                        cell_text = " ".join(
                            (node.text or "") for node in cell.iter() if node.tag.endswith("}t")
                        ).strip()
                        cells.append(cell_text)
                line = " | ".join(c for c in cells if c)
                if line:
                    parts.append(line)
    return parts


def extract_docx(path: Path) -> tuple[list[tuple[int, str]], int]:
    blocks: list[tuple[int, str]] = []
    current: list[str] = []
    size = 0
    for paragraph in docx_paragraphs(path):
        current.append(paragraph)
        size += len(paragraph) + 1
        if size >= DOCX_BLOCK_CHARS:
            blocks.append((len(blocks) + 1, clean_text("\n".join(current))))
            current, size = [], 0
    if current:
        blocks.append((len(blocks) + 1, clean_text("\n".join(current))))
    blocks = [(n, t) for n, t in blocks if not is_noise_page(t)]
    return blocks, len(blocks)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="папка с исходными материалами")
    parser.add_argument("--only", nargs="*", help="извлечь только указанные doc_id")
    args = parser.parse_args(argv)

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    source = Path(args.source)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    PROCESSED.mkdir(exist_ok=True)

    failed = 0
    for doc in manifest["documents"]:
        if args.only and doc["doc_id"] not in args.only:
            continue
        path = source / doc["source"]
        if not path.is_file():
            print(f"[{doc['doc_id']}] нет файла: {path}", file=sys.stderr)
            failed += 1
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pages, total = extract_pdf(path)
            doc["page_kind"] = "page"
        elif suffix == ".docx":
            pages, total = extract_docx(path)
            doc["page_kind"] = "block"
        else:
            print(f"[{doc['doc_id']}] формат не поддерживается: {suffix}", file=sys.stderr)
            failed += 1
            continue

        # точечное удаление фамилий, которые не ловит общее правило (поле redact в manifest)
        for phrase in doc.get("redact", []):
            pages = [(n, clean_text(t.replace(phrase, ""))) for n, t in pages]

        out = PROCESSED / f"{doc['doc_id']}.jsonl"
        with out.open("w", encoding="utf-8", newline="\n") as handle:
            for number, text in pages:
                handle.write(json.dumps({"doc_id": doc["doc_id"], "page": number, "text": text}, ensure_ascii=False) + "\n")

        doc["pages_total"] = total
        doc["pages_with_text"] = len(pages)
        doc["chars"] = sum(len(t) for _, t in pages)
        doc["sha256"] = sha256(path)
        print(f"[{doc['doc_id']}] {doc['pages_with_text']}/{total} стр., {doc['chars']} симв. — {doc['title']}")
        if not pages:
            failed += 1

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
