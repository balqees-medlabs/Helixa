"""Role listing (any authenticated user; roles are fixed reference data)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import AuthContext, current_user
from app.schemas.users import RoleOut

router = APIRouter(tags=["roles"])

ROLES = ("admin", "genomics", "trf", "molecular", "bioinformatics")


@router.get("/roles", response_model=list[RoleOut])
def list_roles(_user: Annotated[AuthContext, Depends(current_user)]) -> list[RoleOut]:
    return [RoleOut(slug=slug, description=None) for slug in ROLES]
