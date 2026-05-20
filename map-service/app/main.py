from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from math import floor
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.ecowatch_common import (
    ParameterType,
    Role,
    SensorReading,
    Settings,
    aggregate_heatmap,
    build_audit_event,
    build_realtime_aggregates,
    has_permission,
)

settings = Settings(service_name="map-service", service_port=8502)
app = FastAPI(title="EcoWatch Map Service", version="1.0.0")

map_records: list[dict[str, Any]] = []
audit_log: list[dict[str, Any]] = []


class MapIngestRequest(BaseModel):
    reading: SensorReading
    region: str
    actor_id: str
    actor_role: Role


MapIngestRequest.model_rebuild()


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any] | None = None) -> None:
    audit_log.append(
        build_audit_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            object_type="map",
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


def _filtered_records(parameter: ParameterType | None = None, region: str | None = None) -> list[dict[str, Any]]:
    items = map_records
    if parameter:
        items = [row for row in items if row["reading"].parameter == parameter]
    if region:
        items = [row for row in items if row["region"] == region]
    return items


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/map/ingest")
async def ingest_map_data(request: MapIngestRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "map:update")
    map_records.append(
        {
            "reading": request.reading,
            "region": request.region,
            "ingested_at": datetime.now(UTC),
        }
    )
    _audit(
        request.actor_id,
        request.actor_role,
        "map.ingest",
        request.reading.reading_id,
        {"parameter": request.reading.parameter.value, "region": request.region},
    )
    return {"status": "accepted", "reading_id": request.reading.reading_id, "region": request.region}


@app.get("/map/points")
async def map_points(
    parameter: ParameterType | None = None,
    region: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    items = _filtered_records(parameter, region)
    ordered = sorted(items, key=lambda row: row["reading"].measured_at, reverse=True)[: max(1, min(limit, 5000))]
    payload = [
        {
            "reading_id": row["reading"].reading_id,
            "sensor_id": row["reading"].sensor_id,
            "parameter": row["reading"].parameter.value,
            "value": row["reading"].value,
            "unit": row["reading"].unit,
            "latitude": row["reading"].latitude,
            "longitude": row["reading"].longitude,
            "measured_at": row["reading"].measured_at,
            "region": row["region"],
            "source": row["reading"].source.value,
        }
        for row in ordered
    ]
    return {"items": payload, "count": len(payload)}


@app.get("/map/heatmap")
async def heatmap(parameter: ParameterType, region: str | None = None, precision: int = 2) -> dict[str, Any]:
    records = _filtered_records(parameter=parameter, region=region)
    cells = aggregate_heatmap(
        [row["reading"] for row in records],
        parameter=parameter,
        precision=max(1, min(precision, 4)),
    )
    return {"parameter": parameter.value, "region": region, "items": [cell.model_dump(mode="json") for cell in cells]}


@app.get("/map/history-layers")
async def history_layers(
    parameter: ParameterType,
    region: str | None = None,
    hours: int = 24,
    bucket_minutes: int = 60,
) -> dict[str, Any]:
    bucket = max(1, bucket_minutes)
    threshold = datetime.now(UTC) - timedelta(hours=max(1, hours))
    records = [
        row
        for row in _filtered_records(parameter=parameter, region=region)
        if row["reading"].measured_at >= threshold
    ]

    layers: dict[str, list[float]] = defaultdict(list)
    for row in records:
        measured = row["reading"].measured_at
        minute_slot = floor(measured.minute / bucket) * bucket
        layer_start = measured.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_slot)
        layers[layer_start.isoformat()].append(row["reading"].value)

    items = []
    for stamp, values in sorted(layers.items()):
        items.append(
            {
                "layer_start": stamp,
                "parameter": parameter.value,
                "average_value": round(sum(values) / len(values), 3),
                "max_value": round(max(values), 3),
                "count": len(values),
            }
        )
    return {"items": items, "count": len(items)}


@app.get("/map/trends")
async def trends(parameter: ParameterType, region: str | None = None, window_minutes: int = 240) -> dict[str, Any]:
    threshold = datetime.now(UTC) - timedelta(minutes=max(10, window_minutes))
    records = [
        row
        for row in _filtered_records(parameter=parameter, region=region)
        if row["reading"].measured_at >= threshold
    ]
    ordered = sorted(records, key=lambda row: row["reading"].measured_at)
    values = [row["reading"].value for row in ordered]
    if len(values) < 2:
        slope = 0.0
    else:
        slope = round((values[-1] - values[0]) / (len(values) - 1), 4)
    return {
        "parameter": parameter.value,
        "region": region,
        "window_minutes": window_minutes,
        "samples": len(values),
        "latest": values[-1] if values else None,
        "average": round(sum(values) / len(values), 3) if values else None,
        "trend_per_sample": slope,
    }


@app.get("/map/realtime-aggregates")
async def realtime_aggregates(region: str | None = None) -> dict[str, Any]:
    records = _filtered_records(region=region)
    aggregates = build_realtime_aggregates([row["reading"] for row in records])
    return {"region": region, "window_minutes": 5, "aggregates": aggregates}


@app.get("/map/tiles/cache-plan")
async def tile_cache_plan(region: str = "Moscow", zoom_min: int = 8, zoom_max: int = 14) -> dict[str, Any]:
    zoom_min = max(1, zoom_min)
    zoom_max = max(zoom_min, zoom_max)
    tiles_per_zoom = {str(zoom): min(20000, 4 ** max(1, zoom - zoom_min + 1)) for zoom in range(zoom_min, zoom_max + 1)}
    return {
        "region": region,
        "zoom_min": zoom_min,
        "zoom_max": zoom_max,
        "tiles_per_zoom": tiles_per_zoom,
        "cache_strategy": "LRU with warmup by hot cells",
    }


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    if not has_permission(actor_role, "audit:read"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"items": audit_log[-limit:]}
