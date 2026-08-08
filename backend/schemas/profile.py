from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Goal(str, Enum):
    fat_loss = "fat_loss"
    muscle_gain = "muscle_gain"
    strength = "strength"
    endurance = "endurance"
    general = "general"


class Experience(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class Equipment(str, Enum):
    none = "none"
    dumbbells = "dumbbells"
    barbell = "barbell"
    machines = "machines"
    bands = "bands"
    pullup_bar = "pullup_bar"
    full_gym = "full_gym"


class Injury(str, Enum):
    knee = "knee"
    lower_back = "lower_back"
    shoulder = "shoulder"
    wrist = "wrist"
    ankle = "ankle"


class SafetyFlags(BaseModel):
    under_18: bool = False
    pregnant_or_postpartum: bool = False
    cardiac_or_bp_condition: bool = False
    diabetes: bool = False
    eating_disorder_history: bool = False
    chest_pain_on_exertion: bool = False


class UserProfile(BaseModel):
    goal: Goal
    experience: Experience
    days_per_week: int = Field(ge=2, le=6)
    session_minutes: Literal[20, 30, 45, 60]
    equipment: list[Equipment]
    injuries: list[Injury] = []
    height_cm: float
    weight_kg: float
    age: int
    sex: Literal["male", "female", "other"]
    activity_level: float = Field(ge=1.2, le=1.9)
    safety: SafetyFlags


class ScreeningResult(BaseModel):
    nutrition_enabled: bool = True
    requires_clearance: bool = False
    message: str | None = None
    volume_cap: float = 1.0
