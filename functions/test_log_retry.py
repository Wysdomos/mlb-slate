import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log_retry import (
    LOG_FINALIZE_INITIAL_DELAY_SECONDS,
    fetch_github_log_archive,
)


class Response:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class LogRetryTests(unittest.TestCase):
    def test_no_fetch_before_initial_delay_elapses(self):
        clock = FakeClock()
        calls = []

        def get(*args, **kwargs):
            calls.append(clock.now)
            return Response(200)

        def sleep(seconds):
            self.assertFalse(calls)
            self.assertEqual(seconds, LOG_FINALIZE_INITIAL_DELAY_SECONDS)
            clock.sleep(seconds)

        resp = fetch_github_log_archive(
            "https://example.test/logs",
            {},
            get=get,
            sleep=sleep,
            monotonic=clock.monotonic,
            run_id=123,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(calls, [LOG_FINALIZE_INITIAL_DELAY_SECONDS])

    def test_log_available_at_150s_is_read(self):
        clock = FakeClock()
        calls = []

        def get(*args, **kwargs):
            calls.append(clock.now)
            return Response(200 if clock.now >= 150 else 404)

        resp = fetch_github_log_archive(
            "https://example.test/logs",
            {},
            get=get,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            timeout_seconds=180,
            initial_delay=8,
            max_delay=45,
            run_id=456,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(calls[-1], 150)
        self.assertLess(calls[-1], 180)
        self.assertEqual(calls[0], LOG_FINALIZE_INITIAL_DELAY_SECONDS)

    def test_permanently_unavailable_terminates_cleanly(self):
        clock = FakeClock()
        out = io.StringIO()

        def get(*args, **kwargs):
            return Response(404)

        with redirect_stdout(out):
            resp = fetch_github_log_archive(
                "https://example.test/logs",
                {},
                get=get,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
                timeout_seconds=20,
                initial_delay=8,
                max_delay=45,
                run_id=789,
            )

        self.assertEqual(resp.status_code, 404)
        self.assertIn("waiting 120s for run 789 logs to finalize", out.getvalue())
        self.assertIn("Logs not ready for run 789", out.getvalue())
        self.assertGreaterEqual(clock.now, LOG_FINALIZE_INITIAL_DELAY_SECONDS + 20)


if __name__ == "__main__":
    unittest.main()
