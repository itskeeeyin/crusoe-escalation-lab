#!/usr/bin/env python3
"""Crusoe Serverless Inference escalation practice lab.

Reproduces common customer-facing API issues against a personal Crusoe
Intelligence account and writes redacted evidence to results.json.

Requires CRUSOE_API_KEY in the environment. The key is never printed or
written to disk.

Usage:
    export CRUSOE_API_KEY=...   # do not commit or paste this
    python practice_lab.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.inference.crusoecloud.com/v1"
CHEAP_MODEL = "nvidia/Nemotron-3.5-Lightning-30B-A3B"
ALT_MODEL = "openai/gpt-oss-120b"
DEFAULT_RESULTS = Path(__file__).resolve().parent / "results.json"

# Public list prices used only if /v1/models does not include pricing.
# Nemotron 3.5 Lightning: $0.05 input / $0.20 output per million tokens
# (https://www.crusoe.ai/models/nemotron-3-5-lightning-30b-a3b).
FALLBACK_PRICES = {
    "nvidia/Nemotron-3.5-Lightning-30B-A3B": {
        "prompt": 0.05,
        "completion": 0.20,
    },
}

# Documented Serverless Inference defaults, from
# https://docs.crusoe.ai/serverless-inference/rate-limits/
DOCUMENTED_RATE_LIMITS = {
    "source": "https://docs.crusoe.ai/serverless-inference/rate-limits/",
    "scope": "per project and per model, one-minute window",
    "no_payment_method": {"tpm": 500_000, "rpm": 30},
    "payment_method_added": {"tpm": 2_000_000, "rpm": 600},
    "status_codes": {
        "429": "Project exceeded TPM or RPM for the model.",
        "503": "Request is within limits, but the shared endpoint is under high load.",
    },
    "headers": [
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-limit-requests",
        "x-ratelimit-remaining-requests",
    ],
    "retry_guidance": "Retry 429 and 503 with exponential backoff and jitter; limits reset each minute.",
}

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "cookie",
    "set-cookie",
    "x-auth-token",
}

SENSITIVE_ID_KEYS = {
    "organization",
    "organization_id",
    "org_id",
    "orgid",
    "project_id",
    "projectid",
    "account_id",
    "accountid",
    "user_id",
    "userid",
    "tenant_id",
    "tenantid",
    "customer_id",
    "team_id",
    "api_key",
    "apikey",
}

FAKE_KEY = "sk-crusoe-practice-fake-key-not-real"
WRONG_MODEL = "nvidia/Nemotron-3.5-Lightning-30B"
DEPRECATED_MODEL = "nvidia/Nemotron-3-Nano"

REASONING_PROMPT = (
    "Think step by step about why cache-aware routing can reduce "
    "time-to-first-token in a multi-tenant inference cluster, then "
    "give a one-sentence answer."
)


class CrusoePracticeIssue(Exception):
    """Base class for a named, human-readable practice finding."""

    code = "practice_issue"

    def __init__(self, message: str, *, evidence: dict[str, Any] | None = None):
        super().__init__(message)
        self.evidence = evidence or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.args[0]}"


class EmptyReplyIssue(CrusoePracticeIssue):
    code = "empty_reply"


class WrongModelIssue(CrusoePracticeIssue):
    code = "wrong_model"


class AuthIssue(CrusoePracticeIssue):
    code = "auth_failure"


class RateLimitIssue(CrusoePracticeIssue):
    code = "rate_limit"


class MalformedRequestIssue(CrusoePracticeIssue):
    code = "malformed_request"


class MissingApiKeyError(CrusoePracticeIssue):
    code = "missing_api_key"


def pacific_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        return datetime.now(timezone.utc)


def load_api_key() -> str:
    key = os.environ.get("CRUSOE_API_KEY", "").strip()
    if not key:
        raise MissingApiKeyError(
            "CRUSOE_API_KEY is not set. Export it in your shell; "
            "never put the key in the script, a file, or chat."
        )
    return key


def redact_secret(value: str, secret: str | None) -> str:
    if not secret or not value:
        return value
    return value.replace(secret, "[REDACTED]")


def sanitize(obj: Any, secret: str | None = None, *, key_name: str | None = None) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower().replace("-", "_")
            raw_lk = str(k).lower()
            if raw_lk in SENSITIVE_HEADER_NAMES or lk in SENSITIVE_ID_KEYS:
                out[k] = "[REDACTED]"
            elif "authorization" in raw_lk or raw_lk.endswith("api-key") or lk.endswith("api_key"):
                out[k] = "[REDACTED]"
            else:
                out[k] = sanitize(v, secret, key_name=str(k))
        return out
    if isinstance(obj, list):
        return [sanitize(v, secret) for v in obj]
    if isinstance(obj, str):
        text = redact_secret(obj, secret)
        if key_name and key_name.lower().replace("-", "_") in SENSITIVE_ID_KEYS:
            return "[REDACTED]"
        return text
    return obj


def contains_secret(obj: Any, secret: str) -> bool:
    if not secret:
        return False
    if isinstance(obj, dict):
        return any(secret in str(k) for k in obj.keys()) or any(
            contains_secret(v, secret) for v in obj.values()
        )
    if isinstance(obj, list):
        return any(contains_secret(v, secret) for v in obj)
    if isinstance(obj, (str, bytes)):
        blob = obj if isinstance(obj, str) else obj.decode("utf-8", "replace")
        return secret in blob
    return False


def pick_headers(headers: dict[str, str]) -> dict[str, str]:
    keep: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in SENSITIVE_HEADER_NAMES:
            continue
        if (
            lk.startswith("x-ratelimit-")
            or lk.startswith("x-crusoe-")
            or lk.startswith("openai-")
            or lk in {
                "retry-after",
                "x-request-id",
                "request-id",
                "content-type",
                "cf-ray",
                "date",
                "server",
            }
        ):
            # Drop header values that look like account identifiers.
            if any(s in lk.replace("-", "_") for s in ("org", "account", "project", "tenant")):
                # Keep rate-limit counters; they are not account IDs.
                if not lk.startswith("x-ratelimit-"):
                    keep[k] = "[REDACTED]"
                    continue
            keep[k] = v
    return keep


def _safe_raw(raw_body: bytes | str | None) -> str | None:
    if raw_body is None:
        return None
    if isinstance(raw_body, bytes):
        try:
            return raw_body.decode("utf-8")
        except UnicodeDecodeError:
            return f"<{len(raw_body)} bytes>"
    return str(raw_body)


def trim_text(text: str | None, limit: int = 4000) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated {len(text) - limit} chars]"


def parse_sse(lines: list[str]) -> dict[str, Any]:
    contents: list[str] = []
    reasoning: list[str] = []
    finish = None
    usage = None
    first_content_event = None
    event_count = 0
    model = None
    for line in lines:
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        event_count += 1
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("model"):
            model = data["model"]
        if data.get("usage"):
            usage = data["usage"]
        choices = data.get("choices") or []
        if not choices:
            continue
        ch = choices[0]
        if ch.get("finish_reason"):
            finish = ch.get("finish_reason")
        delta = ch.get("delta") or {}
        if delta.get("content"):
            if first_content_event is None:
                first_content_event = event_count
            contents.append(delta["content"])
        rc = delta.get("reasoning_content") or delta.get("reasoning")
        if rc:
            reasoning.append(rc)
    return {
        "event_count": event_count,
        "model": model,
        "finish_reason": finish,
        "content": "".join(contents),
        "reasoning_chars": sum(len(x) for x in reasoning),
        "reasoning_preview": trim_text("".join(reasoning), 240) if reasoning else None,
        "usage": usage,
        "first_content_event": first_content_event,
    }


def first_choice(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return None
    return choices[0]


def message_content(body: Any) -> Any:
    ch = first_choice(body)
    if not ch:
        return None
    msg = ch.get("message") or {}
    return msg.get("content")


def finish_reason(body: Any) -> str | None:
    ch = first_choice(body)
    return ch.get("finish_reason") if ch else None


def reasoning_present(body: Any) -> bool:
    ch = first_choice(body)
    if not ch:
        return False
    msg = ch.get("message") or {}
    for key in ("reasoning_content", "reasoning", "reasoning_details"):
        val = msg.get(key)
        if val:
            return True
    return False


def is_empty_success(record: dict[str, Any]) -> bool:
    if record.get("status_code") != 200:
        return False
    body = record.get("body")
    content = message_content(body)
    return (content is None or content == "") and finish_reason(body) == "length"


def describe_empty(record: dict[str, Any]) -> str:
    body = record.get("body") if isinstance(record.get("body"), dict) else {}
    usage = (body or {}).get("usage") or {}
    model = (body or {}).get("model") or (record.get("request") or {}).get("model")
    content = message_content(body)
    return (
        f"HTTP {record.get('status_code')} from {model} but message.content is "
        f"{content!r} (finish_reason={finish_reason(body)}, "
        f"completion_tokens={usage.get('completion_tokens')}). "
        "The model spent its token budget on reasoning and returned no "
        "customer-visible answer."
    )


def usage_of(record: dict[str, Any]) -> dict[str, Any]:
    body = record.get("body")
    if isinstance(body, dict):
        usage = body.get("usage")
        if usage:
            return usage
        # streaming summary
        if "usage" in body and not usage:
            return body.get("usage") or {}
    return {}


def model_of(record: dict[str, Any]) -> str | None:
    body = record.get("body")
    if isinstance(body, dict) and body.get("model"):
        return body["model"]
    req = record.get("request")
    if isinstance(req, dict):
        return req.get("model")
    return None


def extract_prices(models_payload: Any) -> dict[str, dict[str, float]]:
    prices = dict(FALLBACK_PRICES)
    data = models_payload.get("data") if isinstance(models_payload, dict) else None
    if not isinstance(data, list):
        return prices
    for item in data:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not mid:
            continue
        pricing = item.get("pricing") or item.get("price") or {}
        # Common OpenAI-compatible catalog shapes.
        prompt = None
        completion = None
        if isinstance(pricing, dict):
            prompt = pricing.get("prompt") or pricing.get("input")
            completion = pricing.get("completion") or pricing.get("output")
        # Sometimes nested under top_provider or metadata
        for nest_key in ("top_provider", "metadata"):
            nest = item.get(nest_key) or {}
            if isinstance(nest, dict) and isinstance(nest.get("pricing"), dict):
                prompt = prompt or nest["pricing"].get("prompt") or nest["pricing"].get("input")
                completion = (
                    completion
                    or nest["pricing"].get("completion")
                    or nest["pricing"].get("output")
                )
        try:
            if prompt is not None and completion is not None:
                # Values may already be USD per million, or per-token.
                p = float(prompt)
                c = float(completion)
                if p < 0.001 and c < 0.001:
                    # per-token dollars -> per million
                    p, c = p * 1_000_000, c * 1_000_000
                prices[mid] = {"prompt": p, "completion": c}
        except (TypeError, ValueError):
            continue
    return prices


def estimate_cost(records: list[dict[str, Any]], prices: dict[str, dict[str, float]]) -> dict[str, Any]:
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    usd = 0.0
    by_model: dict[str, dict[str, Any]] = {}
    priced_ok = True
    for rec in records:
        usage = usage_of(rec)
        if not usage:
            continue
        pt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        ct = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        tt = int(usage.get("total_tokens") or (pt + ct))
        prompt_tokens += pt
        completion_tokens += ct
        total_tokens += tt
        model = model_of(rec) or "unknown"
        bucket = by_model.setdefault(
            model, {"prompt_tokens": 0, "completion_tokens": 0, "usd": 0.0}
        )
        bucket["prompt_tokens"] += pt
        bucket["completion_tokens"] += ct
        rate = prices.get(model)
        if rate:
            part = (pt / 1_000_000) * rate["prompt"] + (ct / 1_000_000) * rate["completion"]
            bucket["usd"] += part
            usd += part
        else:
            priced_ok = False
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_usd": round(usd, 6),
        "estimate_complete": priced_ok,
        "by_model": {
            m: {
                "prompt_tokens": b["prompt_tokens"],
                "completion_tokens": b["completion_tokens"],
                "estimated_usd": round(b["usd"], 6),
            }
            for m, b in by_model.items()
        },
        "price_source": "model catalog or public list prices, USD per million tokens",
    }


class CrusoeClient:
    def __init__(
        self,
        api_key: str | None,
        session: requests.Session | None = None,
        base_url: str = BASE_URL,
    ):
        self.api_key = api_key
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        raw_body: bytes | str | None = None,
        headers: dict[str, str] | None = None,
        stream: bool = False,
        timeout: float = 120,
        api_key: str | None = None,
        skip_auth: bool = False,
        use_real_key: bool = True,
    ) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        req_headers = {"Accept": "application/json"}
        if json_body is not None or raw_body is not None:
            req_headers.setdefault("Content-Type", "application/json")
        key = api_key if api_key is not None else (self.api_key if use_real_key else None)
        if not skip_auth and key:
            req_headers["Authorization"] = f"Bearer {key}"
        if headers:
            req_headers.update(headers)

        t0 = time.perf_counter()
        t_first = None
        text = ""
        status = None
        resp_headers: dict[str, str] = {}
        error = None
        stream_chunks: list[str] = []
        ttft_ms = None

        try:
            kwargs: dict[str, Any] = {
                "headers": req_headers,
                "stream": stream,
                "timeout": timeout,
            }
            if raw_body is not None:
                kwargs["data"] = raw_body
            elif json_body is not None:
                kwargs["json"] = json_body
            resp = self.session.request(method, url, **kwargs)
            status = resp.status_code
            resp_headers = dict(resp.headers)
            if stream:
                parts: list[str] = []
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if t_first is None:
                        t_first = time.perf_counter()
                    parts.append(line)
                    stream_chunks.append(line)
                text = "\n".join(parts)
            else:
                text = resp.text or ""
                if text or status is not None:
                    t_first = time.perf_counter()
        except requests.RequestException as exc:
            error = f"{type(exc).__name__}: {exc}"
            if self.api_key:
                error = error.replace(self.api_key, "[REDACTED]")
            if api_key:
                error = error.replace(api_key, "[REDACTED]")

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        if t_first is not None:
            ttft_ms = round((t_first - t0) * 1000, 1)

        body: Any
        if stream and stream_chunks:
            body = parse_sse(stream_chunks)
        else:
            try:
                body = json.loads(text) if text else None
            except json.JSONDecodeError:
                body = trim_text(text)

        record = sanitize(
            {
                "method": method,
                "path": path,
                "status_code": status,
                "elapsed_ms": elapsed_ms,
                "ttft_ms": ttft_ms,
                "stream": stream,
                "request": sanitize(
                    json_body if json_body is not None else _safe_raw(raw_body),
                    self.api_key,
                ),
                "headers": pick_headers({k: str(v) for k, v in resp_headers.items()}),
                "body": body,
                "error": error,
            },
            self.api_key,
        )
        if api_key and api_key != self.api_key:
            record = sanitize(record, api_key)
        self.calls.append(record)
        return record

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        stream: bool = False,
        extra: dict[str, Any] | None = None,
        **request_kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if extra:
            payload.update(extra)
        return self.request(
            "POST",
            "/chat/completions",
            json_body=payload,
            stream=stream,
            **request_kwargs,
        )


def collect_rate_headers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for rec in records:
        headers = rec.get("headers") or {}
        rate = {k: v for k, v in headers.items() if k.lower().startswith("x-ratelimit-") or k.lower() == "retry-after"}
        if rate:
            out.append(
                {
                    "status_code": rec.get("status_code"),
                    "path": rec.get("path"),
                    "model": model_of(rec),
                    "headers": rate,
                }
            )
    return out


def run_empty_reply(client: CrusoeClient, model: str) -> dict[str, Any]:
    scenario: dict[str, Any] = {
        "id": "empty_reply",
        "title": "Empty reply on a reasoning model with a low max_tokens",
        "reproduced": False,
        "fix_succeeded": False,
    }
    attempts = []
    broken = None
    for budget in (64, 32, 120):
        rec = client.chat(
            model,
            [{"role": "user", "content": REASONING_PROMPT}],
            max_tokens=budget,
            reasoning_effort="high",
        )
        attempts.append(
            {
                "max_tokens": budget,
                "reasoning_effort": "high",
                "status_code": rec.get("status_code"),
                "elapsed_ms": rec.get("elapsed_ms"),
                "content": message_content(rec.get("body")),
                "finish_reason": finish_reason(rec.get("body")),
                "usage": usage_of(rec),
                "reasoning_present": reasoning_present(rec.get("body")),
                "empty_success": is_empty_success(rec),
                "headers": rec.get("headers"),
                "body": rec.get("body"),
            }
        )
        if is_empty_success(rec):
            broken = rec
            try:
                raise EmptyReplyIssue(describe_empty(rec), evidence={"max_tokens": budget})
            except EmptyReplyIssue as exc:
                scenario["issue"] = str(exc)
            break

    scenario["break_attempts"] = attempts
    if broken is None:
        scenario["observation"] = (
            "Did not observe content=null with finish_reason=length on the "
            "budgets tried. Recorded the actual responses instead."
        )
        # Still try a fix path as a contrast, using a generous budget.
    else:
        scenario["reproduced"] = True

    # Fix 1: same prompt, disable reasoning, modest budget.
    fix_none = client.chat(
        model,
        [{"role": "user", "content": REASONING_PROMPT}],
        max_tokens=256,
        reasoning_effort="none",
    )
    fix_none_ok = (
        fix_none.get("status_code") == 200
        and isinstance(message_content(fix_none.get("body")), str)
        and len(message_content(fix_none.get("body")) or "") > 0
    )
    scenario["fix_reasoning_none"] = {
        "max_tokens": 256,
        "reasoning_effort": "none",
        "status_code": fix_none.get("status_code"),
        "elapsed_ms": fix_none.get("elapsed_ms"),
        "content": trim_text(message_content(fix_none.get("body")) or "", 500),
        "finish_reason": finish_reason(fix_none.get("body")),
        "usage": usage_of(fix_none),
        "succeeded": fix_none_ok,
        "headers": fix_none.get("headers"),
        "body": fix_none.get("body"),
    }

    # Fix 2: keep high reasoning, raise the token cap.
    fix_cap = client.chat(
        model,
        [{"role": "user", "content": REASONING_PROMPT}],
        max_tokens=512,
        reasoning_effort="high",
    )
    fix_cap_ok = (
        fix_cap.get("status_code") == 200
        and isinstance(message_content(fix_cap.get("body")), str)
        and len(message_content(fix_cap.get("body")) or "") > 0
    )
    scenario["fix_higher_max_tokens"] = {
        "max_tokens": 512,
        "reasoning_effort": "high",
        "status_code": fix_cap.get("status_code"),
        "elapsed_ms": fix_cap.get("elapsed_ms"),
        "content": trim_text(message_content(fix_cap.get("body")) or "", 500),
        "finish_reason": finish_reason(fix_cap.get("body")),
        "usage": usage_of(fix_cap),
        "succeeded": fix_cap_ok,
        "headers": fix_cap.get("headers"),
        "body": fix_cap.get("body"),
    }
    scenario["fix_succeeded"] = bool(fix_none_ok or fix_cap_ok)
    return scenario


def run_wrong_model(client: CrusoeClient) -> dict[str, Any]:
    typo = client.chat(
        WRONG_MODEL,
        [{"role": "user", "content": "Say hi in one word."}],
        max_tokens=8,
        reasoning_effort="none",
    )
    deprecated = client.chat(
        DEPRECATED_MODEL,
        [{"role": "user", "content": "Say hi in one word."}],
        max_tokens=8,
        reasoning_effort="none",
    )
    reproduced = typo.get("status_code") not in (200, None) or deprecated.get(
        "status_code"
    ) not in (200, None)
    issue = None
    if typo.get("status_code") not in (200, None):
        body = typo.get("body")
        issue = str(
            WrongModelIssue(
                f"HTTP {typo.get('status_code')} for model {WRONG_MODEL}: "
                f"{_error_text(body)}"
            )
        )
    scenario = {
        "id": "wrong_model",
        "title": "Wrong or deprecated model name",
        "reproduced": bool(reproduced),
        "issue": issue,
        "typo_model": {
            "model": WRONG_MODEL,
            "status_code": typo.get("status_code"),
            "elapsed_ms": typo.get("elapsed_ms"),
            "headers": typo.get("headers"),
            "body": typo.get("body"),
        },
        "deprecated_model": {
            "model": DEPRECATED_MODEL,
            "status_code": deprecated.get("status_code"),
            "elapsed_ms": deprecated.get("elapsed_ms"),
            "headers": deprecated.get("headers"),
            "body": deprecated.get("body"),
        },
    }
    return scenario


def _error_text(body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error") or body
        if isinstance(err, dict):
            parts = [
                str(err.get(k))
                for k in ("type", "code", "message", "error_id")
                if err.get(k)
            ]
            return " ".join(parts) or json.dumps(err)[:500]
        return trim_text(str(err), 500) or ""
    return trim_text(str(body), 500) or ""


def run_auth(client: CrusoeClient, model: str) -> dict[str, Any]:
    bad = client.chat(
        model,
        [{"role": "user", "content": "Say hi in one word."}],
        max_tokens=8,
        reasoning_effort="none",
        api_key=FAKE_KEY,
        use_real_key=False,
    )
    missing = client.chat(
        model,
        [{"role": "user", "content": "Say hi in one word."}],
        max_tokens=8,
        reasoning_effort="none",
        skip_auth=True,
        use_real_key=False,
    )
    reproduced = bad.get("status_code") in (401, 403) or missing.get("status_code") in (
        401,
        403,
    )
    issue = None
    if bad.get("status_code") in (401, 403):
        issue = str(
            AuthIssue(
                f"HTTP {bad.get('status_code')} with an obviously fake API key: "
                f"{_error_text(bad.get('body'))}"
            )
        )
    elif missing.get("status_code") in (401, 403):
        issue = str(
            AuthIssue(
                f"HTTP {missing.get('status_code')} with no Authorization header: "
                f"{_error_text(missing.get('body'))}"
            )
        )
    return {
        "id": "auth_failure",
        "title": "Bad or missing API key",
        "reproduced": bool(reproduced),
        "issue": issue,
        "fake_key_used": FAKE_KEY,
        "bad_key": {
            "status_code": bad.get("status_code"),
            "elapsed_ms": bad.get("elapsed_ms"),
            "headers": bad.get("headers"),
            "body": bad.get("body"),
        },
        "missing_key": {
            "status_code": missing.get("status_code"),
            "elapsed_ms": missing.get("elapsed_ms"),
            "headers": missing.get("headers"),
            "body": missing.get("body"),
        },
    }


def run_malformed(client: CrusoeClient, model: str) -> dict[str, Any]:
    invalid_json = client.request(
        "POST",
        "/chat/completions",
        raw_body='{"model": "' + model + '", "messages": "not-an-array", "max_tokens": 8}',
    )
    invalid_param = client.request(
        "POST",
        "/chat/completions",
        json_body={
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": -1,
        },
    )
    reproduced = invalid_json.get("status_code") in (400, 422) or invalid_param.get(
        "status_code"
    ) in (400, 422)
    issue = None
    target = invalid_json if invalid_json.get("status_code") in (400, 422) else invalid_param
    if target.get("status_code") in (400, 422):
        issue = str(
            MalformedRequestIssue(
                f"HTTP {target.get('status_code')} for a malformed chat request: "
                f"{_error_text(target.get('body'))}"
            )
        )
    return {
        "id": "malformed_request",
        "title": "Malformed request (expected 400)",
        "reproduced": bool(reproduced),
        "issue": issue,
        "invalid_messages_type": {
            "status_code": invalid_json.get("status_code"),
            "elapsed_ms": invalid_json.get("elapsed_ms"),
            "headers": invalid_json.get("headers"),
            "body": invalid_json.get("body"),
        },
        "invalid_max_tokens": {
            "status_code": invalid_param.get("status_code"),
            "elapsed_ms": invalid_param.get("elapsed_ms"),
            "headers": invalid_param.get("headers"),
            "body": invalid_param.get("body"),
        },
    }


def run_latency(client: CrusoeClient, model: str) -> dict[str, Any]:
    prompt = [{"role": "user", "content": "Reply with the single word ready."}]
    nonstream = client.chat(
        model, prompt, max_tokens=32, reasoning_effort="none", stream=False
    )
    streamed = client.chat(
        model, prompt, max_tokens=32, reasoning_effort="none", stream=True
    )
    stream_body = streamed.get("body") if isinstance(streamed.get("body"), dict) else {}
    return {
        "id": "latency_streaming",
        "title": "Latency and streaming versus non-streaming",
        "reproduced": nonstream.get("status_code") == 200 and streamed.get("status_code") == 200,
        "non_streaming": {
            "status_code": nonstream.get("status_code"),
            "elapsed_ms": nonstream.get("elapsed_ms"),
            "ttft_ms": nonstream.get("ttft_ms"),
            "content": trim_text(message_content(nonstream.get("body")) or "", 200),
            "finish_reason": finish_reason(nonstream.get("body")),
            "usage": usage_of(nonstream),
            "headers": nonstream.get("headers"),
        },
        "streaming": {
            "status_code": streamed.get("status_code"),
            "elapsed_ms": streamed.get("elapsed_ms"),
            "ttft_ms": streamed.get("ttft_ms"),
            "content": trim_text((stream_body or {}).get("content") or "", 200),
            "finish_reason": (stream_body or {}).get("finish_reason"),
            "event_count": (stream_body or {}).get("event_count"),
            "first_content_event": (stream_body or {}).get("first_content_event"),
            "usage": (stream_body or {}).get("usage"),
            "headers": streamed.get("headers"),
        },
        "note": (
            "ttft_ms for streaming is time to the first non-empty SSE line. "
            "For non-streaming it is time until the full response body was read."
        ),
    }


def _tiny_chat(api_key: str, model: str, base_url: str) -> dict[str, Any]:
    """One tiny request used only for the rate-limit burst."""
    client = CrusoeClient(api_key, session=requests.Session(), base_url=base_url)
    return client.chat(
        model,
        [{"role": "user", "content": "y"}],
        max_tokens=4,
        reasoning_effort="none",
    )


def run_rate_limits(
    client: CrusoeClient, model: str, burst: int, skip_burst: bool
) -> dict[str, Any]:
    # Probe first so we always capture rate-limit headers even without a burst.
    probe = client.chat(
        model,
        [{"role": "user", "content": "Reply with y."}],
        max_tokens=4,
        reasoning_effort="none",
    )
    burst_records: list[dict[str, Any]] = []
    if not skip_burst and burst > 0:
        n = max(1, min(burst, 30))
        with ThreadPoolExecutor(max_workers=min(8, n)) as pool:
            futures = [
                pool.submit(_tiny_chat, client.api_key or "", model, client.base_url)
                for _ in range(n)
            ]
            for fut in as_completed(futures):
                try:
                    burst_records.append(fut.result())
                except Exception as exc:  # noqa: BLE001 — record the failure, still redact
                    msg = str(exc)
                    if client.api_key:
                        msg = msg.replace(client.api_key, "[REDACTED]")
                    burst_records.append(
                        {
                            "status_code": None,
                            "error": f"{type(exc).__name__}: {msg}",
                            "headers": {},
                            "body": None,
                        }
                    )
        # Keep burst calls out of the main client's call list to avoid
        # double-counting; they are attached on the scenario instead.
        # Usage is still totaled from burst_records below.

    all_recs = [probe, *burst_records]
    statuses = {}
    for rec in all_recs:
        code = rec.get("status_code")
        key = str(code)
        statuses[key] = statuses.get(key, 0) + 1
    hit_429 = any(rec.get("status_code") == 429 for rec in all_recs)
    hit_503 = any(rec.get("status_code") == 503 for rec in all_recs)
    issue = None
    if hit_429:
        sample = next(r for r in all_recs if r.get("status_code") == 429)
        issue = str(
            RateLimitIssue(
                f"HTTP 429 during a burst of {len(burst_records)} tiny requests: "
                f"{_error_text(sample.get('body'))}"
            )
        )
    return {
        "id": "rate_limits",
        "title": "Rate limits and response headers",
        "reproduced_429": hit_429,
        "reproduced_503": hit_503,
        "issue": issue,
        "burst_requested": 0 if skip_burst else burst,
        "burst_completed": len(burst_records),
        "status_counts": statuses,
        "probe": {
            "status_code": probe.get("status_code"),
            "elapsed_ms": probe.get("elapsed_ms"),
            "headers": probe.get("headers"),
            "body": probe.get("body"),
        },
        "burst_headers_sample": collect_rate_headers(all_recs)[:8],
        "burst_error_samples": [
            {
                "status_code": r.get("status_code"),
                "elapsed_ms": r.get("elapsed_ms"),
                "headers": r.get("headers"),
                "body": r.get("body"),
                "error": r.get("error"),
            }
            for r in all_recs
            if r.get("status_code") not in (200, None)
        ],
        "documented_limits": DOCUMENTED_RATE_LIMITS,
        "note": (
            "The burst is capped at 20–30 tiny requests so this lab does not "
            "hammer the API. If no 429 appears, use the observed rate-limit "
            "headers and Crusoe's documented defaults rather than inventing "
            "an error."
        ),
        "burst_usage": [usage_of(r) for r in burst_records if usage_of(r)],
        "_burst_records": burst_records,  # stripped before write if we want; used for cost
    }


def slim_models(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    slim = []
    for item in data:
        if not isinstance(item, dict):
            continue
        entry = {
            "id": item.get("id"),
            "owned_by": item.get("owned_by"),
            "context_length": item.get("context_length") or item.get("context_window"),
            "supported_parameters": item.get("supported_parameters"),
            "pricing": item.get("pricing") or item.get("price"),
        }
        slim.append({k: v for k, v in entry.items() if v is not None})
    return slim


def strip_private_cost_fields(scenario: dict[str, Any]) -> dict[str, Any]:
    out = dict(scenario)
    out.pop("_burst_records", None)
    return out


def run_lab(
    *,
    api_key: str,
    base_url: str = BASE_URL,
    model: str = CHEAP_MODEL,
    burst: int = 25,
    skip_burst: bool = False,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    client = CrusoeClient(api_key, session=session, base_url=base_url)
    started = pacific_now()

    models_rec = client.request("GET", "/models")
    prices = extract_prices(models_rec.get("body"))

    empty = run_empty_reply(client, model)
    wrong = run_wrong_model(client)
    auth = run_auth(client, model)
    malformed = run_malformed(client, model)
    latency = run_latency(client, model)
    rates = run_rate_limits(client, model, burst=burst, skip_burst=skip_burst)

    # Cost: main client calls plus burst records (burst uses other sessions).
    cost_records = list(client.calls) + list(rates.pop("_burst_records", []))
    # Auth calls with fake/missing keys should have no billable usage, but
    # include them anyway if usage is present.
    cost = estimate_cost(cost_records, prices)

    results = {
        "lab": "crusoe-escalation-practice",
        "disclaimer": (
            "Personal lab tests against Crusoe Serverless Inference on the "
            "operator's own account. Observations are from live API responses "
            "plus public docs. This is not a Crusoe-internal document and does "
            "not claim hidden platform behavior beyond public documentation."
        ),
        "started_at": started.isoformat(timespec="seconds"),
        "timezone": "America/Los_Angeles",
        "base_url": base_url,
        "model": model,
        "alt_model": ALT_MODEL,
        "models_available": slim_models(models_rec.get("body")),
        "models_list_status": models_rec.get("status_code"),
        "scenarios": [
            empty,
            wrong,
            auth,
            rates,
            latency,
            malformed,
        ],
        "rate_limit_headers_observed": collect_rate_headers(cost_records),
        "usage_and_cost": cost,
        "prices_used_usd_per_million": prices,
        "documented_rate_limits": DOCUMENTED_RATE_LIMITS,
        "finished_at": pacific_now().isoformat(timespec="seconds"),
    }
    return sanitize(results, api_key)


def write_results(results: dict[str, Any], path: Path, secret: str) -> None:
    if contains_secret(results, secret):
        raise RuntimeError(
            "Refusing to write results.json because the API key was detected "
            "in the payload. Nothing was written."
        )
    text = json.dumps(results, indent=2, default=str)
    if secret in text:
        raise RuntimeError(
            "Refusing to write results.json because the API key was detected "
            "in the serialized JSON. Nothing was written."
        )
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    # Final read-back check before replace.
    if secret in tmp.read_text(encoding="utf-8"):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            "Refusing to write results.json because the API key was detected "
            "after serialization. The temp file was deleted."
        )
    tmp.replace(path)


def summarize(results: dict[str, Any]) -> None:
    print("Crusoe escalation practice lab")
    print(f"  started: {results.get('started_at')} ({results.get('timezone')})")
    print(f"  model:   {results.get('model')}")
    for scenario in results.get("scenarios") or []:
        flag = "YES" if scenario.get("reproduced") or scenario.get("reproduced_429") else "no"
        extra = scenario.get("issue") or scenario.get("title")
        print(f"  [{flag}] {scenario.get('id')}: {extra}")
    cost = results.get("usage_and_cost") or {}
    print(
        "  tokens:  "
        f"{cost.get('prompt_tokens')} prompt / {cost.get('completion_tokens')} completion "
        f"(~${cost.get('estimated_usd')})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Crusoe escalation practice lab.")
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--model", default=CHEAP_MODEL)
    parser.add_argument("--burst", type=int, default=25, help="Tiny requests in the rate-limit burst (max 30).")
    parser.add_argument("--skip-burst", action="store_true")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args(argv)

    try:
        api_key = load_api_key()
    except MissingApiKeyError as exc:
        print(exc, file=sys.stderr)
        return 2

    burst = max(0, min(args.burst, 30))
    results = run_lab(
        api_key=api_key,
        base_url=args.base_url,
        model=args.model,
        burst=burst,
        skip_burst=args.skip_burst,
    )
    write_results(results, args.out, api_key)
    summarize(results)
    print(f"  wrote:   {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
