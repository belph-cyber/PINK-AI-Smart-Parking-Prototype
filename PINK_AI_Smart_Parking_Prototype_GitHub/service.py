# -*- coding: utf-8 -*-
"""
PINK AI: Smart Parking Management System
Core Application Server & Integration Gateway
- FastAPI Modular Application
- Static Files Hosting
- MQTT Client Bridge (CiRA Core & ESP32 Hardware)
- RTSP / MJPEG Camera Stream Gateway
"""

import os
import sys
import time
import json
import base64
import logging
import threading
import urllib.request
import re
from datetime import datetime
from typing import Dict, Any, Optional, List

import uvicorn
try:
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion
    MQTT_IMPORT_ERROR = None
except ImportError as exc:
    mqtt = None
    CallbackAPIVersion = None
    MQTT_IMPORT_ERROR = exc
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import config
from backend.routers import auth, parking, ai, gate, messages, admin, weather, sheets
from backend.services.ai_service import process_ai_lpr_detection
from backend.services.parking_service import update_slot_status
from backend.core.database import query_one, query_all, execute, get_db
from backend.core.mqtt_gateway import set_mqtt_client, publish_gate_command, publish_slots_led

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("parking_core")

app = FastAPI(title="PINK AI - Smart Parking Management System", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public-tunnel guard: requests arriving via Cloudflare Tunnel carry 'cf-connecting-ip'
# (set by Cloudflare, cannot be spoofed by external clients). Block sensitive admin APIs for them.
PUBLIC_BLOCKED_PREFIXES = ("/api/admin", "/api/sheets")

@app.middleware("http")
async def keep_separate_admin_console_local(request: Request, call_next):
    """The shareable PINK AI app may be used on LAN; the separate Admin Console stays local."""
    if request.url.path == "/admin":
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            return JSONResponse({"detail": "Admin Console ใช้ได้เฉพาะในเครื่องเซิร์ฟเวอร์"}, status_code=403)
    return await call_next(request)

@app.middleware("http")
async def public_tunnel_guard(request: Request, call_next):
    if request.headers.get("cf-connecting-ip") and os.getenv("PUBLIC_BLOCK_ADMIN", "true").lower() in ("1", "true", "yes"):
        if request.url.path.startswith(PUBLIC_BLOCKED_PREFIXES):
            return JSONResponse(
                {"detail": "ฟังก์ชันนี้ใช้ได้เฉพาะในเครือข่ายภายใน (ปิดผ่านลิงก์สาธารณะ)"},
                status_code=403,
            )
    return await call_next(request)

# Mount Static Files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "web", "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include Routers
app.include_router(auth.router)
app.include_router(parking.router)
app.include_router(ai.router)
app.include_router(gate.router)
app.include_router(messages.router)
app.include_router(admin.router)
app.include_router(weather.router)
app.include_router(sheets.router)

@app.on_event("startup")
def apply_safe_ai_review_migration():
    """Add review correction fields without resetting or replacing existing data."""
    with get_db() as conn:
        table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_events';").fetchone()
        if not table:
            logger.warning("ai_events table not found; AI review migration deferred")
            return
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(ai_events);").fetchall()}
        if "corrected_plate" not in columns:
            conn.execute("ALTER TABLE ai_events ADD COLUMN corrected_plate TEXT;")
        if "corrected_slot_id" not in columns:
            conn.execute("ALTER TABLE ai_events ADD COLUMN corrected_slot_id INTEGER;")

# Paths
INDEX_HTML = os.path.join(os.path.dirname(__file__), "web", "index.html")
LOGIN_HTML = os.path.join(os.path.dirname(__file__), "web", "login.html")
ADMIN_HTML = os.path.join(os.path.dirname(__file__), "web", "admin.html")
DISPLAY_HTML = os.path.join(os.path.dirname(__file__), "web", "display.html")

# In-memory camera frame cache
CAM_IDS = ("gate", "fl1_head", "fl1_tail", "fl2_head", "fl2_tail")
CAM_STALE_SEC = 10.0
cam_frames: Dict[str, dict] = {}
cam_last_events: Dict[str, dict] = {
    "gate": {"plate": "-", "owner": "-", "time": "-"},
    "fl1_head": {"plate": "-", "owner": "-", "time": "-"},
    "fl1_tail": {"plate": "-", "owner": "-", "time": "-"},
    "fl2_head": {"plate": "-", "owner": "-", "time": "-"},
    "fl2_tail": {"plate": "-", "owner": "-", "time": "-"}
}
cam_lock = threading.Lock()

# ==============================================================================
# Web Page Handlers
# ==============================================================================

@app.get("/login")
def serve_login():
    if os.path.exists(LOGIN_HTML):
        return FileResponse(LOGIN_HTML, headers={"Cache-Control": "no-store"})
    return JSONResponse({"status": "error", "message": "web/login.html not found"})

@app.get("/admin")
def serve_admin_console():
    if os.path.exists(ADMIN_HTML):
        return FileResponse(ADMIN_HTML, headers={"Cache-Control": "no-store"})
    return JSONResponse({"status": "error", "message": "web/admin.html not found"}, status_code=404)


@app.get("/")
@app.get("/dashboard")
def serve_dashboard():
    if os.path.exists(INDEX_HTML):
        return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-store"})
    return JSONResponse({"status": "error", "message": "web/index.html not found"})

@app.get("/display")
@app.get("/ipad")
def serve_kiosk():
    if os.path.exists(DISPLAY_HTML):
        return FileResponse(DISPLAY_HTML)
    return JSONResponse({"status": "error", "message": "web/display.html not found"})

# ==============================================================================
# Camera MJPEG / Snapshot Handlers
# ==============================================================================

def _decode_cam_payload(data: bytes):
    def sniff(b: bytes):
        if b[:2] == b"\xff\xd8": return b, "image/jpeg"
        if b[:4] == b"\x89PNG": return b, "image/png"
        return None
    r = sniff(data)
    if r: return r
    text = data.strip()
    if text[:1] == b"{":
        try:
            obj = json.loads(text.decode("utf-8", errors="ignore"))
            for v in obj.values():
                if isinstance(v, str) and len(v) > 200:
                    text = v.encode("ascii", errors="ignore")
                    break
        except Exception:
            return None
    if text[:5] == b"data:":
        text = text.split(b",", 1)[-1]
    try:
        return sniff(base64.b64decode(text, validate=False))
    except Exception:
        return None

def handle_cam_frame(cam_id: str, data: bytes):
    r = _decode_cam_payload(data)
    if not r: return
    with cam_lock:
        cam_frames[cam_id] = {"bytes": r[0], "mime": r[1], "ts": time.time()}

@app.get("/api/cam/{cam_id}.jpg")
@app.get("/api/cam/frame/{cam_id}")
def get_cam_frame(cam_id: str):
    with cam_lock:
        f = cam_frames.get(cam_id)
    if not f or time.time() - f["ts"] > CAM_STALE_SEC:
        raise HTTPException(status_code=404, detail="no frame available")
    return Response(content=f["bytes"], media_type=f["mime"], headers={"Cache-Control": "no-store"})

@app.get("/api/cam/{cam_id}.mjpg")
def stream_cam(cam_id: str):
    oid = config.CAM_GATE_OID if cam_id in ("gate", "cam1") else None
    if not oid:
        raise HTTPException(status_code=404, detail="camera stream not configured")
    url = f"{config.AGENT_DVR_URL}/video.mjpg?oid={oid}&size=1920x1080"
    try:
        upstream = urllib.request.urlopen(url, timeout=6)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"camera unreachable: {e}")

    def gen():
        try:
            while True:
                chunk = upstream.read1(16384)
                if not chunk: break
                yield chunk
        except Exception:
            pass
        finally:
            try: upstream.close()
            except Exception: pass

    mt = upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=myboundary")
    return StreamingResponse(gen(), media_type=mt, headers={"Cache-Control": "no-store"})

@app.get("/api/cam/status")
def get_cam_status():
    now = time.time()
    with cam_lock:
        res = {}
        for cid in CAM_IDS:
            res[cid] = {
                "online": (cid in cam_frames and now - cam_frames[cid]["ts"] <= CAM_STALE_SEC),
                "age_sec": round(now - cam_frames[cid]["ts"], 1) if cid in cam_frames else None,
                "last_event": cam_last_events.get(cid, {})
            }
        return res

# Backward-compatibility fallback endpoint
@app.get("/api/status")
def get_legacy_status():
    from backend.services.parking_service import get_floors_overview
    return {"status": "ok", "system": "ONLINE", "floors": get_floors_overview()}

@app.get("/api/floors")
def get_display_floors():
    from backend.services.parking_service import get_floors_overview
    floors_list = get_floors_overview()
    floors_dict = {}
    for fl in floors_list:
        fn = str(fl["floor_number"])
        floors_dict[fn] = {
            "name": fl["floor_name"],
            "total": fl["total_slots"],
            "occupied": fl["occupied_slots"],
            "free": fl["free_slots"],
            "reserved": fl.get("reserved_slots", 0),
            "unknown": fl.get("unknown_slots", 0),
            "error": fl.get("error_slots", 0),
            "conflict": fl.get("conflict_slots", 0),
            "data_state": "LIVE" if any(s.get("evidence_state") in ("LIVE", "MANUAL", "ERROR", "CONFLICT", "RESERVATION") for s in fl.get("slots", [])) else "STALE_OR_NO_EVIDENCE",
            "sensor_based": (fn == "1"),
            "cars": [
                {
                    "plate": s.get("plate_clean") or f"รถตรวจพบ • ช่อง {s.get('slot_number')}",
                    "plate_display": s.get("plate_display") or f"ตรวจพบรถ • ช่อง {s.get('slot_number')}",
                    "owner_name": None,
                    "time": s.get("occupied_since") or "-",
                    "pos": "head"
                }
                for s in fl.get("slots", []) if s.get("status") == "OCCUPIED"
            ]
        }

    gate_ev = cam_last_events.get("gate", {})
    gate_plate = {
        "plate_read": gate_ev.get("plate", ""),
        "province": "",
        "student_name": gate_ev.get("owner", ""),
        "observed_at": gate_ev.get("observed_at"),
        "result": "REVIEW_REQUIRED" if gate_ev.get("plate") and gate_ev.get("plate") != "-" else "STANDBY",
        "review_status": gate_ev.get("review_status", "PENDING" if gate_ev.get("plate") else None),
        "gate_command": "NOT_REQUESTED"
    }

    esp_last_seen_ts = esp_hardware_state.get("esp_last_seen_ts")
    esp_display_state = {
        **esp_hardware_state,
        "online": bool(esp_last_seen_ts and (time.time() - esp_last_seen_ts <= 15.0)),
    }
    return {
        "status": "ok",
        "floors": floors_dict,
        "gate_plate": gate_plate,
        "esp32": esp_display_state
    }

# ==============================================================================
# MQTT Hardware & CiRA Core Bridge (Full Integration)
# ==============================================================================

# Multi-Frame Plate Debounce Buffer & Cooldown
plate_read_buffer: Dict[str, List[float]] = {}
plate_cooldown_map: Dict[str, float] = {}
plate_buffer_lock = threading.Lock()

def normalize_plate_str(raw: str) -> str:
    if not raw: return ""
    return re.sub(r"[^0-9a-zA-Z\u0E00-\u0E7F]", "", raw).strip()

def extract_cira_plate(payload_str: str) -> tuple[str, str]:
    """Parse plate text and province from any CiRA Core output format or plain string"""
    province = ""
    raw_plate = ""
    try:
        data = json.loads(payload_str)
        if isinstance(data, dict):
            raw_plate = str(data.get("plate", "")).strip()
            province = str(data.get("province", "")).strip()

            if (not raw_plate or raw_plate.lower() == "waiting...") and "license" in data:
                lic_lines = str(data["license"]).strip().split("\n")
                raw_plate = lic_lines[0].strip()
                if len(lic_lines) > 1 and not province:
                    province = lic_lines[1].strip()

            if (not raw_plate or raw_plate.lower() == "waiting...") and "mqtt_msg" in data:
                try:
                    sub = json.loads(data["mqtt_msg"]) if isinstance(data["mqtt_msg"], str) else data["mqtt_msg"]
                    if isinstance(sub, dict):
                        raw_plate = str(sub.get("plate", "")).strip()
                        if not province:
                            province = str(sub.get("province", "")).strip()
                except Exception:
                    pass

            if not raw_plate or raw_plate.lower() == "waiting...":
                for alt_k in ("full_text", "text", "plate_no", "val"):
                    if alt_k in data and data[alt_k]:
                        raw_plate = str(data[alt_k]).strip().split("\n")[0]
                        break
        else:
            raw_plate = str(data).strip()
    except (json.JSONDecodeError, TypeError):
        raw_plate = payload_str.strip()

    if "\n" in raw_plate:
        parts = raw_plate.split("\n")
        raw_plate = parts[0].strip()
        if len(parts) > 1 and not province:
            province = parts[1].strip()

    return raw_plate, province


def extract_cira_confidence(payload_str: str) -> Optional[float]:
    """Return reported confidence only; missing confidence must stay unknown."""
    try:
        payload = json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    raw_confidence = payload.get("confidence", payload.get("prob"))
    try:
        value = float(raw_confidence)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 1 else None

def cira_reports_vehicle_with_ocr_failure(payload_str: str) -> bool:
    """Require explicit vehicle and OCR-failure signals before queuing a blank plate."""
    try:
        data = json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    vehicle_detected = data.get("vehicle_detected") is True
    ocr_failed = data.get("ocr_failed") is True or str(data.get("ocr_status", "")).upper() in ("FAILED", "OCR_FAILED")
    return vehicle_detected and ocr_failed

def cira_evidence_ref(payload_str: str) -> Optional[str]:
    try:
        data = json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("evidence_image_path") or data.get("image_url") or data.get("image_ref")
    return str(value) if value else None

# Live ESP32 & Hardware Telemetry Cache
esp_hardware_state: Dict[str, Any] = {
    "esp_online": False,
    "esp_status_text": "Waiting for ESP32...",
    "esp_last_seen": None,
    "sensors_slots": [],
    "no_parking_alert": {"active": False, "message": "-", "distance_cm": None, "updated_at": None},
    "gate_controller_report": None,
    "gate_controller_report_at": None,
}
no_park_last_notif_ts: float = 0.0

@app.get("/api/hardware/status")
def get_hardware_status():
    now_ts = time.time()
    last_seen = esp_hardware_state.get("esp_last_seen_ts")
    is_live = bool(last_seen and (now_ts - last_seen <= 15.0))
    return {
        "status": "ok",
        "mqtt_local_host": f"{config.MQTT_HOST}:{config.MQTT_PORT}",
        "mqtt_cloud_bridge": os.getenv("MQTT_CLOUD_HOST", "broker.emqx.io"),
        "esp32": {
            "online": is_live,
            "status_text": esp_hardware_state["esp_status_text"],
            "last_seen": esp_hardware_state["esp_last_seen"],
            "sensors_slots": esp_hardware_state["sensors_slots"],
            "no_parking_alert": esp_hardware_state["no_parking_alert"],
        },
        "gate": {
            "controller_report": esp_hardware_state.get("gate_controller_report"),
            "controller_report_at": esp_hardware_state.get("gate_controller_report_at"),
            "acknowledgement_status": "UNKNOWN_UNCORRELATED",
            "physical_feedback": "UNKNOWN",
            "vehicle_passage": "UNCONFIRMED",
        },
        "cameras": get_cam_status(),
    }

def on_connect(client, userdata, flags, rc, properties=None):
    broker_label = userdata.get("label", f"{config.MQTT_HOST}:{config.MQTT_PORT}") if isinstance(userdata, dict) else f"{config.MQTT_HOST}:{config.MQTT_PORT}"
    if rc == 0:
        logger.info("[MQTT] Connected to Broker (%s)", broker_label)
        topics = [
            ("parking/gate/plate", 1),
            ("cira/plate", 1),
            ("parking/floor/#", 1),
            ("parking/sensors/slots", 1),
            ("parking/slots/status", 1),
            ("parking/alert/#", 1),
            ("parking/esp/status", 1),
            ("parking/cam/#", 0),
            ("parking/image/#", 0)
        ]
        client.subscribe(topics)
        logger.info("[MQTT] Subscribed (%s) to CiRA Core & ESP32 topics: %s", broker_label, [t[0] for t in topics])
    else:
        logger.warning("[MQTT] Connect failed (%s) with code %d", broker_label, rc)

def on_message(client, userdata, msg):
    topic_lower = msg.topic.lower()

    # 1. Camera live frame payload
    if "cam" in topic_lower or "image" in topic_lower:
        if "fl1" in topic_lower and "tail" in topic_lower: cam_id = "fl1_tail"
        elif "fl1" in topic_lower and "head" in topic_lower: cam_id = "fl1_head"
        elif "fl2" in topic_lower and "tail" in topic_lower: cam_id = "fl2_tail"
        elif "fl2" in topic_lower and "head" in topic_lower: cam_id = "fl2_head"
        else: cam_id = "gate"
        handle_cam_frame(cam_id, bytes(msg.payload))
        return

    # 2. Text / JSON payload
    try:
        payload_str = msg.payload.decode("utf-8", errors="ignore").strip()
        logger.info("[MQTT IN] Topic: %s | Payload: %s", msg.topic, payload_str[:80])

        # --- CASE A: Gate Barrier LPR from CiRA Core ---
        if msg.topic in ("parking/gate/plate", "cira/plate") or "gate" in topic_lower:
            raw_plate, province = extract_cira_plate(payload_str)
            ocr_failed = cira_reports_vehicle_with_ocr_failure(payload_str)
            if (not raw_plate or "waiting" in raw_plate.lower() or raw_plate == "-") and not ocr_failed:
                return

            plate_norm = normalize_plate_str(raw_plate)
            if plate_norm and len(plate_norm) < 3:
                return

            logger.info("[CiRA GATE LPR] Detected: '%s' (norm: '%s', prov: '%s')", raw_plate, plate_norm, province)

            # Shot-mode results from CiRA node are already multi-frame voted -> skip server debounce
            is_shot = False
            try:
                _pj = json.loads(payload_str)
                is_shot = isinstance(_pj, dict) and str(_pj.get("mode", "")).upper() == "SHOT"
            except Exception:
                pass

            # Debounce Buffer Confirmation (config.PLATE_CONFIRM_COUNT times within window)
            if plate_norm:
                now_ts = time.time()
                with plate_buffer_lock:
                    last_time = plate_cooldown_map.get(plate_norm, 0.0)
                    if now_ts - last_time < config.PLATE_COOLDOWN_SEC:
                        return

                    history = plate_read_buffer.setdefault(plate_norm, [])
                    history.append(now_ts)
                    history = [t for t in history if now_ts - t <= config.PLATE_CONFIRM_WINDOW_SEC]
                    plate_read_buffer[plate_norm] = history

                    read_count = len(history)
                    logger.info("[CONFIRM BUFFER] Plate '%s' count: %d/%d (%.1fs window)%s",
                                plate_norm, read_count, config.PLATE_CONFIRM_COUNT, config.PLATE_CONFIRM_WINDOW_SEC,
                                " [SHOT]" if is_shot else "")

                    if read_count < config.PLATE_CONFIRM_COUNT and not is_shot:
                        return

                    plate_read_buffer[plate_norm] = []
                    plate_cooldown_map[plate_norm] = now_ts

            # Detection is evidence only. Security must review it, then issue a
            # separate gate command. No LPR outcome publishes OPEN or CLOSE.
            confidence = extract_cira_confidence(payload_str)
            detection = process_ai_lpr_detection(
                camera_code="GATE-IN-LPR",
                raw_plate=raw_plate,
                confidence=confidence,
                suggested_floor=None,
                evidence_image_path=cira_evidence_ref(payload_str),
                event_type="OCR_FAILED" if ocr_failed else "LPR_DETECT",
            )
            veh = query_one("SELECT id, is_active FROM vehicles WHERE plate_clean = ? LIMIT 1;", (plate_norm,)) if plate_norm else None
            plate_state = "registered" if veh and veh.get("is_active") else "unmatched or inactive"
            display_plate = raw_plate or "อ่านทะเบียนไม่สำเร็จ"
            logger.info("[AI REVIEW QUEUE] %s | %s | event=%s", display_plate, plate_state, detection.get("event_id"))
            execute("""
                INSERT INTO notifications (user_id, target_role, title, message, category, related_plate)
                VALUES (NULL, 'SECURITY', 'ต้องตรวจสอบเหตุการณ์ AI', ?, 'AI_ALERT', ?);
            """, (f"{display_plate} ({plate_state}) กรุณาตรวจภาพและยืนยันผล ระบบยังไม่ได้สั่งไม้กั้น", raw_plate or None))

            with cam_lock:
                cam_last_events["gate"] = {
                    "plate": display_plate,
                    "owner": "รอเจ้าหน้าที่ตรวจสอบ",
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "observed_at": datetime.now().isoformat(timespec="seconds"),
                    "review_status": detection.get("status", "PENDING")
                }

        # --- CASE B: Floor LPR Camera Detection from CiRA Core ---
        elif "floor" in msg.topic:
            # Topic format: parking/floor/{floor_num}/{head|tail}
            raw_plate, province = extract_cira_plate(payload_str)
            ocr_failed = cira_reports_vehicle_with_ocr_failure(payload_str)
            if (not raw_plate or "waiting" in raw_plate.lower() or raw_plate == "-") and not ocr_failed:
                return

            parts = msg.topic.split("/")
            floor_num = 1
            pos = "head"
            for pt in parts:
                if pt.isdigit(): floor_num = int(pt)
                elif pt in ("head", "tail"): pos = pt

            plate_norm = normalize_plate_str(raw_plate)
            logger.info("[CiRA FLOOR LPR] Floor %d (%s) detected plate: '%s'", floor_num, pos, raw_plate)

            confidence = extract_cira_confidence(payload_str)
            detection = process_ai_lpr_detection(
                camera_code=f"CAM-FL{floor_num}-{pos.upper()}",
                raw_plate=raw_plate,
                confidence=confidence,
                suggested_floor=floor_num,
                suggested_slot_number=None,
                evidence_image_path=cira_evidence_ref(payload_str),
                event_type="OCR_FAILED" if ocr_failed else "LPR_DETECT",
            )
            # Keep AI-detected floor as a suggestion only. The active session is
            # updated after Security confirms this event through /api/ai/verify.

            cid = f"fl{floor_num}_{pos}"
            with cam_lock:
                cam_last_events[cid] = {
                    "plate": raw_plate,
                    "owner": f"ตำแหน่งชั้น {floor_num} ทราบ; ช่องจอดยังไม่ทราบ",
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "review_status": detection.get("status", "PENDING")
                }

        # --- CASE C: Slot Occupancy Sensors (HC-SR04 #1, #2 on ESP32 & CiRA Slot AI) ---
        elif "slots" in msg.topic or "sensors" in msg.topic:
            try:
                sdata = json.loads(payload_str)
                free = int(sdata.get("free", 0))
                total = int(sdata.get("total", 2))
                occupied = int(sdata.get("occupied", 0))
                slots_list = sdata.get("slots", [])

                now_dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if "sensors" in msg.topic:
                    esp_hardware_state["esp_online"] = True
                    esp_hardware_state["esp_last_seen"] = now_dt_str
                    esp_hardware_state["esp_last_seen_ts"] = time.time()
                    esp_hardware_state["sensors_slots"] = slots_list

                # Aggregate counts alone are not evidence for a free bay.
                # Only an explicit per-slot free/available reading may turn on the green indicator.
                has_confirmed_free_slot = any(
                    isinstance(sl, dict) and str(sl.get("status", "")).strip().lower() in ("free", "available")
                    for sl in slots_list
                )
                publish_slots_led("GREEN" if has_confirmed_free_slot else "RED")

                # Update Floor 1 slots in SQLite (matches both '1-01'/'1-02' and legacy 'A-01'/'A-02')
                if slots_list:
                    source_tag = "ULTRASONIC_SENSOR" if "sensors" in msg.topic else "AI_CAMERA"
                    for sl in slots_list:
                        sid = int(sl.get("id", 1))
                        raw_st = str(sl.get("status", "unknown")).strip().lower()
                        if raw_st == "occupied":
                            sstatus = "OCCUPIED"
                        elif raw_st in ("free", "available"):
                            sstatus = "AVAILABLE"
                        elif raw_st == "reserved":
                            sstatus = "RESERVED"
                        elif raw_st == "conflict":
                            sstatus = "CONFLICT"
                        elif raw_st in ("error", "fault"):
                            sstatus = "ERROR"
                        elif raw_st in ("closed", "disabled", "maintenance"):
                            sstatus = "ERROR"
                        else:
                            sstatus = "UNKNOWN"

                        code_num = f"1-{sid:02d}"
                        code_leg = f"A-{sid:02d}"
                        execute("""
                            UPDATE parking_slots
                            SET status = ?, detection_source = ?, last_detected_at = ?
                            WHERE floor_id = 1
                              AND slot_number IN (?, ?)
                              AND COALESCE(detection_source, '') != 'ADMIN_MANUAL';
                        """, (sstatus, source_tag, now_dt_str, code_num, code_leg))

                logger.info("[SLOTS SENSOR] Updated status (%s): free=%d, occupied=%d", msg.topic, free, occupied)
            except Exception as se:
                logger.error("[SLOTS SENSOR ERROR] %s", se)

        # --- CASE D: ESP32 HC-SR04 #3 No-Parking Violation Alert (parking/alert/no_parking) ---
        elif "alert" in topic_lower:
            global no_park_last_notif_ts
            now_dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            esp_hardware_state["esp_online"] = True
            esp_hardware_state["esp_last_seen"] = now_dt_str
            esp_hardware_state["esp_last_seen_ts"] = time.time()
            try:
                adata = json.loads(payload_str)
                is_active = bool(adata.get("active", False))
                dist_cm = adata.get("distance_cm")
                alert_msg = adata.get("message", "ตรวจพบรถจอดในช่องห้ามจอด!")
                esp_hardware_state["no_parking_alert"] = {
                    "active": is_active,
                    "message": alert_msg,
                    "distance_cm": dist_cm,
                    "updated_at": now_dt_str
                }

                # Update slot 1-NP (ช่องห้ามจอด HC-SR04 #3) in database
                np_status = "OCCUPIED" if is_active else "AVAILABLE"
                execute("""
                    UPDATE parking_slots
                    SET status = ?, detection_source = 'ULTRASONIC_SENSOR', last_detected_at = ?
                    WHERE floor_id = 1 AND slot_number = '1-NP';
                """, (np_status, now_dt_str))

                if is_active and (time.time() - no_park_last_notif_ts >= 15.0):
                    no_park_last_notif_ts = time.time()
                    detail_txt = f"{alert_msg} (เซนเซอร์ ESP32 HC-SR04 #3 ระยะ {dist_cm} ซม.)"
                    execute("""
                        INSERT INTO notifications (user_id, target_role, title, message, category)
                        VALUES (1, 'SECURITY', '🚨 แจ้งเตือนจอดรถในช่องห้ามจอด (ESP32 HC-SR04 #3)', ?, 'SECURITY_ALERT');
                    """, (detail_txt,))
                    logger.warning("[ESP32 NO-PARKING ALERT] %s", detail_txt)
            except Exception as ae:
                logger.error("[ESP32 ALERT ERROR] %s", ae)

        # --- CASE E: ESP32 Heartbeat & Gate Servo Status (parking/esp/status) ---
        elif topic_lower == "parking/esp/status":
            now_dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            esp_hardware_state["esp_online"] = True
            esp_hardware_state["esp_status_text"] = payload_str
            esp_hardware_state["gate_controller_report"] = payload_str
            esp_hardware_state["gate_controller_report_at"] = now_dt_str
            esp_hardware_state["esp_last_seen"] = now_dt_str
            esp_hardware_state["esp_last_seen_ts"] = time.time()
            logger.info("[ESP32 SOFTWARE STATUS; NOT PHYSICAL FEEDBACK] %s", payload_str)

    except Exception as e:
        logger.error("[MQTT ERROR] on_message exception: %s", e)

_mqtt_started = False

def start_mqtt_client():
    global _mqtt_started
    if _mqtt_started:
        return
    _mqtt_started = True

    if os.getenv("PINK_DISABLE_MQTT", "false").lower() in ("1", "true", "yes"):
        logger.info("[MQTT] Disabled by PINK_DISABLE_MQTT; web/API-only mode")
        return

    if mqtt is None:
        logger.warning("[MQTT] paho-mqtt is not installed; web/API is running without hardware messaging: %s", MQTT_IMPORT_ERROR)
        return

    import uuid
    suffix = uuid.uuid4().hex[:6]

    # 1. Primary Broker (from .env / config.py, e.g. 127.0.0.1:1883)
    primary = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=f"pink_ai_local_{suffix}",
        userdata={"label": f"Local {config.MQTT_HOST}:{config.MQTT_PORT}"}
    )
    primary.on_connect = on_connect
    primary.on_message = on_message
    try:
        primary.connect_async(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
        primary.loop_start()
        set_mqtt_client(primary)
        logger.info("[MQTT] Registered primary client (%s:%d)", config.MQTT_HOST, config.MQTT_PORT)
    except Exception as e:
        logger.warning("[MQTT] Could not connect primary broker %s:%d: %s", config.MQTT_HOST, config.MQTT_PORT, e)

    # 2. Optional Cloud Broker Bridge for ESP32 (esp32_parking.ino uses broker.emqx.io:1883 by default)
    cloud_enabled = os.getenv("MQTT_CLOUD_BRIDGE", "true").lower() in ("1", "true", "yes")
    cloud_host = os.getenv("MQTT_CLOUD_HOST", "broker.emqx.io").strip()
    cloud_port = int(os.getenv("MQTT_CLOUD_PORT", "1883"))
    if cloud_enabled and cloud_host and cloud_host != config.MQTT_HOST:
        cloud = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"pink_ai_esp_bridge_{suffix}",
            userdata={"label": f"ESP32 Cloud {cloud_host}:{cloud_port}"}
        )
        cloud.on_connect = on_connect
        cloud.on_message = on_message
        try:
            cloud.connect_async(cloud_host, cloud_port, config.MQTT_KEEPALIVE)
            cloud.loop_start()
            set_mqtt_client(cloud)
            logger.info("[MQTT] Registered ESP32 Cloud Bridge client (%s:%d)", cloud_host, cloud_port)
        except Exception as e:
            logger.warning("[MQTT] Could not connect ESP32 cloud broker %s:%d: %s", cloud_host, cloud_port, e)

@app.on_event("startup")
def on_app_startup():
    start_mqtt_client()

if __name__ == "__main__":
    start_mqtt_client()
    logger.info("=================================================================")
    logger.info("  PINK AI - Smart Parking Management System (Version 2.0.0)      ")
    logger.info("  Backend Gateway URL : http://localhost:8000                    ")
    logger.info("=================================================================")
    uvicorn.run(app, host=config.WEB_HOST, port=config.WEB_PORT, reload=False, log_level="info")
