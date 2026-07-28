import hashlib
import hmac
import io
import json
import os
import re
import sys
import types
import unittest
import zipfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from archive_logs import extract_error_log


class Response:
    def __init__(self, status_code=200, content=b"", payload=None):
        self.status_code = status_code
        self.content = content
        self._payload = payload or {}

    def json(self):
        return self._payload


def zip_bytes(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, text in entries.items():
            zf.writestr(name, text)
    return out.getvalue()


def zip_file(entries):
    return zipfile.ZipFile(io.BytesIO(zip_bytes(entries)))


class ArchiveSelectionTests(unittest.TestCase):
    def test_multiple_txt_entries_selects_failed_job_log(self):
        zf = zip_file({
            "Build/1_Set up job.txt": "setup ok",
            "Build/4_Run Python build.txt": "Traceback (most recent call last):\nboom",
            "Lint/2_Run lint.txt": "lint ok",
        })

        def get(url, **kwargs):
            return Response(payload={
                "jobs": [{
                    "name": "Build",
                    "conclusion": "failure",
                    "steps": [
                        {"name": "Set up job", "number": 1, "conclusion": "success"},
                        {"name": "Run Python build", "number": 4, "conclusion": "failure"},
                    ],
                }]
            })

        extracted = extract_error_log(zf, "Wysdomos/mlb-slate", 30358446123, {}, get=get)

        self.assertEqual(extracted.entry, "Build/4_Run Python build.txt")
        self.assertIn("failed job metadata match", extracted.reason)
        self.assertIn("Traceback", extracted.error_log)

    def test_normal_archive_falls_back_to_failure_signature(self):
        zf = zip_file({
            "Setup/1_Set up job.txt": "setup ok",
            "Build/9_Run build.txt": 'File "build_day46.py", line 1\nException: broken',
        })

        def get(url, **kwargs):
            return Response(payload={"jobs": []})

        extracted = extract_error_log(zf, "Wysdomos/mlb-slate", 1, {}, get=get)

        self.assertEqual(extracted.entry, "Build/9_Run build.txt")
        self.assertIn("failure signature scan", extracted.reason)
        match = re.search(r'File "([^"]+\.py)"', extracted.error_log)
        self.assertEqual(match.group(1), "build_day46.py")


class FakeRequest:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")
        secret = os.environ["WEBHOOK_SECRET"].encode("utf-8")
        signature = hmac.new(secret, self._body, hashlib.sha256).hexdigest()
        self.headers = {"X-Hub-Signature-256": f"sha256={signature}"}

    def get_data(self):
        return self._body

    def get_json(self, silent=False):
        return json.loads(self._body)


def import_main_with_stubs():
    for name in ("main", "firebase_functions", "google", "google.genai", "requests"):
        sys.modules.pop(name, None)

    os.environ["WEBHOOK_SECRET"] = "test-secret"
    os.environ["GITHUB_TOKEN"] = "gh-test"
    os.environ["TELEGRAM_BOT_TOKEN"] = "telegram-test"
    os.environ["TELEGRAM_CHAT_ID"] = "chat-test"

    requests_stub = types.ModuleType("requests")
    requests_stub.get = lambda *args, **kwargs: Response()
    requests_stub.post = lambda *args, **kwargs: Response()
    requests_stub.put = lambda *args, **kwargs: Response()
    sys.modules["requests"] = requests_stub

    firebase_stub = types.ModuleType("firebase_functions")

    class ResponseClass:
        def __init__(self, body="", status=200):
            self.body = body
            self.status_code = status
            self.status = status

    class HttpsFn:
        Request = object
        Response = ResponseClass

        @staticmethod
        def on_request(*args, **kwargs):
            return lambda fn: fn

    class Options:
        class MemoryOption:
            MB_512 = "512MiB"

    firebase_stub.https_fn = HttpsFn
    firebase_stub.options = Options
    sys.modules["firebase_functions"] = firebase_stub

    google_stub = types.ModuleType("google")
    genai_stub = types.ModuleType("google.genai")
    genai_stub.Client = object
    google_stub.genai = genai_stub
    sys.modules["google"] = google_stub
    sys.modules["google.genai"] = genai_stub

    import main
    return main


class MainHandlerSafetyTests(unittest.TestCase):
    def test_empty_archive_reports_and_returns_200(self):
        main = import_main_with_stubs()
        notifications = []
        archive = zip_bytes({"README.md": "no txt logs here"})

        main.notify_mobile = notifications.append
        main.fetch_github_log_archive = lambda *args, **kwargs: Response(200, archive)

        out = io.StringIO()
        req = FakeRequest({
            "repository": "Wysdomos/mlb-slate",
            "run_id": 30358446123,
            "sha": "abc123",
        })
        with redirect_stdout(out):
            resp = main.auto_heal_webhook(req)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("contained no readable step logs", resp.body)
        self.assertIn("README.md", out.getvalue())
        self.assertIn("contained no readable step logs", notifications[-1])

    def test_unhandled_exception_reports_and_returns_200(self):
        main = import_main_with_stubs()
        notifications = []
        main.notify_mobile = notifications.append

        def raise_boom(req):
            raise RuntimeError("forced boom")

        main._auto_heal_webhook_impl = raise_boom
        resp = main.auto_heal_webhook(object())

        self.assertEqual(resp.status_code, 200)
        self.assertIn("RuntimeError", resp.body)
        self.assertIn("forced boom", notifications[-1])


if __name__ == "__main__":
    unittest.main()
