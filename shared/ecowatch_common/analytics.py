from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from math import atan2, cos, radians, sin, sqrt

from .schemas import AlertSeverity, ExceedanceEvent, GeoPoint, MapHeatCell, ParameterType, SensorReading

DEFAULT_PDK_LIMITS: dict[ParameterType, tuple[float, str]] = {
    ParameterType.PM25: (35.0, "ug/m3"),
    ParameterType.PM10: (60.0, "ug/m3"),
    ParameterType.CO2: (1000.0, "ppm"),
    ParameterType.NO2: (0.2, "mg/m3"),
    ParameterType.PH: (8.5, "pH"),
    ParameterType.TURBIDITY: (5.0, "NTU"),
    ParameterType.DISSOLVED_OXYGEN: (4.0, "mg/L"),
    ParameterType.NOISE_DB: (70.0, "dB"),
    ParameterType.RADIATION: (0.3, "uSv/h"),
    ParameterType.TEMPERATURE_C: (35.0, "C"),
    ParameterType.HUMIDITY_PCT: (80.0, "%"),
}

LOWER_BOUND_PARAMETERS = {ParameterType.DISSOLVED_OXYGEN}


def parameter_medium(parameter: ParameterType) -> str:
    if parameter in {ParameterType.PM25, ParameterType.PM10, ParameterType.CO2, ParameterType.NO2}:
        return "air"
    if parameter in {ParameterType.PH, ParameterType.TURBIDITY, ParameterType.DISSOLVED_OXYGEN}:
        return "water"
    if parameter == ParameterType.NOISE_DB:
        return "noise"
    if parameter == ParameterType.RADIATION:
        return "radiation"
    return "meteo"


def check_pdk(sensor_region: str, reading: SensorReading, alert_id: str) -> ExceedanceEvent | None:
    limit, default_unit = DEFAULT_PDK_LIMITS[reading.parameter]
    exceeds = reading.value < limit if reading.parameter in LOWER_BOUND_PARAMETERS else reading.value > limit
    if not exceeds:
        return None

    ratio = abs(reading.value - limit) / max(abs(limit), 0.0001)
    if ratio >= 0.5:
        severity = AlertSeverity.CRITICAL
    elif ratio >= 0.2:
        severity = AlertSeverity.WARNING
    else:
        severity = AlertSeverity.INFO

    return ExceedanceEvent(
        alert_id=alert_id,
        reading_id=reading.reading_id,
        sensor_id=reading.sensor_id,
        parameter=reading.parameter,
        value=reading.value,
        limit_value=limit,
        unit=reading.unit or default_unit,
        severity=severity,
        region=sensor_region,
        location=GeoPoint(latitude=reading.latitude, longitude=reading.longitude),
    )


def forecast_next_value(history: list[float]) -> float:
    if not history:
        return 0.0
    if len(history) == 1:
        return round(history[-1], 3)
    tail = history[-5:]
    weights = [idx + 1 for idx in range(len(tail))]
    weighted = sum(value * weight for value, weight in zip(tail, weights, strict=True)) / sum(weights)
    trend = (tail[-1] - tail[0]) / max(len(tail) - 1, 1)
    return round(weighted + trend * 0.35, 3)


def mape(predicted: list[float], actual: list[float]) -> float:
    if not predicted or not actual or len(predicted) != len(actual):
        return 0.0
    errors = []
    for p_value, a_value in zip(predicted, actual, strict=True):
        if a_value == 0:
            continue
        errors.append(abs((a_value - p_value) / a_value))
    if not errors:
        return 0.0
    return round(sum(errors) / len(errors) * 100, 2)


def aggregate_heatmap(readings: list[SensorReading], parameter: ParameterType, precision: int = 2) -> list[MapHeatCell]:
    buckets: dict[tuple[float, float], list[float]] = defaultdict(list)
    for item in readings:
        if item.parameter != parameter:
            continue
        key = (round(item.latitude, precision), round(item.longitude, precision))
        buckets[key].append(item.value)

    cells: list[MapHeatCell] = []
    for (lat, lon), values in buckets.items():
        cells.append(
            MapHeatCell(
                cell_id=f"{parameter.value}:{lat}:{lon}",
                parameter=parameter,
                center=GeoPoint(latitude=lat, longitude=lon),
                count=len(values),
                average_value=round(sum(values) / len(values), 3),
                max_value=max(values),
                min_value=min(values),
            )
        )
    cells.sort(key=lambda cell: cell.average_value, reverse=True)
    return cells


def build_realtime_aggregates(readings: list[SensorReading]) -> dict[str, dict[str, float]]:
    now = datetime.now(UTC)
    window = [item for item in readings if (now - item.measured_at).total_seconds() <= 300]
    result: dict[str, dict[str, float]] = {}
    for parameter in ParameterType:
        values = [item.value for item in window if item.parameter == parameter]
        if not values:
            continue
        result[parameter.value] = {
            "avg": round(sum(values) / len(values), 3),
            "max": round(max(values), 3),
            "min": round(min(values), 3),
            "count": float(len(values)),
        }
    return result


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0
    d_lat = radians(b_lat - a_lat)
    d_lon = radians(b_lon - a_lon)
    start = sin(d_lat / 2) ** 2 + cos(radians(a_lat)) * cos(radians(b_lat)) * sin(d_lon / 2) ** 2
    c_val = 2 * atan2(sqrt(start), sqrt(1 - start))
    return radius * c_val


def severity_rank(severity: AlertSeverity) -> int:
    order = {
        AlertSeverity.INFO: 1,
        AlertSeverity.WARNING: 2,
        AlertSeverity.CRITICAL: 3,
    }
    return order[severity]
