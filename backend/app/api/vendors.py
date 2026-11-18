"""Vendor management (FR-014): read for any user, write for admins."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, current_user, get_tx, require_roles
from app.schemas.vendors import VendorCreate, VendorOut, VendorUpdate
from app.services import vendor_service

router = APIRouter(prefix="/vendors", tags=["vendors"])

Admin = Annotated[AuthContext, Depends(require_roles("admin"))]
AnyUser = Annotated[AuthContext, Depends(current_user)]
Conn = Annotated[Connection, Depends(get_tx)]


@router.get("", response_model=list[VendorOut])
def list_vendors(_user: AnyUser, conn: Conn) -> list[VendorOut]:
    return [VendorOut(**vendor) for vendor in vendor_service.list_vendors(conn)]


@router.post("", response_model=VendorOut, status_code=201)
def create_vendor(body: VendorCreate, _user: Admin, conn: Conn) -> VendorOut:
    try:
        vendor = vendor_service.create_vendor(
            conn,
            name=body.name,
            tat_days=body.tat_days,
            tat_anchor=body.tat_anchor,
            is_active=body.is_active,
        )
    except vendor_service.VendorExists as exc:
        raise HTTPException(status_code=409, detail=f"Vendor {exc} already exists") from exc
    return VendorOut(**vendor)


@router.patch("/{vendor_id}", response_model=VendorOut)
def update_vendor(vendor_id: uuid.UUID, body: VendorUpdate, _user: Admin, conn: Conn) -> VendorOut:
    try:
        vendor = vendor_service.update_vendor(
            conn,
            vendor_id,
            name=body.name,
            tat_days=body.tat_days,
            tat_anchor=body.tat_anchor,
            is_active=body.is_active,
        )
    except vendor_service.VendorNotFound as exc:
        raise HTTPException(status_code=404, detail="Vendor not found") from exc
    except vendor_service.VendorExists as exc:
        raise HTTPException(status_code=409, detail=f"Vendor {exc} already exists") from exc
    return VendorOut(**vendor)
