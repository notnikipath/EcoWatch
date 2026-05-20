# API Overview

## Gateway

- `POST /auth/token`
- `POST /auth/verify`
- `GET /services/health`
- `POST /workflow/process-reading`
- `POST /workflow/pull-open-source`
- `POST /workflow/subscribe-alert`
- `GET /dashboard/overview`
- `GET /dashboard/map`
- `GET /users/cabinet/{user_id}`

## Ingestion service

- `GET /sensors`
- `POST /sensors/register`
- `POST /ingestion/stationary`
- `POST /ingestion/mobile`
- `POST /ingestion/open-source/pull`
- `GET /readings/latest`
- `GET /readings/history`
- `GET /aggregates/realtime`
- `GET /stream/queue/status`
- `GET /stream/sharding-plan`

## Map service

- `POST /map/ingest`
- `GET /map/points`
- `GET /map/heatmap`
- `GET /map/history-layers`
- `GET /map/trends`
- `GET /map/realtime-aggregates`
- `GET /map/tiles/cache-plan`

## Analysis service

- `POST /analysis/check-pdk`
- `POST /analysis/forecast`
- `GET /analysis/exceedances`
- `GET /analysis/forecasts`
- `GET /analysis/source-detection`
- `POST /analysis/spread-model`
- `GET /analysis/pdk`
- `GET /analysis/kpi`

## Alert service

- `POST /subscriptions`
- `GET /subscriptions`
- `POST /subscriptions/sync-contact`
- `POST /alerts/notify-nearby`
- `GET /alerts`

## Report service

- `POST /reports/ingest-reading`
- `POST /reports/ingest-alert`
- `GET /reports/daily`
- `GET /reports/monthly`
- `GET /reports/export`

## User service

- `GET /users`
- `POST /users`
- `GET /users/{user_id}`
- `PATCH /users/{user_id}`
- `POST /users/{user_id}/subscriptions`
- `GET /users/{user_id}/subscriptions`
- `GET /cabinet/{user_id}`

## Notification service

- `POST /notifications/send`
- `POST /notifications/bulk`
- `POST /notifications/voice`
- `GET /notifications/history`
