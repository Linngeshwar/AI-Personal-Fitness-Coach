from typing import Literal

from pydantic import BaseModel

from schemas.profile import Equipment, Injury


class ConstraintDelta(BaseModel):
    session_minutes_override: int | None = None
    equipment_override: list[Equipment] = []
    new_injuries: list[Injury] = []
    energy: Literal["low", "normal", "high"] = "normal"
    intent: Literal["train", "skip", "shorten", "substitute"]


class AdjustIn(BaseModel):
    text: str
