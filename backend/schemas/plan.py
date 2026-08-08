from datetime import date
from typing import Literal

from pydantic import BaseModel


class PlanBlock(BaseModel):
    exercise_id: str          # MUST exist in exercises table
    order: int
    sets: int
    rep_low: int
    rep_high: int
    rest_seconds: int
    rir: int
    note: str | None = None          # Gemini may write this
    swap_reason: str | None = None   # Gemini may write this


class PlanDay(BaseModel):
    date: date
    type: Literal["workout", "rest", "active_recovery"]
    focus: str | None
    est_minutes: int
    blocks: list[PlanBlock]


class Plan(BaseModel):
    plan_id: str
    user_id: str
    week_start: date
    generated_by: Literal["deterministic", "gemini_refined"]
    volume_multiplier: float
    days: list[PlanDay]


class PlanState(BaseModel):
    """Carries forward what Layer 5's adherence engine adjusts week to week.
    Foundation pass only ever uses the defaults (no adherence engine yet)."""
    volume_multiplier: float = 1.0
    week_number: int = 1
