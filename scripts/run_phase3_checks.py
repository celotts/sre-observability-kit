import argparse
import asyncio
import time
from pathlib import Path

from sre_kit.pg_inspector import run_postgres_check
from sre_kit.settings import get_settings
from sre_kit.synthetics import load_scenarios_config, run_synthetic_journey
from sre_kit.telemetry import init_telemetry


async def execute_cycle(config_path: Path, dsn: str) -> bool:
    scenarios = load_scenarios_config(config_path)
    all_ok = True

    for db_check in scenarios.database_checks:
        if not db_check.enabled:
            continue
        res = run_postgres_check(dsn=dsn, config=db_check)
        icon = "OK" if res.status == "ok" else "ALERTA"
        print(f"[PG:{icon}] {res.name} -> {res.message} ({res.latency_ms}ms)")
        if res.status != "ok":
            all_ok = False

    enabled_journeys = [j for j in scenarios.synthetic_journeys if j.enabled]
    if enabled_journeys:
        journey_results = await asyncio.gather(
            *(run_synthetic_journey(j, scenarios.defaults) for j in enabled_journeys)
        )
        for j_res in journey_results:
            icon = "OK" if j_res.status == "ok" else "ALERTA"
            print(f"[SYN:{icon}] {j_res.name} -> {j_res.message} ({j_res.latency_ms}ms)")
            if j_res.status != "ok":
                all_ok = False

    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecutor de chequeos de Fase 3")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/scenarios.example.yaml"),
        help="Ruta al archivo YAML de escenarios",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecuta un solo ciclo y termina",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Intervalo en segundos entre ciclos en modo continuo",
    )
    args = parser.parse_args()

    settings = get_settings()
    runtime = init_telemetry(settings)
    scenarios = load_scenarios_config(args.config)
    interval = args.interval or scenarios.defaults.interval_seconds

    try:
        if args.once:
            ok = asyncio.run(execute_cycle(args.config, settings.postgres_dsn))
            runtime.flush_and_shutdown()
            return 0 if ok else 1

        print(f"Iniciando monitoreo continuo cada {interval}s (Ctrl+C para detener)...")
        while True:
            asyncio.run(execute_cycle(args.config, settings.postgres_dsn))
            runtime.meter_provider.force_flush(timeout_millis=4000)
            runtime.tracer_provider.force_flush(timeout_millis=4000)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nDeteniendo ejecutor...")
    finally:
        runtime.flush_and_shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
