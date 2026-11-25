# -*- coding: utf-8 -*-
"""
Audit Log Service:
Records all administrative, security, and critical events in audit_logs
"""

from backend.core.database import execute, query_all

def log_audit(username: str, action: str, entity_type: str = None, entity_id: str = None,
              old_value: str = None, new_value: str = None, ip_address: str = None, user_id: int = None):
    try:
        execute("""
            INSERT INTO audit_logs (user_id, username, action, entity_type, entity_id, old_value, new_value, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (user_id, username, action, entity_type, str(entity_id) if entity_id else None, old_value, new_value, ip_address))
    except Exception as e:
        print(f"[AUDIT ERROR] {e}")

def get_recent_audit_logs(limit: int = 50):
    return query_all("""
        SELECT id, user_id, username, action, entity_type, entity_id, old_value, new_value, ip_address, created_at
        FROM audit_logs
        ORDER BY id DESC
        LIMIT ?;
    """, (limit,))

