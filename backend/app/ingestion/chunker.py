import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any


def _split_by_tokens(
    text: str, max_tokens: int, enc: Any, overlap_tokens: int = 0
) -> list[str]:
    """Greedily split text into segments that each fit within max_tokens.

    When overlap_tokens > 0, each segment after the first repeats the
    trailing overlap_tokens worth of words from the previous segment, so a
    sentence that would otherwise land on a segment boundary is fully
    present in at least one segment.
    """
    words = text.split()
    if not words:
        return []

    word_token_counts = [len(enc.encode(w, disallowed_special=())) for w in words]
    n = len(words)
    segments: list[str] = []
    start = 0

    while start < n:
        count = 0
        end = start
        while end < n and (count + word_token_counts[end] <= max_tokens or end == start):
            count += word_token_counts[end]
            end += 1
        segments.append(" ".join(words[start:end]))

        if end >= n:
            break

        # Step back from `end` to build the overlap for the next segment,
        # but always advance start by at least one word to guarantee progress.
        back = end
        back_count = 0
        while back > start + 1 and back_count < overlap_tokens:
            back -= 1
            back_count += word_token_counts[back]
        start = back

    return segments


def _sync_chunk(
    pages: list[dict[str, Any]],
    doc_id: str,
    source: str,
    display_name: str,
    created_at: str,
    parent_tokens: int = 512,
    child_tokens: int = 128,
    doc_type: str = "edital",
    edital_ref: str | None = None,
    child_overlap_tokens: int = 24,
    edital_cycle: str | None = None,
) -> list[dict[str, Any]]:
    """
    Build hierarchical parent→child chunks from extracted page text.
    Called synchronously inside run_in_executor (tiktoken is CPU-bound).
    """
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    chunks: list[dict[str, Any]] = []
    global_chunk_index = 0

    for page in pages:
        page_number: int = page["page_number"]
        text: str = page["text"].replace("\x00", "")
        if not text.strip():
            continue

        parent_texts = _split_by_tokens(text, parent_tokens, enc)

        for parent_text in parent_texts:
            parent_id = str(uuid.uuid4())
            child_texts = _split_by_tokens(
                parent_text, child_tokens, enc, overlap_tokens=child_overlap_tokens
            )

            for child_text in child_texts:
                if not child_text.strip():
                    continue
                chunk_hash = hashlib.sha256(
                    child_text.encode("utf-8")
                ).hexdigest()
                chunks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "parent_id": parent_id,
                        "text": child_text,
                        "metadata": {
                            "doc_id": doc_id,
                            "source": source,
                            "display_name": display_name,
                            "page_number": page_number,
                            "chunk_index": global_chunk_index,
                            "type": "child",
                            "created_at": created_at,
                            "hash": chunk_hash,
                            "parent_text": parent_text,
                            "doc_type": doc_type,
                            "edital_ref": edital_ref,
                            "edital_cycle": edital_cycle,
                        },
                    }
                )
                global_chunk_index += 1

    return chunks


async def chunk_pages(
    pages: list[dict[str, Any]],
    doc_id: str,
    source: str,
    display_name: str,
    parent_tokens: int = 512,
    child_tokens: int = 128,
    doc_type: str = "edital",
    edital_ref: str | None = None,
    child_overlap_tokens: int = 24,
    edital_cycle: str | None = None,
) -> list[dict[str, Any]]:
    """Async wrapper: runs the CPU-bound chunking in the default thread executor."""
    created_at = datetime.now(timezone.utc).isoformat()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _sync_chunk,
        pages,
        doc_id,
        source,
        display_name,
        created_at,
        parent_tokens,
        child_tokens,
        doc_type,
        edital_ref,
        child_overlap_tokens,
        edital_cycle,
    )
