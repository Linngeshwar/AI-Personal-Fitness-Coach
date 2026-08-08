"""
Layer 2 -- deterministic planner core.

generate_plan() is a pure function: same (profile, state, candidate_pool)
in, same Plan out. No network, no LLM, no DB writes -- candidates are
already-fetched, passed in by the caller (routers/plan.py). That's what
makes this trivially unit-testable and safe to call again from inside the
Layer 4 validator's repair step later.
"""
import random
from datetime import date, timedelta

from rules.constants import FOCUS_MUSCLES, REP_SCHEME, SPLITS, VOLUME_LANDMARKS
from schemas.exercise import Exercise
from schemas.plan import Plan, PlanBlock, PlanDay, PlanState
from schemas.profile import UserProfile

WARMUP_SECONDS = 300
MAX_EXERCISES_PER_SESSION = 6
EXERCISES_PER_MUSCLE = 2
MIN_REST_SECONDS = 45
MIN_SETS = 2


def _rest_day_positions(days_per_week: int, total: int = 7) -> set[int]:
    workout = {int(i * total / days_per_week) for i in range(days_per_week)}
    return set(range(total)) - workout


def _select_split(days_per_week: int) -> list[str | None]:
    """7-slot week: a focus tag (from SPLITS) on workout days, None on rest
    days. Rest days are maximally spaced (e.g. 3/week -> Mon/Wed/Fri)."""
    focuses = SPLITS[days_per_week]
    rest = _rest_day_positions(days_per_week)
    week: list[str | None] = [None] * 7
    fi = 0
    for i in range(7):
        if i not in rest:
            week[i] = focuses[fi][0]
            fi += 1
    return week


def _weekly_target_sets(profile: UserProfile, state: PlanState) -> float:
    return VOLUME_LANDMARKS[profile.experience.value]["target"] * state.volume_multiplier


def _sessions_per_muscle(week: list[str | None]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for focus in week:
        if focus is None:
            continue
        for muscle in FOCUS_MUSCLES[focus]:
            counts[muscle] = counts.get(muscle, 0) + 1
    return counts


def _select_exercises_for_muscle(
    pool: list[Exercise], rng: random.Random, already_used: set[str], limit: int
) -> list[Exercise]:
    """Compounds first, then isolation (spec Step 4), each group shuffled
    with a seeded RNG so results are reproducible but not identical every
    week the RNG is re-seeded with a new week_number."""
    candidates = [e for e in pool if e.id not in already_used]
    compounds = [e for e in candidates if e.is_compound]
    isolation = [e for e in candidates if not e.is_compound]
    rng.shuffle(compounds)
    rng.shuffle(isolation)
    return (compounds + isolation)[:limit]


def estimate_minutes(blocks: list[PlanBlock], exercises: dict[str, Exercise]) -> int:
    total = WARMUP_SECONDS
    for b in blocks:
        per_set = exercises[b.exercise_id].est_seconds_per_set
        total += b.sets * per_set + (b.sets - 1) * b.rest_seconds
    return total // 60


def fit_to_budget(
    blocks: list[PlanBlock], exercises: dict[str, Exercise], budget_minutes: int
) -> list[PlanBlock]:
    """Never drops the last compound; sets floor at MIN_SETS, rest floors at
    MIN_REST_SECONDS. Spec's original loop has no terminal condition once
    isolation is gone and both floors are hit -- guarded here with an
    explicit break instead of spinning forever on a tight budget."""
    while estimate_minutes(blocks, exercises) > budget_minutes and len(blocks) > 1:
        isolation = [b for b in blocks if not exercises[b.exercise_id].is_compound]
        if isolation:
            drop = max(isolation, key=lambda b: b.order)
            blocks = [b for b in blocks if b is not drop]
        elif any(b.rest_seconds > MIN_REST_SECONDS for b in blocks):
            for b in blocks:
                b.rest_seconds = max(MIN_REST_SECONDS, b.rest_seconds - 15)
        elif any(b.sets > MIN_SETS for b in blocks):
            for b in blocks:
                b.sets = max(MIN_SETS, b.sets - 1)
        else:
            break
    return blocks


def generate_plan(
    profile: UserProfile,
    state: PlanState,
    candidate_pool: dict[str, list[Exercise]],
    *,
    user_id: str,
    week_start: date,
    plan_id: str,
) -> Plan:
    rng = random.Random(hash((user_id, state.week_number)))

    week = _select_split(profile.days_per_week)
    weekly_target = _weekly_target_sets(profile, state)
    sessions_per_muscle = _sessions_per_muscle(week)
    scheme = REP_SCHEME[profile.goal.value]
    rep_low, rep_high = scheme["reps"]

    exercises_by_id: dict[str, Exercise] = {
        e.id: e for pool in candidate_pool.values() for e in pool
    }

    days: list[PlanDay] = []
    for offset, focus in enumerate(week):
        day_date = week_start + timedelta(days=offset)
        if focus is None:
            days.append(PlanDay(date=day_date, type="rest", focus=None, est_minutes=0, blocks=[]))
            continue

        used_ids: set[str] = set()
        blocks: list[PlanBlock] = []
        order = 0
        for muscle in FOCUS_MUSCLES[focus]:
            if len(blocks) >= MAX_EXERCISES_PER_SESSION:
                break
            pool = candidate_pool.get(muscle, [])
            if not pool:
                continue
            per_muscle_sets = max(round(weekly_target / sessions_per_muscle.get(muscle, 1)), MIN_SETS)
            picks = _select_exercises_for_muscle(pool, rng, used_ids, limit=EXERCISES_PER_MUSCLE)
            if not picks:
                continue
            sets_each = max(per_muscle_sets // len(picks), MIN_SETS)
            for ex in picks:
                if len(blocks) >= MAX_EXERCISES_PER_SESSION:
                    break
                used_ids.add(ex.id)
                blocks.append(PlanBlock(
                    exercise_id=ex.id,
                    order=order,
                    sets=sets_each,
                    rep_low=rep_low,
                    rep_high=rep_high,
                    rest_seconds=scheme["rest"],
                    rir=scheme["rir"],
                ))
                order += 1

        blocks = fit_to_budget(blocks, exercises_by_id, profile.session_minutes)
        est_minutes = estimate_minutes(blocks, exercises_by_id)
        days.append(PlanDay(
            date=day_date, type="workout", focus=focus, est_minutes=est_minutes, blocks=blocks,
        ))

    return Plan(
        plan_id=plan_id,
        user_id=user_id,
        week_start=week_start,
        generated_by="deterministic",
        volume_multiplier=state.volume_multiplier,
        days=days,
    )
