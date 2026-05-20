from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.ecowatch_common import (
    AlertSeverity,
    AlertSubscription,
    EcoUser,
    GeoPoint,
    NotificationChannel,
    ParameterType,
    Role,
    Settings,
    build_audit_event,
    has_permission,
    severity_rank,
)

settings = Settings(service_name="user-service", service_port=8506)
app = FastAPI(title="EcoWatch User Service", version="1.0.0")

users: dict[str, EcoUser] = {
    "USER-001": EcoUser(
        user_id="USER-001",
        display_name="Alina Smirnova",
        role=Role.ACTIVIST,
        email="activist1@ecowatch.local",
        home_region="Moscow",
    ),
    "USER-002": EcoUser(
        user_id="USER-002",
        display_name="Ilya Petrov",
        role=Role.RESEARCHER,
        email="researcher@ecowatch.local",
        home_region="Saint-Petersburg",
    ),
    "USER-ADM": EcoUser(
        user_id="USER-ADM",
        display_name="EcoWatch Admin",
        role=Role.ADMIN,
        email="admin@ecowatch.local",
        home_region="Moscow",
    ),
}
subscriptions: dict[str, AlertSubscription] = {}
audit_log: list[dict[str, Any]] = []


class UserCreateRequest(BaseModel):
    display_name: str
    role: Role
    email: str
    home_region: str
    actor_id: str
    actor_role: Role


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    home_region: str | None = None
    actor_id: str
    actor_role: Role


class SubscriptionCreateRequest(BaseModel):
    parameter: ParameterType
    region: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=5, gt=0)
    channels: list[NotificationChannel] = Field(default_factory=list)
    min_severity: AlertSeverity = AlertSeverity.WARNING
    actor_role: Role


UserCreateRequest.model_rebuild()
UserUpdateRequest.model_rebuild()
SubscriptionCreateRequest.model_rebuild()


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any] | None = None) -> None:
    audit_log.append(
        build_audit_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            object_type="user",
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/users")
async def list_users(role: Role | None = None, region: str | None = None) -> dict[str, Any]:
    items = []
    for user in users.values():
        if role and user.role != role:
            continue
        if region and user.home_region != region:
            continue
        items.append(user.model_dump(mode="json"))
    return {"items": items, "count": len(items)}


@app.get("/users/{user_id}")
async def get_user(user_id: str) -> dict[str, Any]:
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user.model_dump(mode="json")


@app.post("/users")
async def create_user(request: UserCreateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "profile:read")
    user = EcoUser(
        user_id=str(uuid4()),
        display_name=request.display_name,
        role=request.role,
        email=request.email,
        home_region=request.home_region,
    )
    users[user.user_id] = user
    _audit(request.actor_id, request.actor_role, "user.create", user.user_id)
    return user.model_dump(mode="json")


@app.patch("/users/{user_id}")
async def update_user(user_id: str, request: UserUpdateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "profile:read")
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if request.display_name is not None:
        user.display_name = request.display_name
    if request.email is not None:
        user.email = request.email
    if request.home_region is not None:
        user.home_region = request.home_region

    _audit(request.actor_id, request.actor_role, "user.update", user_id)
    return user.model_dump(mode="json")


@app.post("/users/{user_id}/subscriptions")
async def create_subscription(user_id: str, request: SubscriptionCreateRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "alerts:subscribe")
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")

    subscription = AlertSubscription(
        subscription_id=str(uuid4()),
        user_id=user_id,
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
    _audit(user_id, request.actor_role, "user.subscription.create", subscription.subscription_id)
    return subscription.model_dump(mode="json")


@app.get("/users/{user_id}/subscriptions")
async def user_subscriptions(user_id: str) -> dict[str, Any]:
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    items = [item.model_dump(mode="json") for item in subscriptions.values() if item.user_id == user_id]
    return {"items": items, "count": len(items)}


@app.get("/users/subscribers")
async def subscribers(
    parameter: ParameterType,
    region: str,
    min_severity: AlertSeverity = AlertSeverity.WARNING,
) -> dict[str, Any]:
    items = []
    for subscription in subscriptions.values():
        if subscription.parameter != parameter:
            continue
        if subscription.region != region:
            continue
        if severity_rank(min_severity) < severity_rank(subscription.min_severity):
            continue
        user = users.get(subscription.user_id)
        if user is None:
            continue
        items.append(
            {
                "user_id": user.user_id,
                "display_name": user.display_name,
                "email": user.email,
                "channels": [channel.value for channel in subscription.channels],
                "radius_km": subscription.radius_km,
                "center": subscription.center.model_dump(mode="json") if subscription.center else None,
            }
        )
    return {"items": items, "count": len(items)}


@app.get("/cabinet/{user_id}")
async def cabinet(user_id: str) -> dict[str, Any]:
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user_subs = [item for item in subscriptions.values() if item.user_id == user_id]
    return {
        "user": user.model_dump(mode="json"),
        "subscriptions": [item.model_dump(mode="json") for item in user_subs],
        "stats": {
            "active_subscriptions": len(user_subs),
            "member_since": user.created_at,
            "last_seen_at": datetime.now(UTC),
        },
    }


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    if not has_permission(actor_role, "audit:read"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"items": audit_log[-limit:]}
