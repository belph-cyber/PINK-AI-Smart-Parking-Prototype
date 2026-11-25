# -*- coding: utf-8 -*-
"""
AI Integration & Hybrid Parking Detection Service:
- Deduplication of camera reads
- Hybrid verification queue (Pending, Confirmed, Rejected, Resolved)
- Confidence threshold checks
"""

import time
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.core.database import query_one, query_all, execute
from backend.services.audit_service import log_audit

# In-memory deduplication cache: { clean_plate_cam: last_timestamp }
dedup_cache: Dict[str, float] = {}
DEDUP_WINDOW_SEC = 15.0
DEFAULT_CONFIDENCE_THRESHOLD = 0.75

def clean_plate_text(raw_plate: str) -> str:
    """Strip whitespace and punctuation for exact matching"""
    if not raw_plate:
        return ""
    return re.sub(r"[^0-9a-zA-Z\u0E00-\u0E7F]", "", raw_plate).strip()

def process_ai_lpr_detection(camera_code: str, raw_plate: str, confidence: Optional[float] = None,
                             evidence_image_path: Optional[str] = None, suggested_floor: Optional[int] = None,
                             suggested_slot_number: Optional[str] = None,
                             event_type: str = "LPR_DETECT") -> Dict[str, Any]:
    """
    Process incoming LPR detection from CiRA Core or IP Camera:
    1. Deduplicate rapid duplicate reads
    2. Lookup camera and vehicle record
    3. If confidence < threshold -> Set to PENDING for Security Review
    4. Create AI Event and Vehicle Event
    """
    clean_p = clean_plate_text(raw_plate)
    if not clean_p and event_type != "OCR_FAILED":
        return {"status": "ignored", "reason": "empty_plate"}

    now_ts = time.time()
    if clean_p:
        cache_key = f"{camera_code}_{clean_p}"
        if cache_key in dedup_cache and (now_ts - dedup_cache[cache_key]) < DEDUP_WINDOW_SEC:
            return {"status": "deduplicated", "reason": "read_within_cooldown"}
        dedup_cache[cache_key] = now_ts

    cam = query_one("SELECT * FROM cameras WHERE camera_code = ?;", (camera_code,))
    if not cam:
        camera_location = "GATE" if "GATE" in camera_code.upper() else "FLOOR_HEAD"
        cam_id = execute("INSERT INTO cameras (camera_code, name, location_type, status) VALUES (?, ?, ?, 'OFFLINE');",
                         (camera_code, f"Camera {camera_code}", camera_location))
    else:
        cam_id = cam["id"]

    # Check vehicle authorization in database
    veh = query_one("SELECT * FROM vehicles WHERE plate_clean = ?;", (clean_p,)) if clean_p else None
    is_known = veh is not None
    is_authorized = veh and veh["is_active"]

    # Every detection waits in Security review. Confidence and registration are
    # evidence for the reviewer, never approval to open a gate.
    ai_status = "PENDING"

    suggested_slot_id = None
    if suggested_slot_number and suggested_floor:
        slot = query_one("""
            SELECT s.id FROM parking_slots s
            JOIN parking_floors pf ON s.floor_id = pf.id
            WHERE pf.floor_number = ? AND s.slot_number = ?;
        """, (suggested_floor, suggested_slot_number))
        if slot:
            suggested_slot_id = slot["id"]

    event_id = execute("""
        INSERT INTO ai_events (camera_id, event_type, raw_plate, clean_plate, confidence_score,
                               evidence_image_path, suggested_floor, suggested_slot_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (cam_id, event_type, raw_plate or None, clean_p or None, confidence, evidence_image_path,
          suggested_floor, suggested_slot_id, ai_status))

    return {
        "event_id": event_id,
        "clean_plate": clean_p,
        "status": ai_status,
        "is_authorized": is_authorized,
        "confidence": confidence,
        "confidence_state": "MISSING" if confidence is None else "REPORTED",
        "gate_action": "NOT_REQUESTED"
    }

def handle_confirmed_vehicle_movement(vehicle_id: int, location_type: str, floor_num: int, camera_id: int):
    """Record a movement only when an explicit confirmation workflow calls this."""
    active_session = query_one("""
        SELECT * FROM parking_sessions WHERE vehicle_id = ? AND session_status = 'ACTIVE' ORDER BY id DESC LIMIT 1;
    """, (vehicle_id,))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not active_session:
        return {"success": False, "reason": "no_active_session"}
    session_id = active_session["id"]
    execute("UPDATE parking_sessions SET current_floor = ? WHERE id = ?;", (floor_num, session_id))

    execute("""
        INSERT INTO vehicle_events (session_id, vehicle_id, event_type, floor_number, camera_id, detected_at)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (session_id, vehicle_id, location_type, floor_num, camera_id, now_str))
    return {"success": True, "session_id": session_id}

def verify_ai_event(event_id: int, action: str, security_user_id: int, security_username: str,
                    corrected_plate: Optional[str] = None, corrected_slot_id: Optional[int] = None,
                    review_notes: Optional[str] = None) -> Dict[str, Any]:
    """Security Officer reviews and confirms/rejects/corrects an AI event"""
    evt = query_one("SELECT * FROM ai_events WHERE id = ?;", (event_id,))
    if not evt:
        return {"success": False, "message": "Event not found"}

    action = action.upper()
    if action not in ("CONFIRM", "REJECT", "RESOLVE"):
        return {"success": False, "message": "Unsupported review action"}
    if evt["status"] != "PENDING":
        return {"success": False, "message": "This event has already been reviewed"}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target_plate = clean_plate_text(corrected_plate) if corrected_plate else evt["clean_plate"]
    if action == "CONFIRM" and not target_plate:
        return {"success": False, "message": "ต้องระบุทะเบียนที่ตรวจสอบแล้วก่อนยืนยัน"}

    new_status = "CONFIRMED" if action == "CONFIRM" else ("REJECTED" if action == "REJECT" else "RESOLVED")

    location_update = None
    if action == "CONFIRM" and evt["suggested_floor"] and evt["event_type"] == "LPR_DETECT" and target_plate:
        vehicle = query_one("SELECT id FROM vehicles WHERE plate_clean = ? AND is_active = 1;", (target_plate,))
        if vehicle:
            camera = query_one("SELECT location_type FROM cameras WHERE id = ?;", (evt["camera_id"],))
            if camera and camera.get("location_type") != "GATE":
                session = query_one("SELECT id FROM parking_sessions WHERE vehicle_id = ? AND session_status = 'ACTIVE' ORDER BY id DESC LIMIT 1;", (vehicle["id"],))
                if not session:
                    return {"success": False, "message": "ไม่มี Parking Session ที่กำลังใช้งาน จึงไม่อัปเดตตำแหน่งรถ"}
                location_update = (vehicle["id"], evt["suggested_floor"], evt["camera_id"])

    execute("""
        UPDATE ai_events
        SET status = ?, verified_by_user_id = ?, verified_at = ?, review_notes = ?,
            corrected_plate = ?, corrected_slot_id = ?
        WHERE id = ?;
    """, (new_status, security_user_id, now_str, review_notes,
          target_plate if corrected_plate else None, corrected_slot_id, event_id))

    # A floor camera's AI guess stays a suggestion until Security confirms it.
    # Confirmation may update an existing session only; it never creates an entry.
    if location_update:
        vehicle_id, floor_number, camera_id = location_update
        handle_confirmed_vehicle_movement(vehicle_id, "FLOOR_MOVE", floor_number, camera_id)

    log_audit(security_username, f"AI_EVENT_{new_status}", "AI_EVENT", str(event_id),
              evt["status"], f"Plate: {target_plate}, Notes: {review_notes}", user_id=security_user_id)

    return {"success": True, "status": new_status, "message": f"AI Event {event_id} has been {new_status}"}

def get_recent_ai_events(limit: int = 30) -> List[Dict[str, Any]]:
    """Return recent AI events for Security and Admin dashboards"""
    return query_all("""
        SELECT e.*, c.name as camera_name, c.camera_code, u.name as verified_by_name,
               v.plate_display, v.brand, v.model, v.color, v.is_active as vehicle_active,
               usr.name as owner_name, r.name as owner_role
        FROM ai_events e
        JOIN cameras c ON e.camera_id = c.id
        LEFT JOIN users u ON e.verified_by_user_id = u.id
        LEFT JOIN vehicles v ON e.clean_plate = v.plate_clean
        LEFT JOIN user_vehicles uv ON v.id = uv.vehicle_id AND uv.is_primary = 1
        LEFT JOIN users usr ON uv.user_id = usr.id
        LEFT JOIN roles r ON usr.role_id = r.id
        ORDER BY e.id DESC
        LIMIT ?;
    """, (limit,))

