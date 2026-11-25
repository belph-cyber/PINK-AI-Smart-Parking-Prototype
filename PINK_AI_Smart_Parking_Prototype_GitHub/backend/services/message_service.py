# -*- coding: utf-8 -*-
"""
Persistent 2-Way Chat & Notifications Service:
- Stores all conversations & messages permanently in SQLite Database
- Strict participant access control (403 Forbidden for unauthorized users)
- Read/Unread tracking, conversation search, and automatic plate-to-owner resolution
- Ready hook for future LINE Messaging API integration
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status
from backend.core.database import query_one, query_all, execute


def get_user_conversations(user_id: int, role_code: str, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get persistent conversations for the authenticated user or Security/Admin"""
    if role_code in ("SECURITY", "ADMIN"):
        sql = """
            SELECT c.*, u.username as customer_code, u.name as customer_name,
                   u.phone as customer_phone, r.name as customer_role,
                   (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) as last_message,
                   (SELECT created_at FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) as last_message_time,
                   (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id AND is_read = 0 AND sender_role NOT IN ('SECURITY', 'ADMIN')) as unread_count
            FROM conversations c
            JOIN users u ON c.user_id = u.id
            JOIN roles r ON u.role_id = r.id
            WHERE 1=1
        """
        params = []
        if search and search.strip():
            s = f"%{search.strip()}%"
            sql += " AND (u.name LIKE ? OR u.username LIKE ? OR COALESCE(c.related_plate, '') LIKE ? OR COALESCE(c.subject, '') LIKE ?)"
            params.extend([s, s, s, s])
        sql += " ORDER BY c.updated_at DESC, c.id DESC;"
        return query_all(sql, tuple(params))

    # Student / Teacher: strictly own conversations only!
    sql = """
        SELECT c.*, COALESCE(sec.name, 'ศูนย์ควบคุม รปภ.') as security_name,
               u.name as customer_name, r.name as customer_role,
               (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) as last_message,
               (SELECT created_at FROM messages WHERE conversation_id = c.id ORDER BY id DESC LIMIT 1) as last_message_time,
               (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id AND is_read = 0 AND sender_role IN ('SECURITY', 'ADMIN')) as unread_count
        FROM conversations c
        JOIN users u ON c.user_id = u.id
        JOIN roles r ON u.role_id = r.id
        LEFT JOIN users sec ON c.security_user_id = sec.id
        WHERE c.user_id = ?
    """
    params = [user_id]
    if search and search.strip():
        s = f"%{search.strip()}%"
        sql += " AND (COALESCE(c.subject, '') LIKE ? OR COALESCE(c.related_plate, '') LIKE ?)"
        params.extend([s, s])
    sql += " ORDER BY c.updated_at DESC, c.id DESC;"
    return query_all(sql, tuple(params))


def get_conversation_messages(conversation_id: int, user_id: int, role_code: str) -> Dict[str, Any]:
    """Get all messages in a conversation (enforces strict participant access control)"""
    conv = query_one("""
        SELECT c.*, u.name as customer_name, u.username as customer_code, r.name as customer_role
        FROM conversations c
        JOIN users u ON c.user_id = u.id
        JOIN roles r ON u.role_id = r.id
        WHERE c.id = ?;
    """, (conversation_id,))
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบบทสนทนาที่ระบุ")

    if role_code not in ("SECURITY", "ADMIN") and conv["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ปฏิเสธการเข้าถึง: คุณไม่มีสิทธิ์อ่านบทสนทนาของผู้ใช้งานท่านอื่น"
        )

    # Mark incoming messages as read
    if role_code in ("SECURITY", "ADMIN"):
        execute(
            "UPDATE messages SET is_read = 1 WHERE conversation_id = ? AND sender_role NOT IN ('SECURITY', 'ADMIN');",
            (conversation_id,)
        )
    else:
        execute(
            "UPDATE messages SET is_read = 1 WHERE conversation_id = ? AND sender_role IN ('SECURITY', 'ADMIN');",
            (conversation_id,)
        )

    msgs = query_all("""
        SELECT m.*, u.name as sender_name, u.username as sender_code, r.name as sender_role_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        JOIN roles r ON u.role_id = r.id
        WHERE m.conversation_id = ?
        ORDER BY m.id ASC;
    """, (conversation_id,))
    return {"conversation": conv, "messages": msgs}


def send_message(conversation_id: int, sender_id: int, sender_role: str, content: str) -> Dict[str, Any]:
    """Append a persistent message to an existing conversation in SQLite"""
    text = (content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="ข้อความต้องไม่ว่างเปล่า")

    conv = query_one("SELECT * FROM conversations WHERE id = ?;", (conversation_id,))
    if not conv:
        raise HTTPException(status_code=404, detail="ไม่พบบทสนทนา")

    if sender_role not in ("SECURITY", "ADMIN") and conv["user_id"] != sender_id:
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์ส่งข้อความในบทสนทนานี้")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_id = execute("""
        INSERT INTO messages (conversation_id, sender_id, sender_role, content, is_read, created_at)
        VALUES (?, ?, ?, ?, 0, ?);
    """, (conversation_id, sender_id, sender_role, text, now_str))

    if sender_role in ("SECURITY", "ADMIN"):
        execute("UPDATE conversations SET security_user_id = ?, updated_at = ? WHERE id = ?;", (sender_id, now_str, conversation_id))
        execute("""
            INSERT INTO notifications (user_id, target_role, category, title, message, related_plate, is_read, created_at)
            VALUES (?, NULL, 'SECURITY_CHAT', 'ข้อความใหม่จากเจ้าหน้าที่ รปภ.', ?, ?, 0, ?);
        """, (conv["user_id"], text, conv.get("related_plate"), now_str))
    else:
        execute("UPDATE conversations SET updated_at = ? WHERE id = ?;", (now_str, conversation_id))
        execute("""
            INSERT INTO notifications (user_id, target_role, category, title, message, related_plate, is_read, created_at)
            VALUES (NULL, 'SECURITY', 'USER_HELP', ?, ?, ?, 0, ?);
        """, (f"ข้อความจากผู้ใช้งาน ({conv.get('related_plate') or 'ติดต่อ รปภ.'})", text, conv.get("related_plate"), now_str))

    return {"success": True, "message_id": msg_id, "conversation_id": conversation_id, "created_at": now_str}


def create_conversation(user_id: Optional[int], subject: str, related_plate: Optional[str],
                        initial_message: str, sender_id: int, sender_role: str) -> Dict[str, Any]:
    """Create or continue a persistent conversation between Security and Student/Teacher"""
    text = (initial_message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="กรุณาระบุข้อความ")

    target_user_id = user_id
    resolved_plate = (related_plate or "").strip() or None

    if sender_role in ("STUDENT", "TEACHER"):
        target_user_id = sender_id
    else:
        # Security / Admin sending by user_id or license plate
        if not target_user_id and resolved_plate:
            clean_p = resolved_plate.replace(" ", "").strip()
            owner = query_one("""
                SELECT u.id, v.plate_display
                FROM vehicles v
                JOIN user_vehicles uv ON v.id = uv.vehicle_id
                JOIN users u ON uv.user_id = u.id
                WHERE v.plate_clean LIKE ? OR v.plate_display LIKE ?
                ORDER BY uv.is_primary DESC LIMIT 1;
            """, (f"%{clean_p}%", f"%{resolved_plate}%"))
            if not owner:
                raise HTTPException(
                    status_code=404,
                    detail=f"ไม่พบเจ้าของรถทะเบียน '{resolved_plate}' ในระบบฐานข้อมูล กรุณาตรวจสอบทะเบียนอีกครั้ง"
                )
            target_user_id = owner["id"]
            resolved_plate = owner["plate_display"]

        if not target_user_id:
            raise HTTPException(status_code=400, detail="กรุณาเลือกผู้รับหรือระบุทะเบียนรถที่ลงทะเบียนในระบบ")

    # Check if an OPEN conversation already exists for this user_id so thread history stays unified
    existing = query_one("""
        SELECT id FROM conversations
        WHERE user_id = ? AND status = 'OPEN'
        ORDER BY updated_at DESC LIMIT 1;
    """, (target_user_id,))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if existing:
        conv_id = existing["id"]
        if resolved_plate:
            execute("UPDATE conversations SET related_plate = ?, updated_at = ? WHERE id = ?;", (resolved_plate, now_str, conv_id))
    else:
        sec_id = sender_id if sender_role in ("SECURITY", "ADMIN") else None
        conv_id = execute("""
            INSERT INTO conversations (user_id, security_user_id, subject, related_plate, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'OPEN', ?, ?);
        """, (target_user_id, sec_id, subject or "ติดต่อเจ้าหน้าที่รักษาความปลอดภัย", resolved_plate, now_str, now_str))

    msg_res = send_message(conv_id, sender_id, sender_role, text)
    return {"success": True, "conversation_id": conv_id, "message_id": msg_res["message_id"], "created_at": now_str}


def get_user_notifications(user_id: int, role_code: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Retrieve persistent notifications strictly scoped to this user or their role"""
    if role_code in ("SECURITY", "ADMIN"):
        return query_all("""
            SELECT * FROM notifications
            WHERE user_id = ? OR target_role IN ('SECURITY', 'ALL')
            ORDER BY id DESC LIMIT ?;
        """, (user_id, limit))

    return query_all("""
        SELECT * FROM notifications
        WHERE user_id = ? OR (user_id IS NULL AND target_role = ?)
        ORDER BY id DESC LIMIT ?;
    """, (user_id, role_code, limit))


def mark_notification_read(notification_id: int, user_id: int) -> bool:
    execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND (user_id = ? OR user_id IS NULL);", (notification_id, user_id))
    return True
