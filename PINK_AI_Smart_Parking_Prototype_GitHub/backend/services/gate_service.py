# -*- coding: utf-8 -*-
"""
Gate Control & Barrier Operations Service:
- Supports integer gate_id OR symbolic code ('gate_in', 'gate_out', 'all')
- Strict audit logging & MQTT ESP32 dispatch
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from backend.core.database import query_one, query_all, execute
from backend.services.audit_service import log_audit
from backend.core.mqtt_gateway import publish_gate_command


def get_all_gates() -> List[Dict[str, Any]]:
    return query_all("""
        SELECT g.*, c.name as camera_name, c.camera_code
        FROM gates g
        LEFT JOIN cameras c ON g.camera_id = c.id
        WHERE g.is_active = 1
        ORDER BY g.id ASC;
    """)


def _resolve_gate(gate_ref: Union[int, str]) -> Optional[Dict[str, Any]]:
    if isinstance(gate_ref, int) or str(gate_ref).isdigit():
        return query_one("SELECT * FROM gates WHERE id = ?;", (int(gate_ref),))
    ref = str(gate_ref).strip().lower()
    if ref in ("gate_in", "in", "entry", "gate-main-in", "all"):
        g = query_one("SELECT * FROM gates WHERE UPPER(direction) = 'IN' OR UPPER(gate_code) LIKE '%IN%' OR id = 1 ORDER BY id ASC LIMIT 1;")
        if g:
            return g
    if ref in ("gate_out", "out", "exit", "gate-main-out"):
        g = query_one("SELECT * FROM gates WHERE UPPER(direction) = 'OUT' OR UPPER(gate_code) LIKE '%OUT%' OR id = 2 ORDER BY id DESC LIMIT 1;")
        if g:
            return g
    return query_one("SELECT * FROM gates ORDER BY id ASC LIMIT 1;")


def operate_gate(gate_id: Union[int, str], action: str, user_id: int, username: str,
                 reason: Optional[str] = None, vehicle_id: Optional[int] = None,
                 plate_text: Optional[str] = None, client_ip: Optional[str] = None) -> Dict[str, Any]:
    gate = _resolve_gate(gate_id)
    if not gate:
        return {"success": False, "status": "ERROR", "message": "ไม่พบข้อมูลไม้กั้นในระบบ"}

    resolved_id = gate["id"]
    act = action.upper()
    if act not in {"OPEN", "CLOSE", "LOCK", "UNLOCK", "EMERGENCY"}:
        return {"success": False, "status": "ERROR", "message": "Unsupported gate action"}
    if act in {"OPEN", "UNLOCK", "EMERGENCY"} and not (reason and reason.strip()):
        return {"success": False, "status": "DENIED", "message": "ต้องระบุเหตุผลและบันทึกผู้อนุมัติก่อนส่งคำสั่งเปิดไม้กั้น"}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    command = "OPEN" if act in ("OPEN", "EMERGENCY", "UNLOCK") else "CLOSE"
    published = publish_gate_command(command, reason=f"Manual command by {username}: {reason or act}")
    command_status = "SENT" if published else "FAILED"
    result_status = "COMMAND_SENT" if published else "COMMAND_FAILED"

    execute("""
        INSERT INTO gate_logs (gate_id, action, triggered_by, user_id, vehicle_id, plate_text, result_status, response_payload)
        VALUES (?, ?, 'SECURITY_MANUAL', ?, ?, ?, ?, ?);
    """, (resolved_id, command, user_id, vehicle_id, plate_text, result_status,
          f"Requested by {username}; command={command_status}; reason={reason or act}; acknowledgement=UNKNOWN; physical_feedback=UNKNOWN; vehicle_passage=UNCONFIRMED"))

    log_audit(username, f"GATE_{act}", "GATE", str(resolved_id), gate["status"], command_status, client_ip, user_id)

    return {
        "success": published,
        "status": gate["status"],
        "command_status": command_status,
        "acknowledgement_status": "UNKNOWN",
        "physical_feedback": "UNKNOWN",
        "vehicle_passage": "UNCONFIRMED",
        "gate_name": gate["name"],
        "executed_at": now_str,
        "message": (f"ส่งคำสั่ง {act} ไปยังตัวควบคุม {gate['name']} แล้ว; ยังไม่มีข้อมูลยืนยันการเปิดจริงหรือรถผ่าน"
                    if published else f"ส่งคำสั่ง {act} ไปยังตัวควบคุม {gate['name']} ไม่สำเร็จ")
    }


def get_recent_gate_logs(limit: int = 50) -> List[Dict[str, Any]]:
    return query_all("""
        SELECT gl.*, g.name as gate_name, g.direction as gate_type, u.name as user_name
        FROM gate_logs gl
        LEFT JOIN gates g ON gl.gate_id = g.id
        LEFT JOIN users u ON gl.user_id = u.id
        ORDER BY gl.id DESC
        LIMIT ?;
    """, (limit,))
