from gemini.client import call_gemini
from gemini.prompts import build_constraint_prompt, build_refine_prompt
from schemas.adjust import ConstraintDelta
from schemas.plan import Plan
from schemas.profile import UserProfile

# Spec's original budget was 4s/6s, tuned against gemini-2.5-flash (no
# longer reachable on new keys -- see gemini/client.py). gemini-flash-latest
# measured 3.6-11s with thinking left on default; forcing thinking_level=
# "low" in client.py brought that down to a consistent 2-4s. Timeouts stay
# wider than that measured range on purpose -- Gemini's own transient 503s
# ("high demand") are real and expected, and a slow-but-legitimate response
# is strictly better than an unnecessary fallback.
CALL_A_TIMEOUT_S = 8.0
CALL_B_TIMEOUT_S = 12.0


async def interpret_constraints(text: str, profile: UserProfile) -> ConstraintDelta | None:
    """Call A -- Gemini never writes the plan here, it translates human mess
    ("knee's been hurting, only got 25 mins") into UserProfile's own schema.
    Layer 2 re-runs on whatever comes back."""
    prompt = build_constraint_prompt(text, profile)
    return await call_gemini(prompt, ConstraintDelta, temperature=0.2, timeout_s=CALL_A_TIMEOUT_S)


async def refine_plan(plan: Plan, profile: UserProfile, allowed_ids: list[str]) -> Plan | None:
    """Call B -- proposes swaps within an explicit whitelist. Never trusted
    directly: the caller still runs this through the Layer 4 validator."""
    prompt = build_refine_prompt(plan, profile, allowed_ids)
    return await call_gemini(prompt, Plan, temperature=0.3, timeout_s=CALL_B_TIMEOUT_S)
