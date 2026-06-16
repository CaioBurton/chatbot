"""
finetune_reranker.py — Fine-tunes BAAI/bge-reranker-v2-m3 com pares do domínio PROPESQI/UFPI.

Carrega os pares gerados por build_finetune_dataset.py e treina o cross-encoder
para corrigir o viés lexical identificado em Q29 ("filho" ≠ "cônjuge") e outros
casos de mismatch intra-domínio.

O modelo fine-tunado é salvo em /app/models/reranker-propesqi/ e pode ser ativado
definindo RERANKER_MODEL=/app/models/reranker-propesqi no .env.

Uso (dentro do container):
    docker exec propesqi_backend sh -c "cd /app && PYTHONPATH=/app python tests/finetune_reranker.py"

Ou com GPU no host (se CUDA disponível):
    python backend/tests/finetune_reranker.py --data backend/tests/finetune_training_data.json
                                               --output backend/models/reranker-propesqi
"""

import argparse
import json
import math
from pathlib import Path

DEFAULT_DATA = Path("tests/finetune_training_data.json")
DEFAULT_OUTPUT = Path("models/reranker-propesqi")
BASE_MODEL = "BAAI/bge-reranker-v2-m3"
EPOCHS = 4
BATCH_SIZE = 2  # pequeno para caber na VRAM junto com Ollama (~8 GB)
WARMUP_STEPS = 10


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def evaluate_pairs(model, pairs: list[dict], label: str = "eval") -> dict:
    """Calcula accuracy@threshold=0.5 nos pares de avaliação."""
    from sentence_transformers import InputExample
    texts = [(p["query"], p["passage"]) for p in pairs]
    raw_scores = model.predict(texts)
    scores = [_sigmoid(float(s)) for s in raw_scores]

    correct = 0
    for score, pair in zip(scores, pairs):
        pred = 1.0 if score >= 0.5 else 0.0
        if pred == pair["label"]:
            correct += 1

    acc = correct / len(pairs) if pairs else 0.0
    print(f"  [{label}] accuracy@0.5={acc:.3f}  ({correct}/{len(pairs)})")
    return {"accuracy": acc, "n": len(pairs)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    print(f"Carregando dados de: {args.data}")
    pairs = json.loads(args.data.read_text(encoding="utf-8"))
    print(f"  Total de pares: {len(pairs)}")
    pos = sum(1 for p in pairs if p["label"] == 1.0)
    neg = sum(1 for p in pairs if p["label"] == 0.0)
    print(f"  Positivos: {pos}  Negativos: {neg}")

    # Separar pares problemáticos para avaliação específica
    target_qids = {"Q05", "Q15", "Q26", "Q29"}
    eval_pairs = [p for p in pairs if p.get("qid") in target_qids]
    train_pairs = pairs  # treina em todos

    # Importar dependências após confirmação dos dados
    from sentence_transformers import CrossEncoder, InputExample
    from torch.utils.data import DataLoader

    print(f"\nCarregando modelo base: {BASE_MODEL}")
    model = CrossEncoder(BASE_MODEL, num_labels=1, max_length=512)

    print("\n--- Avaliação PRÉ-treino ---")
    if eval_pairs:
        evaluate_pairs(model, eval_pairs, "pré-treino (targets)")
    evaluate_pairs(model, train_pairs, "pré-treino (total)")

    # Construir DataLoader
    samples = [
        InputExample(texts=[p["query"], p["passage"]], label=float(p["label"]))
        for p in train_pairs
    ]
    train_loader = DataLoader(samples, shuffle=True, batch_size=args.batch_size)

    # Fine-tuning
    print(f"\nIniciando fine-tuning: {args.epochs} épocas, batch_size={args.batch_size}")
    args.output.mkdir(parents=True, exist_ok=True)

    import os
    import torch
    # Expandable segments reduzem fragmentação de VRAM
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    use_amp = torch.cuda.is_available()
    if use_amp:
        print("  AMP (FP16) ativado para reduzir uso de VRAM")

    model.fit(
        train_dataloader=train_loader,
        epochs=args.epochs,
        warmup_steps=WARMUP_STEPS,
        output_path=str(args.output),
        show_progress_bar=True,
        use_amp=use_amp,
    )

    print("\n--- Avaliação PÓS-treino ---")
    if eval_pairs:
        evaluate_pairs(model, eval_pairs, "pós-treino (targets)")
    evaluate_pairs(model, train_pairs, "pós-treino (total)")

    # Salvar modelo final
    model.save(str(args.output))
    print(f"\nModelo salvo em: {args.output}")
    print(f"\nPara ativar: adicione RERANKER_MODEL={args.output} ao .env e rebuilde o backend.")


if __name__ == "__main__":
    main()
