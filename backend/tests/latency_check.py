# -*- coding: utf-8 -*-
"""
Mede TTFT (tempo ate o primeiro token de texto) e tempo total do /chat/stream.
Requer o stack Docker rodando.

Uso:
    python tests/latency_check.py
    python tests/latency_check.py --url http://localhost:3000/api --n 5
"""

import argparse
import statistics
import sys
import time

import httpx

PERGUNTAS = [
    "O que e PIBIC?",
    "Qual e o periodo de vigencia das bolsas PIBIC para o ciclo 2025/2026?",
    "Quantos pontos minimos o orientador precisa para ter o plano de trabalho analisado no ICV?",
    "Quem pode ser bolsista do PIBIC-Af?",
    "Por qual sistema sao feitas as inscricoes nos programas de iniciacao cientifica?",
]


def medir(url: str, pergunta: str) -> tuple[float, float]:
    """Retorna (ttft_s, total_s). TTFT = tempo ate o primeiro event: token."""
    payload = {"message": pergunta}
    t0 = time.perf_counter()
    ttft = None
    with httpx.Client(timeout=180.0) as client:
        with client.stream("POST", f"{url}/chat/stream", json=payload) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                if ttft is None and b"event: token" in chunk:
                    ttft = time.perf_counter() - t0
    total = time.perf_counter() - t0
    return ttft if ttft is not None else total, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:3000/api")
    parser.add_argument("--n", type=int, default=3, help="Numero de perguntas a testar (1-5)")
    args = parser.parse_args()

    perguntas = PERGUNTAS[: min(args.n, len(PERGUNTAS))]

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(f"Testando {len(perguntas)} perguntas em {args.url}\n")
    print(f"{'#':<3} {'TTFT':>8} {'Total':>8}  Pergunta")
    print("-" * 70)

    ttfts, totais = [], []
    for i, pergunta in enumerate(perguntas, 1):
        try:
            ttft, total = medir(args.url, pergunta)
            ttfts.append(ttft)
            totais.append(total)
            resumo = pergunta[:45] + "..." if len(pergunta) > 45 else pergunta
            print(f"{i:<3} {ttft:>7.1f}s {total:>7.1f}s  {resumo}")
        except Exception as e:
            print(f"{i:<3} {'ERRO':>8} {'ERRO':>8}  {e}")

    if ttfts:
        media_ttft = statistics.mean(ttfts)
        print("-" * 70)
        print(f"{'Media':<5} {media_ttft:>7.1f}s {statistics.mean(totais):>7.1f}s")
        if len(ttfts) > 1:
            print(f"{'Max':<5} {max(ttfts):>7.1f}s {max(totais):>7.1f}s")

        print()
        if media_ttft <= 5:
            print("TTFT: bom (<=5s)")
        elif media_ttft <= 12:
            print("TTFT: aceitavel (5-12s)")
        else:
            print("TTFT: lento (>12s) — verificar se contextual_compression esta desabilitado no admin")


if __name__ == "__main__":
    main()
