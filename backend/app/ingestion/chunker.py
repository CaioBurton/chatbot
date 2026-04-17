import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any


def _split_by_tokens(text: str, max_tokens: int, enc: Any) -> list[str]:
    """Greedily split text into segments that each fit within max_tokens."""
    words = text.split()
    if not words:
        return []

    segments: list[str] = []
    current_words: list[str] = []
    current_count = 0

    for word in words:
        word_token_count = len(enc.encode(word, disallowed_special=()))
        if current_count + word_token_count > max_tokens and current_words:
            segments.append(" ".join(current_words))
            current_words = [word]
            current_count = word_token_count
        else:
            current_words.append(word)
            current_count += word_token_count

    if current_words:
        segments.append(" ".join(current_words))

    return segments


def _sync_chunk(
    pages: list[dict[str, Any]],
    doc_id: str,
    source: str,
    created_at: str,
    parent_tokens: int = 512,
    child_tokens: int = 128,
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
        text: str = page["text"]
        if not text.strip():
            continue

        parent_texts = _split_by_tokens(text, parent_tokens, enc)

        for parent_text in parent_texts:
            parent_id = str(uuid.uuid4())
            child_texts = _split_by_tokens(parent_text, child_tokens, enc)

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
                            "page_number": page_number,
                            "chunk_index": global_chunk_index,
                            "type": "child",
                            "created_at": created_at,
                            "hash": chunk_hash,
                            "parent_text": parent_text,
                        },
                    }
                )
                global_chunk_index += 1

    return chunks


async def chunk_pages(
    pages: list[dict[str, Any]],
    doc_id: str,
    source: str,
    parent_tokens: int = 512,
    child_tokens: int = 128,
) -> list[dict[str, Any]]:
    """Async wrapper: runs the CPU-bound chunking in the default thread executor."""
    created_at = datetime.now(timezone.utc).isoformat()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _sync_chunk, pages, doc_id, source, created_at, parent_tokens, child_tokens
    )
