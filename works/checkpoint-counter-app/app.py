"""Local HTTP entry point for the Checkpoint Counter Lab."""

from __future__ import annotations

import json
import mimetypes
import time
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from model import ProblemError, default_problem, solve_problem


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


class AppHandler(BaseHTTPRequestHandler):
    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        path = urlparse(self.path).path
        if path == "/api/defaults":
            self._json(default_problem())
            return
        if path == "/api/health":
            self._json({"status": "ok"})
            return
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC not in target.parents and target != STATIC:
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        path = urlparse(self.path).path
        if path != "/api/solve":
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 1_000_000:
                raise ProblemError("The submitted problem is empty or too large.")
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            started = time.perf_counter()
            result = solve_problem(payload)
            result["summary"]["runtime_ms"] = round((time.perf_counter() - started) * 1000, 1)
            self._json(result)
        except (ProblemError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, status=400)
        except Exception as exc:  # keep the local UI useful while surfacing unexpected failures
            print(f"[checkpoint-counter] solve failed: {exc!r}")
            self._json({"error": "The model could not be solved. Check the submitted inputs."}, status=500)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[checkpoint-counter] {self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Checkpoint Counter Lab server.")
    parser.add_argument("--port", type=int, default=8765, help="Local port (default: 8765)")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), AppHandler)
    print(f"Checkpoint Counter Lab: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
