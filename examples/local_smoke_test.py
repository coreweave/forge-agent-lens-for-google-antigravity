#!/usr/bin/env python3
"""Exercise the installed hook and OTLP export without contacting Agent Lens.

Run from the repository root after ``uv sync --group test``:

    uv run python examples/local_smoke_test.py
"""

from __future__ import annotations

import gzip
import json
import os
import queue
import shutil

# The smoke test runs a fixed argument list and never enables a shell.
import subprocess  # nosec B404
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from forge_antigravity import __version__

ROOT = Path(__file__).resolve().parents[1]


class _LocalHTTPServer(ThreadingHTTPServer):
    """Bind without the reverse-DNS lookup performed by HTTPServer."""

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        address = self.server_address
        host_value = address[0]
        if isinstance(host_value, (bytes, bytearray)):
            self.server_name = bytes(host_value).decode()
        else:
            self.server_name = host_value
        self.server_port = address[1]


def otel_attribute(container: Any, key: str) -> Any:
    attribute = next((item for item in container.attributes if item.key == key), None)
    if attribute is None:
        return None
    kind = attribute.value.WhichOneof("value")
    return getattr(attribute.value, kind) if kind else None


@contextmanager
def local_otlp_receiver() -> Iterator[tuple[str, queue.Queue[bytes]]]:
    """Serve the OTLP endpoint used by Forge and return captured requests."""
    captured_requests: queue.Queue[bytes] = queue.Queue()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/agents/otel/v1/traces":
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers["content-length"]))
            if self.headers.get("content-encoding") == "gzip":
                body = gzip.decompress(body)
            captured_requests.put(body)
            response = ExportTraceServiceResponse().SerializeToString()
            self.send_response(200)
            self.send_header("content-type", "application/x-protobuf")
            self.send_header("content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = _LocalHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        address = server.server_address
        host_value = address[0]
        host = host_value.decode() if isinstance(host_value, bytes) else host_value
        port = address[1]
        yield f"http://{host}:{port}", captured_requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _write_transcript(path: Path) -> None:
    records = [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-01-02T12:00:00Z",
            "content": "Run the local smoke test.",
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-01-02T12:00:01Z",
            "thinking": "Use the harmless command.",
            "tool_calls": [
                {
                    "id": "smoke-call",
                    "name": "run_command",
                    "args": {"CommandLine": "printf smoke-ok"},
                }
            ],
        },
        {
            "step_index": 2,
            "source": "MODEL",
            "type": "RUN_COMMAND",
            "status": "DONE",
            "created_at": "2026-01-02T12:00:02Z",
            "content": "smoke-ok",
        },
        {
            "step_index": 3,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-01-02T12:00:03Z",
            "content": "The smoke test passed.",
        },
    ]
    path.write_text(
        "".join(f"{json.dumps(record, separators=(',', ':'))}\n" for record in records),
        encoding="utf-8",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="forge-agent-lens-for-google-antigravity-smoke-"
    ) as temporary:
        root = Path(temporary)
        artifact = root / "artifact"
        logs = artifact / ".system_generated" / "logs"
        logs.mkdir(parents=True)
        transcript = logs / "transcript.jsonl"
        _write_transcript(transcript)
        payload = {
            "conversationId": "local-smoke-test",
            "artifactDirectoryPath": str(artifact),
            "transcriptPath": str(transcript),
            "workspacePaths": [str(ROOT)],
            "modelName": "smoke-test-model",
            "executionNum": 1,
            "fullyIdle": True,
            "terminationReason": "model_stop",
        }

        with local_otlp_receiver() as (base_url, requests):
            executable_path = (
                f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"
            )
            executable = shutil.which(
                "forge-agent-lens-for-google-antigravity", path=executable_path
            )
            if executable is None:
                raise RuntimeError(
                    "forge-agent-lens-for-google-antigravity is not installed on PATH"
                )
            env = {
                **os.environ,
                "FORGE_TRACE_PROJECT": "local/smoke-test",
                "PATH": executable_path,
                "WANDB_API_KEY": "local-smoke-test-key",
                "WF_TRACE_SERVER_URL": base_url,
            }
            completed = subprocess.run(  # nosec B603
                [executable],
                input=json.dumps(payload),
                capture_output=True,
                check=False,
                cwd=ROOT,
                env=env,
                text=True,
                timeout=20,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"hook exited with {completed.returncode}: {completed.stderr.strip()}"
                )
            if json.loads(completed.stdout) != {"decision": "allow"}:
                raise RuntimeError(f"unexpected hook response: {completed.stdout.strip()}")
            request = ExportTraceServiceRequest.FromString(requests.get(timeout=5))

    spans = [
        span
        for resource_spans in request.resource_spans
        for scope_spans in resource_spans.scope_spans
        for span in scope_spans.spans
    ]
    names = [span.name for span in spans]
    expected = {
        "invoke_agent Antigravity",
        "chat smoke-test-model",
        "execute_tool run_command",
    }
    missing = expected.difference(names)
    if missing:
        raise RuntimeError(f"missing expected spans: {', '.join(sorted(missing))}")

    expected_attributes = {
        "forge.integration.name": "antigravity",
        "forge.integration.version": __version__,
        "forge.integration.antigravity.execution.number": 1,
        "forge.integration.antigravity.termination.reason": "model_stop",
    }
    for span in spans:
        for key, expected_value in expected_attributes.items():
            if otel_attribute(span, key) != expected_value:
                raise RuntimeError(f"missing expected attribute: {key}")
    workspace_paths = otel_attribute(spans[0], "forge.integration.antigravity.workspace.paths")
    if workspace_paths is None or [value.string_value for value in workspace_paths.values] != [
        str(ROOT)
    ]:
        raise RuntimeError("missing expected Antigravity workspace paths")

    print("Local hook-to-OTLP smoke test passed.")
    print(f"Captured {len(names)} spans: {', '.join(names)}")
    print("Validated Forge and Antigravity trace attributes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
