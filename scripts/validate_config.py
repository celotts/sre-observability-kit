import argparse
from pathlib import Path

from sre_kit.synthetics import load_scenarios_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida un archivo YAML de escenarios para SRE Observability Kit"
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        type=Path,
        default=Path("config/scenarios.example.yaml"),
        help="Ruta al archivo YAML de escenarios",
    )
    args = parser.parse_args()

    if not args.config_file.exists():
        print(f"[ERROR] No existe el archivo: {args.config_file}")
        return 1

    try:
        cfg = load_scenarios_config(args.config_file)
    except Exception as exc:
        print(f"[ERROR] Configuracion invalida en {args.config_file}:\n{exc}")
        return 1

    enabled_db = [c for c in cfg.database_checks if c.enabled]
    enabled_syn = [j for j in cfg.synthetic_journeys if j.enabled]

    print(f"[OK] Configuracion valida: {args.config_file}")
    print(
        f"  - Defaults: timeout={cfg.defaults.timeout_seconds}s, "
        f"interval={cfg.defaults.interval_seconds}s, max_latency={cfg.defaults.max_latency_ms}ms"
    )
    print(f"  - Database checks: {len(enabled_db)} activos / {len(cfg.database_checks)} definidos")
    for c in enabled_db:
        print(f"      * {c.name} (max_latency={c.max_latency_ms}ms, max_locks={c.max_blocked_queries})")
    print(f"  - Synthetic journeys: {len(enabled_syn)} activos / {len(cfg.synthetic_journeys)} definidos")
    for j in enabled_syn:
        print(f"      * {j.name} [{j.method} {j.url}] -> status={j.expected_status}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
