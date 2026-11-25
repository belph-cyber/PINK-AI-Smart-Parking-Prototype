# -*- coding: utf-8 -*-
"""
AI & Hybrid Verification Router
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from typing import Optional
import hmac
import os
from backend.services.auth_service import get_current_user, require_roles
from backend.services.ai_service import get_recent_ai_events, verify_ai_event, process_ai_lpr_detection
from backend.models.schemas import AiVerifyRequest
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ai", tags=["AI Integration"])

class AiDetectionInput(BaseModel):
    camera_code: str
    plate: Optional[str] = None
    vehicle_detected: Optional[bool] = None
    ocr_failed: Optional[bool] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    floor: Optional[int] = None
    slot_number: Optional[str] = None
    image_url: Optional[str] = None

@router.get("/events")
def list_ai_events(limit: int = Query(30, ge=1, le=100),
                   current_user: dict = Depends(require_roles(["SECURITY", "ADMIN"]))):
    """Retrieve recent AI events queue"""
    return {"status": "ok", "events": get_recent_ai_events(limit)}

@router.post("/verify/{event_id}")
def verify_event(event_id: int, req: AiVerifyRequest,
                 current_user: dict = Depends(require_roles(["SECURITY", "ADMIN"]))):
    """Security Guard verifies or rejects an AI event"""
    res = verify_ai_event(
        event_id=event_id,
        action=req.action,
        security_user_id=current_user["id"],
        security_username=current_user["username"],
        corrected_plate=req.corrected_plate,
        corrected_slot_id=req.corrected_slot_id,
        review_notes=req.review_notes
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Verification failed"))
    return res

@router.post("/detection")
def record_detection(data: AiDetectionInput, x_integration_token: Optional[str] = Header(default=None)):
    """Integration endpoint protected by a separately configured integration token."""
    expected_token = os.getenv("CIRA_INGEST_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=503, detail="CiRA ingestion is not configured")
    if not x_integration_token or not hmac.compare_digest(x_integration_token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid integration token")
    if not data.plate and not (data.vehicle_detected is True and data.ocr_failed is True):
        raise HTTPException(status_code=422, detail="For a blank plate, explicitly set vehicle_detected=true and ocr_failed=true")
    res = process_ai_lpr_detection(
        camera_code=data.camera_code,
        raw_plate=data.plate,
        confidence=data.confidence,
        evidence_image_path=data.image_url,
        suggested_floor=data.floor,
        suggested_slot_number=data.slot_number,
        event_type="OCR_FAILED" if data.ocr_failed is True else "LPR_DETECT"
    )
    return {"status": "ok", "result": res}

