from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.ecowatch_common import (
    AlertSeverity,
    AlertSubscription,
    ExceedanceEvent,
    GeoPoint,
    NotificationChannel,
    ParameterType,
    Role,
    Settings,
    build_audit_event,
    has_permission,
    haversine_km,
    severity_rank,
)

settings = Settings(service_name="alert-service", service_port=8504)
app = FastAPI(title="EcoWatch Alert Service", version="1.0.0")

subscriptions: dict[str, AlertSubscription] = {}
user_contacts: dict[str, dict[str, Any]] = {
    "USER-001": {"recipient": "activist1@ecowatch.local", "channels": [NotificationChannel.EMAIL.value]},
    "USER-002": {
        "recipient": "+79990001122",
        "channels": [NotificationChannel.SMS.value, NotificationChannel.VOICE.value],
    },
}
alerts: list[dict[str, Any]] = []
audit_log: list[dict[str, Any]] = []


class SubscriptionCreateRequest(BaseModel):
    user_id: str
    parameter: ParameterType
    region: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=5, gt=0)
    channels: list[NotificationChannel] = Field(default_factory=list)
    min_severity: AlertSeverity = AlertSeverity.WARNING
    actor_id: str
    actor_role: Role


class ContactSyncRequest(BaseModel):
    user_id: str
    recipient: str
    channels: list[NotificationChannel]


class AlertDispatchRequest(BaseModel):
    alert: ExceedanceEvent
    actor_id: str
    actor_role: Role


SubscriptionCreateRequest.model_rebuild()
ContactSyncRequest.model_rebuild()
AlertDispatchRequest.model_rebuild()


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any] | None = None) -> None:
    audit_log.append(
        build_audit_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            object_type="alert",
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


def _matches_subscription(subscription: AlertSubscription, event: ExceedanceEvent) -> bool:
    if subscription.parameter != event.parameter:
        return False
    if subscription.region != event.region:
        return False
    if severity_rank(event.severity) < severity_rank(subscription.min_severity):
        return False

    if subscription.center is None:
        return True

    distance = haversine_km(
        subscription.center.latitude,
        subscription.center.longitude,
        event.location.latitude,
        event.location.longitude,
    )
    return distance <= subscription.radius_km


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/subscriptions")
async def create_subscription(request: SubscriptionCreateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "alerts:subscribe")
    subscription = AlertSubscription(
        subscription_id=str(uuid4()),
        user_id=request.user_id,
        parameter=request.parameter,
        region=request.region,
        center=(
            GeoPoint(latitude=request.latitude, longitude=request.longitude)
            if request.latitude is not None and request.longitude is not None
            else None
        ),
        radius_km=request.radius_km,
        channels=request.channels,
        min_severity=request.min_severity,
    )

    subscriptions[subscription.subscription_id] = subscription
    _audit(request.actor_id, request.actor_role, "alert.subscription.create", subscription.subscription_id)
    return subscription.model_dump(mode="json")


@app.get("/subscriptions")
async def list_subscriptions(user_id: str | None = None, region: str | None = None) -> dict[str, Any]:
    items = []
    for item in subscriptions.values():
        if user_id and item.user_id != user_id:
            continue
        if region and item.region != region:
            continue
        items.append(item.model_dump(mode="json"))
    return {"items": items, "count": len(items)}


@app.post("/subscriptions/sync-contact")
async def sync_contact(request: ContactSyncRequest) -> dict[str, Any]:
    user_contacts[request.user_id] = {
        "recipient": request.recipient,
        "channels": [channel.value for channel in request.channels],
    }
    return {"status": "synced", "user_id": request.user_id}


@app.post("/alerts/notify-nearby")
async def notify_nearby(request: AlertDispatchRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "alerts:manage")
    event = request.alert

    matched = [item for item in subscriptions.values() if _matches_subscription(item, event)]
    payloads = []
    for subscription in matched:
        contact = user_contacts.get(
            subscription.user_id,
            {"recipient": subscription.user_id, "channels": [channel.value for channel in subscription.channels]},
        )
        channels = subscription.channels or [NotificationChannel.PUSH]
        for channel in channels:
            payloads.append(
                {
                    "message_id": str(uuid4()),
                    "channel": channel.value,
                    "recipient": contact["recipient"],
                    "subject": f"Eco alert: {event.parameter.value} in {event.region}",
                    "body": (
                        f"{event.parameter.value} is {event.value} {event.unit}. "
                        f"Limit is {event.limit_value} {event.unit}."
                    ),
                    "severity": event.severity.value,
                    "status": "pending",
                }
            )

    record = {
        "dispatch_id": str(uuid4()),
        "alert": event.model_dump(mode="json"),
        "subscriptions_matched": len(matched),
        "notifications": payloads,
        "created_at": datetime.now(UTC).isoformat(),
    }
    alerts.append(record)
    _audit(
        request.actor_id,
        request.actor_role,
        "alert.dispatch",
        record["dispatch_id"],
        {"matched": len(matched), "severity": event.severity.value},
    )
    return record


@app.get("/alerts")
async def alert_history(limit: int = 200, severity: AlertSeverity | None = None) -> dict[str, Any]:
    items = alerts
    if severity:
        items = [item for item in items if item["alert"]["severity"] == severity.value]
    ordered = sorted(items, key=lambda row: row["created_at"], reverse=True)[: max(1, min(limit, 1000))]
    return {"items": ordered, "count": len(ordered)}


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    if not has_permission(actor_role, "audit:read"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"items": audit_log[-limit:]}
