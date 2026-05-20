from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from shared.ecowatch_common import (
    DataSource,
    GeoPoint,
    ParameterType,
    Role,
    SensorMetadata,
    SensorReading,
    SensorReadingIn,
    Settings,
    build_audit_event,
    build_realtime_aggregates,
    has_permission,
)

settings = Settings(service_name="ingestion-service", service_port=8501)
app = FastAPI(title="EcoWatch Ingestion Service", version="1.0.0")

sensors: dict[str, SensorMetadata] = {
    "AIR-MSK-001": SensorMetadata(
        sensor_id="AIR-MSK-001",
        name="Moscow Air Station #1",
        source=DataSource.STATIONARY,
        region="Moscow",
        location=GeoPoint(latitude=55.7558, longitude=37.6173),
        parameters=[ParameterType.PM25, ParameterType.PM10, ParameterType.CO2, ParameterType.NO2],
    ),
    "WATER-MSK-002": SensorMetadata(
        sensor_id="WATER-MSK-002",
        name="Yauza Water Point",
        source=DataSource.STATIONARY,
        region="Moscow",
        location=GeoPoint(latitude=55.7725, longitude=37.6508),
        parameters=[ParameterType.PH, ParameterType.TURBIDITY, ParameterType.DISSOLVED_OXYGEN],
    ),
    "NOISE-SPB-003": SensorMetadata(
        sensor_id="NOISE-SPB-003",
        name="Nevsky Noise Monitor",
        source=DataSource.STATIONARY,
        region="Saint-Petersburg",
        location=GeoPoint(latitude=59.9343, longitude=30.3351),
        parameters=[ParameterType.NOISE_DB, ParameterType.RADIATION],
    ),
    "MOBILE-DEMO-01": SensorMetadata(
        sensor_id="MOBILE-DEMO-01",
        name="Citizen Sensor App",
        source=DataSource.MOBILE,
        region="Moscow",
        location=GeoPoint(latitude=55.7633, longitude=37.5839),
        parameters=[
            ParameterType.PM25,
            ParameterType.NOISE_DB,
            ParameterType.TEMPERATURE_C,
            ParameterType.HUMIDITY_PCT,
        ],
        is_mobile=True,
    ),
}

readings: list[SensorReading] = []
queue_events: list[dict[str, Any]] = []
audit_log: list[dict[str, Any]] = []


class IngestRequest(BaseModel):
    reading: SensorReadingIn
    actor_id: str
    actor_role: Role


class OpenSourcePullRequest(BaseModel):
    source: DataSource
    region: str
    actor_id: str
    actor_role: Role


class SensorRegisterRequest(BaseModel):
    sensor_id: str
    name: str
    source: DataSource
    region: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    parameters: list[ParameterType]
    is_mobile: bool = False
    actor_id: str
    actor_role: Role


IngestRequest.model_rebuild()
OpenSourcePullRequest.model_rebuild()
SensorRegisterRequest.model_rebuild()


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(
    actor_id: str,
    actor_role: Role,
    action: str,
    object_type: str,
    object_id: str,
    details: dict | None = None,
) -> None:
    audit_log.append(
        build_audit_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


def _resolve_region(sensor_id: str, fallback: str = "Unknown") -> str:
    sensor = sensors.get(sensor_id)
    return sensor.region if sensor else fallback


def _register_reading(reading: SensorReadingIn, channel: str) -> SensorReading:
    if reading.sensor_id not in sensors:
        sensors[reading.sensor_id] = SensorMetadata(
            sensor_id=reading.sensor_id,
            name=f"Auto-{reading.sensor_id}",
            source=reading.source,
            region="Unknown",
            location=GeoPoint(latitude=reading.latitude, longitude=reading.longitude),
            parameters=[reading.parameter],
            is_mobile=reading.source == DataSource.MOBILE,
        )

    sensor = sensors[reading.sensor_id]
    if reading.parameter not in sensor.parameters:
        sensor.parameters.append(reading.parameter)

    item = SensorReading(
        reading_id=str(uuid4()),
        sensor_id=reading.sensor_id,
        parameter=reading.parameter,
        value=reading.value,
        unit=reading.unit,
        measured_at=reading.measured_at,
        latitude=reading.latitude,
        longitude=reading.longitude,
        source=reading.source,
        quality_score=reading.quality_score,
        tags={"region": sensor.region, "channel": channel},
    )
    readings.append(item)
    queue_events.append(
        {
            "event_id": str(uuid4()),
            "channel": channel,
            "sensor_id": item.sensor_id,
            "reading_id": item.reading_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    return item


def _simulate_open_source_payload(source: DataSource, region: str) -> list[SensorReadingIn]:
    now = datetime.now(UTC)
    if source == DataSource.OPENWEATHER:
        return [
            SensorReadingIn(
                sensor_id=f"OW-{region.upper()}-TEMP",
                parameter=ParameterType.TEMPERATURE_C,
                value=19.5,
                unit="C",
                measured_at=now,
                latitude=55.75,
                longitude=37.61,
                source=source,
                quality_score=0.82,
            ),
            SensorReadingIn(
                sensor_id=f"OW-{region.upper()}-HUM",
                parameter=ParameterType.HUMIDITY_PCT,
                value=61.0,
                unit="%",
                measured_at=now,
                latitude=55.75,
                longitude=37.61,
                source=source,
                quality_score=0.82,
            ),
        ]
    if source == DataSource.ROSGIDROMET:
        return [
            SensorReadingIn(
                sensor_id=f"RGM-{region.upper()}-PM25",
                parameter=ParameterType.PM25,
                value=38.2,
                unit="ug/m3",
                measured_at=now,
                latitude=59.93,
                longitude=30.33,
                source=source,
                quality_score=0.9,
            ),
            SensorReadingIn(
                sensor_id=f"RGM-{region.upper()}-NO2",
                parameter=ParameterType.NO2,
                value=0.23,
                unit="mg/m3",
                measured_at=now,
                latitude=59.93,
                longitude=30.33,
                source=source,
                quality_score=0.9,
            ),
        ]
    raise HTTPException(status_code=400, detail="Unsupported open source")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/sensors")
async def list_sensors(region: str | None = None, source: DataSource | None = None) -> dict[str, Any]:
    items = []
    for sensor in sensors.values():
        if region and sensor.region != region:
            continue
        if source and sensor.source != source:
            continue
        items.append(sensor.model_dump(mode="json"))
    return {"items": items, "count": len(items)}


@app.get("/sensors/{sensor_id}")
async def get_sensor(sensor_id: str) -> dict[str, Any]:
    sensor = sensors.get(sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor.model_dump(mode="json")


@app.post("/sensors/register")
async def register_sensor(request: SensorRegisterRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "reading:submit:stationary")
    sensor = SensorMetadata(
        sensor_id=request.sensor_id,
        name=request.name,
        source=request.source,
        region=request.region,
        location=GeoPoint(latitude=request.latitude, longitude=request.longitude),
        parameters=request.parameters,
        is_mobile=request.is_mobile,
    )
    sensors[sensor.sensor_id] = sensor
    _audit(request.actor_id, request.actor_role, "sensor.register", "sensor", sensor.sensor_id)
    return sensor.model_dump(mode="json")


@app.post("/ingestion/stationary")
async def ingest_stationary(request: IngestRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "reading:submit:stationary")
    if request.reading.source not in {DataSource.STATIONARY, DataSource.OPENWEATHER, DataSource.ROSGIDROMET}:
        raise HTTPException(status_code=400, detail="Stationary endpoint only accepts stationary or open source data")

    item = _register_reading(request.reading, channel="rabbitmq")
    _audit(
        request.actor_id,
        request.actor_role,
        "reading.ingest.stationary",
        "reading",
        item.reading_id,
        {"sensor_id": item.sensor_id, "parameter": item.parameter.value},
    )
    return {"reading": item.model_dump(mode="json"), "region": _resolve_region(item.sensor_id)}


@app.post("/ingestion/mobile")
async def ingest_mobile(request: IngestRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "reading:submit:mobile")
    if request.reading.source != DataSource.MOBILE:
        raise HTTPException(status_code=400, detail="Mobile endpoint accepts only mobile source")

    item = _register_reading(request.reading, channel="mqtt")
    _audit(
        request.actor_id,
        request.actor_role,
        "reading.ingest.mobile",
        "reading",
        item.reading_id,
        {"sensor_id": item.sensor_id, "parameter": item.parameter.value},
    )
    return {"reading": item.model_dump(mode="json"), "region": _resolve_region(item.sensor_id)}


@app.post("/ingestion/open-source/pull")
async def pull_open_source(request: OpenSourcePullRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "analysis:run")
    if request.source not in {DataSource.OPENWEATHER, DataSource.ROSGIDROMET}:
        raise HTTPException(status_code=400, detail="Only OpenWeather and Rosgidromet are supported")

    payload = _simulate_open_source_payload(request.source, request.region)
    items = []
    for reading in payload:
        reading.sensor_id = f"{request.source.value.upper()}-{request.region.upper()}-{reading.parameter.value}"
        item = _register_reading(reading, channel="rabbitmq")
        sensors[item.sensor_id].region = request.region
        items.append(item.model_dump(mode="json"))

    _audit(
        request.actor_id,
        request.actor_role,
        "reading.pull.open_source",
        "source",
        request.source.value,
        {"region": request.region, "count": len(items)},
    )
    return {
        "source": request.source.value,
        "region": request.region,
        "items": items,
        "count": len(items),
        "fetched_at": datetime.now(UTC).isoformat(),
    }


@app.get("/readings/latest")
async def latest_readings(
    parameter: ParameterType | None = None,
    sensor_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=2000),
) -> dict[str, Any]:
    items = readings
    if parameter:
        items = [item for item in items if item.parameter == parameter]
    if sensor_id:
        items = [item for item in items if item.sensor_id == sensor_id]
    ordered = sorted(items, key=lambda item: item.measured_at, reverse=True)[:limit]
    return {"items": [item.model_dump(mode="json") for item in ordered], "count": len(ordered)}


@app.get("/readings/history")
async def readings_history(
    parameter: ParameterType | None = None,
    region: str | None = None,
    since_minutes: int = 60,
) -> dict[str, Any]:
    threshold = datetime.now(UTC) - timedelta(minutes=max(since_minutes, 1))
    items = []
    for item in readings:
        if item.measured_at < threshold:
            continue
        if parameter and item.parameter != parameter:
            continue
        if region and _resolve_region(item.sensor_id) != region:
            continue
        items.append(item.model_dump(mode="json"))
    items.sort(key=lambda row: row["measured_at"])
    return {"items": items, "count": len(items)}


@app.get("/aggregates/realtime")
async def realtime_aggregates() -> dict[str, Any]:
    return {
        "window_minutes": 5,
        "aggregates": build_realtime_aggregates(readings),
        "updated_at": datetime.now(UTC).isoformat(),
    }


@app.get("/stream/queue/status")
async def queue_status() -> dict[str, Any]:
    mqtt_events = [item for item in queue_events if item["channel"] == "mqtt"]
    rabbit_events = [item for item in queue_events if item["channel"] == "rabbitmq"]
    return {
        "total_events": len(queue_events),
        "mqtt_events": len(mqtt_events),
        "rabbitmq_events": len(rabbit_events),
        "refresh_target_minutes": settings.ingestion_refresh_target_minutes,
    }


@app.get("/stream/sharding-plan")
async def sharding_plan(sensor_count: int = 100000, regions: int = 12) -> dict[str, Any]:
    region_shards = max(1, regions)
    sensors_per_shard = max(1, round(sensor_count / region_shards))
    workers = min(64, max(8, sensor_count // 5000))
    return {
        "sensor_count": sensor_count,
        "region_shards": region_shards,
        "sensors_per_shard": sensors_per_shard,
        "consumer_workers": workers,
        "target_supported_sensors": settings.sensor_capacity_target,
    }


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    if not has_permission(actor_role, "audit:read"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"items": audit_log[-limit:]}
