# -*- coding: utf-8 -*-
"""
CiRA Core - Python Node: อ่านป้ายทะเบียนและส่งข้อมูลผ่าน MQTT
ตำแหน่งใน CiRA Core: วางใน Python Node หลัง DeepDetect / DeepD_D (คลาส license_plate)
อินพุต: payload["Deepdetect"] หรือ payload["DeepD_D"] หรือ payload["objects"] (สแกนอัตโนมัติทุกโหนด)
เอาต์พุต:
  - payload["license"]: ข้อความแสดงผลบนหน้าจอ CiRA Display
  - val: ค่าส่งออกของ Node
  - payload["mqtt_msg"]: JSON ส่งต่อไปยัง MqttPub Node (topic: parking/gate/plate)
"""

import json
import time as _time

# รองรับทั้งการทำงานใน CiRA Core และการเปิดใน IDE / VS Code
payload = globals().get("payload", {})
val = globals().get("val", None)

# ตารางจับคู่คลาสกับตัวอักษร/ตัวเลข และจังหวัด
ALPHABET = {
	"0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
	"5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
	"T1": "ก", "T2": "ข", "T3": "ฃ", "T4": "ค", "T5": "ฅ", "T6": "ฆ", "T7": "ง", "T8": "จ", "T9": "ฉ", "T10": "ช",
	"T11": "ซ", "T12": "ฌ", "T13": "ญ", "T14": "ฎ", "T15": "ฏ", "T16": "ฐ", "T17": "ฑ", "T18": "ฒ", "T19": "ณ", "T20": "ด",
	"T21": "ต", "T22": "ถ", "T23": "ท", "T24": "ธ", "T25": "น", "T26": "บ", "T27": "ป", "T28": "ผ", "T29": "ฝ", "T30": "พ",
	"T31": "ฟ", "T32": "ภ", "T33": "ม", "T34": "ย", "T35": "ร", "T36": "ล", "T37": "ว", "T38": "ศ", "T39": "ษ", "T40": "ส",
	"T41": "ห", "T42": "ฬ", "T43": "อ", "T44": "ฮ",
	"BKK": "กรุงเทพมหานคร", "KBV": "กระบี่", "KRI": "กาญจนบุรี", "KSN": "กาฬสินธุ์", "KPT": "กำแพงเพชร",
	"KKC": "ขอนแก่น", "CTI": "จันทบุรี", "CCO": "ฉะเชิงเทรา", "CBI": "ชลบุรี", "CNT": "ชัยนาท", "CPM": "ชัยภูมิ",
	"CPN": "ชุมพร", "CRI": "เชียงราย", "CMI": "เชียงใหม่", "TRG": "ตรัง", "TRT": "ตราด", "TAK": "ตาก",
	"NYK": "นครนายก", "NPT": "นครปฐม", "NPM": "นครพนม", "NMA": "นครราชสีมา", "NSN": "นครศรีธรรมราช", "NSW": "นครสวรรค์",
	"NBI": "นนทบุรี", "NWT": "นราธิวาส", "NAN": "น่าน", "PTM": "ปทุมธานี", "PKN": "ประจวบคีรีขันธ์", "PRI": "ปราจีนบุรี",
	"PTN": "ปัตตานี", "PYO": "พะเยา", "AYA": "พระนครศรีอยุธยา", "PHN": "พังงา", "PLT": "พัทลุง", "PCT": "พิจิตร",
	"PLK": "พิษณุโลก", "PNB": "เพชรบูรณ์", "PBI": "เพชรบุรี", "PRE": "แพร่", "PKT": "ภูเก็ต",
	"MKM": "มหาสารคาม", "MDH": "มุกดาหาร", "MSN": "แม่ฮ่องสอน", "YST": "ยโสธร", "YLA": "ยะลา",
	"RET": "ร้อยเอ็ด", "RNG": "ระนอง", "RYG": "ระยอง", "RBR": "ราชบุรี", "LOP": "ลพบุรี",
	"LPN": "ลำปาง", "LPM": "ลำพูน", "LEI": "เลย", "SSK": "ศรีสะเกษ", "SNK": "สกลนคร",
	"SKA": "สงขลา", "STN": "สตูล", "SPK": "สมุทรปราการ", "SKM": "สมุทรสงคราม", "SKN": "สมุทรสาคร",
	"SKW": "สระแก้ว", "SRI": "สระบุรี", "SGR": "สิงห์บุรี", "STI": "สุโขทัย", "SPB": "สุพรรณบุรี",
	"SNI": "สุราษฎร์ธานี", "SRN": "สุรินทร์", "NKI": "หนองคาย", "NBU": "หนองบัวลำภู",
	"ATG": "อ่างทอง", "ACR": "อำนาจเจริญ", "UDN": "อุดรธานี", "UTT": "อุตรดิตถ์", "UTI": "อุทัยธานี", "UBN": "อุบลราชธานี",
}


def is_digit_class(name):
	return name.isdigit()


def is_letter_class(name):
	# คลาสตัวอักษรไทยขึ้นต้นด้วย T1 ถึง T44
	return name.startswith("T") and name[1:].isdigit()


# รหัสจังหวัดคือคีย์ที่ไม่ใช่ตัวเลขและไม่ใช่ตัวอักษรไทย
PROVINCE_CODES = set(k for k in ALPHABET if not is_digit_class(k) and not is_letter_class(k))


def sort_key(e):
	return e.get("x", 0)


def build_plate(objects):
	"""
	แปลงรายการ objects ที่ตรวจจับได้ให้เป็น (ข้อความแถวบน, ชื่อจังหวัด)
	รองรับทั้งป้ายแบบเก่า 'กท 2058', 'กม 3070' และป้ายแบบใหม่ '1กท 2058'
	"""
	parts = []
	province = ""

	for obj in sorted(objects, key=sort_key):
		name = str(obj.get("name", "")).strip()
		if name in PROVINCE_CODES:
			province = ALPHABET[name]
			continue
		if name not in ALPHABET:
			continue
		kind = "digit" if is_digit_class(name) else "letter"
		parts.append((kind, ALPHABET[name]))

	text = ""
	prev_kind = None
	for kind, char_val in parts:
		if prev_kind is not None and kind != prev_kind:
			text += " "
		text += char_val
		prev_kind = kind

	return text.strip(), province


def extract_plate_info(payload):
	"""
	ดึงข้อมูลตัวอักษรป้ายทะเบียนและความมั่นใจจาก payload ของ CiRA Core ทุกรูปแบบอัตโนมัติ:
	- สแกนหา key ทั้งหมดใน payload ไม่ว่าจะชื่อ Deepdetect, DeepDetect, DeepD_D, YOLO หรือชื่อใดๆ
	- รองรับทั้งแบบมีกรอบ license_plate ครอบ และแบบตรวจจับตัวอักษรป้ายตรงๆ
	"""
	candidates = []

	def evaluate_objs(objs, default_conf=0.85, default_w=200.0, priority=10):
		if not isinstance(objs, list) or not objs:
			return
		valid_chars = sum(1 for o in objs if isinstance(o, dict) and str(o.get("name", "")).strip() in ALPHABET)
		if valid_chars == 0:
			return
		confs = [float(o.get("confidence", o.get("prob", default_conf))) for o in objs if isinstance(o, dict)]
		avg_c = sum(confs) / len(confs) if confs else default_conf
		xs = [float(o.get("x", 0)) for o in objs if isinstance(o, dict)]
		ws = [float(o.get("w", 0)) for o in objs if isinstance(o, dict)]
		span_w = (max(xs) + max(ws) - min(xs)) if (xs and ws) else default_w
		candidates.append((objs, avg_c, span_w, priority, valid_chars))

	if isinstance(payload, dict):
		# 1. ตรวจสอบที่ root ของ payload
		if "objects" in payload:
			evaluate_objs(payload["objects"], priority=10)
		if "detects" in payload and isinstance(payload["detects"], list):
			for d in payload["detects"]:
				if isinstance(d, dict):
					c = float(d.get("confidence", d.get("prob", 1.0)))
					w = float(d.get("w", 0)) or (float(d.get("x2", 0)) - float(d.get("x1", 0)))
					prio = 25 if d.get("name") == "license_plate" else 15
					evaluate_objs(d.get("objects", []), default_conf=c, default_w=w, priority=prio)

		# 2. ตรวจสอบทุก key ใน payload (ไม่สนตัวพิมพ์ใหญ่-เล็ก หรือชื่อโหนด)
		for k, node_val in payload.items():
			if k in ("license", "mqtt_msg"):
				continue
			if isinstance(node_val, dict):
				for d in node_val.get("detects", []):
					if isinstance(d, dict):
						c = float(d.get("confidence", d.get("prob", 1.0)))
						w = float(d.get("w", 0)) or (float(d.get("x2", 0)) - float(d.get("x1", 0)))
						prio = 25 if d.get("name") == "license_plate" else 15
						evaluate_objs(d.get("objects", []), default_conf=c, default_w=w, priority=prio)
				if "objects" in node_val:
					evaluate_objs(node_val["objects"], priority=20)
			elif isinstance(node_val, list):
				for d in node_val:
					if isinstance(d, dict):
						c = float(d.get("confidence", d.get("prob", 1.0)))
						w = float(d.get("w", 0)) or (float(d.get("x2", 0)) - float(d.get("x1", 0)))
						prio = 25 if d.get("name") == "license_plate" else 15
						evaluate_objs(d.get("objects", []), default_conf=c, default_w=w, priority=prio)

	if not candidates:
		return [], 0.0, 0.0

	# เลือก candidate ที่มีตัวอักษรป้ายทะเบียนสมบูรณ์และคะแนนดีที่สุด
	best = max(candidates, key=lambda c: (c[4] >= 4, c[3], c[4], c[1]))
	return best[0], best[1], best[2]


# ------------------------------------------------------------------------------
# โหมดจับภาพเป็นช็อตความแม่นยำสูง (Precision Shot Engine):
# - ปรับจังหวะช็อตให้นิ่ง สุขุม ชัดเจน (SHOT_PACE_SEC) ไม่เร็วรัวจนเบลอ
# - คัดเฉพาะเฟรมที่คมชัดและตัวอักษรสมบูรณ์มาวิเคราะห์
# - อ่านทะเบียนออกมาทันที และค้างผลบนจอ CiRA Display ให้อ่านได้ชัดเจน ไม่กะพริบหาย
# ------------------------------------------------------------------------------
SHOT_PACE_SEC       = 1.0     # จังหวะช็อต (1.0 วินาที เพื่อเก็บเฟรมที่นิ่งและชัดที่สุด)
SHOT_MAX_FRAMES     = 5       # จำนวนเฟรมคุณภาพสูงสุดใน 1 ช็อต
DISPLAY_HOLD_SEC    = 3.5     # ค้างผลทะเบียนบนจอ CiRA Display (ไม่กระพริบกลับเป็น Waiting... ทันที)
MIN_CONF            = 0.50    # ความมั่นใจขั้นต่ำของกรอบป้ายทะเบียน
MIN_CHAR_CONF       = 0.40    # ความมั่นใจเฉลี่ยของตัวอักษร
MIN_CHARS           = 4       # จำนวนตัวอักษร/ตัวเลขขั้นต่ำบนป้าย
MIN_PLATE_W         = 40.0    # ความกว้างของป้ายขั้นต่ำ (พิกเซล)
RESULT_REPEAT_SEC   = 4.0     # เว้นช่วงส่ง MQTT ป้ายเดิมซ้ำ (กันส่งรัว)

_shot = globals().get("_plate_shot")
if not isinstance(_shot, dict):
	_shot = {
		"frames": [],
		"shot_start": 0.0,
		"last_seen": 0.0,
		"current_display": "Waiting...",
		"current_plate": "",
		"current_prov": "",
		"display_until": 0.0,
		"last_pub_plate": "",
		"last_pub_ts": 0.0,
		"last_shot_info": {}
	}


def frame_quality(objs, conf, w):
	"""คืน (plate_text, province, score, is_strong) หรือ None ถ้าเฟรมไม่ชัดพอ"""
	if conf < MIN_CONF:
		return None
	chars = [o for o in objs if str(o.get("name", "")).strip() in ALPHABET
	         and str(o.get("name", "")).strip() not in PROVINCE_CODES]
	if len(chars) < MIN_CHARS:
		return None
	char_confs = [float(o.get("confidence", o.get("prob", 1.0))) for o in chars]
	avg_c = sum(char_confs) / len(char_confs)
	if avg_c < MIN_CHAR_CONF or min(char_confs) < 0.30:
		return None
	if w and w < MIN_PLATE_W:
		return None
	text, prov = build_plate(objs)
	if not text:
		return None
	score = conf * avg_c * (1.0 + min(w, 400.0) / 600.0)
	is_strong = (conf >= 0.70 and avg_c >= 0.70 and len(chars) >= 4)
	return text, prov, score, is_strong


def finalize_shot(frames):
	"""โหวตป้ายที่มีคะแนนความคมชัดรวมสูงสุด พร้อมเลือกจังหวัดที่ตรงกันมากที่สุด"""
	votes = {}
	for t, p, s, _st in frames:
		votes[t] = votes.get(t, 0.0) + s
	best_text = max(votes, key=votes.get)
	prov_votes = {}
	for t, p, s, _st in frames:
		if t == best_text and p:
			prov_votes[p] = prov_votes.get(p, 0.0) + s
	best_prov = max(prov_votes, key=prov_votes.get) if prov_votes else ""
	agree = sum(1 for t, p, s, _st in frames if t == best_text)
	return best_text, best_prov, agree, len(frames)


# ประมวลผลหลัก
try:
	now_t = _time.time()
	objs, plate_conf, plate_w = extract_plate_info(payload)

	# 1. ตรวจสอบคุณภาพเฟรมปัจจุบัน
	if objs:
		q = frame_quality(objs, plate_conf, plate_w)
		if q is not None:
			if not _shot["frames"]:
				_shot["shot_start"] = now_t
			_shot["frames"].append(q)
			_shot["last_seen"] = now_t

	frames = _shot["frames"]
	shot_elapsed = now_t - _shot["shot_start"] if _shot["shot_start"] else 0.0
	no_plate_gap = now_t - _shot["last_seen"] if _shot["last_seen"] else 999.0

	# 2. เงื่อนไขสรุปช็อต (เป็นจังหวะช็อตที่ช้าลง ชัดเจน และอ่านออกทันที)
	should_finalize = False
	if frames:
		if frames[-1][3]: # เฟรมมีความคมชัดสูง สรุปผลอ่านออกทันที
			should_finalize = True
		elif shot_elapsed >= SHOT_PACE_SEC and len(frames) >= 1:
			should_finalize = True
		elif len(frames) >= SHOT_MAX_FRAMES:
			should_finalize = True
		elif no_plate_gap >= 0.6 and len(frames) >= 1:
			should_finalize = True

	new_published = False
	if should_finalize:
		best_t, best_p, agree, total = finalize_shot(frames)
		_shot["frames"] = []
		_shot["shot_start"] = now_t

		if best_t:
			_shot["current_plate"] = best_t
			_shot["current_prov"] = best_p
			_shot["current_display"] = best_t + ("\n" + best_p if best_p else "")
			_shot["display_until"] = now_t + DISPLAY_HOLD_SEC

			if best_t != _shot["last_pub_plate"] or (now_t - _shot["last_pub_ts"] >= RESULT_REPEAT_SEC):
				_shot["last_pub_plate"] = best_t
				_shot["last_pub_ts"] = now_t
				new_published = True
				_shot["last_shot_info"] = {"agree": agree, "frames": total}

	# 3. จัดการสถานะจอ CiRA Display เมื่อไม่มีรถผ่านเกินเวลา
	if now_t > _shot.get("display_until", 0.0) and no_plate_gap > 1.5:
		_shot["current_display"] = "Waiting..."
		_shot["current_plate"] = ""
		_shot["current_prov"] = ""

	# 4. ส่งค่าผลลัพธ์ออกจอ CiRA Display (ค้างป้ายให้นิ่ง ชัดเจน ไม่กะพริบ)
	payload["license"] = _shot["current_display"]
	val = _shot["current_display"]

	# 5. ส่งค่าออก MQTT (MqttPub Node)
	if new_published and _shot["current_plate"]:
		mqtt_data = {
			"plate": _shot["current_plate"],
			"province": _shot["current_prov"],
			"full_text": _shot["current_display"],
			"mode": "SHOT",
			"shot_agree": _shot.get("last_shot_info", {}).get("agree", 1),
			"shot_frames": _shot.get("last_shot_info", {}).get("frames", 1)
		}
		payload["mqtt_msg"] = json.dumps(mqtt_data, ensure_ascii=False)
		print(">>> [SHOT SUCCESS] %s (voted %d/%d frames) -> MQTT SENT" %
		      (_shot["current_display"].replace("\n", " "),
		       _shot.get("last_shot_info", {}).get("agree", 1),
		       _shot.get("last_shot_info", {}).get("frames", 1)))
	else:
		payload["mqtt_msg"] = json.dumps({
			"plate": _shot["current_plate"] if _shot["current_plate"] else "Waiting...",
			"province": _shot["current_prov"],
			"full_text": _shot["current_display"]
		}, ensure_ascii=False)

	globals()["_plate_shot"] = _shot

except Exception as e:
	payload["license"] = "Waiting..."
	payload["mqtt_msg"] = json.dumps({"plate": "Waiting...", "province": ""}, ensure_ascii=False)
	val = payload["mqtt_msg"]
	print("Plate node error:", e)
