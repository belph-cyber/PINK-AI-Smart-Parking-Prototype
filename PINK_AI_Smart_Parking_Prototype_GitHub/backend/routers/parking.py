# -*- coding: utf-8 -*-
"""
Parking, Personal Schedule & Vehicle Search API Endpoints
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from backend.services.auth_service import get_current_user, require_roles
from backend.services.parking_service import (
    get_floors_overview, get_floor_slot_map, update_slot_status, get_user_parking_details
)
from backend.models.schemas import SlotUpdateRequest
from backend.core.database import query_all, query_one, execute
from backend.services.audit_service import log_audit
import re

router = APIRouter(prefix="/api/parking", tags=["Parking"])


@router.get("/overview")
def overview():
    """Building capacity overview (used by Kiosk /iPad and Dashboards; contains no personal user phone/profile)"""
    return {"status": "ok", "floors": get_floors_overview()}


@router.get("/floor/{floor_number}")
def floor_slot_map(floor_number: int):
    """Retrieve slot map for specific floor"""
    data = get_floor_slot_map(floor_number)
    if not data:
        raise HTTPException(status_code=404, detail="Floor not found")
    return {"status": "ok", "data": data}


@router.put("/slot/{slot_id}")
def override_slot(slot_id: int, req: SlotUpdateRequest,
                  current_user: dict = Depends(require_roles(["SECURITY", "ADMIN"]))):
    """Security/Admin manually override slot status"""
    res = update_slot_status(
        slot_id, req.status, req.vehicle_plate,
        user_id=current_user["id"], username=current_user["username"],
        source=f"MANUAL_{current_user['role_code']}"
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Update failed"))
    return res


@router.get("/my")
def my_parking(current_user: dict = Depends(get_current_user)):
    """Strictly isolated Personal My Parking & History for the logged-in user"""
    data = get_user_parking_details(current_user["id"])
    return {"status": "ok", "data": data}

@router.get("/my/vehicles")
def my_vehicles(current_user: dict = Depends(require_roles(["STUDENT", "TEACHER"]))):
    rows = query_all("SELECT v.id,v.plate_no,v.plate_display,v.province,v.vehicle_type,v.brand,v.model,v.color,v.is_active,uv.is_primary,uv.is_approved FROM user_vehicles uv JOIN vehicles v ON v.id=uv.vehicle_id WHERE uv.user_id=? ORDER BY uv.is_primary DESC,v.id DESC", (current_user["id"],))
    return {"status":"ok","vehicles":rows}

@router.post("/my/vehicles")
def add_my_vehicle(body: dict, current_user: dict = Depends(require_roles(["STUDENT", "TEACHER"]))):
    plate = str(body.get("plate_no", "")).strip()
    province = str(body.get("province", "")).strip()
    clean = re.sub(r"[^0-9a-zA-Z\u0E00-\u0E7F]", "", plate).upper()
    if len(clean)<3 or not province: raise HTTPException(status_code=422, detail="กรุณากรอกทะเบียนและจังหวัด")
    if query_one("SELECT id FROM vehicles WHERE plate_clean=?", (clean,)): raise HTTPException(status_code=409, detail="ทะเบียนนี้มีในระบบแล้ว กรุณาติดต่อ Admin")
    user_id=current_user["id"]
    vehicle_id=execute("INSERT INTO vehicles (plate_no,province,plate_display,plate_clean,vehicle_type,brand,model,color,is_active) VALUES (?,?,?,?,?,?,?,?,1)",(plate,province,f"{plate} {province}",clean,body.get("vehicle_type") or "car",body.get("brand"),body.get("model"),body.get("color")))
    primary=not query_one("SELECT id FROM user_vehicles WHERE user_id=? LIMIT 1",(user_id,))
    execute("INSERT INTO user_vehicles (user_id,vehicle_id,is_primary,is_approved) VALUES (?,?,?,0)",(user_id,vehicle_id,int(primary)))
    log_audit(current_user["username"],"OWN_VEHICLE_CREATE","VEHICLE",str(vehicle_id),None,f"plate={plate}; pending approval",user_id=user_id)
    return {"status":"ok","vehicle_id":vehicle_id,"is_approved":0}


@router.get("/schedule/today")
def get_today_schedule(day: Optional[str] = Query(None),
                       current_user: dict = Depends(get_current_user)):
    """Strictly isolated schedule for the logged-in Student or Teacher"""
    day_name = day or datetime.now().strftime("%A")
    user_id = current_user["id"]
    role_code = current_user["role_code"]

    rows = query_all("""
        SELECT * FROM schedules
        WHERE user_id = ? AND day_of_week = ?
        ORDER BY start_time ASC;
    """, (user_id, day_name))

    is_today_exact = True
    if not rows:
        is_today_exact = False
        rows = query_all("""
            SELECT * FROM schedules
            WHERE user_id = ?
            ORDER BY id ASC;
        """, (user_id,))

    return {
        "status": "ok",
        "day": day_name,
        "is_today_exact": is_today_exact,
        "role": role_code,
        "count": len(rows),
        "schedule": rows
    }


@router.get("/history-all")
def all_parking_history(q: Optional[str] = Query(None),
                        days: int = Query(30),
                        current_user: dict = Depends(require_roles(["SECURITY", "ADMIN"]))):
    """Searchable parking history (>= 7 days) for Security & Admin"""
    sql = """
        SELECT ps.id, ps.entry_time, ps.exit_time, ps.current_floor, ps.session_status,
               v.plate_display, v.province,
               COALESCE(u.username, 'ยังไม่ได้ระบุ') as user_code,
               COALESCE(u.name, 'ผู้มาติดต่อ/ไม่ระบุ') as owner_name,
               COALESCE(r.name, '-') as owner_role,
               COALESCE(s.slot_number, 'ตรวจพบบนชั้น') as slot_number,
               COALESCE(g.name, 'CiRA LPR Gate') as source
        FROM parking_sessions ps
        JOIN vehicles v ON ps.vehicle_id = v.id
        LEFT JOIN user_vehicles uv ON v.id = uv.vehicle_id AND uv.is_primary = 1
        LEFT JOIN users u ON uv.user_id = u.id
        LEFT JOIN roles r ON u.role_id = r.id
        LEFT JOIN parking_slots s ON ps.assigned_slot_id = s.id
        LEFT JOIN gates g ON ps.entry_gate_id = g.id
        WHERE 1=1
    """
    params = []
    if q:
        clean_q = q.replace(" ", "").strip()
        like_q = f"%{q.strip()}%"
        sql += " AND (v.plate_clean LIKE ? OR v.plate_display LIKE ? OR u.username LIKE ? OR u.name LIKE ?)"
        params.extend([f"%{clean_q}%", like_q, like_q, like_q])

    sql += " ORDER BY ps.id DESC LIMIT 100;"
    rows = query_all(sql, tuple(params))
    return {"status": "ok", "count": len(rows), "history": rows}


@router.get("/search")
def search_vehicles(q: str = Query(..., min_length=1),
                    current_user: dict = Depends(require_roles(["SECURITY", "ADMIN"]))):
    """Search vehicles and parking records (Restricted to Security & Admin only)"""
    clean_q = q.replace(" ", "").strip()
    results = query_all("""
        SELECT v.*, u.name as owner_name, u.username as owner_code, u.phone as owner_phone,
               r.name as owner_role, ps.session_status, ps.current_floor, ps.entry_time,
               s.slot_number
        FROM vehicles v
        LEFT JOIN user_vehicles uv ON v.id = uv.vehicle_id AND uv.is_primary = 1
        LEFT JOIN users u ON uv.user_id = u.id
        LEFT JOIN roles r ON u.role_id = r.id
        LEFT JOIN parking_sessions ps ON v.id = ps.vehicle_id AND ps.session_status = 'ACTIVE'
        LEFT JOIN parking_slots s ON ps.assigned_slot_id = s.id
        WHERE v.plate_clean LIKE ? OR v.plate_display LIKE ? OR u.name LIKE ? OR u.username LIKE ?
        LIMIT 20;
    """, (f"%{clean_q}%", f"%{q}%", f"%{q}%", f"%{q}%"))
    return {"status": "ok", "count": len(results), "results": results}
