import time
from collections.abc import Callable
from typing import TypeVar

import sentry_sdk
from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

T = TypeVar("T")

_tracer = trace.get_tracer("sre_kit.workflows")
_meter = metrics.get_meter("sre_kit.workflows")

workflow_executions_counter = _meter.create_counter(
    name="sre_workflow_executions",
    description="Cantidad de ejecuciones de flujos instrumentados por resultado",
    unit="1",
)

workflow_duration_histogram = _meter.create_histogram(
    name="sre_workflow_duration",
    description="Duracion de ejecucion de flujos instrumentados en segundos",
    unit="s",
)


def run_instrumented_workflow(
    workflow_name: str,
    operation: Callable[[], T],
    attributes: dict[str, str | int | float | bool] | None = None,
    capture_exceptions: bool = True,
) -> T:
    start_time = time.perf_counter()
    base_attrs: dict[str, str | int | float | bool] = {"workflow": workflow_name}
    if attributes:
        base_attrs.update(attributes)

    with _tracer.start_as_current_span(f"workflow.{workflow_name}") as span:
        for key, value in base_attrs.items():
            span.set_attribute(key, value)

        try:
            result = operation()
            span.set_status(Status(StatusCode.OK))
            workflow_executions_counter.add(
                1,
                {"workflow": workflow_name, "outcome": "success"},
            )
            return result
        except ValueError as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            workflow_executions_counter.add(
                1,
                {"workflow": workflow_name, "outcome": "validation_error"},
            )
            if capture_exceptions:
                sentry_sdk.capture_exception(exc)
            raise
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            workflow_executions_counter.add(
                1,
                {"workflow": workflow_name, "outcome": "error"},
            )
            if capture_exceptions:
                sentry_sdk.capture_exception(exc)
            raise
        finally:
            elapsed_seconds = time.perf_counter() - start_time
            span.set_attribute("workflow.duration_seconds", round(elapsed_seconds, 6))
            workflow_duration_histogram.record(
                elapsed_seconds,
                {"workflow": workflow_name},
            )
