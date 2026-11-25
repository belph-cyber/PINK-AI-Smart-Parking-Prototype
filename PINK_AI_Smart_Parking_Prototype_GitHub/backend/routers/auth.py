# -*- coding: utf-8 -*-
"""
Authentication & Personal Profile Endpoints:
- POST /api/auth/login
- POST /api/auth/logout
- GET  /api/auth/me
- GET  /api/auth/profile
- PUT  /api/auth/profile (Self personal info update - strictly blocks role change!)
"""

import os
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status
from backend.models.schemas import LoginRequest, TokenResponse
from backend.services.auth_service import authenticate_user, logout_user, get_current_user
from backend.core.security import create_access_token
from backend.core.database import execute
from backend.services.audit_service import log_audit
from backend.services.sheets_service import trigger_sheets_sync_async

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class SelfProfileUpdateRequest(BaseModel):
    phone: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    birthdate: Optional[str] = None
    role_code: Optional[str] = None  # Explicitly trapped to block self role escalation!


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "Unknown")
    user = authenticate_user(req.username, req.password, client_ip, user_agent)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="รหัสประจำตัวหรือรหัสผ่านไม่ถูกต้อง (Invalid Username or Password)"
        )

    if (user.get("role_code") == "ADMIN"
            and request.headers.get("cf-connecting-ip")
            and os.getenv("PUBLIC_BLOCK_ADMIN", "true").lower() in ("1", "true", "yes")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="บัญชี Admin เข้าสู่ระบบได้เฉพาะในเครือข่ายภายในเท่านั้น (ปิดการเข้าถึงผ่านลิงก์สาธารณะ)"
        )

    token = create_access_token({"sub": user["id"], "role": user["role_code"], "username": user["username"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }


@router.post("/logout")
def logout(request: Request, current_user: dict = Depends(get_current_user)):
    client_ip = request.client.host if request.client else None
    return logout_user(current_user["id"], current_user["username"], client_ip)


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {"status": "ok", "user": current_user}


@router.get("/profile")
def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Return strictly the authenticated user's own personal information"""
    def disp(v):
        return v if (v is not None and str(v).strip() != "") else "ยังไม่ได้ระบุ"

    return {
        "status": "ok",
        "profile": {
            "id": current_user["id"],
            "username": disp(current_user.get("username")),
            "name": disp(current_user.get("name")),
            "role_code": current_user.get("role_code"),
            "role_name": disp(current_user.get("role_name")),
            "gender": disp(current_user.get("gender")),
            "age": current_user.get("age") if current_user.get("age") is not None else "ยังไม่ได้ระบุ",
            "birthdate": disp(current_user.get("birthdate")),
            "phone": disp(current_user.get("phone")),
            "faculty": disp(current_user.get("faculty")),
            "department": disp(current_user.get("department")),
            "vehicle_plate": disp(current_user.get("vehicle_plate")),
            "vehicle_detail": disp(current_user.get("vehicle_detail")),
            "last_login_at": disp(current_user.get("last_login_at"))
        }
    }


@router.put("/profile")
def update_my_profile(req: SelfProfileUpdateRequest, current_user: dict = Depends(get_current_user)):
    """Allow user to update their own contact/personal fields ONLY — never role!"""
    if req.role_code and req.role_code.upper() != current_user["role_code"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ผู้ใช้ทั่วไปไม่สามารถเปลี่ยน Role ของตนเองได้ (Self role modification forbidden)"
        )

    updates = []
    params = []
    if req.phone is not None:
        updates.append("phone = ?"); params.append(req.phone.strip() or None)
    if req.gender is not None:
        updates.append("gender = ?"); params.append(req.gender.strip() or None)
    if req.age is not None:
        updates.append("age = ?"); params.append(req.age)
    if req.birthdate is not None:
        updates.append("birthdate = ?"); params.append(req.birthdate.strip() or None)

    if updates:
        params.append(current_user["id"])
        execute(f"UPDATE users SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?;", tuple(params))
        log_audit(current_user["username"], "SELF_PROFILE_UPDATE", "USER", str(current_user["id"]), None, f"Updated personal info: {updates}", user_id=current_user["id"])
        trigger_sheets_sync_async(current_user["username"])

    return {"status": "ok", "message": "บันทึกข้อมูลส่วนตัวสำเร็จ"}
