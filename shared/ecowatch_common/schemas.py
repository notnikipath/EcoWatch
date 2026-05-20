from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ParameterType(str, Enum):
    PM25 = "pm25"
    PM10 = "pm10"
    CO2 = "co2"
    NO2 = "no2"
    PH = "ph"
    TURBIDITY = "turbidity"
    DISSOLVED_OXYGEN = "dissolved_oxygen"
    NOISE_DB = "noise_db"
    RADIATION = "radiation"
    TEMPERATURE_C = "temperature_c"
    HUMIDITY_PCT = "humidity_pct"


class DataSource(str, Enum):
    STATIONARY = "stationary"
    MOBILE = "mobile"
    OPENWEATHER = "openweather"
    ROSGIDROMET = "rosgidromet"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    TELEGRAM = "telegram"
    PUSH = "push"
    WEBHOOK = "webhook"
    VOICE = "voice"


class Role(str, Enum):
    ACTIVIST = "activist"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    OPERATOR = "operator"
    ADMIN = "admin"


class GeoPoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SensorMetadata(BaseModel):
    sensor_id: str
    name: str
    source: DataSource
    region: str
    location: GeoPoint
    parameters: list[ParameterType] = Field(default_factory=list)
    is_mobile: bool = False
    installed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SensorReadingIn(BaseModel):
    sensor_id: str
    parameter: ParameterType
    value: float
    unit: str
    measured_at: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source: DataSource
    quality_score: float = Field(default=0.9, ge=0, le=1)


class SensorReading(SensorReadingIn):
    reading_id: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tags: dict[str, Any] = Field(default_factory=dict)


class PdkThreshold(BaseModel):
    parameter: ParameterType
    limit_value: float
    unit: str
    averaging_window_minutes: int = Field(default=20, ge=1)


class ExceedanceEvent(BaseModel):
    alert_id: str
    reading_id: str
    sensor_id: str
    parameter: ParameterType
    value: float
    limit_value: float
    unit: str
    severity: AlertSeverity
    region: str
    location: GeoPoint
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ForecastPoint(BaseModel):
    parameter: ParameterType
    region: str
    forecast_at: datetime
    predicted_value: float
    predicted_mape: float = Field(ge=0)


class MapHeatCell(BaseModel):
    cell_id: str
    parameter: ParameterType
    center: GeoPoint
    count: int = Field(ge=0)
    average_value: float
    max_value: float
    min_value: float


class TrendPoint(BaseModel):
    parameter: ParameterType
    region: str
    bucket_start: datetime
    average_value: float


class AlertSubscription(BaseModel):
    subscription_id: str
    user_id: str
    parameter: ParameterType
    region: str
    center: GeoPoint | None = None
    radius_km: float = Field(default=5, gt=0)
    channels: list[NotificationChannel] = Field(default_factory=list)
    min_severity: AlertSeverity = AlertSeverity.WARNING


class EcoUser(BaseModel):
    user_id: str
    display_name: str
    role: Role
    email: str
    home_region: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEvent(BaseModel):
    event_id: str
    actor_id: str
    actor_role: Role | str
    action: str
    object_type: str
    object_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NotificationMessage(BaseModel):
    message_id: str
    channel: NotificationChannel
    recipient: str
    subject: str
    body: str
    severity: AlertSeverity
    status: str = "queued"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
