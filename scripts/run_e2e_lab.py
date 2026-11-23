import argparse
import subprocess
import sys
import time


def wait_for_mock(port: int, timeout_seconds: float = 5.0) -> None:
    import httpx

    deadline = time.perf_counter() + timeout_seconds
    url = f"http://127.0.0.1:{port}/ok"
    while time.perf_counter() < deadline:
        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"El servicio simulado no respondio en {url} tras {timeout_seconds}s")


def run_step(title: str, args: list[str]) -> int:
    print(f"\n=== {title} ===")
    proc = subprocess.run([sys.executable, *args], check=False)
    print(f"[EXIT {proc.returncode}] {title}")
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta un ciclo completo de prueba (healthy -> degraded -> pg stress)"
    )
    parser.add_argument("--port", type=int, default=8088, help="Puerto para el mock service")
    parser.add_argument(
        "--skip-pg-lock",
        action="store_true",
        help="Omite la simulacion de bloqueo en PostgreSQL",
    )
    args = parser.parse_args()

    mock_proc: subprocess.Popen | None = None
    try:
        print(f"Arrancando mock_target_service en puerto {args.port}...")
        mock_proc = subprocess.Popen(
            [sys.executable, "scripts/mock_target_service.py", "--host", "127.0.0.1", "--port", str(args.port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for_mock(args.port)
        print("Mock service listo.")

        run_step(
            "1. Escenario sano (healthy)",
            ["scripts/run_test_scenario.py", "healthy", "--loops", "2", "--sleep", "2"],
        )

        run_step(
            "2. Escenario degradado (latencia / 503 / contrato)",
            ["scripts/run_test_scenario.py", "degraded", "--loops", "3", "--sleep", "2"],
        )

        if not args.skip_pg_lock:
            print("\n=== 3. Simulacion de bloqueo en PostgreSQL + chequeo ===")
            lock_proc = subprocess.Popen(
                [sys.executable, "scripts/simulate_pg_stress.py", "lock", "--hold", "8"],
            )
            try:
                time.sleep(2)
                subprocess.run(
                    [
                        sys.executable,
                        "scripts/run_phase3_checks.py",
                        "--once",
                        "--config",
                        "config/scenario_healthy.yaml",
                    ],
                    check=False,
                )
            finally:
                lock_proc.wait(timeout=12)

        run_step(
            "4. Recuperacion a escenario sano",
            ["scripts/run_test_scenario.py", "healthy", "--loops", "2", "--sleep", "2"],
        )

        print("\nCiclo completo finalizado. Revisa Prometheus (:9090) y Grafana (:3000).")
        return 0

    except KeyboardInterrupt:
        print("\nLaboratorio interrumpido por el usuario.")
        return 130
    finally:
        if mock_proc is not None and mock_proc.poll() is None:
            mock_proc.terminate()
            try:
                mock_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                mock_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
