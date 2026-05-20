# Deployment

## Requirements

- Docker
- Docker Compose
- Python 3.11 for local lint/test

## Start

```bash
cd d:\Шарага\Кинжа6\Task_18_EcoWatch
docker compose up --build -d
```

## Stop

```bash
docker compose down
```

## Validate

```bash
python -m ruff check .
python -m pytest -q
docker compose config
```

## Ports

- `8580` gateway
- `5178` frontend
- `8501-8507` backend services
- `55535` PostgreSQL
- `55536` TimescaleDB
- `55537` PostGIS
- `5672` RabbitMQ
- `15672` RabbitMQ UI
- `1883` MQTT broker
- `6390` Redis
