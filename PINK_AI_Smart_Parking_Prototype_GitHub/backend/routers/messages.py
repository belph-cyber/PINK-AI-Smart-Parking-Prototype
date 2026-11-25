# -*- coding: utf-8 -*-
"""
Persistent 2-Way Chat & Notifications Router (Strict JWT Auth)
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from backend.services.auth_service import get_current_user
from backend.services.message_service import (
    get_user_conversations, get_conversation_messages, send_message, create_conversation,
    get_user_notifications, mark_notification_read
)
from backend.models.schemas import MessageSendRequest, ConversationCreateRequest

router = APIRouter(prefix="/api/messages", tags=["Messaging & Notifications"])


@router.get("/conversations")
def list_conversations(search: Optional[str] = Query(None),
                       current_user: dict = Depends(get_current_user)):
    convs = get_user_conversations(current_user["id"], current_user["role_code"], search=search)
    return {"status": "ok", "conversations": convs}


@router.get("/conversation/{conv_id}")
def conversation_messages(conv_id: int, current_user: dict = Depends(get_current_user)):
    data = get_conversation_messages(conv_id, current_user["id"], current_user["role_code"])
    return {"status": "ok", "conversation": data["conversation"], "messages": data["messages"]}


@router.post("/send")
def post_message(req: MessageSendRequest, current_user: dict = Depends(get_current_user)):
    res = send_message(req.conversation_id, current_user["id"], current_user["role_code"], req.content)
    return {"status": "ok", "result": res}


@router.post("/create")
def new_conversation(req: ConversationCreateRequest, current_user: dict = Depends(get_current_user)):
    res = create_conversation(
        user_id=req.user_id,
        subject=req.subject,
        related_plate=req.related_plate,
        initial_message=req.initial_message,
        sender_id=current_user["id"],
        sender_role=current_user["role_code"]
    )
    return {"status": "ok", "result": res}


@router.get("/notifications")
def list_notifications(current_user: dict = Depends(get_current_user)):
    notifs = get_user_notifications(current_user["id"], current_user["role_code"])
    return {"status": "ok", "notifications": notifs}


@router.put("/notifications/{notif_id}/read")
def read_notification(notif_id: int, current_user: dict = Depends(get_current_user)):
    mark_notification_read(notif_id, current_user["id"])
    return {"status": "ok"}
