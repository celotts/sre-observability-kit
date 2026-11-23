import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field

from sre_kit.pg_inspector import DatabaseCheckConfig

_tracer = trace.get_tracer("sre_kit.synthetics")
_meter = metrics.get_meter("sre_kit.synthetics")

synthetic_up_gauge = _meter.create_gauge(
    name="sre_synthetic_check_up",
    description="1 si el synthetic check pasa todas las validaciones, 0 si falla",
    unit="1",
)

synthetic_duration_histogram = _meter.create_histogram(
    name="sre_synthetic_check_duration",
    description="Duracion total del synthetic check en segundos",
    unit="s",
)


class DefaultsConfig(BaseModel):
    timeout_seconds: float = Field(default=5.0, gt=0)
    interval_seconds: int = Field(default=30, ge=5)
    max_latency_ms: float = Field(default=500.0, gt=0)
    consecutive_failures_to_alert: int = Field(default=2, ge=1)


class SyntheticJourneyConfig(BaseModel):
    name: str = Field(min_length=1)
    enabled: bool = True
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str = Field(min_length=1)
    expected_status: int = Field(default=200, ge=100, le=599)
    expected_json_key: str | None = None
    expected_json_value: Any = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_latency_ms: float | None = Field(default=None, gt=0)
    headers: dict[str, str] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)


class ScenariosConfig(BaseModel):
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    database_checks: list[DatabaseCheckConfig] = Field(default_factory=list)
    synthetic_journeys: list[SyntheticJourneyConfig] = Field(default_factory=list)


@dataclass
class SyntheticCheckResult:
    name: str
    status: Literal["ok", "failed"]
    latency_ms: float
    http_status: int | None
    message: str


def load_scenarios_config(config_path: Path) -> ScenariosConfig:
    raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return ScenariosConfig.model_validate(raw_data)


async def run_synthetic_journey(
    journey: SyntheticJourneyConfig,
    defaults: DefaultsConfig,
) -> SyntheticCheckResult:
    timeout_sec = journey.timeout_seconds or defaults.timeout_seconds
    max_latency_ms = journey.max_latency_ms or defaults.max_latency_ms
    labels = {"journey": journey.name}

    start_time = time.perf_counter()
    with _tracer.start_as_current_span(f"synthetic.{journey.name}") as span:
        span.set_attribute("synthetic.name", journey.name)
        span.set_attribute("http.method", journey.method)
        span.set_attribute("http.url", journey.url)
        for k, v in journey.tags.items():
            span.set_attribute(f"tag.{k}", v)

        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                response = await client.request(
                    method=journey.method,
                    url=journey.url,
                    headers=journey.headers,
                )

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            synthetic_duration_histogram.record(latency_ms / 1000.0, labels)
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("synthetic.latency_ms", latency_ms)

            errors: list[str] = []
            if response.status_code != journey.expected_status:
                errors.append(
                    f"status {response.status_code} != esperado {journey.expected_status}"
                )
            if latency_ms > max_latency_ms:
                errors.append(f"latencia {latency_ms}ms > {max_latency_ms}ms")

            if journey.expected_json_key is not None:
                payload = response.json()
                if not isinstance(payload, dict) or journey.expected_json_key not in payload:
                    errors.append(f"falta clave JSON '{journey.expected_json_key}'")
                elif (
                    journey.expected_json_value is not None
                    and payload[journey.expected_json_key] != journey.expected_json_value
                ):
                    errors.append(
                        f"valor '{journey.expected_json_key}'={payload[journey.expected_json_key]!r} "
                        f"!= esperado {journey.expected_json_value!r}"
                    )

            if errors:
                msg = "; ".join(errors)
                synthetic_up_gauge.set(0, labels)
                span.set_status(Status(StatusCode.ERROR, msg))
                return SyntheticCheckResult(
                    name=journey.name,
                    status="failed",
                    latency_ms=latency_ms,
                    http_status=response.status_code,
                    message=msg,
                )

            synthetic_up_gauge.set(1, labels)
            span.set_status(Status(StatusCode.OK))
            return SyntheticCheckResult(
                name=journey.name,
                status="ok",
                latency_ms=latency_ms,
                http_status=response.status_code,
                message=f"HTTP {response.status_code} en {latency_ms}ms",
            )

        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            synthetic_duration_histogram.record(latency_ms / 1000.0, labels)
            synthetic_up_gauge.set(0, labels)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            return SyntheticCheckResult(
                name=journey.name,
                status="failed",
                latency_ms=latency_ms,
                http_status=None,
                message=str(exc),
            )
