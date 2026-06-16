"""
reranker_debug.py — Diagnóstico de ranking para Q05, Q26 e Q29.

Roda dentro do container backend (docker exec) onde Qdrant e Ollama são acessíveis.
Mostra o ranking completo do cross-encoder (threshold=0.0) para identificar se o
chunk correto está no pool mas é downrankeado, ou se está ausente do pool.

Uso (de fora do container):
    docker exec propesqi_backend python /app/tests/reranker_debug.py
"""

import asyncio
import os
import sys

# Garante que as variáveis de ambiente do container estejam disponíveis
# (já estão injetadas pelo docker-compose, então basta importar normalmente).

QUERIES = {
    "Q05": "Qual é o período de vigência das bolsas PIBIC para o ciclo 2025/2026?",
    "Q26": "Por qual sistema as inscrições e os relatórios dos programas de iniciação científica são realizados na UFPI?",
    "Q29": "Um professor pode orientar seu filho(a) em qualquer programa de iniciação científica da UFPI?",
}

TOP_K_SEARCH = 30


async def debug_query(qid: str, query: str):
    from app.core.config import get_settings
    from app.db.rag_config import get_rag_config
    from app.db.reranker import rerank
    from app.db.search import hybrid_search
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    settings = get_settings()

    payload_filter = Filter(
        must_not=[
            FieldCondition(key="doc_type", match=MatchAny(any=["portaria", "relatorio"]))
        ]
    )

    print(f"\n{'='*70}")
    print(f"[{qid}] {query}")
    print(f"{'='*70}")

    # 1. Hybrid search (top 30, sem threshold)
    points = await hybrid_search(
        query,
        top_k=TOP_K_SEARCH,
        score_threshold=0.0,
        payload_filter=payload_filter,
        embedding_provider=settings.EMBEDDING_PROVIDER if hasattr(settings, "EMBEDDING_PROVIDER") else "local",
        embedding_model=settings.EMBEDDING_MODEL if hasattr(settings, "EMBEDDING_MODEL") else "bge-m3",
    )
    print(f"\nHybrid search: {len(points)} candidatos\n")

    # 2. Rerank com threshold=0.0 (ver TODOS os scores)
    reranked = await rerank(query, points, top_k=TOP_K_SEARCH, score_threshold=0.0)

    print(f"{'Pos':>3} {'Rerank':>7} {'RRF':>7}  {'DocType':12} {'Source':40} {'Pg':>4}  Preview")
    print("-" * 120)
    for i, pt in enumerate(reranked, 1):
        p = pt.payload or {}
        rerank_score = p.get("rerank_score", pt.score)
        rrf_score = p.get("score", 0)
        source = (p.get("display_name") or p.get("source", ""))[:38]
        doc_type = p.get("doc_type", "?")[:10]
        page = p.get("page_number", "?")
        preview = (p.get("text_preview") or p.get("text") or "")[:80].replace("\n", " ")
        print(f"{i:>3} {rerank_score:>7.4f} {pt.score:>7.4f}  {doc_type:12} {source:40} {str(page):>4}  {preview}")


async def main():
    # Importa settings para verificar embedding provider atual
    from app.core.config import get_settings
    settings = get_settings()
    print(f"embedding_provider={getattr(settings, 'EMBEDDING_PROVIDER', 'local')}  "
          f"embedding_model={getattr(settings, 'EMBEDDING_MODEL', 'bge-m3')}")

    for qid, query in QUERIES.items():
        await debug_query(qid, query)


if __name__ == "__main__":
    asyncio.run(main())
