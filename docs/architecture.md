# Architecture

## Context

EcoWatch supports public and institutional environmental monitoring with frequent telemetry updates, map-centered visibility, threshold control, and notification workflows.

## Service map

- `api-gateway`: single entry point, auth, workflow orchestration
- `ingestion-service`: ingest stationary and mobile data, pull open sources
- `map-service`: geospatial layers, heatmaps, trends, map cache planning
- `analysis-service`: PDK checks, exceedance detection, forecasting, spread simulation
- `alert-service`: subscription matching and alert fan-out preparation
- `report-service`: daily/monthly reports and researcher export
- `user-service`: activist profiles and personal subscriptions
- `notification-service`: dispatch over email, SMS, push, webhook, voice

## Infrastructure

- PostgreSQL for users and metadata
- TimescaleDB for temporal series and high-volume telemetry
- PostGIS for geodata persistence and map-ready structures
- RabbitMQ for asynchronous threshold and reporting pipelines
- MQTT broker for mobile/IoT telemetry streams
- Redis for caches and short-lived aggregates
- Docker Compose for local deployment

## Key workflow

1. Sensor reading arrives via `api-gateway /workflow/process-reading`
2. Reading is stored in `ingestion-service`
3. `analysis-service` validates against PDK and computes forecast
4. `alert-service` resolves subscribers and notification payloads
5. `notification-service` queues outbound alerts
6. `map-service` updates map layers and heat cells
7. `report-service` updates daily and monthly summaries

## Scalability notes

- Sensor sharding plan by region in `ingestion-service /stream/sharding-plan`
- Realtime 5-minute aggregates to reduce dashboard query pressure
- Decoupled alerting and reporting via service boundaries
- Tile cache planning for heavy map traffic
