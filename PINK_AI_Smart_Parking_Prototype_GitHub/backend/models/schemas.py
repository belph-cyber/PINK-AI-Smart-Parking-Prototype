# -*- coding: utf-8 -*-
"""
Pydantic Schemas for API Requests and Responses
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union, Literal

# Authentication
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    faculty: Optional[str] = None
    department: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: int

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role_code: str # 'ADMIN', 'SECURITY', 'STUDENT', 'TEACHER'
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    faculty: Optional[str] = None
    department: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    birthdate: Optional[str] = None

class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    role_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    faculty: Optional[str] = None
    department: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    birthdate: Optional[str] = None
    is_active: Optional[int] = None
    password: Optional[str] = None

class SlotCreateRequest(BaseModel):
    floor_number: int
    slot_number: str
    slot_type: str = "REGULAR"
    status: Literal["AVAILABLE", "OCCUPIED", "RESERVED", "UNKNOWN", "ERROR", "CONFLICT"] = "UNKNOWN"
    zone_code: Optional[str] = "A"

# Vehicles
class VehicleResponse(BaseModel):
    id: int
    plate_no: str
    province: str
    plate_display: str
    plate_clean: str
    vehicle_type: str
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    rfid_tag: Optional[str] = None
    is_active: int
    is_primary: Optional[int] = 0
    is_approved: Optional[int] = 1

class VehicleCreateRequest(BaseModel):
    user_id: int
    plate_no: str
    province: str
    vehicle_type: str = "car"
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    rfid_tag: Optional[str] = None
    is_primary: int = 1

# Parking & Slots
class SlotResponse(BaseModel):
    id: int
    floor_id: int
    floor_number: int
    zone_code: Optional[str] = None
    slot_number: str
    slot_type: str
    status: Literal["AVAILABLE", "OCCUPIED", "RESERVED", "UNKNOWN", "ERROR", "CONFLICT"]
    current_vehicle_plate: Optional[str] = None
    occupied_since: Optional[str] = None
    detection_source: Optional[str] = None
    last_detected_at: Optional[str] = None

class SlotUpdateRequest(BaseModel):
    status: Literal["AVAILABLE", "OCCUPIED", "RESERVED", "UNKNOWN", "ERROR", "CONFLICT"]
    slot_number: Optional[str] = None
    floor_number: Optional[int] = None
    zone_code: Optional[str] = None
    slot_type: Optional[str] = None
    vehicle_plate: Optional[str] = None
    notes: Optional[str] = None
    reason: Optional[str] = None

class FloorOverviewResponse(BaseModel):
    floor_number: int
    floor_name: str
    total_slots: int
    free_slots: int
    occupied_slots: int
    detection_type: str
    slots: List[SlotResponse]

# AI & Events
class AiEventResponse(BaseModel):
    id: int
    camera_id: int
    camera_name: str
    event_type: str
    raw_plate: Optional[str] = None
    clean_plate: Optional[str] = None
    confidence_score: Optional[float] = None
    evidence_image_path: Optional[str] = None
    suggested_floor: Optional[int] = None
    suggested_slot_number: Optional[str] = None
    status: str # 'PENDING', 'CONFIRMED', 'REJECTED', 'RESOLVED'
    verified_by_name: Optional[str] = None
    review_notes: Optional[str] = None
    corrected_plate: Optional[str] = None
    corrected_slot_id: Optional[int] = None
    created_at: str

class AiVerifyRequest(BaseModel):
    action: Literal["CONFIRM", "REJECT", "RESOLVE"]
    corrected_plate: Optional[str] = None
    corrected_slot_id: Optional[int] = None
    review_notes: Optional[str] = None

# Gates
class GateControlRequest(BaseModel):
    gate_id: Union[int, str]
    action: str = "OPEN" # 'OPEN', 'CLOSE', 'LOCK', 'UNLOCK', 'EMERGENCY'
    reason: Optional[str] = None

# Messaging
class MessageSendRequest(BaseModel):
    conversation_id: int
    content: str

class ConversationCreateRequest(BaseModel):
    user_id: Optional[int] = None
    subject: str
    related_plate: Optional[str] = None
    initial_message: str

# Notifications
class NotificationCreateRequest(BaseModel):
    target_user_id: Optional[int] = None
    target_role: Optional[str] = None
    title: str
    message: str
    category: str = "SECURITY"
    related_plate: Optional[str] = None

