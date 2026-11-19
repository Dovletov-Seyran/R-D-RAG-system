"""Проверка документации: обязательные файлы, локальные ссылки, пример benchmark."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    "README.md",
    "CONTRIBUTING.md",
    "CHANGE_HISTORY.md",
    "frontend/index.html",
    "frontend/styles.css",
    "frontend/script.js",
    "spec/product/product.md",
    "spec/product/scenarios.md",
    "spec/product/interface.md",
    "spec/tech/architecture.md",
    "spec/tech/api.md",
    "spec/tech/rag.md",
    "spec/tech/testing.md",
    "spec/team.md",
    "spec/plan.md",
    "spec/decisions.md",
    "docs/checkpoint-1.md",
    "docs/checkpoint-2.md",
    "docs/demo-script.md",
    "docs/repository-structure.md",
    "docs/sources.md",
    "docs/verification.md",
    "benchmark/README.md",
    "benchmark/questions.example.jsonl",
    "corpus/README.md",
]

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def check_required(errors):
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"нет обязательного файла: {rel}")
    return len(REQUIRED)


def check_links(errors):
    count = 0
    for md in sorted(ROOT.rglob("*.md")):
        if ".git" in md.parts:
            continue
        for target in LINK.findall(md.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            count += 1
            if not (md.parent / path).exists():
                errors.append(f"{md.relative_to(ROOT)}: битая ссылка {target}")
    return count


def check_benchmark(errors):
    path = ROOT / "benchmark/questions.example.jsonl"
    if not path.is_file():
        return 0
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for number, line in enumerate(lines, 1):
        try:
            json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"benchmark пример, строка {number}: {error}")
    return len(lines)


def main():
    errors = []
    files = check_required(errors)
    links = check_links(errors)
    questions = check_benchmark(errors)
    for error in errors:
        print(f"FAIL {error}")
    if errors:
        return 1
    print(f"PASS: {files} обязательных файлов, {links} локальных ссылок, {questions} примеров benchmark")
    return 0


if __name__ == "__main__":
    sys.exit(main())
