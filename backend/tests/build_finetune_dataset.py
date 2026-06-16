"""
build_finetune_dataset.py — Extrai pares de treino do Qdrant para fine-tuning do reranker.

Para cada query do groundtruth:
  - Executa hybrid_search(top_k=30) sem threshold
  - Identifica o chunk positivo usando âncoras de palavras-chave (groundtruth)
  - Usa os top-ranked chunks que NÃO são positivos como hard negatives
  - Salva pares {query, passage, label} em JSON

Âncoras explícitas são definidas para as queries problemáticas (Q05, Q26, Q29, Q15).
Para as demais queries, o chunk na posição 1 é assumido como positivo (o modelo já
acerta essas perguntas — queremos manter o desempenho enquanto corrigimos as ruins).

Uso (dentro do container):
    docker exec propesqi_backend sh -c "cd /app && PYTHONPATH=/app python tests/build_finetune_dataset.py"
"""

import asyncio
import csv
import json
import re
from pathlib import Path

GROUNDTRUTH_CSV = Path("tests/groundtruth_chatbot_rag.csv")
OUTPUT_JSON = Path("tests/finetune_training_data.json")

# Âncoras de palavras-chave para identificar o chunk CORRETO de cada query.
# Ao menos UMA das strings listadas deve aparecer no texto do chunk para ele
# ser considerado positivo para aquela query.
POSITIVE_ANCHORS: dict[str, list[str]] = {
    "Q05": ["01/09/2025", "31/08/2026", "setembro de 2025", "agosto de 2026",
            "10.1.2", "início em 1º de setembro"],
    "Q09": ["SIGAA", "sigaa", "11 de março", "08 de abril", "11/03", "08/04"],
    "Q13": ["SIGAA", "não envio", "Relatório Final", "perda do direito"],
    "Q14": ["17 de março", "31 de março", "17/03", "31/03", "relatório parcial"],
    "Q15": ["5 pontos", "cinco pontos", "mínimo de 5", "mínimo 5",
            "habilitado", "ICV", "Seção 6.1.2.2", "somatório"],
    "Q26": ["SIGAA", "sigaa.ufpi.br", "via SIGAA", "Sistema Integrado",
            "inscrições via", "relatórios.*SIGAA", "SIGAA.*relatório"],
    "Q29": ["vedado", "cônjuge", "parente em linha reta", "terceiro grau",
            "conflito de interesses", "orientador.*cônjuge", "orientador.*parente"],
}

# Número máximo de hard negatives por query (chunks top-ranked mas incorretos)
MAX_HARD_NEGATIVES = 3
# Número de positivos por query para as queries "fáceis" (top-1 assumed correct)
EASY_QUERY_POSITIVE_COUNT = 1


def _matches_anchors(text: str, anchors: list[str]) -> bool:
    """Retorna True se o texto contiver ao menos uma âncora (regex)."""
    text_lower = text.lower()
    for anchor in anchors:
        if re.search(anchor.lower(), text_lower):
            return True
    return False


def _get_chunk_text(payload: dict) -> str:
    return (
        payload.get("parent_text")
        or payload.get("text")
        or payload.get("text_preview")
        or ""
    )


async def build_pairs_for_query(
    qid: str,
    query: str,
    anchors: list[str] | None,
    settings,
) -> list[dict]:
    from app.db.search import hybrid_search
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    payload_filter = Filter(
        must_not=[
            FieldCondition(key="doc_type", match=MatchAny(any=["portaria", "relatorio"]))
        ]
    )

    points = await hybrid_search(
        query,
        top_k=30,
        score_threshold=0.0,
        payload_filter=payload_filter,
        embedding_provider=getattr(settings, "EMBEDDING_PROVIDER", "local"),
        embedding_model=getattr(settings, "EMBEDDING_MODEL", "bge-m3"),
    )

    if not points:
        print(f"  [{qid}] Nenhum resultado — pulando")
        return []

    pairs: list[dict] = []
    positives_found = 0
    negatives_added = 0

    if anchors:
        # Modo âncora: identifica positivos por palavras-chave
        positive_indices = set()
        for i, pt in enumerate(points):
            text = _get_chunk_text(pt.payload or {})
            if _matches_anchors(text, anchors):
                positive_indices.add(i)
                pairs.append({
                    "query": query,
                    "passage": text,
                    "label": 1.0,
                    "qid": qid,
                    "pos": i + 1,
                })
                positives_found += 1

        if positives_found == 0:
            # Scroll adicional: busca explícita em todos os chunks do Qdrant
            print(f"  [{qid}] Nenhum positivo via search — tentando scroll do Qdrant...")
            from app.db.qdrant import get_qdrant_client, COLLECTION_NAME
            client = get_qdrant_client()
            offset = None
            while True:
                results, offset = await client.scroll(
                    collection_name=COLLECTION_NAME,
                    limit=200,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for pt in results:
                    p = pt.payload or {}
                    doc_type = p.get("doc_type", "")
                    if doc_type in ("portaria", "relatorio"):
                        continue
                    text = _get_chunk_text(p)
                    if _matches_anchors(text, anchors):
                        pairs.append({
                            "query": query,
                            "passage": text,
                            "label": 1.0,
                            "qid": qid,
                            "pos": "scroll",
                        })
                        positives_found += 1
                        if positives_found >= 3:
                            break
                if offset is None or positives_found >= 3:
                    break

        # Hard negatives: top chunks que NÃO são positivos
        for i, pt in enumerate(points):
            if i not in positive_indices and negatives_added < MAX_HARD_NEGATIVES:
                text = _get_chunk_text(pt.payload or {})
                if text:
                    pairs.append({
                        "query": query,
                        "passage": text,
                        "label": 0.0,
                        "qid": qid,
                        "pos": i + 1,
                    })
                    negatives_added += 1

    else:
        # Modo fácil: top-1 é positivo, top-2 a top-(MAX_HARD_NEGATIVES+1) são negativos
        if points:
            text = _get_chunk_text(points[0].payload or {})
            if text:
                pairs.append({
                    "query": query,
                    "passage": text,
                    "label": 1.0,
                    "qid": qid,
                    "pos": 1,
                })
                positives_found = 1

            for pt in points[1: MAX_HARD_NEGATIVES + 1]:
                text = _get_chunk_text(pt.payload or {})
                if text:
                    pairs.append({
                        "query": query,
                        "passage": text,
                        "label": 0.0,
                        "qid": qid,
                        "pos": points.index(pt) + 1,
                    })
                    negatives_added += 1

    print(f"  [{qid}] positivos={positives_found}  hard_negatives={negatives_added}")
    return pairs


async def main():
    from app.core.config import get_settings
    settings = get_settings()

    with GROUNDTRUTH_CSV.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    all_pairs: list[dict] = []

    for row in rows:
        qid = row["id"]
        query = row["pergunta"]
        anchors = POSITIVE_ANCHORS.get(qid)
        print(f"[{qid}] Processando: {query[:70]}...")
        pairs = await build_pairs_for_query(qid, query, anchors, settings)
        all_pairs.extend(pairs)

    OUTPUT_JSON.write_text(json.dumps(all_pairs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTotal de pares: {len(all_pairs)}")
    pos = sum(1 for p in all_pairs if p["label"] == 1.0)
    neg = sum(1 for p in all_pairs if p["label"] == 0.0)
    print(f"  Positivos: {pos}  Negativos: {neg}")
    print(f"Salvo em: {OUTPUT_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
