from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random


def main() -> None:
    random = Random(18)
    base = datetime.now(UTC)

    sensors = [
        ("AIR-MSK-001", "pm25", "ug/m3", 30, 55.7558, 37.6173, "stationary"),
        ("AIR-MSK-001", "co2", "ppm", 900, 55.7558, 37.6173, "stationary"),
        ("WATER-MSK-002", "ph", "pH", 7.3, 55.7725, 37.6508, "stationary"),
        ("NOISE-SPB-003", "noise_db", "dB", 61, 59.9343, 30.3351, "stationary"),
        ("MOBILE-DEMO-01", "pm25", "ug/m3", 28, 55.7633, 37.5839, "mobile"),
    ]

    payload = []
    for minute in range(180):
        measured_at = (base - timedelta(minutes=minute)).isoformat()
        for sensor_id, parameter, unit, baseline, lat, lon, source in sensors:
            jitter = (random.random() - 0.5) * baseline * 0.15
            value = round(max(0.01, baseline + jitter), 3)
            payload.append(
                {
                    "sensor_id": sensor_id,
                    "parameter": parameter,
                    "value": value,
                    "unit": unit,
                    "measured_at": measured_at,
                    "latitude": lat,
                    "longitude": lon,
                    "source": source,
                    "quality_score": round(0.8 + random.random() * 0.2, 3),
                }
            )

    output = Path(__file__).resolve().parents[1] / "data" / "samples" / "ecowatch_events.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {len(payload)} events to {output}")


if __name__ == "__main__":
    main()
