"""Detecção determinística de linguagem para o workspace local do Condor."""

from __future__ import annotations

import re
from typing import Any


LANGUAGE_EXTENSIONS = {
    "arduino": ".ino",
    "python": ".py",
    "typescript": ".ts",
    "javascript": ".js",
    "cpp": ".cpp",
    "c": ".c",
    "rust": ".rs",
    "html": ".html",
    "css": ".css",
    "shell": ".sh",
    "text": ".txt",
}


def detect_language(content: str) -> dict[str, Any]:
    """Identifica a linguagem sem executar nem compilar o conteúdo."""

    source = str(content or "")[:500_000]
    scores = {name: 0 for name in LANGUAGE_EXTENSIONS if name != "text"}
    rules = {
        "arduino": (
            (r"\bvoid\s+setup\s*\(", 8), (r"\bvoid\s+loop\s*\(", 8),
            (r"\b(pinMode|digitalWrite|analogRead|Serial\.begin)\s*\(", 5),
        ),
        "python": ((r"(?m)^\s*(def|class|from|import)\s+", 4), (r"\b(print|asyncio|self)\b", 2)),
        "typescript": ((r"\b(interface|type|enum)\s+\w+", 5), (r"\b(string|number|boolean)\s*[;=,)\]]", 2)),
        "javascript": ((r"\b(const|let|function)\s+", 3), (r"=>|console\.log|document\.", 2)),
        "cpp": ((r"#include\s*<(iostream|vector|string|memory)>", 6), (r"\bstd::|cout\s*<<|namespace\s+", 4)),
        "c": ((r"#include\s*<(stdio|stdlib|string)\.h>", 6), (r"\bprintf\s*\(|\bstruct\s+", 3)),
        "rust": ((r"(?m)^\s*fn\s+\w+", 5), (r"\b(let\s+mut|impl|match|println!)\b", 4)),
        "html": ((r"<!doctype\s+html|<html\b|<body\b", 8), (r"</?[a-z][^>]*>", 2)),
        "css": ((r"(?m)^\s*[.#]?[\w-]+(?:\s+[.#]?[\w-]+)*\s*\{", 5), (r"\b(display|color|margin|padding)\s*:", 3)),
        "shell": ((r"(?m)^#!.*\b(bash|sh|zsh)\b", 8), (r"(?m)^\s*(echo|export|chmod|sudo)\s+", 3)),
    }
    for language, patterns in rules.items():
        for pattern, weight in patterns:
            if re.search(pattern, source, flags=re.IGNORECASE):
                scores[language] += weight
    if not source.strip() or max(scores.values(), default=0) == 0:
        language = "text"
        confidence = 0.0
    else:
        language = max(scores, key=scores.get)
        top = scores[language]
        confidence = min(0.99, 0.42 + top * 0.055)
    return {
        "language": language,
        "extension": LANGUAGE_EXTENSIONS[language],
        "confidence": round(confidence, 2),
    }
