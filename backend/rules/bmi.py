from schemas.profile import BmiSummary, UserProfile

# Standard WHO adult cutoffs.
BMI_NORMAL_MIN = 18.5
BMI_NORMAL_MAX = 24.9


def compute_bmi_summary(profile: UserProfile) -> BmiSummary:
    """Deterministic, not Gemini's call -- same "light-touch" spirit as
    ENERGY_VOLUME_MULTIPLIER in routers/plan.py. Target weight is the edge
    of the healthy BMI range nearest the user's goal, not a number Gemini
    invented: fat_loss aims down to the top of the healthy range,
    muscle_gain aims up to its bottom (or a modest lean-bulk buffer if
    already inside/above it), everything else just maintains."""
    height_m = profile.height_cm / 100
    bmi = profile.weight_kg / (height_m**2)

    if bmi < BMI_NORMAL_MIN:
        category = "underweight"
    elif bmi <= BMI_NORMAL_MAX:
        category = "normal"
    elif bmi < 30:
        category = "overweight"
    else:
        category = "obese"

    healthy_min_kg = BMI_NORMAL_MIN * height_m**2
    healthy_max_kg = BMI_NORMAL_MAX * height_m**2

    if profile.goal.value == "fat_loss":
        if profile.weight_kg > healthy_max_kg:
            target = healthy_max_kg
            note = "Top of the healthy range for your height"
        else:
            target = profile.weight_kg
            note = "Already within a healthy range for your height"
    elif profile.goal.value == "muscle_gain":
        if profile.weight_kg < healthy_min_kg:
            target = healthy_min_kg
            note = "Bottom of the healthy range for your height"
        else:
            target = profile.weight_kg * 1.05
            note = "Modest lean-bulk target, not a hard limit"
    else:
        target = profile.weight_kg
        note = "Maintenance -- this goal isn't weight-driven"

    return BmiSummary(
        weight_kg=round(profile.weight_kg, 1),
        height_cm=profile.height_cm,
        bmi=round(bmi, 1),
        category=category,
        target_weight_kg=round(target, 1),
        target_note=note,
    )
