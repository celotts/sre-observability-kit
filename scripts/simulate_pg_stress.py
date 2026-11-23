import argparse
import threading
import time

import psycopg

from sre_kit.settings import get_settings


def simulate_slow_query(dsn: str, sleep_seconds: float, iterations: int) -> int:
    print(f"Simulando {iterations} consulta(s) lenta(s) con pg_sleep({sleep_seconds})...")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        for idx in range(1, iterations + 1):
            t0 = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute("SELECT pg_sleep(%s);", (sleep_seconds,))
                cur.fetchone()
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            print(f"  [{idx}/{iterations}] Consulta completada en {elapsed_ms} ms")
    return 0


def simulate_lock_contention(dsn: str, hold_seconds: float) -> int:
    print(f"Preparando simulacion de bloqueo en PostgreSQL por {hold_seconds}s...")

    with psycopg.connect(dsn, connect_timeout=5) as setup_conn:
        setup_conn.autocommit = True
        with setup_conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS sre_lock_lab (id int primary key, note text);")
            cur.execute("INSERT INTO sre_lock_lab (id, note) VALUES (1, 'seed') ON CONFLICT (id) DO NOTHING;")

    blocker_ready = threading.Event()
    release_lock = threading.Event()
    errors: list[str] = []

    def blocker_session() -> None:
        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                conn.autocommit = False
                with conn.cursor() as cur:
                    cur.execute("BEGIN;")
                    cur.execute("LOCK TABLE sre_lock_lab IN ACCESS EXCLUSIVE MODE;")
                    blocker_ready.set()
                    release_lock.wait(timeout=hold_seconds + 5)
                    conn.rollback()
        except Exception as exc:
            errors.append(f"blocker: {exc}")
            blocker_ready.set()

    def waiter_session() -> None:
        if not blocker_ready.wait(timeout=5):
            return
        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                conn.autocommit = False
                with conn.cursor() as cur:
                    cur.execute("BEGIN;")
                    cur.execute("UPDATE sre_lock_lab SET note = 'waiting' WHERE id = 1;")
                    conn.rollback()
        except Exception as exc:
            errors.append(f"waiter: {exc}")

    t_blocker = threading.Thread(target=blocker_session, daemon=True)
    t_waiter = threading.Thread(target=waiter_session, daemon=True)

    t_blocker.start()
    t_waiter.start()

    print(f"Bloqueo activo durante {hold_seconds}s.")
    time.sleep(hold_seconds)
    release_lock.set()

    t_waiter.join(timeout=5)
    t_blocker.join(timeout=5)

    if errors:
        print("Avisos durante la simulacion:", "; ".join(errors))
    else:
        print("Simulacion de bloqueo finalizada limpiamente.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulador de estres para PostgreSQL en laboratorio")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    slow_p = subparsers.add_parser("slow-query", help="Simula consultas lentas con pg_sleep")
    slow_p.add_argument("--sleep", type=float, default=0.6, help="Segundos de pausa por consulta")
    slow_p.add_argument("--iterations", type=int, default=3, help="Numero de consultas a ejecutar")

    lock_p = subparsers.add_parser("lock", help="Simula contencion/bloqueo entre sesiones")
    lock_p.add_argument("--hold", type=float, default=20.0, help="Segundos que se mantiene el bloqueo")

    args = parser.parse_args()
    settings = get_settings()

    if args.mode == "slow-query":
        return simulate_slow_query(settings.postgres_dsn, args.sleep, args.iterations)
    if args.mode == "lock":
        return simulate_lock_contention(settings.postgres_dsn, args.hold)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
