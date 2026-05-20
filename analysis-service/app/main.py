from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.ecowatch_common import (
    DEFAULT_PDK_LIMITS,
    AlertSeverity,
    ForecastPoint,
    ParameterType,
    Role,
    SensorReading,
    Settings,
    build_audit_event,
    check_pdk,
    forecast_next_value,
    has_permission,
    mape,
    parameter_medium,
)

settings = Settings(service_name="analysis-service", service_port=8503)
app = FastAPI(title="EcoWatch Analysis Service", version="1.0.0")

reading_store: dict[tuple[ParameterType, str], list[SensorReading]] = defaultdict(list)
exceedances: list[dict[str, Any]] = []
forecast_log: list[ForecastPoint] = []
predicted_samples: list[float] = [31.0, 36.0, 42.0, 39.5]
actual_samples: list[float] = [34.0, 35.5, 44.0, 41.0]
audit_log: list[dict[str, Any]] = []


class AnalysisCheckRequest(BaseModel):
    reading: SensorReading
    region: str
    actor_id: str
    actor_role: Role


class ForecastRequest(BaseModel):
    parameter: ParameterType
    region: str
    horizon_minutes: int = Field(default=60, ge=5, le=1440)
    actor_id: str
    actor_role: Role


class SpreadModelRequest(BaseModel):
    parameter: ParameterType
    region: str
    wind_direction_deg: float = Field(default=45, ge=0, le=360)
    wind_speed_mps: float = Field(default=3.0, ge=0)


AnalysisCheckRequest.model_rebuild()
ForecastRequest.model_rebuild()
SpreadModelRequest.model_rebuild()


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any] | None = None) -> None:
    audit_log.append(
        build_audit_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            object_type="analysis",
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


def _key(parameter: ParameterType, region: str) -> tuple[ParameterType, str]:
    return (parameter, region)


def _values(parameter: ParameterType, region: str) -> list[float]:
    return [item.value for item in reading_store[_key(parameter, region)]]


def _calc_forecast(parameter: ParameterType, region: str, horizon_minutes: int) -> ForecastPoint:
    values = _values(parameter, region)
    predicted = forecast_next_value(values)
    forecast = ForecastPoint(
        parameter=parameter,
        region=region,
        forecast_at=datetime.now(UTC) + timedelta(minutes=horizon_minutes),
        predicted_value=predicted,
        predicted_mape=mape(predicted_samples, actual_samples),
    )
    forecast_log.append(forecast)
    return forecast


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/analysis/check-pdk")
async def check_threshold(request: AnalysisCheckRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "analysis:run")
    reading_store[_key(request.reading.parameter, request.region)].append(request.reading)

    values = _values(request.reading.parameter, request.region)
    if len(values) > 1:
        predicted_samples.append(forecast_next_value(values[:-1]))
        actual_samples.append(values[-1])

    event = check_pdk(request.region, request.reading, alert_id=str(uuid4()))
    if event is not None:
        event_payload = event.model_dump(mode="json")
        exceedances.append(event_payload)
    else:
        event_payload = None

    forecast = _calc_forecast(request.reading.parameter, request.region, horizon_minutes=60)
    _audit(
        request.actor_id,
        request.actor_role,
        "analysis.check_pdk",
        request.reading.reading_id,
        {
            "parameter": request.reading.parameter.value,
            "region": request.region,
            "has_alert": bool(event_payload),
        },
    )

    return {
        "alert": event_payload,
        "forecast": forecast.model_dump(mode="json"),
        "samples": len(values),
    }


@app.post("/analysis/forecast")
async def forecast(request: ForecastRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "analysis:run")
    forecast_point = _calc_forecast(request.parameter, request.region, request.horizon_minutes)
    _audit(
        request.actor_id,
        request.actor_role,
        "analysis.forecast",
        request.parameter.value,
        {"region": request.region, "horizon_minutes": request.horizon_minutes},
    )
    return forecast_point.model_dump(mode="json")


@app.get("/analysis/exceedances")
async def list_exceedances(
    parameter: ParameterType | None = None,
    region: str | None = None,
    severity: AlertSeverity | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    items = exceedances
    if parameter:
        items = [item for item in items if item["parameter"] == parameter.value]
    if region:
        items = [item for item in items if item["region"] == region]
    if severity:
        items = [item for item in items if item["severity"] == severity.value]
    ordered = sorted(items, key=lambda row: row["created_at"], reverse=True)[: max(1, min(limit, 2000))]
    return {"items": ordered, "count": len(ordered)}


@app.get("/analysis/forecasts")
async def list_forecasts(
    parameter: ParameterType | None = None,
    region: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    items = forecast_log
    if parameter:
        items = [item for item in items if item.parameter == parameter]
    if region:
        items = [item for item in items if item.region == region]
    ordered = sorted(items, key=lambda item: item.forecast_at, reverse=True)[: max(1, min(limit, 2000))]
    return {"items": [item.model_dump(mode="json") for item in ordered], "count": len(ordered)}


@app.get("/analysis/source-detection")
async def source_detection(parameter: ParameterType, region: str) -> dict[str, Any]:
    records = reading_store[_key(parameter, region)]
    if not records:
        raise HTTPException(status_code=404, detail="No records for the selected parameter and region")

    by_source: dict[str, list[float]] = defaultdict(list)
    for reading in records:
        by_source[reading.source.value].append(reading.value)

    probable = []
    for source, values in by_source.items():
        avg = sum(values) / len(values)
        limit, _ = DEFAULT_PDK_LIMITS[parameter]
        risk = round((avg / max(limit, 0.0001)) * 100, 2)
        probable.append({"source": source, "average_value": round(avg, 3), "risk_index": risk})

    probable.sort(key=lambda item: item["risk_index"], reverse=True)
    return {
        "parameter": parameter.value,
        "region": region,
        "medium": parameter_medium(parameter),
        "probable_sources": probable,
    }


@app.post("/analysis/spread-model")
async def spread_model(request: SpreadModelRequest) -> dict[str, Any]:
    records = reading_store[_key(request.parameter, request.region)]
    if not records:
        raise HTTPException(status_code=404, detail="No records for spread model")

    origin = sorted(records, key=lambda item: item.measured_at)[-1]
    base = max(origin.value, 0.01)
    plume = []
    for idx in range(1, 6):
        attenuation = round(base / (1 + idx * 0.7), 3)
        drift = idx * request.wind_speed_mps * 0.001
        plume.append(
            {
                "step": idx,
                "latitude": round(origin.latitude + drift, 6),
                "longitude": round(origin.longitude + drift, 6),
                "predicted_value": attenuation,
            }
        )

    return {
        "parameter": request.parameter.value,
        "region": request.region,
        "origin_reading_id": origin.reading_id,
        "wind_direction_deg": request.wind_direction_deg,
        "wind_speed_mps": request.wind_speed_mps,
        "plume": plume,
    }


@app.get("/analysis/pdk")
async def pdk_catalog() -> dict[str, Any]:
    items = []
    for parameter, (limit, unit) in DEFAULT_PDK_LIMITS.items():
        items.append({"parameter": parameter.value, "limit_value": limit, "unit": unit})
    return {"items": items, "count": len(items)}


@app.get("/analysis/kpi")
async def kpi() -> dict[str, Any]:
    mape_value = mape(predicted_samples, actual_samples)
    return {
        "data_refresh_target_minutes": settings.ingestion_refresh_target_minutes,
        "forecast_mape": mape_value,
        "forecast_mape_target": settings.forecast_mape_target,
        "forecast_target_met": mape_value <= settings.forecast_mape_target,
        "supported_sensor_target": settings.sensor_capacity_target,
        "readings_processed": sum(len(items) for items in reading_store.values()),
        "alerts_generated": len(exceedances),
    }


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    if not has_permission(actor_role, "audit:read"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"items": audit_log[-limit:]}
