"""
core/evaluator.py — RAGAS-based evaluation pipeline for the RAG system.

Imports ragas lazily so the module is importable even if the package is not
installed; missing ragas raises HTTPException 503 at evaluation time rather
than crashing the entire application on startup.

The evaluation mirrors rag_stream() stages 2–8 but runs non-streaming and
without DB side-effects (no chat session / message persistence).
"""

import asyncio
import logging
import math
from typing import Any

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.rag_engine import _LOCAL_MODEL, _ollama_generate
from app.db.reranker import rerank
from app.db.search import expand_to_parents, hybrid_search
from app.schemas.evaluation import EvaluationSample
from qdrant_client.models import ScoredPoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _retrieve_and_answer(sample: EvaluationSample, settings) -> dict:
    """
    For a single EvaluationSample:
      1. Run hybrid_search + expand_to_parents + rerank (mirrors stages 2–4, 6).
      2. Call _ollama_generate to produce a non-streaming answer (mirrors stage 8).

    Returns a dict with keys: question, answer, contexts, ground_truth.
    """
    query = sample.question

    # Stage 2/3: HyDE + multi-query (simplified — single hybrid_search call
    # to avoid multiplying Ollama calls in an already-long evaluation run).
    points: list[ScoredPoint] = await hybrid_search(query, top_k=20)

    # Stage 4: Rerank
    reranked = await rerank(
        query,
        points,
        top_k=settings.RERANKER_TOP_K,
        score_threshold=settings.RERANKER_SCORE_THRESHOLD,
    )

    # Stage 6: Expand to parents
    parents = expand_to_parents(reranked)[:5]

    # Build flat list of context strings for RAGAS
    contexts = [p.get("parent_text", "") for p in parents if p.get("parent_text")]
    if not contexts:
        contexts = [""]

    # Stage 8: Non-streaming answer generation
    # Truncate query for prompt (mirrors rag_engine._compress_context guard).
    query_for_prompt = query[:1000]
    if parents:
        context_block = "\n\n".join(
            # Truncate source name to 200 chars, matching rag_engine._build_context.
            f"[{i + 1}] {p.get('source', '')[:200]} (p. {p.get('page_number') or '?'})\n{p.get('parent_text', '')}"
            for i, p in enumerate(parents)
        )
    else:
        context_block = ""

    answer_prompt = (
        "Você é um assistente da PROPESQI/UFPI. "
        "Responda à pergunta com base exclusivamente nos documentos abaixo. "
        "Se a informação não estiver nos documentos, diga que não possui essa informação.\n\n"
        f"Documentos:\n{context_block}\n\n"
        f"Pergunta: {query_for_prompt}"
    )
    answer = await _ollama_generate(
        answer_prompt,
        temperature=0.1,
        settings=settings,
    )

    return {
        "question": query,
        "answer": answer,
        "contexts": contexts,
        "ground_truth": sample.ground_truth,
    }


def _safe_float(value) -> float | None:
    """Convert a RAGAS metric result to float, returning None on failure."""
    try:
        if value is None:
            return None
        f = float(value)
        # NaN / Inf are not useful to persist
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    except (TypeError, ValueError):
        return None


def _sanitize_for_json(obj: Any) -> Any:
    """
    Recursively convert non-JSON-serializable values (numpy scalars, NaN, Inf)
    to plain Python types that PostgreSQL JSONB / asyncpg can accept.
    NaN and Inf become None; numpy scalars are cast to int or float.
    Called on the RAGAS per-sample DataFrame rows before DB persistence.
    """
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    # numpy scalars, pandas Timestamps, and other numeric-like types
    try:
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        i = int(f)
        return i if f == i else f
    except (TypeError, ValueError, OverflowError):
        return str(obj)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def run_ragas_evaluation(
    samples: list[EvaluationSample],
    settings=None,
) -> dict[str, Any]:
    """
    Run RAGAS metrics against the live RAG pipeline.

    Parameters
    ----------
    samples:
        List of EvaluationSample with question + ground_truth pairs.
    settings:
        App settings; if None, loaded via get_settings().

    Returns
    -------
    dict with keys:
        faithfulness, answer_relevancy, context_precision, context_recall,
        answer_correctness  (float or None)
        num_samples         (int)
        metadata            (dict with per_sample list and any errors)

    Raises
    ------
    HTTPException 503  if the ragas package is not installed.
    HTTPException 500  if the RAGAS evaluate() call itself fails.
    """
    # Lazy import — graceful degradation when ragas is not installed
    try:
        from ragas import evaluate as ragas_evaluate
        from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.metrics import (
            AnswerCorrectness,
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
        from langchain_ollama import ChatOllama, OllamaEmbeddings
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"RAGAS evaluation is unavailable: {exc}",
        ) from exc

    if settings is None:
        settings = get_settings()

    # ------------------------------------------------------------------ #
    # 1. Retrieve contexts and generate answers for every sample          #
    # ------------------------------------------------------------------ #
    errors: list[str] = []
    row_tasks = [_retrieve_and_answer(s, settings) for s in samples]
    row_results = await asyncio.gather(*row_tasks, return_exceptions=True)

    rows: list[dict] = []
    for i, result in enumerate(row_results):
        if isinstance(result, BaseException):
            msg = f"Sample {i} retrieval/answer failed: {result}"
            logger.warning(msg)
            errors.append(msg)
            # Insert a fallback row so RAGAS still runs on surviving samples
            rows.append({
                "question": samples[i].question,
                "answer": "",
                "contexts": [""],
                "ground_truth": samples[i].ground_truth,
            })
        else:
            rows.append(result)

    # Guard: if every sample failed, there is nothing meaningful for RAGAS to
    # score — abort rather than persisting silently invalid metrics.
    if len(errors) == len(samples):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "All samples failed during retrieval/answer generation. "
                "Check Qdrant and Ollama connectivity."
            ),
        )

    # ------------------------------------------------------------------ #
    # 2. Build RAGAS EvaluationDataset                                    #
    # ------------------------------------------------------------------ #
    ragas_samples = [
        SingleTurnSample(
            user_input=r["question"],
            response=r["answer"],
            retrieved_contexts=r["contexts"],
            reference=r["ground_truth"],
        )
        for r in rows
    ]
    dataset = EvaluationDataset(samples=ragas_samples)

    # ------------------------------------------------------------------ #
    # 3. Configure RAGAS to use local Ollama LLM + embeddings             #
    # ------------------------------------------------------------------ #
    ollama_base = settings.OLLAMA_BASE_URL  # e.g. http://ollama:11434
    langchain_llm = ChatOllama(base_url=ollama_base, model=_LOCAL_MODEL, temperature=0.0)
    langchain_embeddings = OllamaEmbeddings(base_url=ollama_base, model="bge-m3")

    ragas_llm = LangchainLLMWrapper(langchain_llm)
    ragas_embeddings = LangchainEmbeddingsWrapper(langchain_embeddings)

    metrics = [
        Faithfulness(llm=ragas_llm),
        AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embeddings),
        ContextPrecision(llm=ragas_llm),
        ContextRecall(llm=ragas_llm),
        AnswerCorrectness(llm=ragas_llm),
    ]

    # ------------------------------------------------------------------ #
    # 4. Run evaluation                                                    #
    # ------------------------------------------------------------------ #
    try:
        # ragas.evaluate() is synchronous CPU/IO-bound — run in thread executor
        # to avoid blocking the event loop.
        loop = asyncio.get_running_loop()
        result_ds = await loop.run_in_executor(
            None,
            lambda: ragas_evaluate(dataset=dataset, metrics=metrics),
        )
    except Exception as exc:
        logger.exception("RAGAS evaluate() raised an exception")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAGAS evaluation failed: {exc}",
        ) from exc

    # ------------------------------------------------------------------ #
    # 5. Extract aggregate scores                                          #
    # ------------------------------------------------------------------ #
    scores: dict[str, float | None] = {}
    per_sample: list = []
    try:
        # Store the DataFrame once to avoid double conversion and potential
        # state inconsistency if the result object is consumed on first access.
        df = result_ds.to_pandas()
        score_dict = df.mean(numeric_only=True).to_dict()
        # _sanitize_for_json converts numpy scalars / NaN / Inf to plain Python
        # types; asyncpg cannot serialize numpy types to PostgreSQL JSONB.
        per_sample = _sanitize_for_json(df.to_dict(orient="records"))
    except Exception:
        score_dict = {}

    scores["faithfulness"] = _safe_float(score_dict.get("faithfulness"))
    scores["answer_relevancy"] = _safe_float(score_dict.get("answer_relevancy"))
    scores["context_precision"] = _safe_float(score_dict.get("context_precision"))
    scores["context_recall"] = _safe_float(score_dict.get("context_recall"))
    scores["answer_correctness"] = _safe_float(score_dict.get("answer_correctness"))

    return {
        **scores,
        "num_samples": len(samples),
        "metadata": {
            "per_sample": per_sample,
            "retrieval_errors": errors,
        },
    }
