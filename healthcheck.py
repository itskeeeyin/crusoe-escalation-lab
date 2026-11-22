#!/usr/bin/env python3
"""Synthetic monitor for Crusoe Serverless Inference.

Probes one or more cheap models for HTTP errors, empty assistant content,
and high latency. Prints a status table. Exits non-zero and raises named
failure classes when a probe fails.

Requires CRUSOE_API_KEY in the environment. The key is never printed or
written to disk.

Usage:
    export CRUSOE_API_KEY=...    # do not commit or paste this
    python healthcheck.py
    python healthcheck.py --interval 60
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import practice_lab
from practice_lab import (
    ALT_MODEL,
    BASE_URL,
    CHEAP_MODEL,
    CrusoeClient,
    CrusoePracticeIssue,
    EmptyReplyIssue,
    MissingApiKeyError,
    describe_empty,
    estimate_cost,
    extract_prices,
    finish_reason,
    is_empty_success,
    load_api_key,
    message_content,
    pacific_now,
    sanitize,
    usage_of,
)

DEFAULT_MODELS = (CHEAP_MODEL, ALT_MODEL)
DEFAULT_PROMPT = "Reply with the single word ready."
DEFAULT_LATENCY_MS = 15_000
PROBE_MAX_TOKENS = 32
# When a model rejects reasoning_effort, leave room for a default reasoning trace.
PROBE_MAX_TOKENS_DEFAULT_REASONING = 256


class HttpErrorIssue(CrusoePracticeIssue):
    code = "http_error"


class HighLatencyIssue(CrusoePracticeIssue):
    code = "high_latency"


def _content_text(body: Any) -> str:
    value = message_content(body)
    if value is None:
        return "null"
    if value == "":
        return '""'
    return value.replace("\n", " ")


def probe_model(
    client: CrusoeClient,
    model: str,
    *,
    latency_ms: int,
) -> dict[str, Any]:
    """Send a short, non-reasoning chat call that should return visible text."""
    rec = client.chat(
        model,
        [{"role": "user", "content": DEFAULT_PROMPT}],
        max_tokens=PROBE_MAX_TOKENS,
        reasoning_effort="none",
    )
    note = None
    if rec.get("status_code") == 400 and "reasoning_effort" in practice_lab._error_text(
        rec.get("body")
    ).lower():
        # Some catalog models reject reasoning_effort entirely, including "none".
        rec = client.chat(
            model,
            [{"role": "user", "content": DEFAULT_PROMPT}],
            max_tokens=PROBE_MAX_TOKENS_DEFAULT_REASONING,
        )
        note = (
            "retried without reasoning_effort after HTTP 400, "
            f"max_tokens raised to {PROBE_MAX_TOKENS_DEFAULT_REASONING}"
        )
    status = rec.get("status_code")
    elapsed = rec.get("elapsed_ms")
    body = rec.get("body")
    content = message_content(body)
    issues: list[CrusoePracticeIssue] = []

    if status != 200:
        issues.append(
            HttpErrorIssue(
                f"HTTP {status} from {model}: {practice_lab._error_text(body)}",
                evidence=rec,
            )
        )
    elif is_empty_success(rec) or content is None or content == "":
        if is_empty_success(rec):
            issues.append(EmptyReplyIssue(describe_empty(rec), evidence=rec))
        else:
            issues.append(
                EmptyReplyIssue(
                    f"HTTP {status} from {model} but message.content is "
                    f"{content!r} (finish_reason={finish_reason(body)}).",
                    evidence=rec,
                )
            )
    if elapsed is not None and elapsed > latency_ms:
        issues.append(
            HighLatencyIssue(
                f"HTTP {status} from {model} took {elapsed} ms, "
                f"which exceeds the {latency_ms} ms probe threshold.",
                evidence=rec,
            )
        )

    ok = not issues
    return {
        "model": model,
        "ok": ok,
        "status_code": status,
        "elapsed_ms": elapsed,
        "content": content,
        "content_display": _content_text(body)[:40],
        "finish_reason": finish_reason(body),
        "usage": usage_of(rec),
        "headers": rec.get("headers") or {},
        "error_body": None if status == 200 else body,
        "issues": [str(i) for i in issues],
        "issue_objects": issues,
        "note": note,
    }


def format_table(probes: list[dict[str, Any]]) -> str:
    headers = ("Result", "Model", "HTTP", "Latency", "Content", "Finish")
    rows = [headers]
    for p in probes:
        rows.append(
            (
                "OK" if p["ok"] else "FAIL",
                p["model"],
                str(p.get("status_code") if p.get("status_code") is not None else "—"),
                f"{p['elapsed_ms']:.1f} ms" if p.get("elapsed_ms") is not None else "—",
                p.get("content_display") or "—",
                str(p.get("finish_reason") or "—"),
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    lines = []
    for idx, row in enumerate(rows):
        line = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        lines.append(line)
        if idx == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def run_once(
    *,
    api_key: str,
    models: list[str],
    base_url: str,
    latency_ms: int,
    session=None,
) -> dict[str, Any]:
    client = CrusoeClient(api_key, session=session, base_url=base_url)
    started = pacific_now()
    prices = dict(practice_lab.FALLBACK_PRICES)
    models_rec = client.request("GET", "/models")
    if models_rec.get("status_code") == 200:
        prices.update(extract_prices(models_rec.get("body")))
    probes = [probe_model(client, model, latency_ms=latency_ms) for model in models]
    cost = estimate_cost(client.calls, prices)
    failed = [p for p in probes if not p["ok"]]
    return {
        "started_at": started.isoformat(timespec="seconds"),
        "timezone": "America/Los_Angeles",
        "base_url": base_url,
        "latency_threshold_ms": latency_ms,
        "models_list_status": models_rec.get("status_code"),
        "probes": [{k: v for k, v in p.items() if k != "issue_objects"} for p in probes],
        "_issue_objects": [i for p in probes for i in p["issue_objects"]],
        "failed_count": len(failed),
        "ok": not failed,
        "usage_and_cost": cost,
        "finished_at": pacific_now().isoformat(timespec="seconds"),
    }


def print_run(result: dict[str, Any]) -> None:
    print(f"Crusoe inference healthcheck  {result['started_at']} ({result['timezone']})")
    print(format_table(result["probes"]))
    cost = result.get("usage_and_cost") or {}
    print(
        "tokens: "
        f"{cost.get('prompt_tokens')} prompt / {cost.get('completion_tokens')} completion "
        f"(~${cost.get('estimated_usd')})"
    )
    for p in result["probes"]:
        if p.get("note"):
            print(f"note: {p['model']}: {p['note']}")
    if result["ok"]:
        print("result: all probes passed")
        return
    print(f"result: {result['failed_count']} probe(s) failed")
    for issue in result.get("_issue_objects") or []:
        print(f"  {issue}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Crusoe Serverless Inference health.")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated model IDs to probe (cheap models only).",
    )
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument(
        "--latency-ms",
        type=int,
        default=DEFAULT_LATENCY_MS,
        help="Fail a probe slower than this many milliseconds (default 15000).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Seconds between runs. Default: a single run.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Stop after this many runs when --interval is set. Default: loop until interrupted.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        api_key = load_api_key()
    except MissingApiKeyError as exc:
        print(exc, file=sys.stderr)
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        print("[http_error] No models given.", file=sys.stderr)
        return 2

    run = 0
    worst = 0
    while True:
        run += 1
        result = run_once(
            api_key=api_key,
            models=models,
            base_url=args.base_url,
            latency_ms=args.latency_ms,
        )
        # Never print raw issue evidence; print_run uses named strings only.
        print_run(sanitize(result, api_key))
        if not result["ok"]:
            worst = 1
        if args.interval is None:
            break
        if args.max_runs is not None and run >= args.max_runs:
            break
        time.sleep(max(args.interval, 0))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
