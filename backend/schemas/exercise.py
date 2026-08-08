from pydantic import BaseModel


class Exercise(BaseModel):
    id: str
    name: str
    primary_muscle: str
    secondary_muscles: list[str] = []
    equipment: str
    level: str
    mechanic: str | None = None
    force: str | None = None
    category: str | None = None
    image_paths: list[str] = []
    contraindications: list[str] = []
    is_compound: bool = False
    est_seconds_per_set: int = 45
    unilateral: bool = False
