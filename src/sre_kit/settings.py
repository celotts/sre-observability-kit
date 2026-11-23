from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="local", alias="APP_ENV")
    app_name: str = Field(default="sre-observability-kit", alias="APP_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="sre_lab", alias="POSTGRES_DB")
    postgres_user: str = Field(default="sre_user", alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(default=SecretStr("sre_secret_local"), alias="POSTGRES_PASSWORD")

    otel_service_name: str = Field(default="sre-core-service", alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4317",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_collector_metrics_port: int = Field(default=8889, alias="OTEL_COLLECTOR_METRICS_PORT")

    prometheus_port: int = Field(default=9090, alias="PROMETHEUS_PORT")
    grafana_port: int = Field(default=3000, alias="GRAFANA_PORT")

    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    dd_api_key: SecretStr = Field(default=SecretStr(""), alias="DD_API_KEY")

    @property
    def postgres_dsn(self) -> str:
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_settings() -> Settings:
    return Settings()
