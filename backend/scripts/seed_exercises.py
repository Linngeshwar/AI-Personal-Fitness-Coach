"""
Seed script: free-exercise-db (one JSON file per exercise) -> Postgres `exercises` table.

Usage:
    python seed_exercises.py /path/to/exercises_dir

Expects a directory containing ~870 files, each shaped like:
    {
      "id": "3_4_Sit-Up",
      "name": "3/4 Sit-Up",
      "force": "pull" | "push" | "static" | null,
      "level": "beginner" | "intermediate" | "expert",
      "mechanic": "isolation" | "compound" | null,
      "equipment": "dumbbell" | ... | null,
      "primaryMuscles": ["abdominals"],
      "secondaryMuscles": [],
      "instructions": ["...", "..."],
      "category": "strength" | ...,
      "images": ["3_4_Sit-Up/0.jpg", "3_4_Sit-Up/1.jpg"]
    }

Design notes:
- The source schema allows `equipment` and `mechanic` to be null (bodyweight
  stretches, cardio). The target table has `equipment TEXT NOT NULL`, so we
  substitute an explicit sentinel ('body only') rather than let asyncpg
  reject the row or silently coerce None -> NULL.
- `primaryMuscles` is an array in the source but the table wants a single
  `primary_muscle`. We take index 0 as primary and fold anything beyond
  that into `secondary_muscles` (deduped against the source's own
  secondaryMuscles list). Files with an empty primaryMuscles array are
  skipped and reported, not guessed at.
- Contraindication tagging is regex-based, run against `name` (and folded
  into the check against `category` for stretching, which is exempted --
  a stretch matching "lunge" isn't a loading risk the way a weighted lunge
  is). Tags are additive: one exercise can get more than one tag.
- Idempotent: ON CONFLICT (id) DO UPDATE, so re-running after fixing a
  handful of files, or after editing CONTRA_PATTERNS, does not require a
  DELETE FROM exercises first.
- Bad files (missing required key, wrong type, empty primaryMuscles) are
  collected and printed as a summary at the end rather than aborting the
  whole run -- with ~870 hand-authored files from an open-source repo,
  a handful of malformed entries is the expected case, not the exception.
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import asyncpg

DATABASE_URL = "postgresql://user:password@localhost:5432/fitness_coach"

# ---------------------------------------------------------------------------
# Contraindication tagging
#
# Matched against exercise name (case-insensitive). Order doesn't matter --
# an exercise can pick up multiple tags. This is a starting pass, not a
# final answer: the plan is to hand-review the ~150 most commonly
# prescribed exercises (compounds, main lifts) after this seed runs once,
# since a false negative here (an exercise that SHOULD be tagged but isn't
# caught by regex) is a safety gap, not just a data quality issue.
# ---------------------------------------------------------------------------
CONTRA_PATTERNS: list[tuple[str, str]] = [
    (r"squat|lunge|leg press|step.?up|box jump|pistol", "knee"),
    (r"deadlift|good.?morning|row.*bent|bent.?over|superman|hyperextension", "lower_back"),
    (r"overhead|press.*shoulder|shoulder.*press|upright row|behind.?the.?neck|military press", "shoulder"),
    (r"wrist curl|reverse curl|handstand", "wrist"),
    (r"calf raise|jump rope|box jump|sprint", "ankle"),
]

# Exercises tagged purely as mobility/flexibility work don't carry the same
# loading risk as a weighted lift with a similar name (e.g. "Standing Hip
# Flexor Stretch" vs "Barbell Squat"), so pure stretches are exempted from
# the knee/lower_back/shoulder loading tags. They can still be re-tagged by
# hand during the manual review pass if a specific stretch is contraindicated.
STRETCH_EXEMPT_CATEGORIES = {"stretching"}

# equipment/mechanic are nullable in the source; the target schema does not
# allow NULL equipment. These are the explicit substitutions, not silent
# coercions -- anything that hits the fallback is countable in the summary.
EQUIPMENT_FALLBACK = "body only"


def tag_contraindications(name: str, category: str) -> list[str]:
    if category in STRETCH_EXEMPT_CATEGORIES:
        return []
    tags: set[str] = set()
    for pattern, tag in CONTRA_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            tags.add(tag)
    return sorted(tags)


def is_unilateral(name: str) -> bool:
    return bool(re.search(r"single.?arm|single.?leg|one.?arm|one.?leg|alternating|split.?stance", name, re.IGNORECASE))


# Rough duration heuristic: cardio/stretching are time-based, not set-based,
# but est_seconds_per_set still needs a value for the planner's time-budget
# math in Layer 2. Compounds run slower per set (more setup, more careful
# reps) than isolation work.
def estimate_seconds_per_set(category: str, mechanic: str | None) -> int:
    if category in ("cardio", "plyometrics"):
        return 30
    if category == "stretching":
        return 30
    if mechanic == "compound":
        return 55
    return 40


class RowResult:
    __slots__ = ("path", "reason")

    def __init__(self, path: Path, reason: str):
        self.path = path
        self.reason = reason


def build_row(data: dict, path: Path) -> tuple[dict, list[str]] | tuple[None, list[str]]:
    """
    Validate + transform one parsed JSON file into the row dict the INSERT
    expects. Returns (row, warnings) on success, or (None, reasons) if the
    file can't be seeded at all.
    """
    warnings: list[str] = []
    required = ["id", "name", "level", "primaryMuscles", "secondaryMuscles",
                "category", "images"]
    missing = [k for k in required if k not in data]
    if missing:
        return None, [f"missing required key(s): {missing}"]

    if not isinstance(data["primaryMuscles"], list) or len(data["primaryMuscles"]) == 0:
        return None, ["primaryMuscles is empty or not a list -- cannot determine primary_muscle"]

    primary_muscle = data["primaryMuscles"][0]
    # anything beyond primaryMuscles[0] folds into secondary_muscles,
    # deduped against the source's own secondaryMuscles
    overflow_primary = data["primaryMuscles"][1:]
    secondary_muscles = list(dict.fromkeys(
        [*data.get("secondaryMuscles", []), *overflow_primary]
    ))
    if overflow_primary:
        warnings.append(
            f"primaryMuscles had {len(data['primaryMuscles'])} entries; "
            f"used '{primary_muscle}' as primary, folded rest into secondary"
        )

    equipment = data.get("equipment")
    if equipment is None:
        equipment = EQUIPMENT_FALLBACK
        warnings.append(f"equipment was null -> defaulted to '{EQUIPMENT_FALLBACK}'")

    mechanic = data.get("mechanic")  # nullable in target table too, no fallback needed
    force = data.get("force")        # nullable in target table too, no fallback needed
    category = data["category"]

    contraindications = tag_contraindications(data["name"], category)
    unilateral = is_unilateral(data["name"])
    is_compound = (mechanic == "compound")
    est_seconds = estimate_seconds_per_set(category, mechanic)

    row = {
        "id": data["id"],
        "name": data["name"],
        "primary_muscle": primary_muscle,
        "secondary_muscles": secondary_muscles,
        "equipment": equipment,
        "level": data["level"],
        "mechanic": mechanic,
        "force": force,
        "category": category,
        "image_paths": data.get("images", []),
        "contraindications": contraindications,
        "is_compound": is_compound,
        "est_seconds_per_set": est_seconds,
        "unilateral": unilateral,
    }
    return row, warnings


INSERT_SQL = """
INSERT INTO exercises (
    id, name, primary_muscle, secondary_muscles, equipment, level,
    mechanic, force, category, image_paths,
    contraindications, is_compound, est_seconds_per_set, unilateral
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
)
ON CONFLICT (id) DO UPDATE SET
    name                 = EXCLUDED.name,
    primary_muscle        = EXCLUDED.primary_muscle,
    secondary_muscles      = EXCLUDED.secondary_muscles,
    equipment             = EXCLUDED.equipment,
    level                 = EXCLUDED.level,
    mechanic              = EXCLUDED.mechanic,
    force                 = EXCLUDED.force,
    category              = EXCLUDED.category,
    image_paths           = EXCLUDED.image_paths,
    contraindications     = EXCLUDED.contraindications,
    is_compound           = EXCLUDED.is_compound,
    est_seconds_per_set    = EXCLUDED.est_seconds_per_set,
    unilateral            = EXCLUDED.unilateral;
"""


async def seed(directory: Path, database_url: str, dry_run: bool = False) -> None:
    files = sorted(directory.rglob("*.json"))
    if not files:
        print(f"No .json files found under {directory}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} JSON files under {directory}")

    rows_to_insert: list[dict] = []
    skipped: list[RowResult] = []
    warned: list[tuple[Path, list[str]]] = []

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            skipped.append(RowResult(path, f"invalid JSON: {e}"))
            continue

        row, info = build_row(data, path)
        if row is None:
            skipped.append(RowResult(path, "; ".join(info)))
            continue
        if info:
            warned.append((path, info))
        rows_to_insert.append(row)

    print(f"Parsed OK: {len(rows_to_insert)}   Warnings: {len(warned)}   Skipped: {len(skipped)}")

    if dry_run:
        print("\n--- DRY RUN: no database writes ---")
        _print_summary(skipped, warned)
        return

    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            for row in rows_to_insert:
                await conn.execute(
                    INSERT_SQL,
                    row["id"], row["name"], row["primary_muscle"],
                    row["secondary_muscles"], row["equipment"], row["level"],
                    row["mechanic"], row["force"], row["category"],
                    row["image_paths"], row["contraindications"],
                    row["is_compound"], row["est_seconds_per_set"],
                    row["unilateral"],
                )
        print(f"\nInserted/updated {len(rows_to_insert)} rows into exercises.")
    finally:
        await conn.close()

    _print_summary(skipped, warned)


def _print_summary(skipped: list[RowResult], warned: list[tuple[Path, list[str]]]) -> None:
    if warned:
        print(f"\n--- {len(warned)} file(s) seeded with warnings ---")
        for path, reasons in warned[:30]:
            print(f"  {path.name}: {'; '.join(reasons)}")
        if len(warned) > 30:
            print(f"  ... and {len(warned) - 30} more")

    if skipped:
        print(f"\n--- {len(skipped)} file(s) SKIPPED (not inserted) ---")
        for r in skipped:
            print(f"  {r.path.name}: {r.reason}")
    else:
        print("\nNo files skipped.")

    # quick contraindication coverage count, useful sanity check before the
    # manual review pass on the top-150 exercises
    print("\nRun a query like:")
    print("  SELECT unnest(contraindications) AS tag, count(*) FROM exercises GROUP BY tag ORDER BY count(*) DESC;")
    print("to see how many exercises got tagged per contraindication category.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path, help="Directory containing per-exercise .json files (searched recursively)")
    parser.add_argument("--database-url", default=DATABASE_URL, help="Postgres DSN (default: env-style placeholder, edit DATABASE_URL at top of file)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only, skip DB writes")
    args = parser.parse_args()

    if not args.directory.exists():
        print(f"Directory not found: {args.directory}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(seed(args.directory, args.database_url, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
