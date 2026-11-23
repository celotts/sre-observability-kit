import asyncio

import httpx

from sre_kit.synthetics import DefaultsConfig, SyntheticJourneyConfig, run_synthetic_journey


def test_synthetic_journey_success_and_json_validation(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Probe"] == "true"
        return httpx.Response(200, json={"status": "ok", "version": "1.0"})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    class PatchedAsyncClient(original_async_client):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

    journey = SyntheticJourneyConfig(
        name="api_health_json",
        url="http://service.local/health",
        expected_status=200,
        expected_json_key="status",
        expected_json_value="ok",
        headers={"X-Probe": "true"},
    )
    defaults = DefaultsConfig(timeout_seconds=2.0, max_latency_ms=1000.0)

    result = asyncio.run(run_synthetic_journey(journey, defaults))
    assert result.status == "ok"
    assert result.http_status == 200


def test_synthetic_journey_fails_on_wrong_status(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "unavailable"})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    class PatchedAsyncClient(original_async_client):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

    journey = SyntheticJourneyConfig(
        name="api_down_check",
        url="http://service.local/health",
        expected_status=200,
    )
    defaults = DefaultsConfig(timeout_seconds=2.0, max_latency_ms=1000.0)

    result = asyncio.run(run_synthetic_journey(journey, defaults))
    assert result.status == "failed"
    assert result.http_status == 503
