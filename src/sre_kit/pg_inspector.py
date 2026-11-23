import time
from dataclasses import dataclass
from typing import Literal

import psycopg
from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field

_tracer = trace.get_tracer("sre_kit.pg_inspector")
_meter = metrics.get_meter("sre_kit.pg_inspector")

pg_check_up_gauge = _meter.create_gauge(
    name="sre_pg_check_up",
    description="1 si el chequeo funcional de PostgreSQL pasa, 0 si falla o excede umbral",
    unit="1",
)

pg_query_latency_histogram = _meter.create_histogram(
    name="sre_pg_query_latency",
    description="Latencia de diagnostico funcional en PostgreSQL en segundos",
    unit="s",
)

pg_blocked_queries_gauge = _meter.create_gauge(
    name="sre_pg_blocked_queries",
    description="Cantidad de consultas bloqueadas detectadas en PostgreSQL",
    unit="1",
)


class DatabaseCheckConfig(BaseModel):
    name: str = Field(min_length=1)
    enabled: bool = True
    max_latency_ms: float = Field(default=250.0, gt=0)
    max_active_connections_ratio: float = Field(default=0.8, gt=0.0, le=1.0)
    max_blocked_queries: int = Field(default=0, ge=0)


@dataclass
class DatabaseCheckResult:
    name: str
    status: Literal["ok", "degraded", "error"]
    latency_ms: float
    active_connections: int
    max_connections: int
    blocked_queries: int
    message: str


def run_postgres_check(dsn: str, config: DatabaseCheckConfig) -> DatabaseCheckResult:
    start_time = time.perf_counter()
    labels = {"check_name": config.name}

    with _tracer.start_as_current_span(f"pg_check.{config.name}") as span:
        span.set_attribute("pg.check.name", config.name)

        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS active_conns,
                            (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_conns,
                            (
                                SELECT count(*)
                                FROM pg_stat_activity
                                WHERE wait_event_type = 'Lock'
                            ) AS blocked_conns;
                        """
                    )
                    row = cur.fetchone()
                    active_conns = int(row[0] or 0)
                    max_conns = max(int(row[1] or 1), 1)
                    blocked_conns = int(row[2] or 0)

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            latency_sec = latency_ms / 1000.0
            conn_ratio = active_conns / max_conns

            pg_query_latency_histogram.record(latency_sec, labels)
            pg_blocked_queries_gauge.set(blocked_conns, labels)

            span.set_attribute("pg.latency_ms", latency_ms)
            span.set_attribute("pg.active_connections", active_conns)
            span.set_attribute("pg.max_connections", max_conns)
            span.set_attribute("pg.blocked_queries", blocked_conns)

            reasons: list[str] = []
            if latency_ms > config.max_latency_ms:
                reasons.append(f"latencia {latency_ms}ms > {config.max_latency_ms}ms")
            if conn_ratio > config.max_active_connections_ratio:
                reasons.append(
                    f"conexiones {active_conns}/{max_conns} ({conn_ratio:.0%}) > "
                    f"{config.max_active_connections_ratio:.0%}"
                )
            if blocked_conns > config.max_blocked_queries:
                reasons.append(f"bloqueos {blocked_conns} > {config.max_blocked_queries}")

            if reasons:
                msg = "; ".join(reasons)
                pg_check_up_gauge.set(0, labels)
                span.set_status(Status(StatusCode.ERROR, msg))
                return DatabaseCheckResult(
                    name=config.name,
                    status="degraded",
                    latency_ms=latency_ms,
                    active_connections=active_conns,
                    max_connections=max_conns,
                    blocked_queries=blocked_conns,
                    message=msg,
                )

            pg_check_up_gauge.set(1, labels)
            span.set_status(Status(StatusCode.OK))
            return DatabaseCheckResult(
                name=config.name,
                status="ok",
                latency_ms=latency_ms,
                active_connections=active_conns,
                max_connections=max_conns,
                blocked_queries=blocked_conns,
                message=f"ok ({active_conns}/{max_conns} conn, {blocked_conns} locks)",
            )

        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            pg_check_up_gauge.set(0, labels)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            return DatabaseCheckResult(
                name=config.name,
                status="error",
                latency_ms=latency_ms,
                active_connections=0,
                max_connections=0,
                blocked_queries=0,
                message=str(exc),
            )
