import random
import time

from sre_kit.settings import get_settings
from sre_kit.telemetry import init_telemetry
from sre_kit.workflows import run_instrumented_workflow


def simulate_step(step_name: str, should_fail: str | None = None) -> str:
    time.sleep(random.uniform(0.02, 0.15))
    if should_fail == "validation":
        raise ValueError(f"Entrada invalida en {step_name}")
    if should_fail == "runtime":
        raise RuntimeError(f"Fallo simulado en {step_name}")
    return f"{step_name}:ok"


def main() -> int:
    settings = get_settings()
    runtime = init_telemetry(settings)

    print(
        f"Enviando trazas y metricas a {settings.otel_exporter_otlp_endpoint} "
        f"(sentry_enabled={runtime.sentry_enabled})..."
    )

    scenarios: list[tuple[str, str | None]] = [
        ("ok", None),
        ("ok", None),
        ("ok", None),
        ("validation", "validation"),
        ("runtime", "runtime"),
    ]

    for idx, (label, failure_mode) in enumerate(scenarios, start=1):
        try:
            output = run_instrumented_workflow(
                workflow_name="sample_critical_flow",
                operation=lambda fm=failure_mode, i=idx: simulate_step(f"item-{i}", fm),
                attributes={"batch_item": idx, "scenario": label},
            )
            print(f"  [{idx}] Resultado: {output}")
        except Exception as exc:
            print(f"  [{idx}] Capturado ({type(exc).__name__}): {exc}")

    time.sleep(6)
    runtime.flush_and_shutdown()
    print("Telemetria enviada y flush completado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
