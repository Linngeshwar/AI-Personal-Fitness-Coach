"""
Layer 4 -- the validator. Anything Gemini's Call B returns passes through
here before a human ever sees it. Only the hard rules the spec gives
explicitly are implemented; nutrition rules (KCAL_FLOOR, PROTEIN_CEILING,
FOOD_ID_EXISTS, SCREENING_GATE) are skipped -- there's no food table yet.
"""
from typing import Literal

from pydantic import BaseModel

from rules.constants import resolve_equipment
from schemas.plan import Plan
from schemas.profile import UserProfile


class Violation(BaseModel):
    rule: str
    severity: Literal["hard", "soft"]
    detail: str


async def validate(conn, plan: Plan, profile: UserProfile) -> list[Violation]:
    violations: list[Violation] = []
    ex_ids = {b.exercise_id for d in plan.days for b in d.blocks}
    rows = await conn.fetch(
        "SELECT id, equipment, contraindications FROM exercises WHERE id = ANY($1)",
        list(ex_ids),
    )
    ex_map = {r["id"]: r for r in rows}

    injuries = {i.value for i in profile.injuries}
    allowed_equipment = set(resolve_equipment([e.value for e in profile.equipment]))

    for day in plan.days:
        for block in day.blocks:
            ex = ex_map.get(block.exercise_id)
            if ex is None:
                violations.append(Violation(
                    rule="EXERCISE_EXISTS", severity="hard",
                    detail=f"{block.exercise_id} not found",
                ))
                continue
            if set(ex["contraindications"]) & injuries:
                violations.append(Violation(
                    rule="NO_CONTRAINDICATION", severity="hard",
                    detail=f"{block.exercise_id} contraindicated for {sorted(injuries)}",
                ))
            if ex["equipment"] not in allowed_equipment:
                violations.append(Violation(
                    rule="EQUIPMENT_AVAILABLE", severity="hard",
                    detail=f"{block.exercise_id} needs {ex['equipment']}",
                ))
        if day.type == "workout" and day.est_minutes > profile.session_minutes * 1.15:
            violations.append(Violation(
                rule="TIME_BUDGET", severity="hard",
                detail=f"{day.date} est {day.est_minutes}min > budget {profile.session_minutes}min",
            ))

    rest_days = sum(1 for d in plan.days if d.type == "rest")
    if rest_days < 1:
        violations.append(Violation(rule="REST_DAY_PRESENT", severity="hard", detail="0 rest days"))

    return violations
