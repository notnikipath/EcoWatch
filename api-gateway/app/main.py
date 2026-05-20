from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.ecowatch_common import (
    AlertSeverity,
    DataSource,
    NotificationChannel,
    ParameterType,
    Role,
    SensorReadingIn,
    Settings,
    sign_token,
    verify_token,
)


class GatewaySettings(BaseSettings):
    service_name: str = "api-gateway"
    service_port: int = 8500

    ingestion_service_url: str = "http://ingestion-service:8501"
    map_service_url: str = "http://map-service:8502"
    analysis_service_url: str = "http://analysis-service:8503"
    alert_service_url: str = "http://alert-service:8504"
    report_service_url: str = "http://report-service:8505"
    user_service_url: str = "http://user-service:8506"
    notification_service_url: str = "http://notification-service:8507"

    jwt_secret: str = Settings().jwt_secret
    token_exp_minutes: int = 240

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = GatewaySettings()
app = FastAPI(title="EcoWatch API Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5178",
        "http://127.0.0.1:5178",
        "http://localhost:5177",
        "http://127.0.0.1:5177",
        "http://localhost:31034",
        "http://127.0.0.1:31034",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    user_id: str
    role: Role
    language: str = Field(default="ru", pattern="^(ru|en)$")


class ProcessReadingRequest(BaseModel):
    reading: SensorReadingIn
    actor_id: str
    actor_role: Role


class OpenSourceWorkflowRequest(BaseModel):
    source: DataSource
    region: str
    actor_id: str
    actor_role: Role


class SubscriptionWorkflowRequest(BaseModel):
    user_id: str
    parameter: ParameterType
    region: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=5, gt=0)
    channels: list[NotificationChannel] = Field(default_factory=lambda: [NotificationChannel.PUSH])
    min_severity: AlertSeverity = AlertSeverity.WARNING
    actor_id: str
    actor_role: Role


AuthRequest.model_rebuild()
ProcessReadingRequest.model_rebuild()
OpenSourceWorkflowRequest.model_rebuild()
SubscriptionWorkflowRequest.model_rebuild()


async def _post_json(client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(url, json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = await client.get(url, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


def _service_urls() -> dict[str, str]:
    return {
        "ingestion": settings.ingestion_service_url,
        "map": settings.map_service_url,
        "analysis": settings.analysis_service_url,
        "alert": settings.alert_service_url,
        "report": settings.report_service_url,
        "user": settings.user_service_url,
        "notification": settings.notification_service_url,
    }


async def _process_ingested_payload(
    client: httpx.AsyncClient,
    reading_payload: dict[str, Any],
    region: str,
    actor_id: str,
    actor_role: Role,
) -> dict[str, Any]:
    analysis_result = await _post_json(
        client,
        f"{settings.analysis_service_url}/analysis/check-pdk",
        {
            "reading": reading_payload,
            "region": region,
            "actor_id": actor_id,
            "actor_role": actor_role.value,
        },
    )

    await _post_json(
        client,
        f"{settings.map_service_url}/map/ingest",
        {
            "reading": reading_payload,
            "region": region,
            "actor_id": actor_id,
            "actor_role": actor_role.value,
        },
    )

    await _post_json(
        client,
        f"{settings.report_service_url}/reports/ingest-reading",
        {
            "reading": reading_payload,
            "region": region,
            "actor_id": actor_id,
            "actor_role": actor_role.value,
        },
    )

    alert_dispatch = None
    notification_result = None
    if analysis_result.get("alert") is not None:
        alert_dispatch = await _post_json(
            client,
            f"{settings.alert_service_url}/alerts/notify-nearby",
            {
                "alert": analysis_result["alert"],
                "actor_id": actor_id,
                "actor_role": actor_role.value,
            },
        )

        notifications = alert_dispatch.get("notifications", [])
        if notifications:
            notification_result = await _post_json(
                client,
                f"{settings.notification_service_url}/notifications/bulk",
                {
                    "messages": notifications,
                    "actor_role": actor_role.value,
                },
            )

        await _post_json(
            client,
            f"{settings.report_service_url}/reports/ingest-alert",
            {
                "alert": analysis_result["alert"],
                "actor_id": actor_id,
                "actor_role": actor_role.value,
            },
        )

    return {
        "analysis": analysis_result,
        "alert_dispatch": alert_dispatch,
        "notifications": notification_result,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/auth/token")
async def issue_token(request: AuthRequest) -> dict[str, str]:
    token = sign_token(
        {"sub": request.user_id, "role": request.role.value, "language": request.language},
        settings.jwt_secret,
        exp_minutes=settings.token_exp_minutes,
    )
    return {"access_token": token, "token_type": "Bearer"}


@app.post("/auth/verify")
async def verify_auth(token: str) -> dict[str, Any]:
    payload = verify_token(token, settings.jwt_secret)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@app.get("/services/health")
async def service_health() -> dict[str, Any]:
    statuses: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, base_url in _service_urls().items():
            try:
                statuses[name] = await _get_json(client, f"{base_url}/health")
            except HTTPException as exc:
                statuses[name] = {"status": "error", "detail": exc.detail}
            except httpx.HTTPError as exc:
                statuses[name] = {"status": "error", "detail": str(exc)}
    return statuses


@app.post("/workflow/process-reading")
async def process_reading(request: ProcessReadingRequest) -> dict[str, Any]:
    ingestion_route = "/ingestion/mobile" if request.reading.source == DataSource.MOBILE else "/ingestion/stationary"
    ingestion_payload = {
        "reading": request.reading.model_dump(mode="json"),
        "actor_id": request.actor_id,
        "actor_role": request.actor_role.value,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        ingested = await _post_json(client, f"{settings.ingestion_service_url}{ingestion_route}", ingestion_payload)
        region = ingested.get("region", "Unknown")
        pipeline = await _process_ingested_payload(
            client,
            reading_payload=ingested["reading"],
            region=region,
            actor_id=request.actor_id,
            actor_role=request.actor_role,
        )

    return {
        "ingested": ingested,
        "analysis": pipeline["analysis"],
        "alerts": pipeline["alert_dispatch"],
        "notifications": pipeline["notifications"],
    }


@app.post("/workflow/pull-open-source")
async def pull_open_source(request: OpenSourceWorkflowRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=35.0) as client:
        pulled = await _post_json(
            client,
            f"{settings.ingestion_service_url}/ingestion/open-source/pull",
            {
                "source": request.source.value,
                "region": request.region,
                "actor_id": request.actor_id,
                "actor_role": request.actor_role.value,
            },
        )

        processed = []
        for item in pulled.get("items", []):
            result = await _process_ingested_payload(
                client,
                reading_payload=item,
                region=request.region,
                actor_id=request.actor_id,
                actor_role=request.actor_role,
            )
            processed.append({"reading_id": item["reading_id"], **result})

    return {
        "source": request.source.value,
        "region": request.region,
        "pulled_count": pulled.get("count", 0),
        "processed": processed,
    }


@app.post("/workflow/subscribe-alert")
async def subscribe_alert(request: SubscriptionWorkflowRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        user = await _get_json(client, f"{settings.user_service_url}/users/{request.user_id}")
        user_subscription = await _post_json(
            client,
            f"{settings.user_service_url}/users/{request.user_id}/subscriptions",
            {
                "parameter": request.parameter.value,
                "region": request.region,
                "latitude": request.latitude,
                "longitude": request.longitude,
                "radius_km": request.radius_km,
                "channels": [channel.value for channel in request.channels],
                "min_severity": request.min_severity.value,
                "actor_role": request.actor_role.value,
            },
        )

        alert_subscription = await _post_json(
            client,
            f"{settings.alert_service_url}/subscriptions",
            {
                "user_id": request.user_id,
                "parameter": request.parameter.value,
                "region": request.region,
                "latitude": request.latitude,
                "longitude": request.longitude,
                "radius_km": request.radius_km,
                "channels": [channel.value for channel in request.channels],
                "min_severity": request.min_severity.value,
                "actor_id": request.actor_id,
                "actor_role": request.actor_role.value,
            },
        )

        await _post_json(
            client,
            f"{settings.alert_service_url}/subscriptions/sync-contact",
            {
                "user_id": request.user_id,
                "recipient": user.get("email", request.user_id),
                "channels": [channel.value for channel in request.channels],
            },
        )

    return {
        "user": user,
        "user_subscription": user_subscription,
        "alert_subscription": alert_subscription,
    }


@app.get("/dashboard/overview")
async def dashboard_overview(parameter: str = "pm25", region: str = "Moscow") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        services = await _get_json(client, f"{settings.ingestion_service_url}/health")
        ingestion_agg = await _get_json(client, f"{settings.ingestion_service_url}/aggregates/realtime")
        map_heatmap = await _get_json(
            client,
            f"{settings.map_service_url}/map/heatmap",
            params={"parameter": parameter, "region": region},
        )
        trends = await _get_json(
            client,
            f"{settings.map_service_url}/map/trends",
            params={"parameter": parameter, "region": region, "window_minutes": 240},
        )
        analysis_kpi = await _get_json(client, f"{settings.analysis_service_url}/analysis/kpi")
        exceedances = await _get_json(
            client,
            f"{settings.analysis_service_url}/analysis/exceedances",
            params={"parameter": parameter, "region": region, "limit": 20},
        )
        alerts = await _get_json(client, f"{settings.alert_service_url}/alerts", params={"limit": 20})
        notifications = await _get_json(
            client,
            f"{settings.notification_service_url}/notifications/history",
            params={"limit": 20},
        )
        report_daily = await _get_json(
            client,
            f"{settings.report_service_url}/reports/daily",
            params={"region": region},
        )

    return {
        "gateway": {"status": "ok"},
        "services": {"ingestion": services},
        "realtime": ingestion_agg,
        "map": {
            "heatmap": map_heatmap,
            "trend": trends,
        },
        "analysis": {
            "kpi": analysis_kpi,
            "exceedances": exceedances,
        },
        "alerts": alerts,
        "notifications": notifications,
        "report": report_daily,
    }


@app.get("/dashboard/map")
async def dashboard_map(parameter: str = "pm25", region: str = "Moscow") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        points = await _get_json(
            client,
            f"{settings.map_service_url}/map/points",
            params={"parameter": parameter, "region": region, "limit": 500},
        )
        heatmap = await _get_json(
            client,
            f"{settings.map_service_url}/map/heatmap",
            params={"parameter": parameter, "region": region},
        )
    return {"points": points, "heatmap": heatmap}


@app.get("/users/cabinet/{user_id}")
async def user_cabinet(user_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        return await _get_json(client, f"{settings.user_service_url}/cabinet/{user_id}")
