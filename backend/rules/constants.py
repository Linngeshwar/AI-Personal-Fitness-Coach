VOLUME_LANDMARKS = {
    "beginner":     {"min": 6,  "target": 10, "max": 14},
    "intermediate": {"min": 8,  "target": 14, "max": 20},
    "advanced":     {"min": 10, "target": 18, "max": 24},
}

REP_SCHEME = {
    "strength":    {"reps": (3, 6),   "rest": 180, "rir": 2},
    "muscle_gain": {"reps": (8, 12),  "rest": 90,  "rir": 1},
    "fat_loss":    {"reps": (10, 15), "rest": 60,  "rir": 2},
    "endurance":   {"reps": (15, 25), "rest": 45,  "rir": 3},
    "general":     {"reps": (8, 15),  "rest": 75,  "rir": 2},
}

SPLITS = {
    2: [["full_body"], ["full_body"]],
    3: [["push"], ["pull"], ["legs"]],
    4: [["upper"], ["lower"], ["upper"], ["lower"]],
    5: [["push"], ["pull"], ["legs"], ["upper"], ["lower"]],
    6: [["push"], ["pull"], ["legs"], ["push"], ["pull"], ["legs"]],
}

# Maps each split-day "focus" tag to the primary_muscle values (as they
# appear in the exercises table, free-exercise-db vocabulary) that day
# trains. Used by planner/core.py to know which candidate pools to pull.
FOCUS_MUSCLES = {
    "full_body": ["chest", "lats", "quadriceps", "shoulders", "hamstrings", "abdominals"],
    "push": ["chest", "shoulders", "triceps"],
    "pull": ["lats", "middle back", "biceps"],
    "legs": ["quadriceps", "hamstrings", "glutes", "calves"],
    "upper": ["chest", "lats", "shoulders", "triceps", "biceps"],
    "lower": ["quadriceps", "hamstrings", "glutes", "calves"],
}

# UserProfile.equipment (schemas/profile.py Equipment enum) uses a coarse
# vocabulary a user picks from onboarding. exercises.equipment (Layer 1)
# uses free-exercise-db's finer vocabulary. This resolves one to the set of
# the other, upstream of planner/queries.py's `equipment = ANY($2)` filter,
# so that query itself stays the one-liner the spec describes.
EQUIPMENT_MAP: dict[str, list[str]] = {
    "none": ["body only"],
    "dumbbells": ["dumbbell", "body only"],
    "barbell": ["barbell", "e-z curl bar", "body only"],
    "machines": ["machine", "cable", "body only"],
    "bands": ["bands", "body only"],
    "pullup_bar": ["body only"],
    "full_gym": [
        "barbell", "dumbbell", "machine", "cable", "bands", "kettlebells",
        "e-z curl bar", "body only", "exercise ball", "medicine ball",
        "foam roll", "other",
    ],
}


def resolve_equipment(user_equipment: list[str]) -> list[str]:
    resolved: set[str] = set()
    for item in user_equipment:
        resolved.update(EQUIPMENT_MAP.get(item, []))
    return sorted(resolved)


# UserProfile.experience is beginner/intermediate/advanced (coarser than
# necessary); exercises.level (free-exercise-db) is beginner/intermediate/
# expert. A user's level unlocks their tier and everything easier than it.
LEVELS_FOR_EXPERIENCE: dict[str, list[str]] = {
    "beginner": ["beginner"],
    "intermediate": ["beginner", "intermediate"],
    "advanced": ["beginner", "intermediate", "expert"],
}
