import pytest

from sre_kit.workflows import run_instrumented_workflow


def test_run_instrumented_workflow_success() -> None:
    value = run_instrumented_workflow(
        workflow_name="unit_test_flow",
        operation=lambda: {"processed": 42},
        attributes={"step": "transform"},
        capture_exceptions=False,
    )
    assert value == {"processed": 42}


def test_run_instrumented_workflow_propagates_validation_error() -> None:
    def failing_op() -> None:
        raise ValueError("monto negativo no permitido")

    with pytest.raises(ValueError, match="monto negativo"):
        run_instrumented_workflow(
            workflow_name="unit_test_validation_flow",
            operation=failing_op,
            capture_exceptions=False,
        )
