from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.ecowatch_common import AlertSeverity, NotificationChannel, Role, Settings, build_audit_event, has_permission

settings = Settings(service_name="notification-service", service_port=8507)
app = FastAPI(title="EcoWatch Notification Service", version="1.0.0")

messages: list[dict[str, Any]] = []
audit_log: list[dict[str, Any]] = []


class NotificationSendRequest(BaseModel):
    channel: NotificationChannel
    recipient: str
    subject: str
    body: str
    severity: AlertSeverity = AlertSeverity.INFO
    actor_role: Role


class NotificationBulkRequest(BaseModel):
    messages: list[dict[str, Any]]
    actor_role: Role


NotificationSendRequest.model_rebuild()
NotificationBulkRequest.model_rebuild()


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_role: Role, action: str, object_id: str, details: dict[str, Any] | None = None) -> None:
    audit_log.append(
        build_audit_event(
            actor_id=f"notify-{actor_role.value}",
            actor_role=actor_role,
            action=action,
            object_type="notification",
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/notifications/send")
async def send_notification(request: NotificationSendRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "notification:send")
    payload = {
        "message_id": str(uuid4()),
        "channel": request.channel.value,
        "recipient": request.recipient,
        "subject": request.subject,
        "body": request.body,
        "severity": request.severity.value,
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
    }
    messages.append(payload)
    _audit(request.actor_role, "notification.send", payload["message_id"], {"channel": payload["channel"]})
    return payload


@app.post("/notifications/bulk")
async def send_bulk(request: NotificationBulkRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "notification:send")
    accepted = []
    for item in request.messages:
        payload = {
            "message_id": item.get("message_id", str(uuid4())),
            "channel": str(item.get("channel", NotificationChannel.PUSH.value)),
            "recipient": str(item.get("recipient", "unknown")),
            "subject": str(item.get("subject", "EcoWatch alert")),
            "body": str(item.get("body", "No details")),
            "severity": str(item.get("severity", AlertSeverity.INFO.value)),
            "status": "queued",
            "created_at": datetime.now(UTC).isoformat(),
        }
        messages.append(payload)
        accepted.append(payload)

    _audit(request.actor_role, "notification.bulk", str(uuid4()), {"count": len(accepted)})
    return {"accepted": len(accepted), "items": accepted}


@app.post("/notifications/voice")
async def send_voice_alert(recipient: str, text: str, actor_role: Role = Role.OPERATOR) -> dict[str, Any]:
    _assert_permission(actor_role, "notification:send")
    payload = {
        "message_id": str(uuid4()),
        "channel": NotificationChannel.VOICE.value,
        "recipient": recipient,
        "subject": "EcoWatch Voice Alert",
        "body": text,
        "severity": AlertSeverity.WARNING.value,
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
    }
    messages.append(payload)
    _audit(actor_role, "notification.voice", payload["message_id"])
    return payload


@app.get("/notifications/history")
async def history(channel: NotificationChannel | None = None, limit: int = 200) -> dict[str, Any]:
    items = messages
    if channel:
        items = [item for item in items if item["channel"] == channel.value]
    ordered = sorted(items, key=lambda row: row["created_at"], reverse=True)[: max(1, min(limit, 1000))]
    return {"items": ordered, "count": len(ordered)}


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    if not has_permission(actor_role, "audit:read"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"items": audit_log[-limit:]}
