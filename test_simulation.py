# -*- coding: utf-8 -*-
"""
End-to-End Simulation Test Script
ใช้สำหรับทดสอบการทำงานของระบบทั้งหมดบนเครื่อง โดยไม่ต้องมีฮาร์ดแวร์จริง
จำลองทั้ง:
  1. CiRA Core (ส่งป้ายทะเบียนทดสอบซ้ำ N รอบ และส่งสถานะช่องจอด)
  2. ESP32 (รับคำสั่งเปิด-ปิดไม้กั้น และไฟ LED)
"""

import json
import time
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import config

print("=================================================================")
print("     Smart AI Parking System - Simulation Test Runner           ")
print("=================================================================")

# จำลอง ESP32 ในตัว
def esp_on_message(client, userdata, msg):
	topic = msg.topic
	payload = msg.payload.decode("utf-8")
	if topic == "parking/esp/gate":
		print(f"\n >>> [SIMULATED ESP32] [GATE] -> {payload}")
	elif topic.startswith("parking/esp/led/"):
		led_target = topic.split("/")[-1]
		print(f" >>> [SIMULATED ESP32] [LED] {led_target} = {payload}")

# สร้าง MQTT Client สำหรับจำลอง ESP32
esp_sim = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="SimulatedESP32")
esp_sim.on_message = esp_on_message
try:
	esp_sim.connect(config.MQTT_HOST, config.MQTT_PORT, 60)
	esp_sim.subscribe("parking/esp/gate")
	esp_sim.subscribe("parking/esp/led/#")
	esp_sim.loop_start()
	print(f"[OK] Simulated ESP32 connected to MQTT Broker ({config.MQTT_HOST}:{config.MQTT_PORT})")
except Exception as e:
	print(f"[ERROR] Cannot connect ESP32 simulator to MQTT Broker: {e}")
	print("โปรดตรวจสอบว่า Mosquitto Broker กำลังทำงานอยู่หรือไม่ (เช่น mosquitto -v)")
	exit(1)

# สร้าง MQTT Client สำหรับจำลอง CiRA Core
cira_sim = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="SimulatedCiRA")
try:
	cira_sim.connect(config.MQTT_HOST, config.MQTT_PORT, 60)
	cira_sim.loop_start()
	print(f"[OK] Simulated CiRA Core connected to MQTT Broker")
except Exception as e:
	print(f"[ERROR] Cannot connect CiRA simulator to MQTT Broker: {e}")
	exit(1)

time.sleep(1)

# -----------------------------------------------------------------------------
# ทดสอบที่ 1: ส่งสถานะช่องจอดรถ (Parking Slots)
# -----------------------------------------------------------------------------
print("\n--- [TEST 1] ส่งสถานะช่องจอดรถ (ว่าง 2 จาก 3 ช่อง) ---")
slots_payload = {
	"free": 2,
	"total": 3,
	"occupied": 1,
	"closed": 0,
	"light_status": "GREEN",
	"slots": [
		{"id": 1, "box": [50, 400, 200, 600], "status": "free", "reason": "ว่าง"},
		{"id": 2, "box": [220, 400, 370, 600], "status": "occupied", "reason": "รถจอดในช่อง (ทับ 95%)"},
		{"id": 3, "box": [390, 400, 540, 600], "status": "free", "reason": "ว่าง"}
	]
}
cira_sim.publish("parking/slots/status", json.dumps(slots_payload, ensure_ascii=False), qos=0)
print("ส่งข้อมูลช่องจอดสำเร็จ -> รอรับค่าที่ ESP32...")
time.sleep(2)

# -----------------------------------------------------------------------------
# ทดสอบที่ 2: จำลองสแกนป้ายทะเบียนที่ได้รับอนุญาต (กบ 1234, active=1)
# ต้องส่งซ้ำ N รอบ (ตามค่า PLATE_CONFIRM_COUNT) เพื่อทดสอบระบบ Debounce
# -----------------------------------------------------------------------------
target_plate = "กบ 1234"
print(f"\n--- [TEST 2] สแกนป้ายที่ลงทะเบียนถูกต้อง ({target_plate}) ---")
print(f"จำลองกล้องส่งเฟรมต่อเนื่อง {config.PLATE_CONFIRM_COUNT} รอบเพื่อยืนยัน...")

plate_payload = {
	"plate": target_plate,
	"province": "กรุงเทพมหานคร",
	"full_text": f"{target_plate}\nกรุงเทพมหานคร"
}

for i in range(1, config.PLATE_CONFIRM_COUNT + 1):
	print(f" -> ส่งเฟรมที่ {i}/{config.PLATE_CONFIRM_COUNT}: {target_plate}")
	cira_sim.publish("parking/gate/plate", json.dumps(plate_payload, ensure_ascii=False), qos=1)
	time.sleep(0.4)

print("ครบจำนวนรอบยืนยันแล้ว รอ service.py ตัดสินใจและสั่งเปิดไม้กั้น...")
time.sleep(config.GATE_OPEN_SEC + 2)

# -----------------------------------------------------------------------------
# ทดสอบที่ 3: จำลองสแกนป้ายที่ถูกระงับสิทธิ์ (บค 5678, active=0)
# -----------------------------------------------------------------------------
inactive_plate = "บค 5678"
print(f"\n--- [TEST 3] สแกนป้ายที่ถูกระงับสิทธิ์ ({inactive_plate}) ---")
plate_payload_inactive = {
	"plate": inactive_plate,
	"province": "กรุงเทพมหานคร"
}
for i in range(1, config.PLATE_CONFIRM_COUNT + 1):
	print(f" -> ส่งเฟรมที่ {i}/{config.PLATE_CONFIRM_COUNT}: {inactive_plate}")
	cira_sim.publish("parking/gate/plate", json.dumps(plate_payload_inactive, ensure_ascii=False), qos=1)
	time.sleep(0.4)

time.sleep(2)

# -----------------------------------------------------------------------------
# ทดสอบที่ 4: จำลองสแกนป้ายที่ไม่พบในฐานข้อมูล (9กก 8888)
# -----------------------------------------------------------------------------
unknown_plate = "9กก 8888"
print(f"\n--- [TEST 4] สแกนป้ายคนภายนอก ไม่พบในฐานข้อมูล ({unknown_plate}) ---")
plate_payload_unknown = {
	"plate": unknown_plate,
	"province": "เชียงใหม่"
}
for i in range(1, config.PLATE_CONFIRM_COUNT + 1):
	print(f" -> ส่งเฟรมที่ {i}/{config.PLATE_CONFIRM_COUNT}: {unknown_plate}")
	cira_sim.publish("parking/gate/plate", json.dumps(plate_payload_unknown, ensure_ascii=False), qos=1)
	time.sleep(0.4)

time.sleep(2)

# -----------------------------------------------------------------------------
# ทดสอบที่ 5: จำลองสแกนป้ายอาจารย์ (ดร. กิตติพงษ์ วิทยาคุณ: 1กก 9999, active=1)
# -----------------------------------------------------------------------------
teacher_plate = "1กก 9999"
print(f"\n--- [TEST 5] สแกนป้ายอาจารย์/คณาจารย์ ({teacher_plate}) ---")
plate_payload_teacher = {
	"plate": teacher_plate,
	"province": "กรุงเทพมหานคร"
}
for i in range(1, config.PLATE_CONFIRM_COUNT + 1):
	print(f" -> ส่งเฟรมที่ {i}/{config.PLATE_CONFIRM_COUNT}: {teacher_plate}")
	cira_sim.publish("parking/gate/plate", json.dumps(plate_payload_teacher, ensure_ascii=False), qos=1)
	time.sleep(0.4)

print("ครบจำนวนรอบยืนยันแล้ว รอ service.py ตัดสินใจและสั่งเปิดไม้กั้น...")
time.sleep(config.GATE_OPEN_SEC + 2)

print("\n=================================================================")
print("                   การทดสอบ Simulation เสร็จสิ้น                ")
print(" สามารถเปิดดูหน้า Web Dashboard ได้ที่: http://localhost:8000     ")
print("=================================================================")

esp_sim.loop_stop()
cira_sim.loop_stop()
