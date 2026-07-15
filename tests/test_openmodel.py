"""Open-model baseline: OpenAICompatBackend against a mock OpenAI-compatible server.

Proves the open-weight-model path end-to-end (the same wire protocol vLLM /
SGLang / llama.cpp serve) without any external model or network — a tiny
http.server in a thread stands in for the serving endpoint.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from acme.models.backends import OfflineDeferBackend, OpenAICompatBackend


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or "{}")
        # echo the model + last message so the test can assert round-trip
        last = body["messages"][-1]["content"]
        payload = {
            "choices": [{
                "message": {
                    "content": f"served:{body['model']}:{last}",
                    "tool_calls": [{"id": "c1", "type": "function",
                                    "function": {"name": "noop", "arguments": "{}"}}],
                }
            }]
        }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    host, port = httpd.server_address
    yield f"http://{host}:{port}/v1"
    httpd.shutdown()


def test_backend_drives_openai_compatible_endpoint(server):
    backend = OpenAICompatBackend(server, model_map={"planner-high": "llama-3.3-70b"})
    result = backend.complete(profile="planner-high",
                              messages=[{"role": "user", "content": "hello"}])
    assert result.status == "ok"
    assert result.text == "served:llama-3.3-70b:hello"
    assert result.tool_calls and result.tool_calls[0]["function"]["name"] == "noop"
    assert result.meta["model"] == "llama-3.3-70b"


def test_backend_fails_closed_on_unreachable_endpoint():
    backend = OpenAICompatBackend("http://127.0.0.1:1/v1")  # nothing listening
    result = backend.complete(profile="x", messages=[{"role": "user", "content": "y"}])
    assert result.status == "error" and result.text == ""  # never a fabricated answer


def test_offline_backend_defers_without_network():
    result = OfflineDeferBackend().complete(profile="x", messages=[])
    assert result.status == "deferred"
