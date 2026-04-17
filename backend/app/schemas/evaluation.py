from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EvaluationSample(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    ground_truth: str = Field(..., min_length=1, max_length=10_000)


class EvaluationRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1, max_length=200)
    samples: list[EvaluationSample] = Field(..., min_length=1, max_length=100)


class EvaluationResponse(BaseModel):
    id: UUID
    dataset_name: str
    faithfulness: Optional[float]
    answer_relevancy: Optional[float]
    context_precision: Optional[float]
    context_recall: Optional[float]
    answer_correctness: Optional[float]
    num_samples: int
    created_at: datetime
    metadata: Optional[Any]

    model_config = {"from_attributes": True}


class EvaluationListItem(BaseModel):
    id: UUID
    dataset_name: str
    faithfulness: Optional[float]
    answer_relevancy: Optional[float]
    context_precision: Optional[float]
    context_recall: Optional[float]
    answer_correctness: Optional[float]
    num_samples: int
    created_at: datetime

    model_config = {"from_attributes": True}
