"""
api/routes/evaluation.py — Admin-only RAGAS evaluation endpoints.

NOTE: Evaluation runs are long-running (several minutes). These endpoints are
admin-only and should be called with an HTTP client configured for a long
timeout (e.g. 10–30 minutes). The request runs synchronously within the
FastAPI worker; no background task is used by design.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.evaluator import run_ragas_evaluation
from app.core.security import require_admin
from app.db.postgres import get_db
from app.models.evaluation import RagEvaluation
from app.schemas.evaluation import (
    EvaluationListItem,
    EvaluationRequest,
    EvaluationResponse,
)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

logger = logging.getLogger(__name__)


@router.post(
    "/run",
    response_model=EvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_evaluation(
    body: EvaluationRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> EvaluationResponse:
    """
    Trigger a RAGAS evaluation run against the live RAG pipeline.

    For each sample in the request the pipeline performs hybrid_search +
    rerank + answer generation, then RAGAS computes faithfulness,
    answer_relevancy, context_precision, context_recall, and
    answer_correctness.

    **Warning:** This endpoint can take several minutes to complete depending
    on the number of samples and hardware. Configure your HTTP client
    accordingly (recommended timeout: ≥ 10 minutes).
    """
    settings = get_settings()

    scores = await run_ragas_evaluation(body.samples, settings=settings)

    record = RagEvaluation(
        dataset_name=body.dataset_name,
        faithfulness=scores.get("faithfulness"),
        answer_relevancy=scores.get("answer_relevancy"),
        context_precision=scores.get("context_precision"),
        context_recall=scores.get("context_recall"),
        answer_correctness=scores.get("answer_correctness"),
        num_samples=scores["num_samples"],
        metadata=scores.get("metadata"),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return EvaluationResponse.model_validate(record)


@router.get(
    "/results",
    response_model=list[EvaluationListItem],
)
async def list_evaluation_results(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> list[EvaluationListItem]:
    """Return paginated evaluation runs ordered by most recent first."""
    result = await db.execute(
        select(RagEvaluation)
        .order_by(desc(RagEvaluation.created_at))
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [EvaluationListItem.model_validate(r) for r in rows]


@router.get(
    "/results/{evaluation_id}",
    response_model=EvaluationResponse,
)
async def get_evaluation_result(
    evaluation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> EvaluationResponse:
    """Return a single evaluation result including per-sample metadata."""
    result = await db.execute(
        select(RagEvaluation).where(RagEvaluation.id == evaluation_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation result not found",
        )
    return EvaluationResponse.model_validate(record)
