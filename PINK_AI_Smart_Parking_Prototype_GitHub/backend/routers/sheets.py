# -*- coding: utf-8 -*-
"""
PINK AI: Google Sheets & Apps Script Integration Router
Protected by Admin RBAC
"""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from backend.services.auth_service import require_roles
from backend.services.sheets_service import (
    get_sheets_sync_status,
    trigger_sheets_sync,
    compile_all_sheets_payload,
    save_webapp_config,
    inspect_remote_sheets,
    get_apps_script_source,
    SPREADSHEET_ID,
    SPREADSHEET_URL
)

router = APIRouter(prefix="/api/sheets", tags=["Google Sheets Integration"])


class SheetsConfigRequest(BaseModel):
    webapp_url: str
    sync_secret: Optional[str] = None


@router.get("/status")
def sheets_status(current_user: dict = Depends(require_roles(["ADMIN"]))):
    """Retrieve Google Sheets synchronization status and 6-sheet counts"""
    return {"status": "ok", "sync": get_sheets_sync_status()}


@router.post("/config")
def update_sheets_config(req: SheetsConfigRequest, current_user: dict = Depends(require_roles(["ADMIN"]))):
    """Save Google Apps Script Web App URL (/exec) in system_settings"""
    res = save_webapp_config(req.webapp_url, req.sync_secret, username=current_user["username"])
    return {"status": "ok", "config": res, "sync": get_sheets_sync_status()}


@router.post("/inspect")
def sheets_inspect(current_user: dict = Depends(require_roles(["ADMIN"]))):
    """Inspect remote Google Sheets structure before syncing"""
    res = inspect_remote_sheets(username=current_user["username"])
    return {"status": "ok", "inspection": res}


@router.post("/sync")
def sheets_sync(current_user: dict = Depends(require_roles(["ADMIN"]))):
    """Trigger synchronization of all 6 standardized sheets to Google Sheets"""
    res = trigger_sheets_sync(username=current_user["username"])
    return {"status": "ok", "result": res, "sync": get_sheets_sync_status()}


@router.get("/export")
def sheets_export(current_user: dict = Depends(require_roles(["ADMIN"]))):
    """Export all 6 sheets data structure (Database as Source of Truth, no passwords)"""
    data = compile_all_sheets_payload()
    return {"status": "ok", "export": data}


@router.get("/apps-script-code")
def apps_script_code(current_user: dict = Depends(require_roles(["ADMIN"]))):
    """Return Code.gs source code so Admin can copy & paste into Google Sheets Apps Script"""
    return {
        "status": "ok",
        "spreadsheet_id": SPREADSHEET_ID,
        "spreadsheet_url": SPREADSHEET_URL,
        "code_gs": get_apps_script_source()
    }
