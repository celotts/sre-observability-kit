# SRE Observability Kit

Kit modular y configurable de observabilidad funcional, *synthetic checks* y diagnóstico profundo de PostgreSQL con Python, OpenTelemetry, Prometheus y Grafana.

## Arranque rápido

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
docker compose -f compose/compose.yaml --env-file .env up -d
python scripts/check_env.py
pytest
 source /Users/carloslott/develop/python/sre-observability-kit/.venv/bin/activate
