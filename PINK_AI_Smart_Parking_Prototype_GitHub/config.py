# -*- coding: utf-8 -*-
"""
Config loader: โหลดค่าการตั้งค่าจากไฟล์ .env
ป้องกันการ Hardcode รหัสผ่าน และรองรับค่าเริ่มต้น (Default Fallbacks)
"""

import os
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env (หากมี)
load_dotenv()

# MySQL / MariaDB Database Settings
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "parking")

# MQTT Broker Settings
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "60"))

# Gate Timing and Cooldown
GATE_OPEN_SEC = float(os.getenv("GATE_OPEN_SEC", "5.0"))
PLATE_COOLDOWN_SEC = float(os.getenv("PLATE_COOLDOWN_SEC", "15.0"))

# Multi-Frame Plate Confirmation (จำนวนครั้งที่ต้องตรวจจับป้ายเดียวกันซ้ำก่อนเปิดไม้กั้น)
PLATE_CONFIRM_COUNT = int(os.getenv("PLATE_CONFIRM_COUNT", "3"))
PLATE_CONFIRM_WINDOW_SEC = float(os.getenv("PLATE_CONFIRM_WINDOW_SEC", "3.0"))

# Web Dashboard & API Server Settings
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))


# กล้องสดจาก Agent DVR (ไม่ผ่าน AI) - ใช้ oid ของกล้องใน Agent DVR; เว้นว่างถ้าไม่มี
AGENT_DVR_URL = os.getenv("AGENT_DVR_URL", "http://CAMERA_GATEWAY:8090").rstrip("/")
CAM_GATE_OID = os.getenv("CAM_GATE_OID", "1")
CAM_SLOT_OID = os.getenv("CAM_SLOT_OID", "")
