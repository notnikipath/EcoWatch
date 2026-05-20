# Project Report

## Goal

Build a scalable ecological monitoring platform that collects data from diverse sensors, visualizes it on a map, and informs nearby citizens about dangerous exceedances.

## Functional coverage

- Air quality, water quality, noise, radiation, and weather data
- Stationary and mobile ingestion flows
- Open source ingestion stubs for OpenWeather and Rosgidromet
- Threshold checks against PDK values with severity classes
- Heatmap and trend layers for geospatial views
- User cabinet and personalized alert subscriptions
- Daily and monthly report generation plus researcher export

## Target metrics

- Data refresh target: less than 5 minutes
- Forecast MAPE target: less than 15%
- Scaling target: support strategy for 100000 sensors

## Testing strategy

- Unit tests for forecast, PDK logic, heatmap aggregation, security token flow
- Integration tests for cross-service pipeline and user subscription flow

## Result

The delivered solution covers mandatory modules, provides an end-to-end processing workflow, and includes advanced enhancements for forecasting, stream scaling, and richer alert channels.
