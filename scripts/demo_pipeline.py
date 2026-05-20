from __future__ import annotations

import json

import httpx

GATEWAY = "http://localhost:8580"


async def run_demo() -> None:
    reading_payload = {
        "reading": {
            "sensor_id": "AIR-MSK-001",
            "parameter": "pm25",
            "value": 47.5,
            "unit": "ug/m3",
            "measured_at": "2026-05-13T09:00:00Z",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "source": "stationary",
            "quality_score": 0.97,
        },
        "actor_id": "OPS-001",
        "actor_role": "operator",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        result = await client.post(f"{GATEWAY}/workflow/process-reading", json=reading_payload)
        result.raise_for_status()
        print("process-reading:")
        print(json.dumps(result.json(), indent=2, ensure_ascii=False))

        dashboard = await client.get(f"{GATEWAY}/dashboard/overview", params={"parameter": "pm25", "region": "Moscow"})
        dashboard.raise_for_status()
        print("dashboard summary:")
        payload = dashboard.json()
        print(
            json.dumps(
                {
                    "alerts": payload.get("analysis", {}).get("exceedances", {}).get("count", 0),
                    "notifications": payload.get("notifications", {}).get("count", 0),
                    "measurements": payload.get("report", {}).get("measurements", 0),
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_demo())
