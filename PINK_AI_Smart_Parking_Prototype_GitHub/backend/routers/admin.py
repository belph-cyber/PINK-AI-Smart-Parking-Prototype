# -*- coding: utf-8 -*-
"""
Admin Management Router (Strict RBAC Enforced):
- User CRUD, Role Change, Suspend/Activate & Password Reset (ADMIN only)
- Parking Slot Management with Duplicate Vehicle Validation & History (ADMIN / SECURITY)
- Login History (Sheet 5) & Audit Trail (ADMIN only)
- System Health Overview
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional, Dict, Any
import json
from datetime import datetime
from backend.services.auth_service import require_roles, require_console_admin
from backend.models.schemas import UserCreateRequest, UserUpdateRequest, SlotCreateRequest, SlotUpdateRequest
from backend.core.database import query_all, query_one, execute
from backend.core.security import hash_password
from backend.services.audit_service import log_audit, get_recent_audit_logs
from backend.services.sheets_service import trigger_sheets_sync_async

router = APIRouter(prefix="/api/admin", tags=["Admin Management"])

# Admin data console resources. Identifiers and editable columns are fixed here;
# request values are always SQL parameters. Histories, credentials and hardware
# secrets are intentionally not exposed through this generic editor.
ADMIN_DATA = {
    "vehicles": {"table": "vehicles", "label": "รถ", "write": {"plate_no", "province", "plate_display", "plate_clean", "vehicle_type", "brand", "model", "color", "rfid_tag", "is_active"}, "read_only": {"id", "created_at", "updated_at"}},
    "user_vehicles": {"table": "user_vehicles", "label": "สิทธิ์รถของผู้ใช้", "write": {"user_id", "vehicle_id", "is_primary", "is_approved"}, "read_only": {"id", "created_at"}},
    "floors": {"table": "parking_floors", "label": "ชั้นจอด", "write": {"floor_number", "floor_name", "total_slots", "detection_type", "is_active"}, "read_only": {"id", "created_at"}},
    "zones": {"table": "parking_zones", "label": "โซนจอด", "write": {"floor_id", "zone_code", "zone_name"}, "read_only": {"id", "created_at"}},
    "camera_zones": {"table": "camera_slot_zones", "label": "พื้นที่ตรวจจับของกล้อง", "write": {"camera_id", "slot_id", "polygon_points", "is_active"}, "read_only": {"id", "created_at"}},
    "cameras": {"table": "cameras", "label": "กล้อง", "write": {"camera_code", "name", "location_type", "floor_id", "status"}, "read_only": {"id", "last_frame_ts", "created_at"}},
    "gates": {"table": "gates", "label": "ไม้กั้น", "write": {"gate_code", "name", "direction", "status", "auto_close_sec", "camera_id", "is_active"}, "read_only": {"id", "created_at"}},
}

@router.get("/data-resources")
def list_admin_data_resources(current_user: dict = Depends(require_console_admin)):
    return {"status": "ok", "resources": [{"key": k, "label": v["label"]} for k, v in ADMIN_DATA.items()]}

@router.get("/data/{resource}")
def list_admin_data(resource: str, current_user: dict = Depends(require_console_admin)):
    spec = ADMIN_DATA.get(resource)
    if not spec:
        raise HTTPException(status_code=404, detail="ไม่พบหมวดข้อมูล")
    rows = query_all(f"SELECT * FROM {spec['table']} ORDER BY id DESC LIMIT 500;")
    hidden = {"password_hash", "rtsp_url", "stream_url", "controller_ip"}
    safe_rows = [{k: v for k, v in row.items() if k not in hidden} for row in rows]
    return {"status": "ok", "rows": safe_rows, "writable_fields": sorted(spec["write"])}

def _admin_data_values(resource: str, values: Dict[str, Any]):
    spec = ADMIN_DATA.get(resource)
    if not spec:
        raise HTTPException(status_code=404, detail="ไม่พบหมวดข้อมูล")
    if not isinstance(values, dict) or not values:
        raise HTTPException(status_code=422, detail="กรุณาระบุข้อมูลที่ต้องบันทึก")
    if set(values) - spec["write"]:
        raise HTTPException(status_code=400, detail="มีฟิลด์ที่ไม่อนุญาตให้แก้ไข")
    return spec

@router.post("/data/{resource}")
def create_admin_data(resource: str, values: Dict[str, Any] = Body(...), current_user: dict = Depends(require_console_admin)):
    spec = _admin_data_values(resource, values)
    cols = list(values)
    try:
        new_id = execute(f"INSERT INTO {spec['table']} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)});", tuple(values[c] for c in cols))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"เพิ่มข้อมูลไม่สำเร็จ: {exc}")
    log_audit(current_user["username"], "ADMIN_DATA_CREATE", resource.upper(), str(new_id), None, json.dumps(values, ensure_ascii=False), user_id=current_user["id"])
    return {"status": "ok", "id": new_id}

@router.put("/data/{resource}/{row_id}")
def update_admin_data(resource: str, row_id: int, values: Dict[str, Any] = Body(...), current_user: dict = Depends(require_console_admin)):
    spec = _admin_data_values(resource, values)
    old = query_one(f"SELECT * FROM {spec['table']} WHERE id = ?;", (row_id,))
    if not old:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล")
    cols = list(values)
    try:
        execute(f"UPDATE {spec['table']} SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?;", tuple(values[c] for c in cols) + (row_id,))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"แก้ไขข้อมูลไม่สำเร็จ: {exc}")
    log_audit(current_user["username"], "ADMIN_DATA_UPDATE", resource.upper(), str(row_id), json.dumps({k: old.get(k) for k in cols}, ensure_ascii=False), json.dumps(values, ensure_ascii=False), user_id=current_user["id"])
    return {"status": "ok", "id": row_id}

@router.delete("/data/{resource}/{row_id}")
def delete_admin_data(resource: str, row_id: int, current_user: dict = Depends(require_console_admin)):
    # Only relationship/mapping rows may be removed; historical or primary entities are retained.
    if resource not in {"user_vehicles", "camera_zones"}:
        raise HTTPException(status_code=403, detail="ข้อมูลหลักและประวัติไม่อนุญาตให้ลบ ให้ปิดใช้งานหรือแก้ไขแทน")
    spec = ADMIN_DATA[resource]
    old = query_one(f"SELECT * FROM {spec['table']} WHERE id = ?;", (row_id,))
    if not old:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล")
    execute(f"DELETE FROM {spec['table']} WHERE id = ?;", (row_id,))
    log_audit(current_user["username"], "ADMIN_DATA_DELETE", resource.upper(), str(row_id), json.dumps(old, ensure_ascii=False), None, user_id=current_user["id"])
    return {"status": "ok"}


# ==============================================================================
# 1. USER MANAGEMENT (ADMIN ONLY)
# ==============================================================================

@router.get("/users")
def list_users(role: Optional[str] = Query(None), search: Optional[str] = Query(None),
               current_user: dict = Depends(require_console_admin)):
    """List all users with search, role filter, personal info, and last login"""
    sql = """
        SELECT u.id, u.username, r.code as role_code, r.name as role_name,
               u.name, u.email, u.phone, u.faculty, u.department,
               u.gender, u.age, u.birthdate, u.last_login_at,
               u.is_active, u.created_at
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE 1=1
    """
    params = []
    if role:
        sql += " AND r.code = ?"
        params.append(role.upper())
    if search:
        s = f"%{search.strip()}%"
        sql += " AND (u.name LIKE ? OR u.username LIKE ? OR COALESCE(u.phone, '') LIKE ?)"
        params.extend([s, s, s])

    sql += " ORDER BY u.id ASC;"
    users = query_all(sql, tuple(params))
    return {"status": "ok", "users": users}


@router.post("/users")
def create_user(req: UserCreateRequest, current_user: dict = Depends(require_console_admin)):
    role = query_one("SELECT id, code FROM roles WHERE code = ?;", (req.role_code.upper(),))
    if not role:
        raise HTTPException(status_code=400, detail="บทบาทผู้ใช้งาน (role_code) ไม่ถูกต้อง")

    existing = query_one("SELECT id FROM users WHERE username = ?;", (req.username.strip(),))
    if existing:
        raise HTTPException(status_code=400, detail="รหัสประจำตัว (Username) นี้มีในระบบแล้ว")

    pwd_hash = hash_password(req.password)
    user_id = execute("""
        INSERT INTO users (username, password_hash, role_id, name, email, phone, faculty, department, gender, age, birthdate, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
    """, (
        req.username.strip(), pwd_hash, role["id"], req.name.strip(),
        req.email, req.phone, req.faculty, req.department,
        req.gender, req.age, req.birthdate
    ))

    log_audit(
        current_user["username"], "USER_CREATE", "USER", str(user_id),
        None, f"Created user {req.username} with role {role['code']} (SUCCESS)",
        user_id=current_user["id"]
    )
    trigger_sheets_sync_async(current_user["username"])
    return {"status": "ok", "user_id": user_id, "message": "เพิ่มผู้ใช้งานใหม่สำเร็จ"}


@router.put("/users/{user_id}")
def update_user(user_id: int, req: UserUpdateRequest, current_user: dict = Depends(require_console_admin)):
    user = query_one("""
        SELECT u.*, r.code as old_role_code
        FROM users u JOIN roles r ON u.role_id = r.id
        WHERE u.id = ?;
    """, (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งานในระบบ")

    updates = []
    params = []
    audit_changes = []

    if req.name is not None:
        updates.append("name = ?"); params.append(req.name.strip())
        audit_changes.append(f"name='{req.name.strip()}'")
    if req.role_code is not None:
        role = query_one("SELECT id, code FROM roles WHERE code = ?;", (req.role_code.upper(),))
        if not role:
            raise HTTPException(status_code=400, detail="Role ที่ระบุไม่ถูกต้อง")
        updates.append("role_id = ?"); params.append(role["id"])
        if role["code"] != user["old_role_code"]:
            audit_changes.append(f"role:{user['old_role_code']}->{role['code']}")
    if req.email is not None:
        updates.append("email = ?"); params.append(req.email.strip() or None)
    if req.phone is not None:
        updates.append("phone = ?"); params.append(req.phone.strip() or None)
        audit_changes.append("phone")
    if req.faculty is not None:
        updates.append("faculty = ?"); params.append(req.faculty.strip() or None)
    if req.department is not None:
        updates.append("department = ?"); params.append(req.department.strip() or None)
    if req.gender is not None:
        val_g = None if req.gender.strip() in ("", "ยังไม่ได้ระบุ") else req.gender.strip()
        updates.append("gender = ?"); params.append(val_g)
        audit_changes.append("gender")
    if req.age is not None:
        updates.append("age = ?"); params.append(req.age)
        audit_changes.append("age")
    if req.birthdate is not None:
        val_b = None if req.birthdate.strip() in ("", "ยังไม่ได้ระบุ") else req.birthdate.strip()
        updates.append("birthdate = ?"); params.append(val_b)
        audit_changes.append("birthdate")
    if req.is_active is not None:
        updates.append("is_active = ?"); params.append(req.is_active)
        audit_changes.append(f"is_active={req.is_active}")
    if req.password:
        updates.append("password_hash = ?"); params.append(hash_password(req.password))
        audit_changes.append("password_reset")

    if updates:
        params.append(user_id)
        execute(f"UPDATE users SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?;", tuple(params))
        log_audit(
            current_user["username"], "USER_UPDATE", "USER", str(user_id),
            user["old_role_code"], f"Updated {', '.join(audit_changes)} -> SUCCESS",
            user_id=current_user["id"]
        )
        trigger_sheets_sync_async(current_user["username"])

    return {"status": "ok", "message": "อัปเดตข้อมูลและสิทธิ์ผู้ใช้งานสำเร็จทันที"}


# ==============================================================================
# 2. PARKING SLOT MANAGEMENT (ADMIN & SECURITY)
# ==============================================================================

@router.get("/slots")
def list_all_slots(floor: Optional[int] = Query(None),
                   current_user: dict = Depends(require_roles(["ADMIN", "SECURITY"]))):
    """List all parking slots with vehicle, owner, and detection info from DB"""
    sql = """
        SELECT s.id, s.slot_number, s.slot_type, s.status, s.occupied_since,
               s.detection_source, s.last_detected_at,
               pf.floor_number, pf.floor_name, pz.zone_code,
               v.plate_display, v.plate_clean, u.name as owner_name, u.phone as owner_phone
        FROM parking_slots s
        JOIN parking_floors pf ON s.floor_id = pf.id
        LEFT JOIN parking_zones pz ON s.zone_id = pz.id
        LEFT JOIN vehicles v ON s.current_vehicle_id = v.id
        LEFT JOIN user_vehicles uv ON v.id = uv.vehicle_id AND uv.is_primary = 1
        LEFT JOIN users u ON uv.user_id = u.id
    """
    params = []
    if floor:
        sql += " WHERE pf.floor_number = ?"
        params.append(floor)
    sql += " ORDER BY pf.floor_number ASC, s.slot_number ASC;"

    slots = query_all(sql, tuple(params))
    return {"status": "ok", "slots": slots}


@router.get("/slots/history")
def list_slot_history(current_user: dict = Depends(require_roles(["ADMIN", "SECURITY"]))):
    """Return audit history of slot status & configuration changes"""
    logs = query_all("""
        SELECT * FROM audit_logs
        WHERE resource_type = 'SLOT'
        ORDER BY id DESC LIMIT 50;
    """)
    return {"status": "ok", "history": logs}


@router.post("/slots")
def add_slot(req: SlotCreateRequest, current_user: dict = Depends(require_console_admin)):
    """Add a new parking slot with floor/zone/code validation"""
    fl = query_one("SELECT id FROM parking_floors WHERE floor_number = ?;", (req.floor_number,))
    if not fl:
        raise HTTPException(status_code=400, detail="ชั้นจอดรถที่ระบุไม่ถูกต้อง")

    clean_code = req.slot_number.strip().upper()
    existing = query_one("SELECT id FROM parking_slots WHERE floor_id = ? AND slot_number = ?;", (fl["id"], clean_code))
    if existing:
        raise HTTPException(status_code=400, detail=f"รหัสช่องจอด {clean_code} มีอยู่แล้วในชั้น {req.floor_number}")

    new_status = req.status.upper()
    if new_status not in ("AVAILABLE", "OCCUPIED", "RESERVED", "UNKNOWN", "ERROR", "CONFLICT"):
        raise HTTPException(status_code=400, detail="สถานะช่องจอดไม่ถูกต้อง")

    zone_code = (req.zone_code or "A").strip().upper()
    zone = query_one("SELECT id FROM parking_zones WHERE floor_id = ? AND zone_code = ?;", (fl["id"], zone_code))
    if not zone:
        zone_id = execute(
            "INSERT INTO parking_zones (floor_id, zone_code, zone_name) VALUES (?, ?, ?);",
            (fl["id"], zone_code, f"โซน {zone_code}")
        )
    else:
        zone_id = zone["id"]

    slot_id = execute("""
        INSERT INTO parking_slots (floor_id, zone_id, slot_number, slot_type, status, detection_source)
        VALUES (?, ?, ?, ?, ?, 'MANUAL_ADMIN');
    """, (fl["id"], zone_id, clean_code, req.slot_type.upper(), new_status))

    log_audit(
        current_user["username"], "SLOT_CREATE", "SLOT", str(slot_id),
        None, f"Added slot {clean_code} on Floor {req.floor_number} Zone {zone_code} ({req.slot_type.upper()})",
        user_id=current_user["id"]
    )
    return {"status": "ok", "slot_id": slot_id, "message": f"เพิ่มช่องจอด {clean_code} ชั้น {req.floor_number} สำเร็จ"}


@router.put("/slots/{slot_id}")
def update_slot(slot_id: int, req: SlotUpdateRequest,
                current_user: dict = Depends(require_roles(["ADMIN", "SECURITY"]))):
    """Update parking slot configuration/status with strict duplicate car & reason tracking"""
    slot = query_one("SELECT * FROM parking_slots WHERE id = ?;", (slot_id,))
    if not slot:
        raise HTTPException(status_code=404, detail="ไม่พบช่องจอดที่ระบุ")

    new_status = req.status.upper()
    if new_status not in ("AVAILABLE", "OCCUPIED", "RESERVED", "UNKNOWN", "ERROR", "CONFLICT"):
        raise HTTPException(status_code=400, detail="สถานะช่องจอดต้องเป็น AVAILABLE, OCCUPIED, RESERVED, UNKNOWN, ERROR หรือ CONFLICT เท่านั้น")

    # Only ADMIN can rename slot_number, floor_number, zone_code, slot_type
    floor_id = slot["floor_id"]
    zone_id = slot["zone_id"]
    slot_number = slot["slot_number"]
    slot_type = slot["slot_type"]

    if current_user["role_code"] == "ADMIN":
        if req.floor_number is not None:
            fl = query_one("SELECT id FROM parking_floors WHERE floor_number = ?;", (req.floor_number,))
            if not fl:
                raise HTTPException(status_code=400, detail="ชั้นจอดรถไม่ถูกต้อง")
            floor_id = fl["id"]
        if req.slot_number is not None and req.slot_number.strip():
            cand = req.slot_number.strip().upper()
            dup = query_one(
                "SELECT id FROM parking_slots WHERE floor_id = ? AND slot_number = ? AND id != ?;",
                (floor_id, cand, slot_id)
            )
            if dup:
                raise HTTPException(status_code=400, detail=f"รหัสช่องจอด {cand} ซ้ำกับช่องอื่นในชั้นเดียวกัน")
            slot_number = cand
        if req.zone_code is not None and req.zone_code.strip():
            zc = req.zone_code.strip().upper()
            zrow = query_one("SELECT id FROM parking_zones WHERE floor_id = ? AND zone_code = ?;", (floor_id, zc))
            zone_id = zrow["id"] if zrow else execute(
                "INSERT INTO parking_zones (floor_id, zone_code, zone_name) VALUES (?, ?, ?);",
                (floor_id, zc, f"โซน {zc}")
            )
        if req.slot_type is not None and req.slot_type.strip():
            slot_type = req.slot_type.strip().upper()

    vehicle_id = None
    plate_str = (req.vehicle_plate or "").strip()
    if plate_str and new_status == "OCCUPIED":
        clean_p = plate_str.replace(" ", "").strip()
        veh = query_one(
            "SELECT id, plate_display FROM vehicles WHERE plate_clean = ? OR plate_display LIKE ? LIMIT 1;",
            (clean_p, f"%{clean_p}%")
        )
        if not veh:
            # Register temporary guest vehicle record if not in vehicles yet so FK is valid
            vid = execute(
                "INSERT INTO vehicles (plate_no, province, plate_display, plate_clean, vehicle_type, is_active) VALUES (?, 'ไม่ระบุ', ?, ?, 'car', 1);",
                (plate_str, plate_str, clean_p)
            )
            veh = {"id": vid, "plate_display": plate_str}

        # Rule 5: One vehicle CANNOT occupy 2 slots simultaneously!
        conflict = query_one(
            "SELECT id, slot_number FROM parking_slots WHERE current_vehicle_id = ? AND status = 'OCCUPIED' AND id != ?;",
            (veh["id"], slot_id)
        )
        if conflict:
            raise HTTPException(
                status_code=400,
                detail=f"ไม่อนุญาต: รถทะเบียน {veh['plate_display']} กำลังครอบครองช่องจอด {conflict['slot_number']} อยู่แล้ว"
            )
        vehicle_id = veh["id"]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    occ_since = (slot["occupied_since"] or now_str) if new_status == "OCCUPIED" else None
    src = f"MANUAL_{current_user['role_code']}"

    execute("""
        UPDATE parking_slots
        SET floor_id = ?, zone_id = ?, slot_number = ?, slot_type = ?,
            status = ?, current_vehicle_id = ?, occupied_since = ?,
            detection_source = ?, last_detected_at = ?
        WHERE id = ?;
    """, (floor_id, zone_id, slot_number, slot_type, new_status, vehicle_id, occ_since, src, now_str, slot_id))

    reason_text = req.reason or req.notes or "ยืนยันการปรับปรุงสถานะโดยเจ้าหน้าที่"
    log_audit(
        current_user["username"], "SLOT_UPDATE", "SLOT", str(slot_id),
        slot["status"], f"{slot_number} -> {new_status} | รถ: {plate_str or '-'} | เหตุผล: {reason_text}",
        user_id=current_user["id"]
    )
    return {"status": "ok", "message": f"บันทึกช่องจอด {slot_number} สถานะ {new_status} สำเร็จ"}


@router.delete("/slots/{slot_id}")
def delete_slot(slot_id: int, current_user: dict = Depends(require_console_admin)):
    """Delete parking slot (prevent deleting if actively occupied)"""
    slot = query_one("SELECT * FROM parking_slots WHERE id = ?;", (slot_id,))
    if not slot:
        raise HTTPException(status_code=404, detail="ไม่พบช่องจอดที่ระบุ")
    if slot["status"] == "OCCUPIED":
        raise HTTPException(status_code=400, detail="ไม่สามารถลบช่องจอดที่มีรถกำลังจอดอยู่ได้ กรุณาย้ายรถออกก่อน")

    execute("DELETE FROM parking_slots WHERE id = ?;", (slot_id,))
    log_audit(
        current_user["username"], "SLOT_DELETE", "SLOT", str(slot_id),
        slot["slot_number"], f"Deleted slot {slot['slot_number']}",
        user_id=current_user["id"]
    )
    return {"status": "ok", "message": f"ลบช่องจอด {slot['slot_number']} สำเร็จ"}


# ==============================================================================
# 3. LOGIN HISTORY, AUDIT LOGS & SYSTEM HEALTH
# ==============================================================================

@router.get("/login-logs")
def login_history(current_user: dict = Depends(require_console_admin)):
    """List user login/logout history for Sheet 5 and Admin inspection"""
    logs = query_all("SELECT * FROM login_logs ORDER BY id DESC LIMIT 100;")
    return {"status": "ok", "logs": logs}


@router.get("/vehicles")
def list_vehicles(current_user: dict = Depends(require_roles(["ADMIN", "SECURITY"]))):
    vehicles = query_all("""
        SELECT v.*, u.name as owner_name, u.username as owner_code, r.name as owner_role
        FROM vehicles v
        LEFT JOIN user_vehicles uv ON v.id = uv.vehicle_id AND uv.is_primary = 1
        LEFT JOIN users u ON uv.user_id = u.id
        LEFT JOIN roles r ON u.role_id = r.id
        ORDER BY v.id DESC;
    """)
    return {"status": "ok", "vehicles": vehicles}


@router.get("/audit-logs")
def audit_logs(current_user: dict = Depends(require_console_admin)):
    return {"status": "ok", "logs": get_recent_audit_logs(100)}


@router.get("/system-health")
def system_health(current_user: dict = Depends(require_roles(["ADMIN", "SECURITY"]))):
    total_users = query_one("SELECT COUNT(*) as count FROM users;")["count"]
    total_vehicles = query_one("SELECT COUNT(*) as count FROM vehicles;")["count"]
    total_parked = query_one("SELECT COUNT(*) as count FROM parking_slots WHERE status = 'OCCUPIED';")["count"]
    total_slots = query_one("SELECT COUNT(*) as count FROM parking_slots;")["count"]
    pending_ai = query_one("SELECT COUNT(*) as count FROM ai_events WHERE status = 'PENDING';")["count"]

    return {
        "status": "ok",
        "health": {
            "backend": "ONLINE",
            "database": "CONNECTED",
            "mqtt_broker": "CONNECTED",
            "total_users": total_users,
            "total_vehicles": total_vehicles,
            "total_parked": total_parked,
            "total_slots": total_slots,
            "pending_ai_events": pending_ai
        }
    }
