# EcoWatch

EcoWatch is a microservice platform for public ecological monitoring: air, water, noise, radiation, and weather parameters from stationary sensors, mobile measurements, and open data sources.

## Implemented modules

- `api-gateway` - orchestration and unified API
- `ingestion-service` - stationary, mobile, and open source ingestion
- `map-service` - points, heatmap, history layers, trends
- `analysis-service` - PDK checks, forecasting, spread model
- `alert-service` - threshold alerts and nearby subscriber targeting
- `report-service` - daily or monthly summaries and export
- `user-service` - activist cabinet and alert subscriptions
- `notification-service` - email, SMS, push, webhook, voice queues
- `frontend` - React + Leaflet ecological dashboard

## Optional improvements implemented

- Pollution forecasting (`analysis-service /analysis/forecast`)
- Source detection heuristics (`/analysis/source-detection`)
- Spread modeling (`/analysis/spread-model`)
- Telemetry stream sharding plan (`ingestion-service /stream/sharding-plan`)
- Realtime aggregation (`ingestion-service /aggregates/realtime`, `map-service /map/realtime-aggregates`)
- Map tile cache planning (`map-service /map/tiles/cache-plan`)
- Voice alerts (`notification-service /notifications/voice`)

## Quality targets

- Data refresh: target `< 5 min`
- Forecast quality: target `MAPE < 15%`
- Scaling: strategy for `100000` sensors

## Tech stack

- Backend: Python FastAPI
- Databases: PostgreSQL, TimescaleDB, PostGIS
- Queues: MQTT (Mosquitto), RabbitMQ
- Cache: Redis
- Frontend: React, Leaflet, Vite

## Local run

```bash
cd d:\Шарага\Кинжа6\Task_18_EcoWatch
docker compose up --build -d
```

## Useful URLs

- Frontend: `http://localhost:5178`
- Gateway health: `http://localhost:8580/health`
- Gateway docs: `http://localhost:8580/docs`

## Validation

```bash
python -m ruff check .
python -m pytest -q
docker compose config
```

## Demo workflow

```bash
python scripts/demo_pipeline.py
```

## Sample data generation

```bash
python scripts/generate_sample_data.py
```

Result file: `data/samples/ecowatch_events.json`
