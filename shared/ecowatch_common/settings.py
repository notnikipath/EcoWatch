from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "ecowatch-service"
    service_port: int = 8500
    environment: str = "dev"

    postgres_dsn: str = "postgresql+psycopg://ecowatch:ecowatch@postgres:5432/ecowatch"
    timescale_dsn: str = "postgresql+psycopg://ecowatch:ecowatch@timescaledb:5432/ecowatch"
    postgis_dsn: str = "postgresql+psycopg://ecowatch:ecowatch@postgis:5432/ecowatch_geo"
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    mqtt_broker_url: str = "mqtt://mosquitto:1883"

    openweather_base_url: str = "https://api.openweathermap.org"
    rosgidromet_base_url: str = "https://example.rosgidromet.local"

    jwt_secret: str = "ecowatch-dev-secret"
    encryption_key: str = "ecowatch-dev-encryption-key"

    ingestion_refresh_target_minutes: int = 5
    forecast_mape_target: float = 15.0
    sensor_capacity_target: int = 100000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
