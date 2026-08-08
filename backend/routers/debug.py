import json
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from db import get_conn
from validator.rules import Violation

router = APIRouter(prefix="/api")


class RejectedPlan(BaseModel):
    id: str
    user_id: str
    violations: list[Violation]
    created_at: datetime


@router.get("/debug/validations")
async def debug_validations() -> list[RejectedPlan]:
    """Judge-facing: 'Gemini proposed a plan with an overhead press for a
    user with a shoulder injury. Our validator rejected it and fell back.
    The model never gets the last word.'"""
    async with get_conn() as conn:
        rows = await conn.fetch(
            "SELECT id, user_id, violations, created_at FROM rejected_plans "
            "ORDER BY created_at DESC LIMIT 50"
        )
    return [
        RejectedPlan(
            id=str(r["id"]),
            user_id=str(r["user_id"]),
            violations=[Violation(**v) for v in json.loads(r["violations"])],
            created_at=r["created_at"],
        )
        for r in rows
    ]
