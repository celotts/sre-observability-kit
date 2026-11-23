from dataclasses import dataclass, field
from urllib.parse import urlparse

import sentry_sdk
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from sre_kit.settings import Settings


@dataclass
class TelemetryRuntime:
    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    sentry_enabled: bool
    _shutdown_done: bool = field(default=False, init=False, repr=False)

    def flush_and_shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True

        try:
            self.meter_provider.force_flush(timeout_millis=5000)
        except Exception:
            pass

        try:
            self.tracer_provider.force_flush(timeout_millis=5000)
        except Exception:
            pass

        try:
            self.meter_provider.shutdown()
        except Exception:
            pass

        try:
            self.tracer_provider.shutdown()
        except Exception:
            pass

        if self.sentry_enabled:
            try:
                sentry_sdk.flush(timeout=5.0)
            except Exception:
                pass


def _normalize_otlp_grpc_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme and parsed.netloc:
        return parsed.netloc
    return endpoint


def init_telemetry(settings: Settings) -> TelemetryRuntime:
    sentry_enabled = False
    if settings.sentry_dsn.strip():
        sentry_sdk.init(
            dsn=settings.sentry_dsn.strip(),
            environment=settings.app_env,
            release=f"{settings.app_name}@0.2.0",
            traces_sample_rate=0.2,
            send_default_pii=False,
        )
        sentry_enabled = True

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.namespace": settings.app_name,
            "deployment.environment": settings.app_env,
        }
    )

    grpc_endpoint = _normalize_otlp_grpc_endpoint(settings.otel_exporter_otlp_endpoint)

    span_exporter = OTLPSpanExporter(endpoint=grpc_endpoint, insecure=True)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_exporter = OTLPMetricExporter(endpoint=grpc_endpoint, insecure=True)
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=5000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    return TelemetryRuntime(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        sentry_enabled=sentry_enabled,
    )
