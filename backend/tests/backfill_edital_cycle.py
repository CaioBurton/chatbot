"""
backfill_edital_cycle.py — One-off retroactive edital_cycle tagging.

`edital_cycle` was added after most editais/aditivos were already indexed, so
every existing document has edital_cycle=NULL in both Postgres and the Qdrant
payload. rag_engine.py's active_edital_cycle guard treats NULL as "eligible in
any cycle" — meaning it currently does nothing to disambiguate the 2025/2026
vs 2026/2027 editais, which compete purely on semantic similarity (see
Passo 22/23 analysis in relatorio_otimizacao_rag.md, Q22/Q34/Q41).

This script tags the recurring PIBIC/PIBITI/ICV/PIBIC-EM editais and aditivos
by cycle, inferred from filename patterns confirmed against each document's
own indexed text (not just guessed from the filename). One-off calls with no
competing-cycle counterpart (PROINFRA, GAAI, DesafioStartUFPI, Centros
Temáticos, Ideathon CTT, Agricultura Familiar FINEP, Chamada Pública
Sociedades Protetoras) are deliberately left untagged — tagging them changes
nothing in retrieval (no other-cycle version exists to disambiguate against)
and risks a wrong guess for no benefit.

edital_cycle is not chunking-relevant, so PATCH /documents/{doc_id} (which
purges and re-ingests every chunk) would be wasteful here — this script
updates Postgres directly and calls Qdrant's set_payload so only the
edital_cycle key changes, with no re-embedding.

Must run inside the backend container as a module (needs DATABASE_URL,
QDRANT_URL, and the app's own modules on sys.path — `python tests/x.py`
doesn't add /app to sys.path, `-m` does):

    docker compose -f docker-compose.aws.yml exec backend \\
        python -m tests.backfill_edital_cycle            # dry-run (default)
    docker compose -f docker-compose.aws.yml exec backend \\
        python -m tests.backfill_edital_cycle --apply     # writes changes
"""

import argparse
import asyncio
import sys

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select

from app.db.postgres import AsyncSessionLocal
from app.db.qdrant import COLLECTION_NAME, get_qdrant_client
from app.models.document import Document

# original_name -> edital_cycle. Confirmed either by the "N-2025-2026_..." /
# "NNNEdital_..._2026-2027_..." filename pattern, or (for the three
# 2026-04-06 aditivos, whose filenames carry a signing date, not a cycle) by
# reading the indexed parent_text, which opens with "EDITAL N° X/2026 ...
# 2026/2027" for all three.
_CYCLE_MAP: dict[str, str] = {
    # 2025/2026
    "1-2025-2026_Edital_PIBIC_e_PIBIC_Af.pdf": "2025/2026",
    "2-2025-2026_Edital_PIBITI.pdf": "2025/2026",
    "3-2025-2026_Edital_ICV.pdf": "2025/2026",
    "4-2025-2026_Edital_PIBIC-EM.pdf": "2025/2026",
    "Aditivo_1_-_ICV_2025-2026_assinado_assinado.pdf": "2025/2026",
    "Aditivo_2_-_ICV_2025-2026_assinado_assinado.pdf": "2025/2026",
    "Aditivo_1_-_PIBIC-EM_2025-2026_assinado_assinado.pdf": "2025/2026",
    "Aditivo_1_-_PIBIC_2025-2026_assinado_assinado.pdf": "2025/2026",
    "Aditivo_1_-_PIBITI_2025-2026_assinado_assinado.pdf": "2025/2026",
    # 2026/2027
    "000Edital_PIBIC_2026-2027_assinado_assinado.pdf": "2026/2027",
    "001Edital_PIBIC-EM_2026-2027_28129_assinado_assinado.pdf": "2026/2027",
    "002Edital_PIBITI_2026-2027_assinado_assinado.pdf": "2026/2027",
    "2026-04-06_PIBIC_Aditivo_01_5D_29_assinado_assinado.pdf": "2026/2027",
    "2026-04-06_PIBIC-EM_Aditivo_01_5D_29_assinado_assinado.pdf": "2026/2027",
    "2026-04-06_PIBITI_Aditivo_01_5D_29_assinado_assinado.pdf": "2026/2027",
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()

    qdrant = get_qdrant_client()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(Document.original_name.in_(_CYCLE_MAP.keys()))
        )
        docs = list(result.scalars().all())

        found_names = {d.original_name for d in docs}
        missing = set(_CYCLE_MAP) - found_names
        if missing:
            print(f"WARNING: {len(missing)} filenames in _CYCLE_MAP not found in documents table:", file=sys.stderr)
            for name in sorted(missing):
                print(f"  - {name}", file=sys.stderr)

        print(f"{'APPLYING' if args.apply else 'DRY-RUN'}: {len(docs)} documents matched\n")

        for doc in docs:
            cycle = _CYCLE_MAP[doc.original_name]
            print(f"[{doc.id}] {doc.original_name} -> edital_cycle={cycle!r} (current: {doc.edital_cycle!r})")

            if not args.apply:
                continue

            doc.edital_cycle = cycle
            await qdrant.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"edital_cycle": cycle},
                points=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=str(doc.id)))]
                ),
            )

        if args.apply:
            await db.commit()
            print(f"\n{len(docs)} documents updated in Postgres + Qdrant.")
        else:
            print("\nDry-run only — pass --apply to write these changes.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
