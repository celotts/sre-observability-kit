import argparse
import subprocess
import sys
import time
from pathlib import Path

SCENARIOS = {
    "healthy": Path("config/scenario_healthy.yaml"),
    "degraded": Path("config/scenario_degraded.yaml"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta un escenario de prueba predefinido")
    parser.add_argument(
        "scenario",
        choices=sorted(SCENARIOS.keys()),
        help="Escenario de prueba a ejecutar: 'healthy' o 'degraded'",
    )
    parser.add_argument(
        "--loops",
        type=int,
        default=1,
        help="Cantidad de repeticiones del escenario",
    )
    parser.add_argument(
        "--sleep",
        type=int,
        default=5,
        help="Segundos de pausa entre repeticiones",
    )
    args = parser.parse_args()

    config_file = SCENARIOS[args.scenario]
    if not config_file.exists():
        print(f"[ERROR] No se encontro {config_file}")
        return 1

    val = subprocess.run(
        [sys.executable, "scripts/validate_config.py", str(config_file)],
        check=False,
    )
    if val.returncode != 0:
        return val.returncode

    for i in range(1, args.loops + 1):
        print(f"\n--- Ejecutando escenario '{args.scenario}' (iteracion {i}/{args.loops}) ---")
        subprocess.run(
            [sys.executable, "scripts/run_phase3_checks.py", "--once", "--config", str(config_file)],
            check=False,
        )
        if i < args.loops:
            time.sleep(args.sleep)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
