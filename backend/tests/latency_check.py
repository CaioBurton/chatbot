"""
Mede TTFB e tempo total de resposta do endpoint /chat/stream.
Requer o stack Docker rodando em localhost:8000.

Uso:
    python tests/latency_check.py
    python tests/latency_check.py --url http://localhost:8000 --n 5
"""

import argparse
import statistics
import sys
import time

import httpx

PERGUNTAS = [
    "O que é PIBIC?",
    "Qual é o período de vigência das bolsas PIBIC para o ciclo 2025/2026?",
    "Quantos pontos mínimos o orientador precisa para ter o plano de trabalho analisado no ICV?",
    "Quem pode ser bolsista do PIBIC-Af?",
    "Por qual sistema são feitas as inscrições nos programas de iniciação científica?",
]


def medir(url: str, pergunta: str) -> tuple[float, float]:
    """Retorna (ttfb_ms, total_ms)."""
    payload = {"message": pergunta}
    t0 = time.perf_counter()
    ttfb_ms = None
    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", f"{url}/chat/stream", json=payload) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                if ttfb_ms is None and chunk.strip():
                    ttfb_ms = (time.perf_counter() - t0) * 1000
    total_ms = (time.perf_counter() - t0) * 1000
    return ttfb_ms or total_ms, total_ms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--n", type=int, default=3, help="Número de perguntas a testar (1-5)")
    args = parser.parse_args()

    perguntas = PERGUNTAS[: min(args.n, len(PERGUNTAS))]

    print(f"Testando {len(perguntas)} perguntas em {args.url}\n")
    print(f"{'#':<3} {'TTFB':>8} {'Total':>8}  Pergunta")
    print("-" * 70)

    ttfbs, totais = [], []
    for i, pergunta in enumerate(perguntas, 1):
        try:
            ttfb, total = medir(args.url, pergunta)
            ttfbs.append(ttfb)
            totais.append(total)
            resumo = pergunta[:45] + "..." if len(pergunta) > 45 else pergunta
            print(f"{i:<3} {ttfb/1000:>7.1f}s {total/1000:>7.1f}s  {resumo}")
        except Exception as e:
            print(f"{i:<3} {'ERRO':>8} {'ERRO':>8}  {e}")

    if ttfbs:
        print("-" * 70)
        print(f"{'Média':<3} {statistics.mean(ttfbs)/1000:>7.1f}s {statistics.mean(totais)/1000:>7.1f}s")
        if len(ttfbs) > 1:
            print(f"{'Máx':<3} {max(ttfbs)/1000:>7.1f}s {max(totais)/1000:>7.1f}s")

        print()
        ttfb_medio = statistics.mean(ttfbs) / 1000
        if ttfb_medio <= 5:
            print("TTFB: bom (≤5s — usuário vê resposta rapidamente)")
        elif ttfb_medio <= 10:
            print("TTFB: aceitável (5–10s)")
        else:
            print("TTFB: lento (>10s — considere desabilitar contextual_compression no admin)")


if __name__ == "__main__":
    main()
