"""Verifica se existe algum chunk com 'SIGAA' indexado no Qdrant."""
import asyncio
from app.db.qdrant import get_qdrant_client, COLLECTION_NAME


async def main():
    client = get_qdrant_client()
    offset = None
    found = []
    total = 0
    while True:
        results, offset = await client.scroll(
            collection_name=COLLECTION_NAME,
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        total += len(results)
        for pt in results:
            p = pt.payload or {}
            texts = " ".join(filter(None, [
                p.get("text", ""),
                p.get("text_preview", ""),
                p.get("parent_text", ""),
            ]))
            if "SIGAA" in texts or "sigaa" in texts.lower():
                found.append((
                    p.get("source", "")[:50],
                    p.get("page_number", "?"),
                    p.get("doc_type", "?"),
                    texts[:150],
                ))
        if offset is None:
            break

    print(f"Total chunks escaneados: {total}")
    print(f"Chunks com 'SIGAA': {len(found)}")
    for src, pg, dt, txt in found:
        print(f"\n  Fonte: {src}  pg={pg}  doc_type={dt}")
        print(f"  Texto: {txt}")


if __name__ == "__main__":
    asyncio.run(main())
