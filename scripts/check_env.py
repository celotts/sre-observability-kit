import sys

import httpx
import psycopg

from sre_kit.settings import get_settings


def check_python_version() -> bool:
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 11)
    status = "OK" if ok else "ERROR"
    print(f"[{status}] Python {major}.{minor}.{sys.version_info.micro} (requerido >= 3.11)")
    return ok


def check_postgres(dsn: str) -> bool:
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database(), version();")
            db_name, version_str = cur.fetchone()
        print(f"[OK] PostgreSQL conectado -> db='{db_name}' | {version_str.split(',')[0]}")
        return True
    except Exception as exc:
        print(f"[ERROR] PostgreSQL no disponible: {exc}")
        return False


def check_http_endpoint(label: str, url: str) -> bool:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
        print(f"[OK] {label} accesible en {url} (HTTP {resp.status_code})")
        return True
    except Exception as exc:
        print(f"[ERROR] {label} no accesible en {url}: {exc}")
        return False


def main() -> int:
    settings = get_settings()
    print(f"Verificando entorno '{settings.app_env}' para '{settings.app_name}'...\n")

    checks = [
        check_python_version(),
        check_postgres(settings.postgres_dsn),
        check_http_endpoint(
            "OTel Collector metrics",
            f"http://localhost:{settings.otel_collector_metrics_port}/metrics",
        ),
        check_http_endpoint(
            "Prometheus",
            f"http://localhost:{settings.prometheus_port}/-/healthy",
        ),
        check_http_endpoint(
            "Grafana health",
            f"http://localhost:{settings.grafana_port}/api/health",
        ),
    ]

    print("\nResultado general:", "ENTORNO LISTO" if all(checks) else "HAY PENDIENTES")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
