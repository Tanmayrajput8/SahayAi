"""Endpoints for Demographic Fairness and Multilingual Model Evaluation."""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.fairness_eval import run_fairness_evaluation

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/benchmark",
    summary="Get Fairness & Demographic Benchmark Metrics",
    description="Returns empirical performance breakdown across English, Hindi, Marathi, and Code-Mixed emergency calls.",
)
def get_fairness_benchmark(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return run_fairness_evaluation(db=db)


@router.post(
    "/run-eval",
    summary="Trigger Model Evaluation Run",
    description="Executes full benchmark suite across labeled test cases and updates metrics.",
)
def trigger_fairness_evaluation(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return run_fairness_evaluation(db=db)
