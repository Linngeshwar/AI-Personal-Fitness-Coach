from schemas.profile import ScreeningResult, UserProfile


def apply_screening(profile: UserProfile) -> ScreeningResult:
    s = profile.safety
    if s.under_18 or s.pregnant_or_postpartum or s.eating_disorder_history:
        return ScreeningResult(
            nutrition_enabled=False,
            message="We won't set calorie targets for you. Talk to a doctor or dietitian.",
            volume_cap=0.7,
        )
    if s.chest_pain_on_exertion or s.cardiac_or_bp_condition:
        return ScreeningResult(
            requires_clearance=True,
            message="Check with a doctor before starting a new training program.",
        )
    return ScreeningResult()
