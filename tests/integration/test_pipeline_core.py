from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.helpers import load_module

ROOT = Path(__file__).resolve().parents[2]

ingestion_module = load_module("ingestion_module", ROOT / "ingestion-service" / "app" / "main.py")
analysis_module = load_module("analysis_module", ROOT / "analysis-service" / "app" / "main.py")
map_module = load_module("map_module", ROOT / "map-service" / "app" / "main.py")
alert_module = load_module("alert_module", ROOT / "alert-service" / "app" / "main.py")
report_module = load_module("report_module", ROOT / "report-service" / "app" / "main.py")
user_module = load_module("user_module", ROOT / "user-service" / "app" / "main.py")
notification_module = load_module("notification_module", ROOT / "notification-service" / "app" / "main.py")

ingestion_client = TestClient(ingestion_module.app)
analysis_client = TestClient(analysis_module.app)
map_client = TestClient(map_module.app)
alert_client = TestClient(alert_module.app)
report_client = TestClient(report_module.app)
user_client = TestClient(user_module.app)
notification_client = TestClient(notification_module.app)


def test_end_to_end_alert_flow() -> None:
    user_subscription = user_client.post(
        "/users/USER-001/subscriptions",
        json={
            "parameter": "pm25",
            "region": "Moscow",
            "latitude": 55.75,
            "longitude": 37.61,
            "radius_km": 8,
            "channels": ["email"],
            "min_severity": "warning",
            "actor_role": "admin",
        },
    )
    assert user_subscription.status_code == 200

    alert_subscription = alert_client.post(
        "/subscriptions",
        json={
            "user_id": "USER-001",
            "parameter": "pm25",
            "region": "Moscow",
            "latitude": 55.75,
            "longitude": 37.61,
            "radius_km": 8,
            "channels": ["email"],
            "min_severity": "warning",
            "actor_id": "USER-ADM",
            "actor_role": "admin",
        },
    )
    assert alert_subscription.status_code == 200

    reading_response = ingestion_client.post(
        "/ingestion/stationary",
        json={
            "reading": {
                "sensor_id": "AIR-MSK-001",
                "parameter": "pm25",
                "value": 49.0,
                "unit": "ug/m3",
                "measured_at": "2026-05-13T09:00:00Z",
                "latitude": 55.755,
                "longitude": 37.617,
                "source": "stationary",
                "quality_score": 0.96,
            },
            "actor_id": "OPS-001",
            "actor_role": "operator",
        },
    )
    assert reading_response.status_code == 200
    reading = reading_response.json()["reading"]

    analysis_response = analysis_client.post(
        "/analysis/check-pdk",
        json={
            "reading": reading,
            "region": "Moscow",
            "actor_id": "OPS-001",
            "actor_role": "operator",
        },
    )
    assert analysis_response.status_code == 200
    analysis_payload = analysis_response.json()
    assert analysis_payload["alert"] is not None

    map_response = map_client.post(
        "/map/ingest",
        json={
            "reading": reading,
            "region": "Moscow",
            "actor_id": "OPS-001",
            "actor_role": "operator",
        },
    )
    assert map_response.status_code == 200

    dispatch_response = alert_client.post(
        "/alerts/notify-nearby",
        json={
            "alert": analysis_payload["alert"],
            "actor_id": "OPS-001",
            "actor_role": "operator",
        },
    )
    assert dispatch_response.status_code == 200
    dispatch_payload = dispatch_response.json()

    bulk_response = notification_client.post(
        "/notifications/bulk",
        json={
            "messages": dispatch_payload["notifications"],
            "actor_role": "operator",
        },
    )
    assert bulk_response.status_code == 200

    report_reading = report_client.post(
        "/reports/ingest-reading",
        json={
            "reading": reading,
            "region": "Moscow",
            "actor_id": "OPS-001",
            "actor_role": "admin",
        },
    )
    assert report_reading.status_code == 200

    report_alert = report_client.post(
        "/reports/ingest-alert",
        json={
            "alert": analysis_payload["alert"],
            "actor_id": "OPS-001",
            "actor_role": "admin",
        },
    )
    assert report_alert.status_code == 200


def test_open_source_pull_and_monthly_report() -> None:
    pull_response = ingestion_client.post(
        "/ingestion/open-source/pull",
        json={
            "source": "openweather",
            "region": "Moscow",
            "actor_id": "ANL-001",
            "actor_role": "analyst",
        },
    )
    assert pull_response.status_code == 200
    assert pull_response.json()["count"] >= 1

    monthly = report_client.get("/reports/monthly", params={"region": "Moscow"})
    assert monthly.status_code == 200
    assert "summary" in monthly.json()
