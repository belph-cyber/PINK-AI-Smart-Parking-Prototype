# -*- coding: utf-8 -*-
"""
Authentication & RBAC Service
- Strict JWT validation & Role-Based Access Control
- Login & Logout tracking in login_logs (Sheet 5)
- Personal Information enrichment with registered vehicle
"""

from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any, List
from datetime import datetime

from backend.core.database import query_one, query_all, execute
from backend.core.security import verify_password, decode_access_token
from backend.services.audit_service import log_audit
from backend.services.sheets_service import trigger_sheets_sync_async

security_bearer = HTTPBearer(auto_error=False)


def _enrich_user_vehicles(user_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Attach primary vehicle info to user profile without mutating DB"""
    try:
        veh = query_one("""
            SELECT v.plate_display, v.province, v.brand, v.model, v.color
            FROM user_vehicles uv
            JOIN vehicles v ON uv.vehicle_id = v.id
            WHERE uv.user_id = ?
            ORDER BY uv.is_primary DESC, v.id ASC
            LIMIT 1;
        """, (user_dict["id"],))
        if veh:
            user_dict["vehicle_plate"] = f"{veh['plate_display']} {veh.get('province') or ''}".strip()
            user_dict["vehicle_detail"] = f"{veh.get('brand') or ''} {veh.get('model') or ''} ({veh.get('color') or ''})".strip(" ()")
        else:
            user_dict["vehicle_plate"] = None
            user_dict["vehicle_detail"] = None
    except Exception:
        user_dict["vehicle_plate"] = None
        user_dict["vehicle_detail"] = None
    return user_dict


def authenticate_user(username: str, password: str, client_ip: str = None, user_agent: str = None) -> Optional[Dict[str, Any]]:
    """Validate credentials and return user dict if successful"""
    clean_username = username.strip()
    user = query_one("""
        SELECT u.id, u.username, u.password_hash, u.role_id, r.code as role_code, r.name as role_name,
               u.name, u.email, u.phone, u.faculty, u.department, u.avatar_url, u.is_active,
               u.gender, u.age, u.birthdate, u.last_login_at
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.username = ?;
    """, (clean_username,))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not user:
        log_audit(clean_username, "LOGIN_FAILED", "AUTH", None, None, "User not found", client_ip)
        try:
            execute("""
                INSERT INTO login_logs (username, name, role, ip_address, user_agent, status, event_detail, login_at)
                VALUES (?, ?, ?, ?, ?, 'FAILED', 'User not found', ?)
            """, (clean_username, "ยังไม่ได้ระบุ", "UNKNOWN", client_ip, user_agent, now_str))
        except Exception:
            pass
        return None

    if not user["is_active"]:
        log_audit(clean_username, "LOGIN_BLOCKED", "AUTH", str(user["id"]), None, "Account is suspended", client_ip, user["id"])
        try:
            execute("""
                INSERT INTO login_logs (user_id, username, name, role, ip_address, user_agent, status, event_detail, login_at)
                VALUES (?, ?, ?, ?, ?, ?, 'BLOCKED', 'Account suspended', ?)
            """, (user["id"], user["username"], user["name"], user["role_code"], client_ip, user_agent, now_str))
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="บัญชีนี้ถูกระงับสิทธิ์การใช้งาน (Account Suspended)")

    if not verify_password(password, user["password_hash"]):
        log_audit(clean_username, "LOGIN_FAILED", "AUTH", str(user["id"]), None, "Invalid password", client_ip, user["id"])
        try:
            execute("""
                INSERT INTO login_logs (user_id, username, name, role, ip_address, user_agent, status, event_detail, login_at)
                VALUES (?, ?, ?, ?, ?, ?, 'FAILED', 'Incorrect password', ?)
            """, (user["id"], user["username"], user["name"], user["role_code"], client_ip, user_agent, now_str))
        except Exception:
            pass
        return None

    # Success: Record login log and update last_login_at
    log_id = None
    try:
        execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_str, user["id"]))
        log_id = execute("""
            INSERT INTO login_logs (user_id, username, name, role, ip_address, user_agent, status, event_detail, login_at)
            VALUES (?, ?, ?, ?, ?, ?, 'SUCCESS', 'Interactive Login', ?)
        """, (user["id"], user["username"], user["name"], user["role_code"], client_ip, user_agent, now_str))
    except Exception as e:
        print(f"[AUTH] Error recording login log: {e}")

    log_audit(clean_username, "LOGIN_SUCCESS", "AUTH", str(user["id"]), None, f"Logged in as {user['role_code']}", client_ip, user["id"])
    trigger_sheets_sync_async(clean_username)

    user_info = {k: v for k, v in user.items() if k != "password_hash"}
    user_info["last_login_at"] = now_str
    user_info["login_log_id"] = log_id
    return _enrich_user_vehicles(user_info)


def logout_user(user_id: int, username: str, client_ip: str = None) -> Dict[str, Any]:
    """Record logout timestamp in login_logs and audit_logs"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        latest_open = query_one("""
            SELECT id FROM login_logs
            WHERE user_id = ? AND status = 'SUCCESS' AND logout_at IS NULL
            ORDER BY id DESC LIMIT 1;
        """, (user_id,))
        if latest_open:
            execute("UPDATE login_logs SET logout_at = ?, event_detail = 'Logged out normally' WHERE id = ?;", (now_str, latest_open["id"]))
    except Exception:
        pass
    log_audit(username, "LOGOUT", "AUTH", str(user_id), None, f"Logged out at {now_str}", client_ip, user_id)
    trigger_sheets_sync_async(username)
    return {"status": "ok", "logged_out_at": now_str}


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)) -> Dict[str, Any]:
    """Dependency: Extract and strictly verify current user from JWT token (fetches fresh role from DB!)"""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="กรุณาเข้าสู่ระบบก่อนใช้งาน (Authentication Required)")

    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="เซสชันหมดอายุหรือไม่ถูกต้อง กรุณาเข้าสู่ระบบใหม่")

    user_id = payload["sub"]
    # Always query fresh role & active status from DB so Admin role changes or suspensions take effect immediately!
    user = query_one("""
        SELECT u.id, u.username, u.role_id, r.code as role_code, r.name as role_name,
               u.name, u.email, u.phone, u.faculty, u.department, u.avatar_url, u.is_active,
               u.gender, u.age, u.birthdate, u.last_login_at, u.created_at
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.id = ?;
    """, (user_id,))

    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="บัญชีผู้ใช้งานถูกระงับหรือไม่พร้อมใช้งาน")

    return _enrich_user_vehicles(dict(user))


def get_current_user_or_default(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)) -> Dict[str, Any]:
    """Resolve an explicit user identity; never substitute a seeded demo account."""
    if credentials and credentials.credentials:
        return get_current_user(credentials)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="กรุณาเข้าสู่ระบบด้วยบัญชีที่ได้รับอนุญาต")


def require_roles(allowed_roles: List[str]):
    """Strict Role-Based Access Control dependency"""
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if current_user["role_code"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"ปฏิเสธการเข้าถึง: บทบาท {current_user['role_code']} ไม่มีสิทธิ์เข้าใช้งานส่วนนี้ (ต้องเป็น: {', '.join(allowed_roles)})"
            )
        return current_user
    return role_checker


def require_console_admin(current_user: Dict[str, Any] = Depends(require_roles(["ADMIN"]))):
    """Restrict the separate personnel console to users with the ADMIN role."""
    return current_user
