# -*- coding: utf-8 -*-
"""
PINK AI: Google Sheets & Google Apps Script Integration Service
Spreadsheet ID: REPLACE_WITH_YOUR_SPREADSHEET_ID
Maintains 6 standardized sheets with SQLite Database as primary Source of Truth.
NEVER exports passwords or password hashes.
"""

import os
import json
import logging
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional

from backend.core.database import query_all, query_one, execute
from backend.services.audit_service import log_audit

logger = logging.getLogger("sheets_service")

SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "")
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?usp=sharing"
CODE_GS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "google_apps_script", "Code.gs")

# Sync State Store
_sync_state: Dict[str, Any] = {
    "status": "PENDING",  # 'PENDING', 'SUCCESS', 'FAILED'
    "last_sync_time": None,
    "last_sync_summary": None,
    "error_message": None,
    "sheet_counts": {},
    "remote_inspection": None
}

# Standard Header Definitions for the 6 Sheets
SHEET_SCHEMAS = {
    "Users": [
        "User ID", "รหัสประจำตัว", "ชื่อ-นามสกุล", "Role", "สถานะบัญชี", "วันที่สร้างบัญชี"
    ],
    "Teacher Schedule": [
        "รหัสอาจารย์", "ชื่ออาจารย์", "วันสอน", "เวลาเริ่มต้น", "เวลาสิ้นสุด", "รายวิชา", "ห้องเรียน"
    ],
    "Student Schedule": [
        "รหัสนักศึกษา", "ชื่อนักศึกษา", "วันเรียน", "เวลาเริ่มต้น", "เวลาสิ้นสุด", "รายวิชา", "ห้องเรียน"
    ],
    "Parking History": [
        "Event ID", "รหัสผู้ใช้งาน", "ทะเบียนรถ", "วันที่เข้า", "เวลาเข้า", "วันที่ออก", "เวลาออก", "ชั้นจอด", "รหัสช่องจอด", "สถานะ", "แหล่งที่มาของข้อมูล"
    ],
    "Login History": [
        "Log ID", "รหัสผู้ใช้งาน", "ชื่อผู้ใช้งาน", "Role", "วันและเวลา Login", "วันและเวลา Logout", "สถานะการเข้าสู่ระบบ", "รายละเอียดเหตุการณ์ที่เกี่ยวข้อง"
    ],
    "Personal Information": [
        "รหัสประจำตัว", "ชื่อ-นามสกุล", "เพศ", "อายุ", "วันเกิด", "เบอร์ติดต่อ"
    ]
}


class _AppsScriptRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    Google Apps Script Web App returns HTTP 302 after executing doPost()
    redirecting to script.googleusercontent.com/macros/echo?... which expects GET.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if code in (301, 302, 303, 307, 308):
            return urllib.request.Request(
                newurl,
                headers={"User-Agent": "PinkAISmartParking/2.0", "Accept": "application/json"},
                method="GET"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get_setting(key: str, default: str = "") -> str:
    try:
        row = query_one("SELECT setting_value FROM system_settings WHERE setting_key = ?;", (key,))
        if row and row.get("setting_value"):
            return str(row["setting_value"]).strip()
    except Exception:
        pass
    return default


def _set_setting(key: str, value: str, description: str = "") -> None:
    try:
        existing = query_one("SELECT id FROM system_settings WHERE setting_key = ?;", (key,))
        if existing:
            execute(
                "UPDATE system_settings SET setting_value = ?, updated_at = CURRENT_TIMESTAMP WHERE setting_key = ?;",
                (value, key)
            )
        else:
            execute(
                "INSERT INTO system_settings (setting_key, setting_value, description) VALUES (?, ?, ?);",
                (key, value, description)
            )
    except Exception as e:
        logger.warning("[SHEETS] Could not save setting %s: %s", key, e)


def get_webapp_url() -> str:
    env_url = os.getenv("GOOGLE_SHEETS_WEBAPP_URL", "").strip()
    db_url = _get_setting("google_sheets_webapp_url", "")
    return db_url or env_url


def get_sync_secret() -> str:
    env_sec = os.getenv("GOOGLE_SHEETS_SYNC_SECRET", "").strip()
    db_sec = _get_setting("google_sheets_sync_secret", "")
    return db_sec or env_sec


def save_webapp_config(webapp_url: str, sync_secret: Optional[str] = None, username: str = "admin") -> Dict[str, Any]:
    clean_url = (webapp_url or "").strip()
    _set_setting("google_sheets_webapp_url", clean_url, "Google Apps Script Deployed Web App URL (/exec)")
    if sync_secret is not None:
        _set_setting("google_sheets_sync_secret", sync_secret.strip(), "Google Apps Script Shared Secret")
    log_audit(username, "SHEETS_CONFIG_UPDATE", "INTEGRATION", SPREADSHEET_ID, None,
              f"Updated Apps Script Web App URL ({'configured' if clean_url else 'cleared'})")
    return {"success": True, "webapp_url": clean_url}


def get_apps_script_source() -> str:
    if os.path.exists(CODE_GS_PATH):
        with open(CODE_GS_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "// Code.gs file not found"


# ==============================================================================
# 6 Standardized Data Extractors (Passwords & Hashes Strictly Excluded)
# ==============================================================================

def extract_sheet_1_users() -> List[List[Any]]:
    """Sheet 1: Users (No passwords or hashes exported!)"""
    users = query_all("""
        SELECT u.id, u.username, u.name, r.code as role_code,
               CASE WHEN u.is_active = 1 THEN 'Active (ปกติ)' ELSE 'Suspended (ระงับสิทธิ์)' END as status_desc,
               u.created_at
        FROM users u
        JOIN roles r ON u.role_id = r.id
        ORDER BY u.id ASC;
    """)
    return [
        [u["id"], u["username"], u["name"], u["role_code"], u["status_desc"], u["created_at"] or "-"]
        for u in users
    ]


def extract_sheet_2_teacher_schedule() -> List[List[Any]]:
    """Sheet 2: Teacher Schedule"""
    schedules = query_all("""
        SELECT u.username as teacher_code, u.name as teacher_name,
               s.day_of_week, s.start_time, s.end_time,
               TRIM(COALESCE(s.course_code, '') || ' ' || COALESCE(s.course_name, '')) as course,
               TRIM(COALESCE(s.room, '') || CASE WHEN s.building IS NOT NULL AND s.building != '' THEN ' (' || s.building || ')' ELSE '' END) as room_info
        FROM schedules s
        JOIN users u ON s.user_id = u.id
        WHERE s.role = 'TEACHER'
        ORDER BY u.username, s.start_time;
    """)
    return [
        [s["teacher_code"], s["teacher_name"], s["day_of_week"], s["start_time"], s["end_time"], s["course"], s["room_info"]]
        for s in schedules
    ]


def extract_sheet_3_student_schedule() -> List[List[Any]]:
    """Sheet 3: Student Schedule"""
    schedules = query_all("""
        SELECT u.username as student_code, u.name as student_name,
               s.day_of_week, s.start_time, s.end_time,
               TRIM(COALESCE(s.course_code, '') || ' ' || COALESCE(s.course_name, '')) as course,
               TRIM(COALESCE(s.room, '') || CASE WHEN s.building IS NOT NULL AND s.building != '' THEN ' (' || s.building || ')' ELSE '' END) as room_info
        FROM schedules s
        JOIN users u ON s.user_id = u.id
        WHERE s.role = 'STUDENT'
        ORDER BY u.username, s.start_time;
    """)
    return [
        [s["student_code"], s["student_name"], s["day_of_week"], s["start_time"], s["end_time"], s["course"], s["room_info"]]
        for s in schedules
    ]


def extract_sheet_4_parking_history() -> List[List[Any]]:
    """Sheet 4: Parking History"""
    sessions = query_all("""
        SELECT ps.id, COALESCE(u.username, 'ยังไม่ได้ระบุ') as user_code,
               v.plate_display,
               DATE(ps.entry_time) as entry_date, TIME(ps.entry_time) as entry_time,
               DATE(ps.exit_time) as exit_date, TIME(ps.exit_time) as exit_time,
               ps.current_floor,
               COALESCE(s.slot_number, 'ตรวจพบบนชั้น') as slot_no,
               ps.session_status,
               COALESCE(g.name, 'CiRA LPR Gate') as source
        FROM parking_sessions ps
        JOIN vehicles v ON ps.vehicle_id = v.id
        LEFT JOIN user_vehicles uv ON v.id = uv.vehicle_id AND uv.is_primary = 1
        LEFT JOIN users u ON uv.user_id = u.id
        LEFT JOIN parking_slots s ON ps.assigned_slot_id = s.id
        LEFT JOIN gates g ON ps.entry_gate_id = g.id
        ORDER BY ps.id DESC LIMIT 200;
    """)
    return [
        [
            s["id"], s["user_code"], s["plate_display"],
            s["entry_date"] or "-", s["entry_time"] or "-",
            s["exit_date"] or "-", s["exit_time"] or "-",
            f"ชั้น {s['current_floor']}" if s["current_floor"] else "-",
            s["slot_no"], s["session_status"], s["source"]
        ]
        for s in sessions
    ]


def extract_sheet_5_login_history() -> List[List[Any]]:
    """Sheet 5: Login History"""
    logs = query_all("""
        SELECT id, COALESCE(username, '-') as user_code,
               COALESCE(name, '-') as user_name,
               COALESCE(role, '-') as role_name,
               login_at, logout_at, status, event_detail
        FROM login_logs
        ORDER BY id DESC LIMIT 200;
    """)
    return [
        [
            l["id"], l["user_code"], l["user_name"], l["role_name"],
            l["login_at"] or "-", l["logout_at"] or "-",
            l["status"], l["event_detail"] or "-"
        ]
        for l in logs
    ]


def extract_sheet_6_personal_info() -> List[List[Any]]:
    """Sheet 6: Personal Information"""
    users = query_all("""
        SELECT username, name, gender, age, birthdate, phone
        FROM users
        ORDER BY username ASC;
    """)
    return [
        [
            u["username"],
            u["name"],
            u["gender"] if (u["gender"] and str(u["gender"]).strip()) else "ยังไม่ได้ระบุ",
            u["age"] if u["age"] is not None else "ยังไม่ได้ระบุ",
            u["birthdate"] if (u["birthdate"] and str(u["birthdate"]).strip()) else "ยังไม่ได้ระบุ",
            u["phone"] if (u["phone"] and str(u["phone"]).strip()) else "ยังไม่ได้ระบุ"
        ]
        for u in users
    ]


def compile_all_sheets_payload() -> Dict[str, Any]:
    """Compiles complete dataset of all 6 sheets for sync and export"""
    return {
        "spreadsheet_id": SPREADSHEET_ID,
        "spreadsheet_url": SPREADSHEET_URL,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "Asia/Bangkok",
        "source_of_truth": "parking_local.db (SQLite)",
        "sheets": {
            "Users": {"headers": SHEET_SCHEMAS["Users"], "data": extract_sheet_1_users()},
            "Teacher Schedule": {"headers": SHEET_SCHEMAS["Teacher Schedule"], "data": extract_sheet_2_teacher_schedule()},
            "Student Schedule": {"headers": SHEET_SCHEMAS["Student Schedule"], "data": extract_sheet_3_student_schedule()},
            "Parking History": {"headers": SHEET_SCHEMAS["Parking History"], "data": extract_sheet_4_parking_history()},
            "Login History": {"headers": SHEET_SCHEMAS["Login History"], "data": extract_sheet_5_login_history()},
            "Personal Information": {"headers": SHEET_SCHEMAS["Personal Information"], "data": extract_sheet_6_personal_info()},
        }
    }


def _call_apps_script_get(params: Dict[str, str], timeout: int = 15) -> Dict[str, Any]:
    webapp_url = get_webapp_url()
    if not webapp_url:
        raise RuntimeError("ยังไม่ได้ตั้งค่า Google Apps Script Web App URL (/exec)")
    secret = get_sync_secret()
    if secret:
        params["secret"] = secret
    sep = "&" if "?" in webapp_url else "?"
    full_url = f"{webapp_url}{sep}{urllib.parse.urlencode(params)}"
    opener = urllib.request.build_opener(_AppsScriptRedirectHandler())
    req = urllib.request.Request(full_url, headers={"User-Agent": "PinkAISmartParking/2.0", "Accept": "application/json"})
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def _call_apps_script_post(body: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    webapp_url = get_webapp_url()
    if not webapp_url:
        raise RuntimeError("ยังไม่ได้ตั้งค่า Google Apps Script Web App URL (/exec)")
    secret = get_sync_secret()
    if secret:
        body["secret"] = secret
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    opener = urllib.request.build_opener(_AppsScriptRedirectHandler())
    req = urllib.request.Request(
        webapp_url,
        data=encoded,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "PinkAISmartParking/2.0",
            "Accept": "application/json"
        },
        method="POST"
    )
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def inspect_remote_sheets(username: str = "admin") -> Dict[str, Any]:
    """Inspect existing tabs and headers in Google Sheets before syncing"""
    webapp_url = get_webapp_url()
    if not webapp_url:
        return {
            "success": False,
            "status": "PENDING",
            "message": "กรุณานำโค้ด Code.gs ไป Deploy เป็น Web App ใน Google Sheets แล้ววาง Web App URL (/exec) ก่อนตรวจสอบ"
        }
    try:
        res = _call_apps_script_get({"action": "inspect"})
        _sync_state["remote_inspection"] = res
        log_audit(username, "GOOGLE_SHEETS_INSPECT", "INTEGRATION", SPREADSHEET_ID, None, "Inspected Google Sheets structure")
        return res
    except Exception as e:
        logger.warning("[SHEETS INSPECT ERROR] %s", e)
        return {
            "success": False,
            "status": "FAILED",
            "error": str(e),
            "message": f"ไม่สามารถเชื่อมต่อ Google Apps Script ได้: {e}"
        }


def trigger_sheets_sync(username: str = "admin") -> Dict[str, Any]:
    """
    Synchronizes all 6 standardized sheets from SQLite Database (Source of Truth)
    to Google Sheets via deployed Google Apps Script Web App.
    - Never exports passwords or password hashes.
    - Deduplicates / upserts by unique reference ID.
    - Preserves local DB integrity even if Google Sheets is unreachable.
    """
    global _sync_state
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = compile_all_sheets_payload()
    counts = {k: len(v["data"]) for k, v in data["sheets"].items()}
    _sync_state["sheet_counts"] = counts

    webapp_url = get_webapp_url()
    if not webapp_url:
        _sync_state["status"] = "PENDING"
        _sync_state["error_message"] = "ยังไม่ได้ตั้งค่า Web App URL (/exec) จาก Google Apps Script"
        _sync_state["last_sync_summary"] = (
            "เตรียมข้อมูลทั้ง 6 Sheets พร้อมซิงก์แล้ว (รอวาง Web App URL จากการ Deploy Code.gs ใน Google Sheets)"
        )
        return {
            "success": False,
            "status": "PENDING",
            "spreadsheet_url": SPREADSHEET_URL,
            "last_sync_time": _sync_state.get("last_sync_time") or "ยังไม่ได้ซิงก์",
            "summary": _sync_state["last_sync_summary"],
            "error": _sync_state["error_message"],
            "sheet_counts": counts
        }

    _sync_state["status"] = "PENDING"
    try:
        remote_res = _call_apps_script_post({
            "action": "sync_all",
            "spreadsheet_id": SPREADSHEET_ID,
            "sheets": data["sheets"]
        })

        if not remote_res.get("success"):
            raise RuntimeError(remote_res.get("error") or "Apps Script returned failure")

        _sync_state["status"] = "SUCCESS"
        _sync_state["last_sync_time"] = remote_res.get("synced_at") or now_str
        _sync_state["error_message"] = None
        _sync_state["last_sync_summary"] = (
            f"ซิงก์ไปยัง Google Sheets สำเร็จครบทั้ง 6 แผ่นงาน: "
            f"Users {counts['Users']}, Teacher {counts['Teacher Schedule']}, "
            f"Student {counts['Student Schedule']}, Parking {counts['Parking History']}, "
            f"Login {counts['Login History']}, Personal {counts['Personal Information']}"
        )

        _set_setting("google_sheets_last_sync_status", "SUCCESS", "Last Google Sheets sync status")
        _set_setting("google_sheets_last_sync_time", _sync_state["last_sync_time"], "Last Google Sheets sync timestamp")

        log_audit(username, "GOOGLE_SHEETS_SYNC", "INTEGRATION", SPREADSHEET_ID, None, _sync_state["last_sync_summary"])
        logger.info("[SHEETS SYNC] Real Sync Success: %s", _sync_state["last_sync_summary"])

        return {
            "success": True,
            "status": "SUCCESS",
            "spreadsheet_url": SPREADSHEET_URL,
            "last_sync_time": _sync_state["last_sync_time"],
            "summary": _sync_state["last_sync_summary"],
            "sheet_counts": counts,
            "remote_details": remote_res.get("sheet_stats", {})
        }

    except Exception as e:
        _sync_state["status"] = "FAILED"
        _sync_state["error_message"] = str(e)
        _set_setting("google_sheets_last_sync_status", "FAILED", "Last Google Sheets sync status")
        log_audit(username, "GOOGLE_SHEETS_SYNC_FAILED", "INTEGRATION", SPREADSHEET_ID, None, f"Sync failed: {e}")
        logger.error("[SHEETS SYNC ERROR] %s", e)
        return {
            "success": False,
            "status": "FAILED",
            "error": str(e),
            "spreadsheet_url": SPREADSHEET_URL,
            "last_sync_time": _sync_state.get("last_sync_time") or "ซิงก์ไม่สำเร็จ",
            "sheet_counts": counts
        }


def trigger_sheets_sync_async(username: str = "system") -> None:
    """Non-blocking background sync when Web App URL is configured"""
    if not get_webapp_url():
        return
    threading.Thread(target=trigger_sheets_sync, args=(username,), daemon=True).start()


def get_sheets_sync_status() -> Dict[str, Any]:
    """Returns real-time status and row counts of Google Sheets integration"""
    data = compile_all_sheets_payload()
    counts = {k: len(v["data"]) for k, v in data["sheets"].items()}
    webapp_url = get_webapp_url()
    persisted_time = _get_setting("google_sheets_last_sync_time", "")
    persisted_status = _get_setting("google_sheets_last_sync_status", "")

    current_status = _sync_state.get("status")
    if not webapp_url:
        current_status = "PENDING"
    elif persisted_status and current_status == "PENDING" and not _sync_state.get("error_message"):
        current_status = persisted_status

    return {
        "status": current_status,
        "webapp_configured": bool(webapp_url),
        "webapp_url": webapp_url,
        "spreadsheet_id": SPREADSHEET_ID,
        "spreadsheet_url": SPREADSHEET_URL,
        "last_sync_time": _sync_state.get("last_sync_time") or persisted_time or "ยังไม่ได้ซิงก์",
        "last_sync_summary": _sync_state.get("last_sync_summary") or (
            "เชื่อมต่อ Web App URL แล้ว พร้อมซิงก์ข้อมูล" if webapp_url else "รอติดตั้ง Code.gs และวาง Web App URL (/exec)"
        ),
        "error_message": _sync_state.get("error_message"),
        "schemas": SHEET_SCHEMAS,
        "sheet_counts": counts
    }
