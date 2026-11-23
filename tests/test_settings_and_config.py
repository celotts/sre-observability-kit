from pathlib import Path

import pytest
from pydantic import ValidationError

from sre_kit.settings import Settings
from sre_kit.synthetics import load_scenarios_config


def test_settings_builds_postgres_dsn() -> None:
    settings = Settings(
        _env_file=None,
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="test_db",
        POSTGRES_USER="tester",
        POSTGRES_PASSWORD="secret_value",
    )
    assert settings.postgres_dsn == "postgresql://tester:secret_value@localhost:5432/test_db"


def test_load_example_scenarios_yaml() -> None:
    cfg = load_scenarios_config(Path("config/scenarios.example.yaml"))
    assert len(cfg.database_checks) >= 1
    assert len(cfg.synthetic_journeys) >= 1
    assert cfg.defaults.timeout_seconds > 0


def test_invalid_config_raises_validation_error(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad_scenario.yaml"
    bad_file.write_text(
        """
defaults:
  timeout_seconds: -1
""",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_scenarios_config(bad_file)
