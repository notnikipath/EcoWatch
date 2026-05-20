from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from shared.ecowatch_common import (
    ExceedanceEvent,
    ParameterType,
    Role,
    SensorReading,
    Settings,
    build_audit_event,
    has_permission,
)

settings = Settings(service_name="report-service", service_port=8505)
app = FastAPI(title="EcoWatch Report Service", version="1.0.0")

reading_records: list[dict[str, Any]] = []
alert_records: list[dict[str, Any]] = []
audit_log: list[dict[str, Any]] = []


class ReadingIngestRequest(BaseModel):
    reading: SensorReading
    region: str
    actor_id: str
    actor_role: Role


class AlertIngestRequest(BaseModel):
    alert: ExceedanceEvent
    actor_id: str
    actor_role: Role


class ExportRequest(BaseModel):
    actor_role: Role = Role.RESEARCHER


ReadingIngestRequest.model_rebuild()
AlertIngestRequest.model_rebuild()
ExportRequest.model_rebuild()


def _assert_permission(role: Role, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(status_code=403, detail=f"Role {role.value} cannot perform {action}")


def _audit(actor_id: str, actor_role: Role, action: str, object_id: str, details: dict[str, Any] | None = None) -> None:
    audit_log.append(
        build_audit_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            object_type="report",
            object_id=object_id,
            details=details or {},
        ).model_dump(mode="json")
    )


def _day_key(stamp: datetime) -> str:
    return stamp.date().isoformat()


def _month_key(stamp: datetime) -> str:
    return f"{stamp.year:04d}-{stamp.month:02d}"


def _summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["reading"]["parameter"]].append(row["reading"]["value"])
    result: dict[str, dict[str, float]] = {}
    for parameter, values in grouped.items():
        result[parameter] = {
            "avg": round(sum(values) / len(values), 3),
            "max": round(max(values), 3),
            "min": round(min(values), 3),
            "count": float(len(values)),
        }
    return result


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/reports/ingest-reading")
async def ingest_reading(request: ReadingIngestRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "report:read")
    record = {
        "record_id": str(uuid4()),
        "reading": request.reading.model_dump(mode="json"),
        "region": request.region,
        "created_at": datetime.now(UTC).isoformat(),
    }
    reading_records.append(record)
    _audit(request.actor_id, request.actor_role, "report.ingest.reading", record["record_id"])
    return {"status": "accepted", "record_id": record["record_id"]}


@app.post("/reports/ingest-alert")
async def ingest_alert(request: AlertIngestRequest) -> dict[str, Any]:
    _assert_permission(request.actor_role, "report:read")
    record = {
        "record_id": str(uuid4()),
        "alert": request.alert.model_dump(mode="json"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    alert_records.append(record)
    _audit(request.actor_id, request.actor_role, "report.ingest.alert", record["record_id"])
    return {"status": "accepted", "record_id": record["record_id"]}


@app.get("/reports/daily")
async def daily_report(report_date: str | None = None, region: str | None = None) -> dict[str, Any]:
    target = date.fromisoformat(report_date) if report_date else datetime.now(UTC).date()
    rows = []
    for row in reading_records:
        measured = datetime.fromisoformat(row["reading"]["measured_at"].replace("Z", "+00:00"))
        if measured.date() != target:
            continue
        if region and row["region"] != region:
            continue
        rows.append(row)

    alerts = []
    for row in alert_records:
        created = datetime.fromisoformat(row["alert"]["created_at"].replace("Z", "+00:00"))
        if created.date() != target:
            continue
        if region and row["alert"]["region"] != region:
            continue
        alerts.append(row)

    return {
        "date": target.isoformat(),
        "region": region,
        "measurements": len(rows),
        "alerts": len(alerts),
        "summary": _summary(rows),
    }


@app.get("/reports/monthly")
async def monthly_report(
    year: int | None = None,
    month: int | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    year = year or now.year
    month = month or now.month
    target = f"{year:04d}-{month:02d}"

    rows = []
    for row in reading_records:
        measured = datetime.fromisoformat(row["reading"]["measured_at"].replace("Z", "+00:00"))
        if _month_key(measured) != target:
            continue
        if region and row["region"] != region:
            continue
        rows.append(row)

    alerts = []
    for row in alert_records:
        created = datetime.fromisoformat(row["alert"]["created_at"].replace("Z", "+00:00"))
        if _month_key(created) != target:
            continue
        if region and row["alert"]["region"] != region:
            continue
        alerts.append(row)

    by_day: dict[str, int] = defaultdict(int)
    for row in rows:
        measured = datetime.fromisoformat(row["reading"]["measured_at"].replace("Z", "+00:00"))
        by_day[_day_key(measured)] += 1

    return {
        "month": target,
        "region": region,
        "measurements": len(rows),
        "alerts": len(alerts),
        "daily_volume": by_day,
        "summary": _summary(rows),
    }


@app.get("/reports/export")
async def export_data(
    format: str = "json",
    parameter: ParameterType | None = None,
    region: str | None = None,
    actor_role: Role = Role.RESEARCHER,
):
    _assert_permission(actor_role, "report:export")
    rows = reading_records
    if parameter:
        rows = [row for row in rows if row["reading"]["parameter"] == parameter.value]
    if region:
        rows = [row for row in rows if row["region"] == region]

    if format == "json":
        return {"items": rows, "count": len(rows)}
    if format == "csv":
        header = "reading_id,sensor_id,parameter,value,unit,measured_at,region,source"
        lines = [header]
        for row in rows:
            reading = row["reading"]
            lines.append(
                ",".join(
                    [
                        reading["reading_id"],
                        reading["sensor_id"],
                        reading["parameter"],
                        str(reading["value"]),
                        reading["unit"],
                        reading["measured_at"],
                        row["region"],
                        reading["source"],
                    ]
                )
            )
        return PlainTextResponse(content="\n".join(lines), media_type="text/csv")

    raise HTTPException(status_code=400, detail="Supported formats: json, csv")


@app.get("/audit")
async def get_audit(limit: int = 100, actor_role: Role = Role.ADMIN) -> dict[str, Any]:
    if not has_permission(actor_role, "audit:read"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"items": audit_log[-limit:]}
