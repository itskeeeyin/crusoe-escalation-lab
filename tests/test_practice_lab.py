#!/usr/bin/env python3
"""Offline tests for the Crusoe practice lab. No API key and no network."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import practice_lab  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, json_body=None, headers=None, text=None, lines=None):
        self.status_code = status_code
        self._json_body = json_body
        self.headers = headers or {"Content-Type": "application/json"}
        if text is not None:
            self.text = text
        elif json_body is not None:
            self.text = json.dumps(json_body)
        else:
            self.text = ""
        self._lines = lines

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines or [])


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        if not self.responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        return self.responses.pop(0)


class SanitizeTests(unittest.TestCase):
    def test_redacts_authorization_and_secret(self):
        secret = "super-secret-lab-key-value"
        payload = {
            "Authorization": f"Bearer {secret}",
            "headers": {"authorization": f"Bearer {secret}", "x-ratelimit-limit-requests": "30"},
            "account_id": "acct_123",
            "body": {"message": f"token {secret} leaked"},
        }
        cleaned = practice_lab.sanitize(payload, secret)
        blob = json.dumps(cleaned)
        self.assertNotIn(secret, blob)
        self.assertEqual(cleaned["Authorization"], "[REDACTED]")
        self.assertEqual(cleaned["headers"]["authorization"], "[REDACTED]")
        self.assertEqual(cleaned["account_id"], "[REDACTED]")
        self.assertIn("[REDACTED]", cleaned["body"]["message"])
        self.assertEqual(cleaned["headers"]["x-ratelimit-limit-requests"], "30")

    def test_contains_secret(self):
        self.assertTrue(practice_lab.contains_secret({"a": {"b": "abcXYZ"}}, "abcXYZ"))
        self.assertFalse(practice_lab.contains_secret({"a": "ok"}, "abcXYZ"))

    def test_write_results_aborts_if_secret_present(self):
        secret = "super-secret-lab-key-value"
        path = Path("/tmp/crusoe-practice-should-not-write.json")
        path.unlink(missing_ok=True)
        with self.assertRaises(RuntimeError):
            practice_lab.write_results({"note": f"has {secret}"}, path, secret)
        self.assertFalse(path.exists())


class FailureClassTests(unittest.TestCase):
    def test_named_failures_are_human_readable(self):
        err = practice_lab.EmptyReplyIssue(
            "HTTP 200 from nvidia/Nemotron-3.5-Lightning-30B-A3B but "
            "message.content is None (finish_reason=length, completion_tokens=64)."
        )
        text = str(err)
        self.assertTrue(text.startswith("[empty_reply]"))
        self.assertIn("finish_reason=length", text)
        self.assertIn("[auth_failure]", str(practice_lab.AuthIssue("HTTP 401 invalid key")))
        self.assertIn("[wrong_model]", str(practice_lab.WrongModelIssue("HTTP 404")))
        self.assertIn("[rate_limit]", str(practice_lab.RateLimitIssue("HTTP 429")))
        self.assertIn("[malformed_request]", str(practice_lab.MalformedRequestIssue("HTTP 400")))

    def test_missing_key_message(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(practice_lab.MissingApiKeyError) as ctx:
                practice_lab.load_api_key()
        self.assertIn("CRUSOE_API_KEY", str(ctx.exception))
        self.assertIn("[missing_api_key]", str(ctx.exception))


class EmptyReplyClassificationTests(unittest.TestCase):
    def test_detects_null_content_with_length_finish(self):
        record = {
            "status_code": 200,
            "body": {
                "model": practice_lab.CHEAP_MODEL,
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"role": "assistant", "content": None, "reasoning_content": "thinking..."},
                    }
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 64, "total_tokens": 104},
            },
        }
        self.assertTrue(practice_lab.is_empty_success(record))
        self.assertIn("message.content is None", practice_lab.describe_empty(record))

    def test_non_empty_is_not_a_hit(self):
        record = {
            "status_code": 200,
            "body": {
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "Cache hits cut TTFT."}}
                ]
            },
        }
        self.assertFalse(practice_lab.is_empty_success(record))


class SseAndCostTests(unittest.TestCase):
    def test_parse_sse(self):
        lines = [
            "data: {\"choices\":[{\"delta\":{\"reasoning_content\":\"hmm\"}}]}",
            "data: {\"choices\":[{\"delta\":{\"content\":\"OK\"}}]}",
            "data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":5,\"completion_tokens\":1,\"total_tokens\":6}}",
            "data: [DONE]",
        ]
        parsed = practice_lab.parse_sse(lines)
        self.assertEqual(parsed["content"], "OK")
        self.assertEqual(parsed["finish_reason"], "stop")
        self.assertEqual(parsed["reasoning_chars"], 3)
        self.assertEqual(parsed["usage"]["total_tokens"], 6)
        self.assertEqual(parsed["first_content_event"], 2)

    def test_estimate_cost_uses_per_million_prices(self):
        records = [
            {
                "body": {
                    "model": practice_lab.CHEAP_MODEL,
                    "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "total_tokens": 2_000_000},
                }
            }
        ]
        cost = practice_lab.estimate_cost(records, practice_lab.FALLBACK_PRICES)
        self.assertEqual(cost["estimated_usd"], 0.25)


class MockedLabTests(unittest.TestCase):
    def test_run_lab_with_mocked_session(self):
        empty_body = {
            "id": "chatcmpl-test",
            "model": practice_lab.CHEAP_MODEL,
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": None, "reasoning_content": "planning"},
                }
            ],
            "usage": {"prompt_tokens": 30, "completion_tokens": 64, "total_tokens": 94},
        }
        ok_body = {
            "id": "chatcmpl-ok",
            "model": practice_lab.CHEAP_MODEL,
            "choices": [
                {"finish_reason": "stop", "message": {"role": "assistant", "content": "Cache hits cut TTFT."}}
            ],
            "usage": {"prompt_tokens": 30, "completion_tokens": 8, "total_tokens": 38},
        }
        err_404 = {"error": {"type": "invalid_request_error", "message": "model not found", "code": "model_not_found"}}
        err_401 = {"error": {"type": "auth_error", "message": "Invalid API key", "code": "invalid_api_key"}}
        err_400 = {"error": {"type": "invalid_request_error", "message": "messages must be an array", "code": "invalid_body"}}
        models = {"data": [{"id": practice_lab.CHEAP_MODEL, "pricing": {"prompt": 0.05, "completion": 0.20}}]}
        rate_headers = {
            "Content-Type": "application/json",
            "x-ratelimit-limit-requests": "30",
            "x-ratelimit-remaining-requests": "29",
            "x-ratelimit-limit-tokens": "500000",
            "x-ratelimit-remaining-tokens": "499900",
        }

        # Order in run_lab:
        # GET /models
        # empty: 64 (empty), then maybe stops, then fix none, fix cap
        # wrong typo, deprecated
        # auth bad, missing
        # malformed raw, invalid max_tokens
        # latency nonstream, stream
        # rate probe (burst skipped)
        responses = [
            FakeResponse(200, models, rate_headers),
            FakeResponse(200, empty_body, rate_headers),
            FakeResponse(200, ok_body, rate_headers),
            FakeResponse(200, ok_body, rate_headers),
            FakeResponse(404, err_404, rate_headers),
            FakeResponse(404, err_404, rate_headers),
            FakeResponse(401, err_401, rate_headers),
            FakeResponse(401, err_401, rate_headers),
            FakeResponse(400, err_400, rate_headers),
            FakeResponse(400, err_400, rate_headers),
            FakeResponse(200, ok_body, rate_headers),
            FakeResponse(
                200,
                headers={**rate_headers, "Content-Type": "text/event-stream"},
                lines=[
                    'data: {"choices":[{"delta":{"content":"ready"}}]}',
                    'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":8,"completion_tokens":1,"total_tokens":9}}',
                    "data: [DONE]",
                ],
            ),
            FakeResponse(200, ok_body, rate_headers),
        ]
        session = FakeSession(responses)
        results = practice_lab.run_lab(
            api_key="super-secret-lab-key-value",
            session=session,
            skip_burst=True,
            burst=0,
        )
        by_id = {s["id"]: s for s in results["scenarios"]}
        self.assertTrue(by_id["empty_reply"]["reproduced"])
        self.assertTrue(by_id["empty_reply"]["fix_succeeded"])
        self.assertTrue(by_id["wrong_model"]["reproduced"])
        self.assertTrue(by_id["auth_failure"]["reproduced"])
        self.assertTrue(by_id["malformed_request"]["reproduced"])
        self.assertTrue(by_id["latency_streaming"]["reproduced"])
        self.assertFalse(by_id["rate_limits"]["reproduced_429"])
        self.assertIn("[empty_reply]", by_id["empty_reply"]["issue"])
        self.assertNotIn("super-secret-lab-key-value", json.dumps(results))
        self.assertGreater(results["usage_and_cost"]["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
