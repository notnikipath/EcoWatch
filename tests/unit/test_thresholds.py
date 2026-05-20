from shared.ecowatch_common import ParameterType, check_pdk
from shared.ecowatch_common.schemas import DataSource, SensorReading


def test_check_pdk_triggers_alert_for_high_pm25() -> None:
    reading = SensorReading(
        reading_id="R-1",
        sensor_id="AIR-1",
        parameter=ParameterType.PM25,
        value=48.0,
        unit="ug/m3",
        measured_at="2026-05-13T09:00:00Z",
        latitude=55.75,
        longitude=37.61,
        source=DataSource.STATIONARY,
        quality_score=0.98,
    )
    event = check_pdk("Moscow", reading, "A-1")
    assert event is not None
    assert event.parameter == ParameterType.PM25
