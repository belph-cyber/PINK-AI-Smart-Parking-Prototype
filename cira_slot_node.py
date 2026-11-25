# -*- coding: utf-8 -*-
"""
CiRA Core - Python Node: ตรวจนับช่องจอดในอาคาร (มุมกล้องเฉียง/มี perspective)
ตำแหน่งใน CiRA Core ตามโฟลว์:
  [Button Run] -> [Image Slide / กล้อง] -> [Deep Detect: parking] -> [Python (ไฟล์นี้)] -> [Mqtt Pub] + [Debug]
อินพุต: payload["DeepDetect"]["objects"]  (คลาส: parking_slot, car, x_parking_slot, cone ...)
เอาต์พุต:
  - payload["free_count"] / ["total_slots"] / ["occupied_count"] / ["closed_count"]
  - payload["out_text"]: ข้อความแสดงบนจอ CiRA
  - payload["light_status"]: "GREEN" หรือ "RED"
  - payload["mqtt_msg"]: JSON ส่งต่อไปยัง MqttPub Node (topic: parking/slots/status)

หลักการสำคัญ (แก้จากเวอร์ชันเดิมที่ใช้ได้ไม่ดีกับภาพในอาคารมุมเฉียง):
  1. ใช้ "จุดสัมผัสพื้น" ของรถ (ฐานล้อ ส่วนล่างของกรอบรถ) เทียบกับกรอบช่อง
     ไม่ใช้กรอบรถทั้งคัน เพราะในภาพเฉียงรถคันหน้าจะบังช่องที่อยู่ลึกเข้าไป
  2. รถ 1 คัน = 1 ช่อง (เลือกช่องที่ตรงที่สุด) ไม่ให้รถคันเดียวทำให้หลายช่องเต็ม
  3. กรองด้วย confidence และตรวจขนาดรถเทียบช่อง (กันรถไกล ๆ ไปตกในกรอบช่องใหญ่ด้านหน้า)
  4. x_parking_slot = ช่องที่ถูกปิด (ถ้าไม่ซ้อนกับ parking_slot ใด จะนับเป็นช่องปิดเพิ่ม)
  5. มี smoothing หลายเฟรม (ตั้ง SMOOTH_FRAMES > 1 เมื่อใช้กล้องสด) กันสถานะกะพริบ
"""

import json

# รองรับทั้งการทำงานใน CiRA Core และการเปิดใน IDE / VS Code (ป้องกันแจ้งเตือนตัวแปร Undefined)
payload = globals().get("payload", {})
val = globals().get("val", None)

# ------------------------------------------------------------------------------
# การตั้งค่า (ปรับได้)
# ------------------------------------------------------------------------------
VEHICLE_CLASSES = ("car", "motorcycle", "bicycle", "truck", "bus", "van")
SLOT_CLASS = "parking_slot"                                   # กรอบช่องจอดปกติ
CLOSED_SLOT_CLASS = "x_parking_slot"                          # ช่องที่ทำเครื่องหมาย X (ปิดช่อง)
OBSTACLE_CLASSES = ("cone", "traffic_cone", "barrier", "obstacle")  # สิ่งกีดขวางวางบนช่อง

CONF_VEHICLE = 0.50      # ความมั่นใจขั้นต่ำของรถ
CONF_SLOT = 0.40         # ความมั่นใจขั้นต่ำของช่องจอด
CONF_OBSTACLE = 0.50     # ความมั่นใจขั้นต่ำของสิ่งกีดขวาง
MIN_BOX_AREA = 400.0     # ตัดกรอบเล็กเกินไป (พิกเซล^2)

FOOT_RATIO = 0.30        # สัดส่วนส่วนล่างของกรอบรถที่ถือเป็นพื้นที่สัมผัสพื้น
FOOT_SHRINK = 0.15       # หดด้านข้างของฐานล้อเข้ามา (กันตัวถังที่ยื่นออกข้าง)
FOOT_TH = 0.35           # ฐานรถต้องอยู่ในช่องอย่างน้อย 35% (ถ้าจุดสัมผัสพื้นไม่ได้อยู่ในช่อง)
SIZE_RATIO_MIN = 0.25    # ความกว้างรถ / ความกว้างช่อง ต้องไม่น้อยกว่านี้ (กันรถที่อยู่ไกลกว่า)
SIZE_RATIO_MAX = 4.00    # และต้องไม่มากกว่านี้
OBSTACLE_FOOT_TH = 0.30  # สิ่งกีดขวางทับช่องอย่างน้อย 30% ของฐาน
DUP_IOU_TH = 0.50        # ตัดกรอบช่องซ้ำที่ IoU เกิน 50%
VEH_DUP_IOU_TH = 0.60    # ตัดกรอบรถซ้ำ
CLOSED_IOU_TH = 0.35     # x_parking_slot ซ้อนกับ parking_slot เกินนี้ = ช่องเดียวกัน

# จำนวนเฟรมติดกันที่ต้องเห็นสถานะใหม่ก่อนเปลี่ยน
#   1 = ไม่หน่วง (ใช้ตอนทดสอบด้วย Image Slide ที่เปลี่ยนภาพไปมา)
#   3-5 = แนะนำเมื่อใช้กล้อง IP สด
SMOOTH_FRAMES = 1


# ------------------------------------------------------------------------------
# ฟังก์ชันเรขาคณิต
# ------------------------------------------------------------------------------
def get_box(d):
	"""ดึงพิกัด [x1, y1, x2, y2] จากข้อมูล detection ของ CiRA"""
	if all(k in d for k in ("x1", "y1", "x2", "y2")):
		return [float(d["x1"]), float(d["y1"]), float(d["x2"]), float(d["y2"])]
	x = float(d.get("x", 0))
	y = float(d.get("y", 0))
	w = float(d.get("w", 0))
	h = float(d.get("h", 0))
	return [x, y, x + w, y + h]


def area(b):
	return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def width(b):
	return max(0.0, b[2] - b[0])


def intersect(a, b):
	w = min(a[2], b[2]) - max(a[0], b[0])
	h = min(a[3], b[3]) - max(a[1], b[1])
	return max(0.0, w) * max(0.0, h)


def coverage(inner, outer):
	"""สัดส่วนพื้นที่ของ inner ที่ถูก outer ทับ"""
	a = area(inner)
	return intersect(inner, outer) / a if a > 0 else 0.0


def iou(a, b):
	inter = intersect(a, b)
	union = area(a) + area(b) - inter
	return inter / union if union > 0 else 0.0


def footprint(b):
	"""ฐานล้อ/ส่วนที่สัมผัสพื้นของรถ (ส่วนล่างของกรอบ หดด้านข้างเล็กน้อย)"""
	w = b[2] - b[0]
	h = b[3] - b[1]
	return [b[0] + FOOT_SHRINK * w, b[3] - FOOT_RATIO * h, b[2] - FOOT_SHRINK * w, b[3]]


def anchor(b):
	"""จุดสัมผัสพื้น = กึ่งกลางด้านล่างของกรอบ (ยกขึ้นเล็กน้อยกันกรอบเลยพื้น)"""
	return ((b[0] + b[2]) / 2.0, b[3] - 0.08 * (b[3] - b[1]))


def point_inside(p, b):
	return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def dedupe(boxes, th):
	"""ตัดกรอบที่ซ้อนกันเกิน th (เก็บกรอบใหญ่กว่าไว้)"""
	out = []
	for b in sorted(boxes, key=area, reverse=True):
		if all(iou(b, o) < th for o in out):
			out.append(b)
	return out


def pick_slot(box, slots, check_size=True, foot_th=FOOT_TH):
	"""
	เลือกช่องที่ตรงกับวัตถุ (รถ/สิ่งกีดขวาง) มากที่สุด 1 ช่อง คืน index หรือ None
	เงื่อนไข: จุดสัมผัสพื้นอยู่ในช่อง หรือฐานล้อทับช่องเกิน foot_th
	ถ้ามีหลายช่อง (กรอบช่องซ้อนกันตาม perspective) เลือกช่องที่เล็กที่สุดที่มีจุดสัมผัสอยู่ข้างใน
	"""
	fp = footprint(box)
	anc = anchor(box)
	inside = []
	partial = []
	for i, s in enumerate(slots):
		sb = s["box"]
		if check_size and width(sb) > 0:
			ratio = width(box) / width(sb)
			if ratio < SIZE_RATIO_MIN or ratio > SIZE_RATIO_MAX:
				continue
		sc = coverage(fp, sb)
		if point_inside(anc, sb):
			inside.append((area(sb), -sc, i))
		elif sc >= foot_th:
			partial.append((-sc, i))
	if inside:
		inside.sort()
		return inside[0][2]
	if partial:
		partial.sort()
		return partial[0][1]
	return None


# ------------------------------------------------------------------------------
# Smoothing หลายเฟรม (ทำงานเมื่อ CiRA คง globals ไว้ระหว่างเฟรม)
# ------------------------------------------------------------------------------
_hist = globals().get("_slot_hist")
if not isinstance(_hist, dict):
	_hist = {}


def smooth_status(slot_id, new_status):
	"""เปลี่ยนสถานะก็ต่อเมื่อเห็นสถานะใหม่ติดกันครบ SMOOTH_FRAMES เฟรม"""
	if SMOOTH_FRAMES <= 1:
		return new_status
	h = _hist.get(slot_id)
	if h is None:
		_hist[slot_id] = {"stable": new_status, "cand": new_status, "n": 0}
		return new_status
	if new_status == h["stable"]:
		h["cand"] = new_status
		h["n"] = 0
		return h["stable"]
	if new_status == h["cand"]:
		h["n"] += 1
	else:
		h["cand"] = new_status
		h["n"] = 1
	if h["n"] >= SMOOTH_FRAMES:
		h["stable"] = new_status
		h["n"] = 0
	return h["stable"]


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
try:
	raw = payload.get("DeepDetect", {}).get("objects", [])

	vehicles = []      # [(box, conf)]
	slot_boxes = []
	closed_boxes = []  # x_parking_slot
	obstacles = []

	for d in raw:
		name = str(d.get("name", "")).strip().lower().replace(" ", "_")
		conf = float(d.get("confidence", 1.0))
		box = get_box(d)
		if area(box) < MIN_BOX_AREA:
			continue

		if name in VEHICLE_CLASSES and conf >= CONF_VEHICLE:
			vehicles.append((box, conf))
		elif name == SLOT_CLASS and conf >= CONF_SLOT:
			slot_boxes.append(box)
		elif name == CLOSED_SLOT_CLASS and conf >= CONF_SLOT:
			closed_boxes.append(box)
		elif name in OBSTACLE_CLASSES and conf >= CONF_OBSTACLE:
			obstacles.append(box)

	# ตัดกรอบซ้ำ
	slot_boxes = dedupe(slot_boxes, DUP_IOU_TH)
	closed_boxes = dedupe(closed_boxes, DUP_IOU_TH)
	veh_unique = dedupe([v[0] for v in vehicles], VEH_DUP_IOU_TH)
	veh_conf = {}
	for b, c in vehicles:
		veh_conf[tuple(b)] = c

	slots = [{"box": b, "closed": None, "car": None} for b in slot_boxes]

	# x_parking_slot: ซ้อนกับช่องเดิม -> ปิดช่องนั้น / ไม่ซ้อน -> เพิ่มเป็นช่องปิดใหม่
	for cb in closed_boxes:
		best_i, best_iou = None, 0.0
		for i, s in enumerate(slots):
			v = iou(cb, s["box"])
			if v > best_iou:
				best_i, best_iou = i, v
		if best_i is not None and best_iou >= CLOSED_IOU_TH:
			slots[best_i]["closed"] = u"มีเครื่องหมาย X ปิดช่อง"
		else:
			slots.append({"box": cb, "closed": u"มีเครื่องหมาย X ปิดช่อง", "car": None})

	# สิ่งกีดขวาง (กรวย ฯลฯ) -> ปิดช่องที่มันวางอยู่
	for ob in obstacles:
		i = pick_slot(ob, slots, check_size=False, foot_th=OBSTACLE_FOOT_TH)
		if i is not None and not slots[i]["closed"]:
			slots[i]["closed"] = u"มีสิ่งกีดขวาง/กรวยวางในช่อง"

	# รถ 1 คัน -> 1 ช่อง
	for vb in veh_unique:
		i = pick_slot(vb, slots, check_size=True)
		if i is None:
			continue
		conf = veh_conf.get(tuple(vb), 0.0)
		cur = slots[i]["car"]
		if cur is None or conf > cur:
			slots[i]["car"] = conf

	# เรียงช่องจากซ้ายไปขวา เพื่อให้หมายเลขช่องคงที่
	slots.sort(key=lambda s: s["box"][0])

	free = 0
	occupied = 0
	closed = 0
	slot_details = []

	for idx, s in enumerate(slots, start=1):
		if s["closed"]:
			status, reason = "closed", s["closed"]
		elif s["car"] is not None:
			status, reason = "occupied", u"มีรถจอดในช่อง (%.0f%%)" % (s["car"] * 100)
		else:
			status, reason = "free", u"ว่าง"

		status = smooth_status(idx, status)
		if status == "occupied":
			occupied += 1
		elif status == "closed":
			closed += 1
		else:
			free += 1

		slot_details.append({
			"id": idx,
			"box": [round(c, 1) for c in s["box"]],
			"status": status,
			"reason": reason
		})

	globals()["_slot_hist"] = _hist

	total = len(slots)
	light_status = "GREEN" if free > 0 else "RED"

	payload["free_count"] = free
	payload["total_slots"] = total
	payload["occupied_count"] = occupied
	payload["closed_count"] = closed
	payload["light_status"] = light_status
	payload["out_text"] = u"ว่าง %d จาก %d ช่อง (มีรถ %d / ปิด %d)" % (free, total, occupied, closed) if total > 0 else u"ไม่พบช่องจอด"
	val = free

	mqtt_data = {
		"free": free,
		"total": total,
		"occupied": occupied,
		"closed": closed,
		"light_status": light_status,
		"slots": slot_details
	}
	payload["mqtt_msg"] = json.dumps(mqtt_data, ensure_ascii=False)
	val = payload["mqtt_msg"]

	print("[SLOTS] Total: %d, Free: %d, Occupied: %d, Closed: %d | LED: %s" % (
		total, free, occupied, closed, light_status
	))

except Exception as e:
	payload["out_text"] = u"System Error: " + str(e)
	payload["light_status"] = "RED"
	payload["free_count"] = 0
	payload["total_slots"] = 0
	payload["mqtt_msg"] = json.dumps({"free": 0, "total": 0, "error": str(e)}, ensure_ascii=False)
	val = payload["mqtt_msg"]
	print("Slot node error:", e)
