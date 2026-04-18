import re
from pathlib import Path
from typing import Any


_UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}_",
    re.IGNORECASE,
)
_SIGNED_SUFFIX_RE = re.compile(r"(?:[_\-\s]*(?:assinado|signed))+$$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_KEYWORDS_RE = re.compile(
    r"\b("
    r"aditivo|edital|resolu[cç][aã]o|portaria|instru[cç][aã]o|chamada|"
    r"regulamento|pol[ií]tica|programa|resultado|retifica[cç][aã]o|"
    r"cepex|cepep|consun|pibic|pibiti|icv|ufpi"
    r")\b",
    re.IGNORECASE,
)
_TITLE_NOISE_RE = re.compile(
    r"\b(p[aá]gina|page|telefone|email|e-mail|www\.|http|cep|cnpj|cpf)\b",
    re.IGNORECASE,
)


def _normalize_spaces(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip())


def _looks_like_title_candidate(line: str) -> bool:
    if not 5 <= len(line) <= 160:
        return False
    if _TITLE_NOISE_RE.search(line):
        return False
    if re.fullmatch(r"[\d\W_]+", line):
        return False
    if len(line) > 90 and re.search(r"[\.!?]", line):
        return False
    return True


def _score_title_candidate(line: str) -> int:
    score = 0
    if _TITLE_KEYWORDS_RE.search(line):
        score += 6

    letters = [char for char in line if char.isalpha()]
    if letters:
        uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
        if uppercase_ratio >= 0.6:
            score += 3

    if re.search(r"20\d{2}(?:\s*[-/]\s*20\d{2})?", line):
        score += 2
    if ":" in line and len(line) > 70:
        score -= 2
    if len(line) > 120:
        score -= 2

    return score


def _extract_title_from_pages(pages: list[dict[str, Any]]) -> str | None:
    if not pages:
        return None

    first_page_text = str(pages[0].get("text") or "")
    if not first_page_text.strip():
        return None

    raw_lines = [
        _normalize_spaces(line)
        for line in first_page_text.splitlines()
        if _normalize_spaces(line)
    ]
    lines = raw_lines[:12]

    best_index = -1
    best_score = -1
    for index, line in enumerate(lines):
        if not _looks_like_title_candidate(line):
            continue
        score = _score_title_candidate(line)
        if score > best_score:
            best_score = score
            best_index = index

    if best_index == -1 or best_score < 5:
        return None

    selected = [lines[best_index]]
    for next_line in lines[best_index + 1 : best_index + 3]:
        if not _looks_like_title_candidate(next_line):
            break
        if _score_title_candidate(next_line) < 2:
            break
        if len(" ".join(selected + [next_line])) > 180:
            break
        if re.search(r"[\.!?]$", next_line):
            break
        selected.append(next_line)

    title = _normalize_spaces(" - ".join(selected))
    if 5 <= len(title) <= 200:
        return title
    return None


def format_document_display_name(raw_name: str) -> str:
    name = Path((raw_name or "").strip()).name
    stem = Path(name).stem if name else ""
    stem = _UUID_PREFIX_RE.sub("", stem)
    stem = _SIGNED_SUFFIX_RE.sub("", stem)
    stem = stem.replace("_", " ")
    stem = re.sub(r"\s*-\s*", " - ", stem)
    stem = _WHITESPACE_RE.sub(" ", stem).strip(" -_")
    if stem:
        return stem
    if name:
        return name
    return "Documento"


def resolve_document_display_name(
    original_name: str,
    pages: list[dict[str, Any]],
    metadata_title: str | None = None,
) -> str:
    title = _normalize_spaces(metadata_title or "")
    if 5 <= len(title) <= 200:
        return title

    page_title = _extract_title_from_pages(pages)
    if page_title:
        return page_title

    return format_document_display_name(original_name)