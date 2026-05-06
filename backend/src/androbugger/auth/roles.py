"""Role definitions and permission hierarchy."""
from typing import Literal

Role = Literal["technician", "qa_engineer", "developer", "admin"]

_HIERARCHY: dict[Role, int] = {
    "technician": 0,
    "qa_engineer": 1,
    "developer": 2,
    "admin": 3,
}


def role_gte(user_role: str, required: str) -> bool:
    """Return True if user_role is >= required in the hierarchy."""
    return _HIERARCHY.get(user_role, -1) >= _HIERARCHY.get(required, 999)  # type: ignore[arg-type]
