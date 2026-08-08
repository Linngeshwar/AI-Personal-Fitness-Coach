"""
Layer 4 repair ladder. Only the two repairs the spec calls out are
attempted: swap an unsafe/unavailable/nonexistent exercise for the best
legal candidate on the same muscle, and re-fit a day that's over its time
budget. Anything else (most notably a missing rest day -- Gemini's system
prompt already forbids changing day count, so this should be rare) falls
through: validate_and_repair discards the plan and ships the deterministic
fallback instead.
"""
import json

from planner.core import estimate_minutes, fit_to_budget
from planner.queries import get_candidate_exercises
from rules.constants import FOCUS_MUSCLES, LEVELS_FOR_EXPERIENCE, resolve_equipment
from schemas.exercise import Exercise
from schemas.plan import Plan
from schemas.profile import UserProfile
from validator.rules import Violation, validate

SWAP_RULES = {"EXERCISE_EXISTS", "NO_CONTRAINDICATION", "EQUIPMENT_AVAILABLE"}


async def _fetch_exercises(conn, ids: set[str]) -> dict[str, Exercise]:
    if not ids:
        return {}
    rows = await conn.fetch("SELECT * FROM exercises WHERE id = ANY($1)", list(ids))
    return {r["id"]: Exercise(**dict(r)) for r in rows}


async def _find_replacement(conn, muscle: str, profile: UserProfile, exclude: set[str]) -> Exercise | None:
    equipment = resolve_equipment([e.value for e in profile.equipment])
    levels = LEVELS_FOR_EXPERIENCE[profile.experience.value]
    injuries = [i.value for i in profile.injuries]
    candidates = await get_candidate_exercises(conn, muscle, equipment, levels, injuries)
    candidates = [c for c in candidates if c.id not in exclude]
    if not candidates:
        return None
    compounds = [c for c in candidates if c.is_compound]
    return (compounds or candidates)[0]


async def attempt_repair(conn, plan: Plan, violations: list[Violation], profile: UserProfile) -> Plan:
    bad_ids = {v.detail.split()[0] for v in violations if v.rule in SWAP_RULES}
    over_budget_dates = {v.detail.split()[0] for v in violations if v.rule == "TIME_BUDGET"}

    new_days = []
    for day in plan.days:
        blocks = list(day.blocks)
        needs_swap = any(b.exercise_id in bad_ids for b in blocks)
        needs_fit = str(day.date) in over_budget_dates

        if needs_swap:
            used_ids = {b.exercise_id for b in blocks}
            # only exercises that exist but were disqualified show up here --
            # a nonexistent id (EXERCISE_EXISTS) has nothing to look up
            known = await _fetch_exercises(conn, used_ids - bad_ids | {
                b.exercise_id for b in blocks if b.exercise_id in bad_ids
            })
            fixed_blocks = []
            for block in blocks:
                if block.exercise_id not in bad_ids:
                    fixed_blocks.append(block)
                    continue
                ex = known.get(block.exercise_id)
                if ex:
                    muscle = ex.primary_muscle
                elif day.focus and FOCUS_MUSCLES.get(day.focus):
                    muscle = FOCUS_MUSCLES[day.focus][0]
                else:
                    muscle = None
                replacement = await _find_replacement(conn, muscle, profile, used_ids) if muscle else None
                if replacement is None:
                    fixed_blocks.append(block)  # couldn't fix -- re-validate will re-flag it
                    continue
                used_ids.discard(block.exercise_id)
                used_ids.add(replacement.id)
                fixed_blocks.append(block.model_copy(update={
                    "exercise_id": replacement.id,
                    "swap_reason": "Swapped by the validator: original exercise was unsafe or unavailable.",
                }))
            blocks = fixed_blocks

        if needs_fit or needs_swap:
            exercises_by_id = await _fetch_exercises(conn, {b.exercise_id for b in blocks})
            blocks = fit_to_budget(blocks, exercises_by_id, profile.session_minutes)
            est_minutes = estimate_minutes(blocks, exercises_by_id)
            day = day.model_copy(update={"blocks": blocks, "est_minutes": est_minutes})

        new_days.append(day)

    return plan.model_copy(update={"days": new_days})


async def log_rejected_plan(conn, plan: Plan, violations: list[Violation]) -> None:
    await conn.execute(
        "INSERT INTO rejected_plans (user_id, plan_json, violations) VALUES ($1, $2::jsonb, $3::jsonb)",
        plan.user_id,
        plan.model_dump_json(),
        json.dumps([v.model_dump() for v in violations]),
    )


async def validate_and_repair(
    conn, plan: Plan, profile: UserProfile, fallback: Plan
) -> tuple[Plan, list[Violation]]:
    violations = await validate(conn, plan, profile)
    hard = [v for v in violations if v.severity == "hard"]
    if not hard:
        return plan, violations

    repaired = await attempt_repair(conn, plan, hard, profile)
    re_violations = await validate(conn, repaired, profile)
    re_hard = [v for v in re_violations if v.severity == "hard"]
    if not re_hard:
        return repaired, re_violations

    await log_rejected_plan(conn, plan, hard)
    return fallback, hard
