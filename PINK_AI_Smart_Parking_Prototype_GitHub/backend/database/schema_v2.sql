-- ==============================================================================
-- PINK AI: SMART PARKING MANAGEMENT SYSTEM
-- Unified Database Schema v2 (19 Core Tables)
-- ==============================================================================

-- 1. ROLES
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL, -- 'ADMIN', 'SECURITY', 'STUDENT', 'TEACHER'
    name TEXT NOT NULL,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. USERS
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL, -- e.g. 'admin', 'sec01', '65010001', 'T8800101'
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    faculty TEXT,
    department TEXT,
    avatar_url TEXT,
    is_active INTEGER DEFAULT 1, -- 1=active, 0=suspended
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id);

-- 3. VEHICLES
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_no TEXT NOT NULL,
    province TEXT NOT NULL,
    plate_display TEXT NOT NULL,
    plate_clean TEXT UNIQUE NOT NULL, -- stripped for LPR lookup
    vehicle_type TEXT DEFAULT 'car', -- 'car', 'motorcycle', 'van'
    brand TEXT,
    model TEXT,
    color TEXT,
    rfid_tag TEXT,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_vehicles_plate_clean ON vehicles(plate_clean);

-- 4. USER_VEHICLES (M:N link between users and authorized vehicles)
CREATE TABLE IF NOT EXISTS user_vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    vehicle_id INTEGER NOT NULL,
    is_primary INTEGER DEFAULT 1,
    is_approved INTEGER DEFAULT 1, -- must be approved by admin
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    UNIQUE(user_id, vehicle_id)
);

-- 5. PARKING_FLOORS
CREATE TABLE IF NOT EXISTS parking_floors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    floor_number INTEGER UNIQUE NOT NULL,
    floor_name TEXT NOT NULL,
    total_slots INTEGER NOT NULL DEFAULT 10,
    detection_type TEXT DEFAULT 'LPR', -- 'SENSOR_HCSR04' or 'LPR'
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 6. PARKING_ZONES
CREATE TABLE IF NOT EXISTS parking_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    floor_id INTEGER NOT NULL,
    zone_code TEXT NOT NULL, -- 'A', 'B', 'VIP'
    zone_name TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (floor_id) REFERENCES parking_floors(id) ON DELETE CASCADE,
    UNIQUE(floor_id, zone_code)
);

-- 7. PARKING_SLOTS
CREATE TABLE IF NOT EXISTS parking_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    floor_id INTEGER NOT NULL,
    zone_id INTEGER,
    slot_number TEXT NOT NULL, -- e.g. '1-01', '1-02', 'B-025'
    slot_type TEXT DEFAULT 'REGULAR', -- 'REGULAR', 'VIP', 'DISABLED', 'EV'
    status TEXT DEFAULT 'UNKNOWN', -- 'AVAILABLE', 'OCCUPIED', 'RESERVED', 'UNKNOWN', 'ERROR', 'CONFLICT'
    current_vehicle_id INTEGER,
    occupied_since DATETIME,
    detection_source TEXT, -- 'AI_CAMERA', 'ULTRASONIC_SENSOR', 'MANUAL_SECURITY'
    last_detected_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (floor_id) REFERENCES parking_floors(id) ON DELETE CASCADE,
    FOREIGN KEY (zone_id) REFERENCES parking_zones(id) ON DELETE SET NULL,
    FOREIGN KEY (current_vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL,
    UNIQUE(floor_id, slot_number)
);
CREATE INDEX IF NOT EXISTS idx_slots_status ON parking_slots(status);

-- 8. CAMERAS
CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_code TEXT UNIQUE NOT NULL, -- 'GATE-IN-LPR', 'CAM-FL1-HEAD', 'CAM-FL1-TAIL', 'CAM-FL2-HEAD', 'CAM-FL2-TAIL'
    name TEXT NOT NULL,
    location_type TEXT NOT NULL, -- 'GATE', 'FLOOR_HEAD', 'FLOOR_TAIL', 'SLOT_OVERVIEW'
    floor_id INTEGER,
    rtsp_url TEXT,
    stream_url TEXT,
    status TEXT DEFAULT 'OFFLINE', -- 'ONLINE', 'OFFLINE', 'ERROR'
    last_frame_ts DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (floor_id) REFERENCES parking_floors(id) ON DELETE SET NULL
);

-- 9. CAMERA_SLOT_ZONES (Bounding boxes / Polygons on camera view for slot detection)
CREATE TABLE IF NOT EXISTS camera_slot_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    polygon_points TEXT, -- JSON coordinates [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES parking_slots(id) ON DELETE CASCADE
);

-- 10. PARKING_SESSIONS
CREATE TABLE IF NOT EXISTS parking_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL,
    user_id INTEGER,
    entry_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    exit_time DATETIME,
    entry_gate_id INTEGER,
    exit_gate_id INTEGER,
    assigned_slot_id INTEGER,
    current_floor INTEGER DEFAULT 1,
    session_status TEXT DEFAULT 'ACTIVE', -- 'ACTIVE', 'COMPLETED', 'DISPUTED'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_slot_id) REFERENCES parking_slots(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_vehicle_status ON parking_sessions(vehicle_id, session_status);

-- 11. VEHICLE_EVENTS (Real physical vehicle movements & gate events)
CREATE TABLE IF NOT EXISTS vehicle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    vehicle_id INTEGER NOT NULL,
    event_type TEXT NOT NULL, -- 'GATE_ENTRY', 'FLOOR_HEAD', 'FLOOR_TAIL', 'PARKED', 'UNPARKED', 'GATE_EXIT'
    floor_number INTEGER,
    position TEXT, -- 'head', 'tail', 'slot'
    camera_id INTEGER,
    detected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (session_id) REFERENCES parking_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_vehicle_events_vehicle ON vehicle_events(vehicle_id, detected_at);

-- 12. AI_EVENTS (Hybrid Verification queue for LPR and slot classification)
CREATE TABLE IF NOT EXISTS ai_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL,
    event_type TEXT NOT NULL, -- 'LPR_DETECT', 'SLOT_OCCUPANCY', 'UNKNOWN_VEHICLE', 'WRONG_PARKING'
    raw_plate TEXT,
    clean_plate TEXT,
    confidence_score REAL DEFAULT 0.0,
    evidence_image_path TEXT,
    suggested_floor INTEGER,
    suggested_slot_id INTEGER,
    status TEXT DEFAULT 'PENDING', -- 'PENDING', 'CONFIRMED', 'REJECTED', 'RESOLVED'
    verified_by_user_id INTEGER,
    verified_at DATETIME,
    review_notes TEXT,
    corrected_plate TEXT,
    corrected_slot_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
    FOREIGN KEY (verified_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_events_status ON ai_events(status);

-- 13. GATES
CREATE TABLE IF NOT EXISTS gates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gate_code TEXT UNIQUE NOT NULL, -- 'GATE-MAIN-IN', 'GATE-MAIN-OUT'
    name TEXT NOT NULL,
    direction TEXT NOT NULL, -- 'IN', 'OUT'
    status TEXT DEFAULT 'CLOSED', -- 'OPEN', 'CLOSED', 'ERROR', 'OFFLINE'
    auto_close_sec INTEGER DEFAULT 5,
    camera_id INTEGER,
    controller_ip TEXT,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE SET NULL
);

-- 14. GATE_LOGS (Audit trail of barrier gate operations)
CREATE TABLE IF NOT EXISTS gate_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gate_id INTEGER NOT NULL,
    action TEXT NOT NULL, -- 'OPEN_REQUEST', 'OPEN_SUCCESS', 'OPEN_FAILED', 'AUTO_CLOSED', 'TIMEOUT'
    triggered_by TEXT NOT NULL, -- 'AUTO_AI', 'SECURITY_MANUAL', 'EMERGENCY_BUTTON'
    user_id INTEGER, -- security officer id if manual
    vehicle_id INTEGER,
    plate_text TEXT,
    result_status TEXT NOT NULL, -- 'SUCCESS', 'DENIED', 'ERROR', 'TIMEOUT'
    response_payload TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gate_id) REFERENCES gates(id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_gate_logs_created_at ON gate_logs(created_at);

-- 15. NOTIFICATIONS
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, -- target user (NULL = all security/admin)
    target_role TEXT, -- 'STUDENT', 'TEACHER', 'SECURITY', 'ADMIN'
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    category TEXT DEFAULT 'SYSTEM', -- 'AI_ALERT', 'SECURITY', 'PARKING_STATUS', 'EMERGENCY'
    related_plate TEXT,
    is_read INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read);

-- 16. CONVERSATIONS (2-Way messaging between Security and vehicle owners)
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, -- Vehicle owner / student / teacher
    security_user_id INTEGER, -- Assigned security officer
    subject TEXT,
    related_plate TEXT,
    status TEXT DEFAULT 'OPEN', -- 'OPEN', 'CLOSED'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (security_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 17. MESSAGES
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_role TEXT NOT NULL, -- 'SECURITY', 'STUDENT', 'TEACHER', 'ADMIN'
    content TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

-- 18. AUDIT_LOGS
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    action TEXT NOT NULL, -- 'LOGIN', 'LOGOUT', 'USER_CREATE', 'GATE_OPEN_MANUAL', 'AI_VERIFIED', 'SLOT_CHANGED'
    entity_type TEXT, -- 'USER', 'GATE', 'SLOT', 'VEHICLE', 'SYSTEM'
    entity_id TEXT,
    old_value TEXT,
    new_value TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- 19. SYSTEM_SETTINGS
CREATE TABLE IF NOT EXISTS system_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT UNIQUE NOT NULL,
    setting_value TEXT NOT NULL,
    description TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

