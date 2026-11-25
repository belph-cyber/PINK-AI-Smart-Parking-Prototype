# -*- coding: utf-8 -*-
"""
Gate Control Router (Strict RBAC: SECURITY & ADMIN only)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from backend.services.auth_service import require_roles
from backend.services.gate_service import get_all_gates, operate_gate, get_recent_gate_logs
from backend.models.schemas import GateControlRequest

router = APIRouter(prefix="/api/gate", tags=["Gate Control"])


@router.get("/list")
def list_gates(current_user: dict = Depends(require_roles(["SECURITY", "ADMIN"]))):
    return {"status": "ok", "gates": get_all_gates()}


@router.post("/control")
def control_gate(req: GateControlRequest, request: Request,
                 current_user: dict = Depends(require_roles(["SECURITY", "ADMIN"]))):
    client_ip = request.client.host if request.client else None
    res = operate_gate(
        gate_id=req.gate_id,
        action=req.action,
        user_id=current_user["id"],
        username=current_user["username"],
        reason=req.reason,
        client_ip=client_ip
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Gate operation failed"))
    return res


@router.get("/logs")
def gate_logs(current_user: dict = Depends(require_roles(["SECURITY", "ADMIN"]))):
    return {"status": "ok", "logs": get_recent_gate_logs(50)}
