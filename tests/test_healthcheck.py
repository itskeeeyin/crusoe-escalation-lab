#!/usr/bin/env python3
"""Offline tests for healthcheck.py. No API key and no network."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import healthcheck
import practice_lab


def _ok_body(model, content="ready"):
    return {
        "id": "chatcmpl-test",
        "model": model,
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


def _empty_body(model):
    return {
        "id": "chatcmpl-empty",
        "model": model,
        "choices": [
            {
                "finish_reason": "length",
                "message": {"role": "assistant", "content": None, "reasoning": "thinking"},
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 32,
            "total_tokens": 42,
            "completion_tokens_details": {"reasoning_tokens": 32},
        },
    }


class HealthcheckTests(unittest.TestCase):
    def _run(self, responses, latency_ms=15_000, models=None):
        from tests.test_practice_lab import FakeSession

        session = FakeSession(responses)
        return healthcheck.run_once(
            api_key="super-secret-lab-key-value",
            models=models or [practice_lab.CHEAP_MODEL, practice_lab.ALT_MODEL],
            base_url=practice_lab.BASE_URL,
            latency_ms=latency_ms,
            session=session,
        )

    def test_healthy_probes_pass(self):
        from tests.test_practice_lab import FakeResponse

        models_payload = {"data": [{"id": practice_lab.CHEAP_MODEL, "pricing": {"prompt": 0.05, "completion": 0.20}}]}
        headers = {"Content-Type": "application/json", "x-ratelimit-limit-requests": "600"}
        result = self._run(
            [
                FakeResponse(200, models_payload, headers),
                FakeResponse(200, _ok_body(practice_lab.CHEAP_MODEL), headers),
                FakeResponse(200, _ok_body(practice_lab.ALT_MODEL), headers),
            ]
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(result["probes"][0]["content"], "ready")
        table = healthcheck.format_table(result["probes"])
        self.assertIn("OK", table)
        self.assertIn(practice_lab.CHEAP_MODEL, table)
        self.assertNotIn("super-secret-lab-key-value", json.dumps(result))

    def test_empty_content_fails_with_named_class(self):
        from tests.test_practice_lab import FakeResponse

        headers = {"Content-Type": "application/json"}
        result = self._run(
            [
                FakeResponse(200, {"data": []}, headers),
                FakeResponse(200, _empty_body(practice_lab.CHEAP_MODEL), headers),
            ],
            models=[practice_lab.CHEAP_MODEL],
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any(str(i).startswith("[empty_reply]") for i in result["_issue_objects"]))
        self.assertIsInstance(result["_issue_objects"][0], practice_lab.EmptyReplyIssue)

    def test_http_error_fails_with_named_class(self):
        from tests.test_practice_lab import FakeResponse

        headers = {"Content-Type": "application/json"}
        result = self._run(
            [
                FakeResponse(200, {"data": []}, headers),
                FakeResponse(503, {"error": {"message": "busy", "type": "unavailable"}}, headers),
            ],
            models=[practice_lab.CHEAP_MODEL],
        )
        self.assertFalse(result["ok"])
        self.assertIsInstance(result["_issue_objects"][0], healthcheck.HttpErrorIssue)
        self.assertIn("[http_error]", str(result["_issue_objects"][0]))
        self.assertIn("503", str(result["_issue_objects"][0]))

    def test_high_latency_fails_with_named_class(self):
        rec = {
            "status_code": 200,
            "elapsed_ms": 20_000,
            "body": _ok_body(practice_lab.CHEAP_MODEL),
            "headers": {},
        }

        class Stub:
            def chat(self, *args, **kwargs):
                return rec

        probe = healthcheck.probe_model(Stub(), practice_lab.CHEAP_MODEL, latency_ms=15_000)
        self.assertFalse(probe["ok"])
        self.assertIsInstance(probe["issue_objects"][0], healthcheck.HighLatencyIssue)
        self.assertIn("[high_latency]", probe["issues"][0])

    def test_retries_without_reasoning_effort_after_400(self):
        from tests.test_practice_lab import FakeResponse

        headers = {"Content-Type": "application/json"}
        rejected = {
            "error": {
                "message": "Harmony does not support reasoning_effort='none'",
                "type": "BadRequestError",
                "param": "reasoning_effort",
                "code": "400",
            }
        }
        result = self._run(
            [
                FakeResponse(200, {"data": []}, headers),
                FakeResponse(400, rejected, headers),
                FakeResponse(200, _ok_body(practice_lab.ALT_MODEL), headers),
            ],
            models=[practice_lab.ALT_MODEL],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["probes"][0]["content"], "ready")
        self.assertIn("retried without reasoning_effort", result["probes"][0]["note"])

    def test_missing_key_exits_2(self):

        with patch.dict("os.environ", {}, clear=True):
            code = healthcheck.main(["--models", practice_lab.CHEAP_MODEL])
        self.assertEqual(code, 2)

    def test_interval_stops_after_max_runs(self):
        from tests.test_practice_lab import FakeResponse, FakeSession

        headers = {"Content-Type": "application/json"}
        responses = [
            FakeResponse(200, {"data": []}, headers),
            FakeResponse(200, _ok_body(practice_lab.CHEAP_MODEL), headers),
            FakeResponse(200, {"data": []}, headers),
            FakeResponse(200, _ok_body(practice_lab.CHEAP_MODEL), headers),
        ]
        session = FakeSession(responses)
        runs = {"n": 0}
        original = healthcheck.run_once

        def wrapped(**kwargs):
            runs["n"] += 1
            kwargs["session"] = session
            return original(**kwargs)

        with patch.dict("os.environ", {"CRUSOE_API_KEY": "super-secret-lab-key-value"}):
            with patch.object(healthcheck, "run_once", side_effect=wrapped):
                with patch.object(healthcheck, "print_run"):
                    with patch.object(healthcheck.time, "sleep") as slept:
                        code = healthcheck.main(
                            [
                                "--models",
                                practice_lab.CHEAP_MODEL,
                                "--interval",
                                "0.01",
                                "--max-runs",
                                "2",
                            ]
                        )
        self.assertEqual(code, 0)
        self.assertEqual(runs["n"], 2)
        slept.assert_called()

    def test_format_table_marks_failures(self):
        table = healthcheck.format_table(
            [
                {
                    "ok": False,
                    "model": "demo-model",
                    "status_code": 500,
                    "elapsed_ms": 12.3,
                    "content_display": "null",
                    "finish_reason": None,
                }
            ]
        )
        self.assertIn("FAIL", table)
        self.assertIn("500", table)
        self.assertIn("demo-model", table)


if __name__ == "__main__":
    unittest.main()
