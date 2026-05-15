"""Compatibility facade for domain layer modules."""

from app.domain.models.metrics import calc_metrics, calc_yoy
from app.domain.policies.ranking import grade_summary, rank_forecast_yoy, rank_next_yoy, rank_progress, rank_symbol
from app.domain.usecases.fundamental_analysis import FundamentalAnalysisService

progress_rank = rank_progress

__all__ = [
    "FundamentalAnalysisService",
    "calc_yoy",
    "calc_metrics",
    "rank_progress",
    "progress_rank",
    "rank_forecast_yoy",
    "rank_next_yoy",
    "rank_symbol",
    "grade_summary",
]
