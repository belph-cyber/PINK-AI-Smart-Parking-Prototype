# -*- coding: utf-8 -*-
"""
Parking & Slot Management Service:
- Multi-floor summaries from SQLite DB
- Interactive Parking Slot Map
- Strict Personal My Parking & History per user_id
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import os
from backend.core.database import query_one, query_all, execute
from backend.services.audit_service import log_audit

SLOT_STALE_SEC = max(1, int(os.getenv("SLOT_STALE_SEC", "90")))
SLOT_STATES = {"AVAILABLE", "OCCUPIED", "RESERVED", "UNKNOWN", "ERROR", "CONFLICT"}


def _apply_evidence_state(slot: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Fail closed: an old, missing, or malformed observation is never AVAILABLE."""
    result = dict(slot)
    state = str(result.get("status") or "UNKNOWN").upper()
    source = result.get("detection_source")
    observed_at = result.get("last_detected_at")
    if state not in SLOT_STATES:
        state = "ERROR"

    if state in {"ERROR", "CONFLICT"}:
        evidence_state = state
        age_sec = None
    elif state == "RESERVED":
        evidence_state = "RESERVATION"
        age_sec = None
    elif not source or not observed_at:
        state = "UNKNOWN"
        evidence_state = "NO_EVIDENCE"
        age_sec = None
    else:
        try:
            observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
            current = now or datetime.now(observed.tzinfo) if observed.tzinfo else (now or datetime.now())
            age_sec = max(0, int((current - observed).total_seconds()))
            if age_sec > SLOT_STALE_SEC:
                state = "UNKNOWN"
                evidence_state = "STALE"
            else:
                evidence_state = "MANUAL" if str(source).upper() in {"MANUAL_SECURITY", "ADMIN_MANUAL"} else "LIVE"
        except (TypeError, ValueError):
            state = "UNKNOWN"
            evidence_state = "NO_EVIDENCE"
            age_sec = None

    result["status"] = state
    result["evidence_state"] = evidence_state
    result["evidence_age_sec"] = age_sec
    return result


def get_floors_overview() -> List[Dict[str, Any]]:
    """Return overview of all floors with real available and occupied counts"""
    floors = query_all("SELECT * FROM parking_floors WHERE is_active = 1 ORDER BY floor_number ASC;")
    result = []
    for fl in floors:
        slots = query_all("""
            SELECT s.id, s.floor_id, s.zone_id, z.zone_code, s.slot_number, s.slot_type, s.status,
                   s.occupied_since, s.detection_source, s.last_detected_at,
                   v.plate_display, v.plate_clean
            FROM parking_slots s
            LEFT JOIN parking_zones z ON s.zone_id = z.id
            LEFT JOIN vehicles v ON s.current_vehicle_id = v.id
            WHERE s.floor_id = ?
            ORDER BY s.slot_number ASC;
        """, (fl["id"],))

        slots = [_apply_evidence_state(s) for s in slots]
        total = max(fl["total_slots"], len(slots))
        available_count = sum(1 for s in slots if s["status"] == "AVAILABLE")
        occupied_count = sum(1 for s in slots if s["status"] == "OCCUPIED")
        reserved_count = sum(1 for s in slots if s["status"] == "RESERVED")
        error_count = sum(1 for s in slots if s["status"] == "ERROR")
        conflict_count = sum(1 for s in slots if s["status"] == "CONFLICT")
        unknown_count = sum(1 for s in slots if s["status"] == "UNKNOWN") + max(0, total - len(slots))

        result.append({
            "floor_id": fl["id"],
            "floor_number": fl["floor_number"],
            "floor_name": fl["floor_name"],
            "total_slots": total,
            "occupied_slots": occupied_count,
            "reserved_slots": reserved_count,
            "free_slots": available_count,
            "detection_type": fl["detection_type"],
            "unknown_slots": unknown_count,
            "error_slots": error_count,
            "conflict_slots": conflict_count,
            "slots": slots
        })
    return result


def get_floor_slot_map(floor_number: int) -> Dict[str, Any]:
    """Return detailed slot map for a specific floor"""
    floor = query_one("SELECT * FROM parking_floors WHERE floor_number = ?;", (floor_number,))
    if not floor:
        return {}

    slots = query_all("""
        SELECT s.id, s.slot_number, s.slot_type, s.status, s.occupied_since, s.detection_source,
               s.last_detected_at, z.zone_code, z.zone_name,
               v.plate_display, v.plate_clean, v.brand, v.model, v.color
        FROM parking_slots s
        LEFT JOIN parking_zones z ON s.zone_id = z.id
        LEFT JOIN vehicles v ON s.current_vehicle_id = v.id
        WHERE s.floor_id = ?
        ORDER BY s.slot_number ASC;
    """, (floor["id"],))

    slots = [_apply_evidence_state(s) for s in slots]
    occupied = sum(1 for s in slots if s["status"] == "OCCUPIED")
    available = sum(1 for s in slots if s["status"] == "AVAILABLE")
    unknown = sum(1 for s in slots if s["status"] == "UNKNOWN")
    total = max(floor["total_slots"], len(slots))
    return {
        "floor": floor,
        "total_slots": total,
        "occupied_slots": occupied,
        "free_slots": available,
        "unknown_slots": unknown + max(0, total - len(slots)),
        "slots": slots
    }


def update_slot_status(slot_id: int, new_status: str, vehicle_plate: Optional[str] = None,
                       user_id: Optional[int] = None, username: str = "security",
                       source: str = "MANUAL_SECURITY") -> Dict[str, Any]:
    """Update or override a parking slot status with duplicate validation & Audit Logging"""
    new_status = str(new_status or "").upper()
    if new_status not in SLOT_STATES:
        return {"success": False, "message": "Unsupported slot status"}

    slot = query_one("SELECT * FROM parking_slots WHERE id = ?;", (slot_id,))
    if not slot:
        return {"success": False, "message": "Slot not found"}

    old_status = slot["status"]
    vehicle_id = None

    if vehicle_plate and new_status.upper() == "OCCUPIED":
        clean_p = vehicle_plate.replace(" ", "").strip()
        veh = query_one("SELECT id FROM vehicles WHERE plate_clean = ? OR plate_display LIKE ?;", (clean_p, f"%{clean_p}%"))
        if veh:
            conflict = query_one(
                "SELECT id, slot_number FROM parking_slots WHERE current_vehicle_id = ? AND status = 'OCCUPIED' AND id != ?;",
                (veh["id"], slot_id)
            )
            if conflict:
                return {"success": False, "message": f"รถทะเบียน {vehicle_plate} ครองช่อง {conflict['slot_number']} อยู่แล้ว"}
            vehicle_id = veh["id"]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    occ_since = (slot["occupied_since"] or now_str) if new_status.upper() == "OCCUPIED" else None

    execute("""
        UPDATE parking_slots
        SET status = ?, current_vehicle_id = ?, occupied_since = ?, detection_source = ?, last_detected_at = ?
        WHERE id = ?;
    """, (new_status.upper(), vehicle_id, occ_since, source, now_str, slot_id))

    log_audit(username, "SLOT_OVERRIDE", "SLOT", str(slot_id), old_status, new_status.upper(), user_id=user_id)
    return {"success": True, "message": f"Updated slot {slot['slot_number']} to {new_status.upper()}"}


def get_user_parking_details(user_id: int) -> Dict[str, Any]:
    """Retrieve strictly isolated personal My Parking & History for the authenticated user"""
    vehicles = query_all("""
        SELECT v.*, uv.is_primary, uv.is_approved
        FROM user_vehicles uv
        JOIN vehicles v ON uv.vehicle_id = v.id
        WHERE uv.user_id = ?;
    """, (user_id,))

    primary_veh = next((v for v in vehicles if v["is_primary"]), vehicles[0] if vehicles else None)
    vehicle_ids = [v["id"] for v in vehicles]

    active_session = None
    history = []

    if vehicle_ids:
        placeholders = ",".join("?" for _ in vehicle_ids)
        active_session = query_one(f"""
            SELECT ps.*, g.name as entry_gate_name, ps_slot.slot_number, pf.floor_name, v.plate_display
            FROM parking_sessions ps
            JOIN vehicles v ON ps.vehicle_id = v.id
            LEFT JOIN gates g ON ps.entry_gate_id = g.id
            LEFT JOIN parking_slots ps_slot ON ps.assigned_slot_id = ps_slot.id
            LEFT JOIN parking_floors pf ON ps.current_floor = pf.floor_number
            WHERE ps.vehicle_id IN ({placeholders}) AND ps.session_status = 'ACTIVE'
            ORDER BY ps.id DESC LIMIT 1;
        """, tuple(vehicle_ids))

        history = query_all(f"""
            SELECT ps.id, ps.entry_time, ps.exit_time, ps.current_floor, ps.session_status,
                   v.plate_display, ps_slot.slot_number, COALESCE(g.name, 'CiRA LPR') as source
            FROM parking_sessions ps
            JOIN vehicles v ON ps.vehicle_id = v.id
            LEFT JOIN parking_slots ps_slot ON ps.assigned_slot_id = ps_slot.id
            LEFT JOIN gates g ON ps.entry_gate_id = g.id
            WHERE ps.vehicle_id IN ({placeholders})
            ORDER BY ps.id DESC LIMIT 30;
        """, tuple(vehicle_ids))

    return {
        "vehicles": vehicles,
        "primary_vehicle": primary_veh,
        "active_session": active_session,
        "is_parked": bool(active_session),
        "current_floor": active_session["current_floor"] if active_session else None,
        "slot_number": active_session["slot_number"] if active_session else None,
        "entry_time": active_session["entry_time"] if active_session else None,
        "history": history
    }
