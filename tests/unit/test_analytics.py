from shared.ecowatch_common import ParameterType, aggregate_heatmap, forecast_next_value, mape
from shared.ecowatch_common.schemas import DataSource, SensorReading


def test_forecast_next_value_changes_with_trend() -> None:
    value = forecast_next_value([20.0, 24.0, 28.0, 30.0])
    assert value >= 28


def test_mape_is_positive() -> None:
    assert mape([10, 12], [11, 13]) > 0


def test_heatmap_aggregation() -> None:
    readings = [
        SensorReading(
            reading_id="1",
            sensor_id="S1",
            parameter=ParameterType.PM25,
            value=30.0,
            unit="ug/m3",
            measured_at="2026-05-13T09:00:00Z",
            latitude=55.75,
            longitude=37.61,
            source=DataSource.STATIONARY,
            quality_score=0.95,
        ),
        SensorReading(
            reading_id="2",
            sensor_id="S2",
            parameter=ParameterType.PM25,
            value=40.0,
            unit="ug/m3",
            measured_at="2026-05-13T09:05:00Z",
            latitude=55.751,
            longitude=37.611,
            source=DataSource.STATIONARY,
            quality_score=0.96,
        ),
    ]
    cells = aggregate_heatmap(readings, ParameterType.PM25, precision=2)
    assert cells
    assert cells[0].count >= 1
