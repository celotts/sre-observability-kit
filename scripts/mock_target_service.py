import argparse
import json
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class MockHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/ok":
            self._send_json(200, {"status": "ok", "mode": "healthy"})
            return

        if parsed.path == "/slow":
            delay_ms = float(params.get("delay_ms", ["800"])[0])
            time.sleep(max(delay_ms, 0.0) / 1000.0)
            self._send_json(200, {"status": "ok", "mode": "slow", "delay_ms": delay_ms})
            return

        if parsed.path == "/flaky":
            fail_rate = float(params.get("fail_rate", ["0.6"])[0])
            if random.random() < fail_rate:
                self._send_json(503, {"status": "error", "mode": "flaky_fail"})
                return
            self._send_json(200, {"status": "ok", "mode": "flaky_pass"})
            return

        if parsed.path == "/bad-contract":
            self._send_json(200, {"status": "unexpected_schema", "ok": False})
            return

        self._send_json(404, {"status": "not_found", "path": parsed.path})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Servidor simulado para escenarios de prueba SRE")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), MockHandler)
    print(f"Mock target service escuchando en http://{args.host}:{args.port} (Ctrl+C para detener)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMock target service detenido.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
